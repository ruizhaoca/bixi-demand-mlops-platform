"""Build compact historical baseline lookups used by online inference.

Training features use leave-one-out statistics to prevent leakage. Future
predictions instead need full 2024 station/weekday/slot averages. This module
derives that lookup from the rebuilt training feature table and writes it to the
CDK-managed data bucket as part of the normal pipeline.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import config, io

SLOTS_PER_DAY = 96
SLOTS_PER_WEEK = 7 * SLOTS_PER_DAY
SOURCE_COLUMNS = [
    config.STATION_COL,
    config.TIME_COL,
    config.TARGET_COL,
    "latitude",
    "longitude",
]
BASELINE_FEATURE_SPECS = [
    ("hist_avg_demand", 0),
    ("baseline_prev_15min", 1),
    ("baseline_prev_1h", 4),
    ("baseline_yesterday_same_slot", SLOTS_PER_DAY),
]


def add_time_keys(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    ts = pd.to_datetime(out[config.TIME_COL])
    out["dayofweek"] = ts.dt.dayofweek.astype("int8")
    out["slot_of_day"] = (ts.dt.hour * 4 + ts.dt.minute // 15).astype("int16")
    return out


def shifted_keys(frame: pd.DataFrame, slots_back: int) -> tuple[pd.Series, pd.Series]:
    weekly_slot = (
        frame["dayofweek"].astype("int16") * SLOTS_PER_DAY
        + frame["slot_of_day"].astype("int16")
        - slots_back
    ) % SLOTS_PER_WEEK
    return (
        (weekly_slot // SLOTS_PER_DAY).astype("int8"),
        (weekly_slot % SLOTS_PER_DAY).astype("int16"),
    )


def add_baseline_feature(
    base: pd.DataFrame,
    primary: pd.DataFrame,
    station_slot: pd.DataFrame,
    station: pd.DataFrame,
    global_mean: float,
    feature_name: str,
    slots_back: int,
) -> pd.DataFrame:
    out = base.copy()
    source_day, source_slot = shifted_keys(out, slots_back)
    out["_source_dayofweek"] = source_day
    out["_source_slot_of_day"] = source_slot

    primary_lookup = primary.rename(
        columns={
            "dayofweek": "_source_dayofweek",
            "slot_of_day": "_source_slot_of_day",
            "mean_demand": feature_name,
        }
    )
    out = out.merge(
        primary_lookup[
            [config.STATION_COL, "_source_dayofweek", "_source_slot_of_day", feature_name]
        ],
        on=[config.STATION_COL, "_source_dayofweek", "_source_slot_of_day"],
        how="left",
    )

    station_slot_lookup = station_slot.rename(
        columns={"slot_of_day": "_source_slot_of_day", "mean_demand": "_station_slot_mean"}
    )
    out = out.merge(
        station_slot_lookup[
            [config.STATION_COL, "_source_slot_of_day", "_station_slot_mean"]
        ],
        on=[config.STATION_COL, "_source_slot_of_day"],
        how="left",
    )
    out[feature_name] = out[feature_name].fillna(out["_station_slot_mean"])

    station_lookup = station.rename(columns={"mean_demand": "_station_mean"})
    out = out.merge(
        station_lookup[[config.STATION_COL, "_station_mean"]],
        on=config.STATION_COL,
        how="left",
    )
    out[feature_name] = (
        out[feature_name].fillna(out["_station_mean"]).fillna(global_mean).fillna(0.0)
    )
    out[feature_name] = out[feature_name].astype("float32")
    return out.drop(
        columns=[
            "_source_dayofweek",
            "_source_slot_of_day",
            "_station_slot_mean",
            "_station_mean",
        ],
        errors="ignore",
    )


def build_serving_baselines(df: pd.DataFrame) -> pd.DataFrame:
    data = add_time_keys(df)
    primary = (
        data.groupby([config.STATION_COL, "dayofweek", "slot_of_day"], as_index=False)
        .agg(mean_demand=(config.TARGET_COL, "mean"))
    )
    station_slot = (
        data.groupby([config.STATION_COL, "slot_of_day"], as_index=False)
        .agg(mean_demand=(config.TARGET_COL, "mean"))
    )
    station = (
        data.groupby(config.STATION_COL, as_index=False)
        .agg(mean_demand=(config.TARGET_COL, "mean"))
    )
    station_meta = (
        data.sort_values(config.STATION_COL)
        .drop_duplicates(subset=[config.STATION_COL])
        [[config.STATION_COL, "latitude", "longitude"]]
    )

    base = primary[[config.STATION_COL, "dayofweek", "slot_of_day"]].copy()
    base = base.merge(station_meta, on=config.STATION_COL, how="left")
    base["slot_sin"] = np.sin(
        2 * np.pi * base["slot_of_day"] / SLOTS_PER_DAY
    ).astype("float32")
    base["slot_cos"] = np.cos(
        2 * np.pi * base["slot_of_day"] / SLOTS_PER_DAY
    ).astype("float32")

    global_mean = float(data[config.TARGET_COL].mean())
    for feature_name, slots_back in BASELINE_FEATURE_SPECS:
        base = add_baseline_feature(
            base,
            primary,
            station_slot,
            station,
            global_mean,
            feature_name,
            slots_back,
        )

    ordered = [
        config.STATION_COL,
        "dayofweek",
        "slot_of_day",
        "latitude",
        "longitude",
        "slot_sin",
        "slot_cos",
        *[name for name, _ in BASELINE_FEATURE_SPECS],
    ]
    result = base[ordered].sort_values(
        [config.STATION_COL, "dayofweek", "slot_of_day"]
    ).reset_index(drop=True)
    required = ["latitude", "longitude", *[name for name, _ in BASELINE_FEATURE_SPECS]]
    if result[required].isna().any().any():
        raise ValueError("Generated serving baselines contain null values")
    return result


def serving_key(run_id: str, target: str, prefix: str | None = None) -> str:
    root = (prefix or config.SERVING_PREFIX).strip("/")
    return f"{root}/{run_id}/{target}/serving_baselines.parquet"


def generate_for_target(
    target: str,
    run_id: str,
    *,
    source_bucket: str | None = None,
    source_prefix: str | None = None,
    output_bucket: str | None = None,
    output_prefix: str | None = None,
    force: bool = False,
) -> str:
    if target not in config.TARGETS:
        raise ValueError(f"Unsupported target {target!r}")
    source_bucket = source_bucket or config.DATA_BUCKET
    output_bucket = output_bucket or config.DATA_BUCKET
    source_prefix = (source_prefix or config.DATA_PREFIX).strip("/")
    key = serving_key(run_id, target, output_prefix)
    if io.exists(key, bucket=output_bucket) and not force:
        return f"s3://{output_bucket}/{key}"

    source_key = f"{source_prefix}/2024_{target}_features.parquet"
    frame = io.read_parquet_s3(source_key, bucket=source_bucket, columns=SOURCE_COLUMNS)
    baselines = build_serving_baselines(frame)
    return io.write_parquet_s3(key, baselines, bucket=output_bucket)
