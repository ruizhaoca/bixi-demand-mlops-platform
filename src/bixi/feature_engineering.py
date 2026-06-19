"""Feature engineering for BIXI 15-minute demand forecasting.

Reads the cleaned 15-minute demand tables (produced by
:mod:`bixi.demand_ingestion_cleaning`) plus the Open-Meteo weather CSVs, builds
model-ready features, and writes the leakage-safe feature tables the modeling
pipeline consumes:

    s3://<DATA_BUCKET>/<DATA_PREFIX>/{2024,2025_may,2025_oct}_{departure,arrival}_features.parquet

Features per row (== :data:`bixi.config.EXPECTED_COLUMNS`):
  * geo:        latitude, longitude
  * temporal:   dayofweek, month, slot_sin, slot_cos (cyclical 15-min slot)
  * baselines:  hist_avg_demand, baseline_prev_15min, baseline_prev_1h,
                baseline_yesterday_same_slot — all built from the **2024** profile
                only, with **leave-one-out** on the 2024 training rows so a row's
                own demand never leaks into its baseline.
  * weather:    temperature_2m, precipitation, wind_speed_10m,
                relative_humidity_2m, weather_code

Uses the shared :mod:`bixi.config` / :mod:`bixi.io` helpers (default boto3
credential chain) — no hard-coded bucket, no extra runtime dependencies. Wired
into the pipeline as the ``features`` stage; also runnable standalone with
``python -m bixi.feature_engineering``.
"""

from __future__ import annotations

import io as _io
import os
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from . import config, io

TIME_FREQ = "15min"
SLOTS_PER_DAY = 96
SLOTS_PER_WEEK = 7 * SLOTS_PER_DAY

# Weather CSV filenames per period (note: hyphenated, unlike the demand stems).
WEATHER_FILES = {
    "2024": "2024_weather_15min.csv",
    "2025_may": "2025-may_weather_15min.csv",
    "2025_oct": "2025-oct_weather_15min.csv",
}

# Period -> (year_label, use_leave_one_out). 2024 = training (LOO); 2025 = eval.
PERIODS = [("2024", True), ("2025_may", False), ("2025_oct", False)]
_LABEL_TO_SPLIT = {"2024": "train", "2025_may": "val", "2025_oct": "test"}


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


# --------------------------------------------------------------------------- #
# S3 key helpers
# --------------------------------------------------------------------------- #
def demand_key(year_label: str, target: str) -> str:
    return f"{config.DATA_PREFIX}/{year_label}_{target}_demand_15min.csv"


def weather_key(year_label: str) -> str:
    return f"{config.WEATHER_PREFIX}/{WEATHER_FILES[year_label]}"


def output_key(year_label: str, target: str) -> str:
    """Output stem == ``config.split_specs`` file stem, kept in sync."""
    stem = config.split_specs(target)[_LABEL_TO_SPLIT[year_label]].file_stem
    return f"{config.DATA_PREFIX}/{stem}.parquet"


# --------------------------------------------------------------------------- #
# S3 I/O (via bixi.io)
# --------------------------------------------------------------------------- #
def read_csv_from_s3(key: str) -> pd.DataFrame:
    return pd.read_csv(_io.BytesIO(io.get_bytes(key, bucket=config.DATA_BUCKET)))


def write_parquet_to_s3(df: pd.DataFrame, key: str) -> None:
    """Write a DataFrame to S3 as Parquet via a temp file (memory-friendly)."""
    temp_dir = Path(os.getenv("BIXI_TEMP_DIR", tempfile.gettempdir()))
    temp_dir.mkdir(parents=True, exist_ok=True)

    local_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".parquet", dir=temp_dir, delete=False) as tmp:
            local_path = Path(tmp.name)
        df.to_parquet(local_path, index=False)
        io.upload_file(str(local_path), key, bucket=config.DATA_BUCKET)
        log(f"Saved s3://{config.DATA_BUCKET}/{key} | shape={df.shape}")
    finally:
        if local_path is not None and local_path.exists():
            local_path.unlink()


