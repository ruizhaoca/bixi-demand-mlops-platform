"""Central configuration and data/feature contract for the BIXI pipeline.

Everything is overridable via environment variables so the identical code runs:
  * locally on a subsample (fast development), and
  * on AWS Batch over the full dataset (cloud training).

Naming of the Phase-1 feature tables in S3 (``s3://<DATA_BUCKET>/<DATA_PREFIX>/``):
  2024_<target>_features.parquet            (training)
  2025_may_<target>_features.parquet        (validation)
  2025_oct_<target>_features.parquet        (test)
where ``<target>`` is ``departure`` or ``arrival``.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

# --------------------------------------------------------------------------- #
# AWS / storage
# --------------------------------------------------------------------------- #
AWS_REGION = os.getenv("AWS_REGION", "us-east-2")

# Read-only source data produced by Phase 1 (Sarah / Louis / Rui).
DATA_BUCKET = os.getenv("BIXI_DATA_BUCKET", "insy684")
DATA_PREFIX = os.getenv("BIXI_DATA_PREFIX", "processed-data").strip("/")
RAW_PREFIX = os.getenv("BIXI_RAW_PREFIX", "bixi-data").strip("/")
WEATHER_PREFIX = os.getenv("BIXI_WEATHER_PREFIX", "weather-data").strip("/")

# Pipeline outputs (checkpoints, models, reports). Created by the CDK StorageStack;
# defaults to the data bucket under a prefix so local dev works with no extra setup.
PIPELINE_BUCKET = os.getenv("BIXI_PIPELINE_BUCKET", DATA_BUCKET)
PIPELINE_PREFIX = os.getenv("BIXI_PIPELINE_PREFIX", "bixi-mlops").strip("/")

# MLflow tracking server (CDK MlflowStack). Empty -> local ./mlruns file store.
MLFLOW_TRACKING_URI = os.getenv("MLFLOW_TRACKING_URI", "")

# --------------------------------------------------------------------------- #
# Targets & columns (verified against the Phase-1 parquet schema)
# --------------------------------------------------------------------------- #
TARGETS = ("departure", "arrival")

TARGET_COL = "demand"
TIME_COL = "time_15min"          # ordering only — never a model feature
STATION_COL = "station_name"     # high-cardinality id — encoded, not used raw

GEO_COLS = ["latitude", "longitude"]
TEMPORAL_COLS = ["dayofweek", "month", "slot_sin", "slot_cos"]
BASELINE_COLS = [
    "hist_avg_demand",
    "baseline_prev_15min",
    "baseline_prev_1h",
    "baseline_yesterday_same_slot",
]
WEATHER_COLS = [
    "temperature_2m",
    "precipitation",
    "wind_speed_10m",
    "relative_humidity_2m",
    "weather_code",
]
# Leakage-safe high-cardinality station encodings, added during the data stage
# (fit on TRAIN only): see bixi.data.StationEncoder.
ENCODED_COLS = ["station_freq", "station_target_enc"]

RAW_FEATURE_COLS = GEO_COLS + TEMPORAL_COLS + BASELINE_COLS + WEATHER_COLS
MODEL_FEATURES = RAW_FEATURE_COLS + ENCODED_COLS

# Columns we expect to read from every feature file (schema guard).
EXPECTED_COLUMNS = (
    [STATION_COL, TIME_COL, TARGET_COL]
    + GEO_COLS
    + TEMPORAL_COLS
    + BASELINE_COLS
    + WEATHER_COLS
)


# --------------------------------------------------------------------------- #
# Splits — train=2024 (full year), val=May-2025, test=Oct-2025.
# ``months=None`` keeps the whole year. Filtering by (year, months) hardens the
# loader against the known Phase-1 date-range spillover in the arrival/2024 files.
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class SplitSpec:
    name: str
    file_stem: str            # e.g. "2024_departure_features"
    year: int
    months: tuple | None      # None => all months in `year`


def split_specs(target: str) -> dict[str, SplitSpec]:
    if target not in TARGETS:
        raise ValueError(f"target must be one of {TARGETS}, got {target!r}")
    return {
        "train": SplitSpec("train", f"2024_{target}_features", 2024, None),
        "val": SplitSpec("val", f"2025_may_{target}_features", 2025, (5,)),
        "test": SplitSpec("test", f"2025_oct_{target}_features", 2025, (10,)),
    }


# --------------------------------------------------------------------------- #
# Pipeline stages
# --------------------------------------------------------------------------- #
# `ingest` (raw trip/weather download + 15-min demand cleaning -> S3) and
# `features` (build the leakage-safe feature tables -> S3) are the from-scratch
# rebuild stages. They are excluded from the default run because the good raw
# files and feature tables already live in S3 — run the full rebuild explicitly
# with ``python -m bixi.pipeline --from ingest``.
INGEST_STAGE = "ingest"
FEATURES_STAGE = "features"
DEFAULT_STAGES = ["data", "train", "explain", "fairness", "drift", "register"]
ALL_STAGES = [INGEST_STAGE, FEATURES_STAGE] + DEFAULT_STAGES


def _join(*parts: str) -> str:
    return "/".join(p.strip("/") for p in parts if p != "")


def run_prefix(run_id: str, target: str) -> str:
    """S3 key prefix (no bucket) for a given run + target."""
    return _join(PIPELINE_PREFIX, "runs", run_id, target)


def stage_prefix(run_id: str, target: str, stage: str) -> str:
    return _join(run_prefix(run_id, target), stage)


def success_key(run_id: str, target: str, stage: str) -> str:
    return _join(stage_prefix(run_id, target, stage), "_SUCCESS")


# MLflow experiment + registered model names, per target.
def experiment_name(target: str) -> str:
    return f"bixi-demand-{target}"


def registered_model_name(target: str) -> str:
    return f"bixi-demand-{target}"
