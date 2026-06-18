"""
Feature engineering script for BIXI demand forecasting.

The script reads demand and weather data from S3, creates temporal features, 
leakage-aware historical baseline features, merges weather features, 
and writes the final feature tables back to S3.
"""

from __future__ import annotations

import io
import os
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

import boto3
import numpy as np
import pandas as pd
from dotenv import load_dotenv

load_dotenv()


BUCKET = "insy684"
TIME_FREQ = "15min"
SLOTS_PER_DAY = 96
SLOTS_PER_WEEK = 7 * SLOTS_PER_DAY


@dataclass(frozen=True)
class FeatureJob:
    demand_key: str
    weather_key: str
    output_key: str
    baseline_type: str
    use_leave_one_out: bool


@dataclass(frozen=True)
class ProfileStats:
    primary: pd.DataFrame
    station_slot: pd.DataFrame
    station: pd.DataFrame
    global_sum: float
    global_count: int


def log(message: str) -> None:
    print(message, flush=True)


def read_csv_from_s3(s3_client, bucket: str, key: str) -> pd.DataFrame:
    obj = s3_client.get_object(Bucket=bucket, Key=key)
    return pd.read_csv(io.BytesIO(obj["Body"].read()))


def write_parquet_to_s3(s3_client, df: pd.DataFrame, bucket: str, key: str) -> None:
    """
    Write a large DataFrame to S3 as Parquet without keeping the full output in memory.
    """
    temp_dir = Path(os.getenv("BIXI_TEMP_DIR", tempfile.gettempdir()))
    temp_dir.mkdir(parents=True, exist_ok=True)

    local_path: Path | None = None

    try:
        with tempfile.NamedTemporaryFile(
            suffix=".parquet",
            dir=temp_dir,
            delete=False,
        ) as tmp:
            local_path = Path(tmp.name)

        df.to_parquet(local_path, index=False)
        s3_client.upload_file(str(local_path), bucket, key)
        log(f"Saved s3://{bucket}/{key} | shape={df.shape}")

    finally:
        if local_path is not None and local_path.exists():
            local_path.unlink()


def complete_station_time_grid(df: pd.DataFrame) -> pd.DataFrame:
    """
    Complete the station x 15-minute demand grid.

    Missing station-time demand values are filled with 0.
    """
    df = df.copy()
    df["time_15min"] = pd.to_datetime(df["time_15min"])

    required_cols = {"station_name", "time_15min", "demand"}
    missing_cols = required_cols - set(df.columns)
    if missing_cols:
        raise ValueError(f"Demand data is missing required columns: {missing_cols}")

    metadata_cols = [col for col in df.columns if col not in {"time_15min", "demand"}]
    station_meta = (
        df[metadata_cols]
        .sort_values("station_name")
        .drop_duplicates(subset=["station_name"])
        .reset_index(drop=True)
    )

    demand = (
        df.groupby(["station_name", "time_15min"], as_index=False)["demand"]
        .sum()
    )

    full_times = pd.date_range(
        start=demand["time_15min"].min(),
        end=demand["time_15min"].max(),
        freq=TIME_FREQ,
    )

    grid = pd.MultiIndex.from_product(
        [station_meta["station_name"], full_times],
        names=["station_name", "time_15min"],
    ).to_frame(index=False)

    grid = grid.merge(station_meta, on="station_name", how="left")
    grid = grid.merge(demand, on=["station_name", "time_15min"], how="left")
    grid["demand"] = grid["demand"].fillna(0)

    return grid