# --------------------------------------------------------------------------- #
# Grid completion + temporal features
# --------------------------------------------------------------------------- #
def complete_station_time_grid(df: pd.DataFrame) -> pd.DataFrame:
    """Complete the station x 15-minute grid; missing demand -> 0."""
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
    """Add calendar + cyclical time features. ``slot_of_day`` is a temporary key
    for baseline construction and is removed from the final output."""
    df = df.copy()
    df["time_15min"] = pd.to_datetime(df["time_15min"])

    slot_of_day = df["time_15min"].dt.hour * 4 + df["time_15min"].dt.minute // 15

    df["dayofweek"] = df["time_15min"].dt.dayofweek.astype("int8")
    df["month"] = df["time_15min"].dt.month.astype("int8")
    df["slot_of_day"] = slot_of_day.astype("int8")
    df["slot_sin"] = np.sin(2 * np.pi * slot_of_day / SLOTS_PER_DAY).astype("float32")
    df["slot_cos"] = np.cos(2 * np.pi * slot_of_day / SLOTS_PER_DAY).astype("float32")

    return df


def load_prepare_demand(key: str) -> pd.DataFrame:
    df = read_csv_from_s3(key)
    df = complete_station_time_grid(df)
    return add_time_features(df)


# --------------------------------------------------------------------------- #
# Leakage-safe 2024 profile baselines
# --------------------------------------------------------------------------- #
def build_profile_stats(baseline_df: pd.DataFrame) -> ProfileStats:
    """Precompute 2024 profile statistics once and reuse them for all baselines."""
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


def add_shifted_lookup_keys(df: pd.DataFrame, slots_back: int,
                            dow_col: str, slot_col: str) -> pd.DataFrame:
    """Create weekly lookup keys for profile-based historical features.

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


def mean_with_optional_leave_one_out(total: pd.Series, count: pd.Series,
                                     current_demand: pd.Series, include_current: pd.Series,
                                     use_leave_one_out: bool) -> pd.Series:
    """Mean from precomputed group sums/counts. When ``use_leave_one_out``,
    subtract the current row's demand from any fallback group containing it."""
    adjusted_total = total
    adjusted_count = count

    if use_leave_one_out:
        adjusted_total = adjusted_total.where(~include_current, adjusted_total - current_demand)
        adjusted_count = adjusted_count.where(~include_current, adjusted_count - 1)

    adjusted_count = adjusted_count.where(adjusted_count > 0)
    return adjusted_total / adjusted_count


def merge_profile_feature(target_df: pd.DataFrame, profile_stats: ProfileStats,
                          feature_name: str, source_dow_col: str, source_slot_col: str,
                          use_leave_one_out: bool) -> pd.DataFrame:
    """Merge one 2024 profile-based baseline feature.

    Fallback order: station+dow+slot -> station+slot -> station -> global -> 0.
    For 2024 training rows ``use_leave_one_out=True`` removes each row's own demand
    from any fallback group containing it; 2025 rows use the full 2024 profile.
    """
    target = target_df

    primary_stats = profile_stats.primary.rename(
        columns={"dayofweek": source_dow_col, "slot_of_day": source_slot_col}
    )
    target = target.merge(
        primary_stats, on=["station_name", source_dow_col, source_slot_col], how="left"
    )

    current_in_primary = (
        target["dayofweek"].eq(target[source_dow_col])
        & target["slot_of_day"].eq(target[source_slot_col])
    )
    target[feature_name] = mean_with_optional_leave_one_out(
        total=target["primary_sum"], count=target["primary_count"],
        current_demand=target["demand"], include_current=current_in_primary,
        use_leave_one_out=use_leave_one_out,
    )
    target = target.drop(columns=["primary_sum", "primary_count"], errors="ignore")

    station_slot_stats = profile_stats.station_slot.rename(
        columns={"slot_of_day": source_slot_col}
    )
    target = target.merge(station_slot_stats, on=["station_name", source_slot_col], how="left")

    current_in_station_slot = target["slot_of_day"].eq(target[source_slot_col])
    station_slot_mean = mean_with_optional_leave_one_out(
        total=target["station_slot_sum"], count=target["station_slot_count"],
        current_demand=target["demand"], include_current=current_in_station_slot,
        use_leave_one_out=use_leave_one_out,
    )
    target[feature_name] = target[feature_name].fillna(station_slot_mean)
    target = target.drop(columns=["station_slot_sum", "station_slot_count"], errors="ignore")

    target = target.merge(profile_stats.station, on="station_name", how="left")

    current_in_station = target["station_count"].notna()
    station_mean = mean_with_optional_leave_one_out(
        total=target["station_sum"], count=target["station_count"],
        current_demand=target["demand"], include_current=current_in_station,
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


def add_profile_baseline_features(df: pd.DataFrame, profile_stats: ProfileStats,
                                  use_leave_one_out: bool) -> pd.DataFrame:
    """Add all profile-based historical demand features."""
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
            target_df=df, profile_stats=profile_stats, feature_name=feature_name,
            source_dow_col=dow_col, source_slot_col=slot_col,
            use_leave_one_out=use_leave_one_out,
        )
        temp_cols.extend([dow_col, slot_col])
        log(f"  Added {feature_name} | shape={df.shape}")

    return df.drop(columns=temp_cols, errors="ignore")


