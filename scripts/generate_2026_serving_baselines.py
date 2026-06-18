"""Generate Phase-4 serving baseline artifacts for future predictions.

The Phase-2 2024 training feature tables used leave-one-out historical baseline
features. That is correct for training, but not for future serving. This script
rebuilds the compact station x weekday x 15-minute-slot baseline lookup from the
2024 demand column using full 2024 averages, then uploads the serving artifact
to S3.
"""

from __future__ import annotations

import argparse
import io
import os
import sys
from pathlib import Path

import boto3
import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from bixi import config  # noqa: E402


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


def load_env_file(path: Path | None) -> None:
    """Load simple KEY=VALUE pairs without printing secrets."""
    if path is None or not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def read_parquet_from_s3(
    s3_client,
    bucket: str,
    key: str,
    columns: list[str],
) -> pd.DataFrame:
    with io.BytesIO() as buffer:
        s3_client.download_fileobj(bucket, key, buffer)
        buffer.seek(0)
        return pd.read_parquet(buffer, columns=columns)


def write_parquet_to_s3(s3_client, df: pd.DataFrame, bucket: str, key: str) -> str:
    with io.BytesIO() as buffer:
        df.to_parquet(buffer, index=False)
        buffer.seek(0)
        s3_client.put_object(
            Bucket=bucket,
            Key=key,
            Body=buffer.getvalue(),
            ContentType="application/octet-stream",
        )
    return f"s3://{bucket}/{key}"


def add_time_keys(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    ts = pd.to_datetime(out[config.TIME_COL])
    slot = ts.dt.hour * 4 + ts.dt.minute // 15
    out["dayofweek"] = ts.dt.dayofweek.astype("int8")
    out["slot_of_day"] = slot.astype("int16")
    return out


def shifted_keys(frame: pd.DataFrame, slots_back: int) -> tuple[pd.Series, pd.Series]:
    weekly_slot = (
        frame["dayofweek"].astype("int16") * SLOTS_PER_DAY
        + frame["slot_of_day"].astype("int16")
        - slots_back
    ) % SLOTS_PER_WEEK
    return (weekly_slot // SLOTS_PER_DAY).astype("int8"), (weekly_slot % SLOTS_PER_DAY).astype("int16")


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
    src_dow, src_slot = shifted_keys(out, slots_back)
    out["_source_dayofweek"] = src_dow
    out["_source_slot_of_day"] = src_slot

    primary_lookup = primary.rename(
        columns={
            "dayofweek": "_source_dayofweek",
            "slot_of_day": "_source_slot_of_day",
            "mean_demand": feature_name,
        }
    )
    out = out.merge(
        primary_lookup[[config.STATION_COL, "_source_dayofweek", "_source_slot_of_day", feature_name]],
        on=[config.STATION_COL, "_source_dayofweek", "_source_slot_of_day"],
        how="left",
    )

    station_slot_lookup = station_slot.rename(
        columns={"slot_of_day": "_source_slot_of_day", "mean_demand": "_station_slot_mean"}
    )
    out = out.merge(
        station_slot_lookup[[config.STATION_COL, "_source_slot_of_day", "_station_slot_mean"]],
        on=[config.STATION_COL, "_source_slot_of_day"],
        how="left",
    )
    out[feature_name] = out[feature_name].fillna(out["_station_slot_mean"])

    station_lookup = station.rename(columns={"mean_demand": "_station_mean"})
    out = out.merge(station_lookup[[config.STATION_COL, "_station_mean"]], on=config.STATION_COL, how="left")
    out[feature_name] = out[feature_name].fillna(out["_station_mean"]).fillna(global_mean).fillna(0.0)
    out[feature_name] = out[feature_name].astype("float32")

    return out.drop(
        columns=["_source_dayofweek", "_source_slot_of_day", "_station_slot_mean", "_station_mean"],
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
    base["slot_sin"] = np.sin(2 * np.pi * base["slot_of_day"] / SLOTS_PER_DAY).astype("float32")
    base["slot_cos"] = np.cos(2 * np.pi * base["slot_of_day"] / SLOTS_PER_DAY).astype("float32")

    global_mean = float(data[config.TARGET_COL].mean())
    for feature_name, slots_back in BASELINE_FEATURE_SPECS:
        base = add_baseline_feature(
            base=base,
            primary=primary,
            station_slot=station_slot,
            station=station,
            global_mean=global_mean,
            feature_name=feature_name,
            slots_back=slots_back,
        )

    ordered_columns = [
        config.STATION_COL,
        "dayofweek",
        "slot_of_day",
        "latitude",
        "longitude",
        "slot_sin",
        "slot_cos",
        "hist_avg_demand",
        "baseline_prev_15min",
        "baseline_prev_1h",
        "baseline_yesterday_same_slot",
    ]
    return base[ordered_columns].sort_values([config.STATION_COL, "dayofweek", "slot_of_day"]).reset_index(drop=True)


def generate_for_target(
    s3_client,
    target: str,
    source_bucket: str,
    source_prefix: str,
    output_bucket: str,
    output_prefix: str,
) -> str:
    source_key = f"{source_prefix.rstrip('/')}/2024_{target}_features.parquet"
    output_key = f"{output_prefix.rstrip('/')}/{target}/serving_baselines.parquet"

    print(f"Reading s3://{source_bucket}/{source_key}", flush=True)
    df = read_parquet_from_s3(s3_client, source_bucket, source_key, SOURCE_COLUMNS)
    baselines = build_serving_baselines(df)

    expected_max_rows = df[config.STATION_COL].nunique() * 7 * SLOTS_PER_DAY
    print(
        f"{target}: source rows={len(df):,}, stations={df[config.STATION_COL].nunique():,}, "
        f"serving rows={len(baselines):,}, complete-grid max={expected_max_rows:,}",
        flush=True,
    )
    if baselines[["latitude", "longitude"] + [name for name, _ in BASELINE_FEATURE_SPECS]].isna().any().any():
        raise ValueError(f"{target}: generated baselines contain null values")

    uri = write_parquet_to_s3(s3_client, baselines, output_bucket, output_key)
    print(f"Wrote {uri}", flush=True)
    return uri


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate S3 serving baseline parquet artifacts.")
    parser.add_argument("--source-bucket", default="insy684")
    parser.add_argument("--source-prefix", default="processed-data-clean")
    parser.add_argument("--output-bucket", default="insy684")
    parser.add_argument("--output-prefix", default="bixi-serving-artifacts/cloud-2024")
    parser.add_argument("--targets", default="both", help="departure | arrival | both")
    parser.add_argument("--region", default=os.getenv("AWS_REGION", config.AWS_REGION))
    parser.add_argument("--env-file", default=str(REPO_ROOT.parent / ".env"))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    load_env_file(Path(args.env_file) if args.env_file else None)
    targets = config.TARGETS if args.targets == "both" else (args.targets,)
    for target in targets:
        if target not in config.TARGETS:
            raise ValueError(f"Unsupported target {target!r}; expected one of {config.TARGETS}")

    s3_client = boto3.client("s3", region_name=args.region)
    uris = [
        generate_for_target(
            s3_client=s3_client,
            target=target,
            source_bucket=args.source_bucket,
            source_prefix=args.source_prefix,
            output_bucket=args.output_bucket,
            output_prefix=args.output_prefix,
        )
        for target in targets
    ]
    print("Done:", *uris, sep="\n", flush=True)


if __name__ == "__main__":
    main()