def add_time_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add model-ready calendar and cyclical time features.

    slot_of_day is kept only as a temporary key for baseline construction
    and is removed from the final output.
    """
    df = df.copy()
    df["time_15min"] = pd.to_datetime(df["time_15min"])

    slot_of_day = df["time_15min"].dt.hour * 4 + df["time_15min"].dt.minute // 15

    df["dayofweek"] = df["time_15min"].dt.dayofweek.astype("int8")
    df["month"] = df["time_15min"].dt.month.astype("int8")
    df["slot_of_day"] = slot_of_day.astype("int8")
    df["slot_sin"] = np.sin(2 * np.pi * slot_of_day / SLOTS_PER_DAY).astype("float32")
    df["slot_cos"] = np.cos(2 * np.pi * slot_of_day / SLOTS_PER_DAY).astype("float32")

    return df


def load_prepare_demand(s3_client, bucket: str, key: str) -> pd.DataFrame:
    df = read_csv_from_s3(s3_client, bucket, key)
    df = complete_station_time_grid(df)
    return add_time_features(df)


def build_profile_stats(baseline_df: pd.DataFrame) -> ProfileStats:
    """Precompute 2024 profile statistics once and reuse them for all baseline features."""
    primary = (
        baseline_df.groupby(["station_name", "dayofweek", "slot_of_day"], as_index=False)
        .agg(primary_sum=("demand", "sum"), primary_count=("demand", "count"))
    )

    station_slot = (
        baseline_df.groupby(["station_name", "slot_of_day"], as_index=False)
        .agg(station_slot_sum=("demand", "sum"), station_slot_count=("demand", "count"))
    )

    station = (
        baseline_df.groupby("station_name", as_index=False)
        .agg(station_sum=("demand", "sum"), station_count=("demand", "count"))
    )

    return ProfileStats(
        primary=primary,
        station_slot=station_slot,
        station=station,
        global_sum=float(baseline_df["demand"].sum()),
        global_count=len(baseline_df),
    )


def add_shifted_lookup_keys(
    df: pd.DataFrame,
    slots_back: int,
    dow_col: str,
    slot_col: str,
) -> pd.DataFrame:
    """
    Create weekly lookup keys for profile-based historical features.

    slots_back=0: current same day-of-week and slot
    slots_back=1: previous 15-minute slot
    slots_back=4: previous 1 hour
    slots_back=96: yesterday same slot
    """
    weekly_slot = (
        df["dayofweek"].astype("int16") * SLOTS_PER_DAY
        + df["slot_of_day"].astype("int16")
        - slots_back
    ) % SLOTS_PER_WEEK

    df[dow_col] = (weekly_slot // SLOTS_PER_DAY).astype("int8")
    df[slot_col] = (weekly_slot % SLOTS_PER_DAY).astype("int8")

    return df


def mean_with_optional_leave_one_out(
    total: pd.Series,
    count: pd.Series,
    current_demand: pd.Series,
    include_current: pd.Series,
    use_leave_one_out: bool,
) -> pd.Series:
    """
    Calculate a mean from precomputed group sums and counts.

    When use_leave_one_out=True, subtract the current row's demand from the
    group only when the current row belongs to that fallback group.
    """
    adjusted_total = total
    adjusted_count = count

    if use_leave_one_out:
        adjusted_total = adjusted_total.where(~include_current, adjusted_total - current_demand)
        adjusted_count = adjusted_count.where(~include_current, adjusted_count - 1)

    adjusted_count = adjusted_count.where(adjusted_count > 0)
    return adjusted_total / adjusted_count


def merge_profile_feature(
    target_df: pd.DataFrame,
    profile_stats: ProfileStats,
    feature_name: str,
    source_dow_col: str,
    source_slot_col: str,
    use_leave_one_out: bool,
) -> pd.DataFrame:
    """
    Merge one 2024 profile-based baseline feature.

    Fallback order:
    1. station_name + dayofweek + slot_of_day
    2. station_name + slot_of_day
    3. station_name
    4. global mean
    5. 0

    For 2024 training samples, use_leave_one_out=True removes each row's own
    demand from any fallback group that contains that row. For 2025 validation
    and test samples, use_leave_one_out=False uses the complete 2024 profile.
    """
    target = target_df

    primary_stats = profile_stats.primary.rename(
        columns={
            "dayofweek": source_dow_col,
            "slot_of_day": source_slot_col,
        }
    )
    target = target.merge(
        primary_stats,
        on=["station_name", source_dow_col, source_slot_col],
        how="left",
    )

    current_in_primary = (
        target["dayofweek"].eq(target[source_dow_col])
        & target["slot_of_day"].eq(target[source_slot_col])
    )
    target[feature_name] = mean_with_optional_leave_one_out(
        total=target["primary_sum"],
        count=target["primary_count"],
        current_demand=target["demand"],
        include_current=current_in_primary,
        use_leave_one_out=use_leave_one_out,
    )

    target = target.drop(columns=["primary_sum", "primary_count"], errors="ignore")

    station_slot_stats = profile_stats.station_slot.rename(
        columns={"slot_of_day": source_slot_col}
    )
    target = target.merge(
        station_slot_stats,
        on=["station_name", source_slot_col],
        how="left",
    )

    current_in_station_slot = target["slot_of_day"].eq(target[source_slot_col])
    station_slot_mean = mean_with_optional_leave_one_out(
        total=target["station_slot_sum"],
        count=target["station_slot_count"],
        current_demand=target["demand"],
        include_current=current_in_station_slot,
        use_leave_one_out=use_leave_one_out,
    )
    target[feature_name] = target[feature_name].fillna(station_slot_mean)

    target = target.drop(columns=["station_slot_sum", "station_slot_count"], errors="ignore")

    target = target.merge(profile_stats.station, on="station_name", how="left")

    current_in_station = target["station_count"].notna()
    station_mean = mean_with_optional_leave_one_out(
        total=target["station_sum"],
        count=target["station_count"],
        current_demand=target["demand"],
        include_current=current_in_station,
        use_leave_one_out=use_leave_one_out,
    )
    target[feature_name] = target[feature_name].fillna(station_mean)

    target = target.drop(columns=["station_sum", "station_count"], errors="ignore")

    if use_leave_one_out and profile_stats.global_count > 1:
        global_mean = (profile_stats.global_sum - target["demand"]) / (profile_stats.global_count - 1)
    elif profile_stats.global_count > 0:
        global_mean = pd.Series(profile_stats.global_sum / profile_stats.global_count, index=target.index)
    else:
        global_mean = pd.Series(np.nan, index=target.index)

    target[feature_name] = target[feature_name].fillna(global_mean).fillna(0).astype("float32")

    return target


def add_profile_baseline_features(
    df: pd.DataFrame,
    profile_stats: ProfileStats,
    use_leave_one_out: bool,
) -> pd.DataFrame:
    """
    Add all profile-based historical demand features.
    """
    feature_specs = [
        ("hist_avg_demand", 0, "_hist_dow", "_hist_slot"),
        ("baseline_prev_15min", 1, "_prev15_dow", "_prev15_slot"),
        ("baseline_prev_1h", 4, "_prev1h_dow", "_prev1h_slot"),
        ("baseline_yesterday_same_slot", SLOTS_PER_DAY, "_yesterday_dow", "_yesterday_slot"),
    ]

    temp_cols: list[str] = []

    for feature_name, slots_back, dow_col, slot_col in feature_specs:
        log(f"  Adding {feature_name}...")
        df = add_shifted_lookup_keys(df, slots_back, dow_col, slot_col)
        df = merge_profile_feature(
            target_df=df,
            profile_stats=profile_stats,
            feature_name=feature_name,
            source_dow_col=dow_col,
            source_slot_col=slot_col,
            use_leave_one_out=use_leave_one_out,
        )
        temp_cols.extend([dow_col, slot_col])
        log(f"  Added {feature_name} | shape={df.shape}")

    return df.drop(columns=temp_cols, errors="ignore")


def prepare_weather(
    weather_df: pd.DataFrame,
    start_time: pd.Timestamp,
    end_time: pd.Timestamp,
) -> pd.DataFrame:
    """
    Sort weather data, complete it to a 15-minute grid, and forward-fill
    missing values. All weather columns are preserved.
    """
    weather = weather_df.copy()
    weather["time"] = pd.to_datetime(weather["time"])

    weather = (
        weather.sort_values("time")
        .drop_duplicates(subset=["time"])
        .set_index("time")
    )

    full_times = pd.date_range(start=start_time, end=end_time, freq=TIME_FREQ)
    weather = weather.reindex(full_times).ffill()
    weather.index.name = "time"

    return weather.reset_index()


def merge_weather(
    s3_client,
    df: pd.DataFrame,
    bucket: str,
    weather_key: str,
) -> pd.DataFrame:
    weather = read_csv_from_s3(s3_client, bucket, weather_key)
    weather = prepare_weather(
        weather_df=weather,
        start_time=df["time_15min"].min(),
        end_time=df["time_15min"].max(),
    )

    return df.merge(weather, left_on="time_15min", right_on="time", how="left").drop(
        columns=["time"],
        errors="ignore",
    )


def finalize_features(df: pd.DataFrame) -> pd.DataFrame:
    """Remove temporary feature-construction columns from the final output."""
    return df.drop(columns=["slot_of_day"], errors="ignore")


def run_feature_job(
    s3_client,
    bucket: str,
    job: FeatureJob,
    profile_stats: ProfileStats,
    prepared_target_df: pd.DataFrame | None = None,
) -> pd.DataFrame:
    start = time.perf_counter()
    log(f"\nProcessing {job.demand_key}")

    if prepared_target_df is None:
        df = load_prepare_demand(s3_client, bucket, job.demand_key)
    else:
        df = prepared_target_df.copy()

    log(f"Loaded and completed demand grid: {df.shape}")

    df = add_profile_baseline_features(
        df=df,
        profile_stats=profile_stats,
        use_leave_one_out=job.use_leave_one_out,
    )
    log(f"Added baseline features: {df.shape}")

    df = merge_weather(s3_client, df, bucket, job.weather_key)
    log(f"Merged weather: {df.shape}")

    df = finalize_features(df)
    log(f"Finalized features: {df.shape}")

    write_parquet_to_s3(s3_client, df, bucket, job.output_key)

    elapsed = (time.perf_counter() - start) / 60
    log(f"Finished {job.output_key} in {elapsed:.2f} minutes")

    return df


def main() -> None:
    s3_client = boto3.client("s3")

    log("Loading 2024 departure baseline...")
    baseline_departure = load_prepare_demand(
        s3_client,
        BUCKET,
        "processed-data/2024_departure_demand_15min.csv",
    )
    log(f"Loaded 2024 departure baseline: {baseline_departure.shape}")

    log("Loading 2024 arrival baseline...")
    baseline_arrival = load_prepare_demand(
        s3_client,
        BUCKET,
        "processed-data/2024_arrival_demand_15min.csv",
    )
    log(f"Loaded 2024 arrival baseline: {baseline_arrival.shape}")

    log("Building departure profile stats...")
    departure_stats = build_profile_stats(baseline_departure)
    log("Built departure profile stats.")

    log("Building arrival profile stats...")
    arrival_stats = build_profile_stats(baseline_arrival)
    log("Built arrival profile stats.")

    baseline_data = {
        "departure": baseline_departure,
        "arrival": baseline_arrival,
    }

    profile_stats = {
        "departure": departure_stats,
        "arrival": arrival_stats,
    }

    jobs = [
        FeatureJob(
            demand_key="processed-data/2024_departure_demand_15min.csv",
            weather_key="weather-data/2024_weather_15min.csv",
            output_key="processed-data/2024_departure_features.parquet",
            baseline_type="departure",
            use_leave_one_out=True,
        ),
        FeatureJob(
            demand_key="processed-data/2024_arrival_demand_15min.csv",
            weather_key="weather-data/2024_weather_15min.csv",
            output_key="processed-data/2024_arrival_features.parquet",
            baseline_type="arrival",
            use_leave_one_out=True,
        ),
        FeatureJob(
            demand_key="processed-data/2025_may_departure_demand_15min.csv",
            weather_key="weather-data/2025-may_weather_15min.csv",
            output_key="processed-data/2025_may_departure_features.parquet",
            baseline_type="departure",
            use_leave_one_out=False,
        ),
        FeatureJob(
            demand_key="processed-data/2025_may_arrival_demand_15min.csv",
            weather_key="weather-data/2025-may_weather_15min.csv",
            output_key="processed-data/2025_may_arrival_features.parquet",
            baseline_type="arrival",
            use_leave_one_out=False,
        ),
        FeatureJob(
            demand_key="processed-data/2025_oct_departure_demand_15min.csv",
            weather_key="weather-data/2025-oct_weather_15min.csv",
            output_key="processed-data/2025_oct_departure_features.parquet",
            baseline_type="departure",
            use_leave_one_out=False,
        ),
        FeatureJob(
            demand_key="processed-data/2025_oct_arrival_demand_15min.csv",
            weather_key="weather-data/2025-oct_weather_15min.csv",
            output_key="processed-data/2025_oct_arrival_features.parquet",
            baseline_type="arrival",
            use_leave_one_out=False,
        ),
    ]

    for job in jobs:
        prepared_target_df = baseline_data[job.baseline_type] if job.use_leave_one_out else None
        run_feature_job(
            s3_client=s3_client,
            bucket=BUCKET,
            job=job,
            profile_stats=profile_stats[job.baseline_type],
            prepared_target_df=prepared_target_df,
        )


if __name__ == "__main__":
    main()