# --------------------------------------------------------------------------- #
# Weather merge + finalize
# --------------------------------------------------------------------------- #
def prepare_weather(weather_df: pd.DataFrame, start_time: pd.Timestamp,
                    end_time: pd.Timestamp) -> pd.DataFrame:
    """Sort weather, complete to a 15-minute grid, and forward-fill gaps."""
    weather = weather_df.copy()
    weather["time"] = pd.to_datetime(weather["time"])

    weather = (
        weather.sort_values("time").drop_duplicates(subset=["time"]).set_index("time")
    )

    full_times = pd.date_range(start=start_time, end=end_time, freq=TIME_FREQ)
    weather = weather.reindex(full_times).ffill()
    weather.index.name = "time"

    return weather.reset_index()


def merge_weather(df: pd.DataFrame, weather_s3_key: str) -> pd.DataFrame:
    weather = read_csv_from_s3(weather_s3_key)
    weather = prepare_weather(
        weather_df=weather, start_time=df["time_15min"].min(), end_time=df["time_15min"].max()
    )
    return df.merge(weather, left_on="time_15min", right_on="time", how="left").drop(
        columns=["time"], errors="ignore"
    )


def finalize_features(df: pd.DataFrame) -> pd.DataFrame:
    """Drop temporary construction columns and enforce the column contract."""
    df = df.drop(columns=["slot_of_day"], errors="ignore")
    # Select + order exactly the columns the modeling pipeline expects; raises if
    # any are missing (a strong schema guard before writing to S3).
    return df[list(config.EXPECTED_COLUMNS)]


# --------------------------------------------------------------------------- #
# Job runner + per-target / all-target builders
# --------------------------------------------------------------------------- #
def run_feature_job(job: FeatureJob, profile_stats: ProfileStats,
                    prepared_target_df: pd.DataFrame | None = None) -> pd.DataFrame:
    start = time.perf_counter()
    log(f"\nProcessing {job.demand_key}")

    df = prepared_target_df.copy() if prepared_target_df is not None \
        else load_prepare_demand(job.demand_key)
    log(f"Loaded and completed demand grid: {df.shape}")

    df = add_profile_baseline_features(df, profile_stats, job.use_leave_one_out)
    log(f"Added baseline features: {df.shape}")

    df = merge_weather(df, job.weather_key)
    log(f"Merged weather: {df.shape}")

    df = finalize_features(df)
    log(f"Finalized features: {df.shape}")

    write_parquet_to_s3(df, job.output_key)

    elapsed = (time.perf_counter() - start) / 60
    log(f"Finished {job.output_key} in {elapsed:.2f} minutes")
    return df


def build_features_for_target(target: str, force: bool = False) -> list[str]:
    """Build train/val/test feature tables for one target (departure | arrival).

    The 2024 demand for this target defines the profile statistics; the 2024 table
    is built leave-one-out, the 2025 May/Oct tables use the full 2024 profile.
    Idempotent: a period whose output parquet already exists is skipped unless
    ``force``.
    """
    if target not in config.TARGETS:
        raise ValueError(f"target must be one of {config.TARGETS}, got {target!r}")

    log(f"\n=== features: target={target} ===")
    log(f"Loading 2024 {target} baseline...")
    baseline = load_prepare_demand(demand_key("2024", target))
    stats = build_profile_stats(baseline)
    log(f"Built {target} profile stats | baseline shape={baseline.shape}")

    written: list[str] = []
    for year_label, use_loo in PERIODS:
        out_key = output_key(year_label, target)
        if io.exists(out_key, bucket=config.DATA_BUCKET) and not force:
            log(f"[features] {out_key} already in S3 — skip.")
            continue
        job = FeatureJob(
            demand_key=demand_key(year_label, target),
            weather_key=weather_key(year_label),
            output_key=out_key,
            baseline_type=target,
            use_leave_one_out=use_loo,
        )
        run_feature_job(job, stats, prepared_target_df=baseline if use_loo else None)
        written.append(out_key)
    return written


def build_all_features(force: bool = False) -> list[str]:
    written: list[str] = []
    for target in config.TARGETS:
        written += build_features_for_target(target, force=force)
    return written


def main(force: bool = False) -> None:
    build_all_features(force=force)
    log("\nFeature engineering complete.")


if __name__ == "__main__":
    main()
