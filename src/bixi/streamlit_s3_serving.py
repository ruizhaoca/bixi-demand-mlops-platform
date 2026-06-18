"""S3-backed serving helpers for the EC2-only Streamlit deployment.

This module does not use the packaged local artifact bundle committed for
Streamlit Community Cloud. It reads Phase-2 artifacts from S3 at app startup
using the EC2 instance IAM role, then keeps the loaded model objects in the
Streamlit process cache.
"""

from __future__ import annotations

import io
import json
import os
import pickle
from dataclasses import dataclass
from pathlib import Path

import boto3
import pandas as pd
from botocore.exceptions import ClientError

from . import config
from .data import StationEncoder  # noqa: F401  # required for encoder.pkl unpickling
from .streamlit_local_serving import LocalTargetBundle


DEFAULT_RUN_ID = "cloud-2024"
DEFAULT_PIPELINE_BUCKET = "bixistorage-pipelinebucketb967bd35-icnkid23rfsa"
DEFAULT_BASELINE_PREFIX = "bixi-serving-artifacts"


@dataclass(frozen=True)
class S3ArtifactConfig:
    run_id: str
    pipeline_bucket: str
    pipeline_prefix: str
    data_bucket: str
    baseline_prefix: str
    region: str


def s3_artifact_config() -> S3ArtifactConfig:
    """Read EC2 Streamlit artifact settings from environment variables."""
    return S3ArtifactConfig(
        run_id=os.getenv("BIXI_RUN_ID", DEFAULT_RUN_ID),
        pipeline_bucket=os.getenv("BIXI_PIPELINE_BUCKET", DEFAULT_PIPELINE_BUCKET),
        pipeline_prefix=os.getenv("BIXI_PIPELINE_PREFIX", config.PIPELINE_PREFIX).strip("/"),
        data_bucket=os.getenv("BIXI_DATA_BUCKET", config.DATA_BUCKET),
        baseline_prefix=os.getenv("BIXI_BASELINE_PREFIX", DEFAULT_BASELINE_PREFIX).strip("/"),
        region=os.getenv("AWS_REGION", os.getenv("AWS_DEFAULT_REGION", config.AWS_REGION)),
    )


def _s3_uri(bucket: str, key: str) -> str:
    return f"s3://{bucket}/{key}"


def _run_prefix(settings: S3ArtifactConfig, target: str) -> str:
    return f"{settings.pipeline_prefix}/runs/{settings.run_id}/{target}"


def _baseline_key(settings: S3ArtifactConfig, target: str) -> str:
    return f"{settings.baseline_prefix}/{settings.run_id}/{target}/serving_baselines.parquet"


def _missing_object(exc: ClientError) -> bool:
    code = exc.response.get("Error", {}).get("Code")
    return code in {"404", "NoSuchKey", "NotFound"}


def _read_s3_bytes(s3_client, bucket: str, key: str, *, required: bool) -> bytes | None:
    try:
        response = s3_client.get_object(Bucket=bucket, Key=key)
        return response["Body"].read()
    except ClientError as exc:
        if _missing_object(exc) and not required:
            return None
        if _missing_object(exc):
            raise FileNotFoundError(f"Required S3 artifact not found: {_s3_uri(bucket, key)}") from exc
        raise


def _read_json_s3(s3_client, bucket: str, key: str, default):
    payload = _read_s3_bytes(s3_client, bucket, key, required=False)
    if payload is None:
        return default
    return json.loads(payload.decode("utf-8"))


def _read_csv_s3(s3_client, bucket: str, key: str) -> pd.DataFrame:
    payload = _read_s3_bytes(s3_client, bucket, key, required=False)
    if payload is None:
        return pd.DataFrame(columns=["feature", "mean_abs_shap"])
    return pd.read_csv(io.BytesIO(payload))


def _load_target_bundle(s3_client, settings: S3ArtifactConfig, target: str) -> LocalTargetBundle:
    run_prefix = _run_prefix(settings, target)
    model = pickle.loads(
        _read_s3_bytes(
            s3_client,
            settings.pipeline_bucket,
            f"{run_prefix}/train/best_model.pkl",
            required=True,
        )
    )
    encoder = pickle.loads(
        _read_s3_bytes(
            s3_client,
            settings.pipeline_bucket,
            f"{run_prefix}/data/encoder.pkl",
            required=True,
        )
    )
    baselines = pd.read_parquet(
        io.BytesIO(
            _read_s3_bytes(
                s3_client,
                settings.data_bucket,
                _baseline_key(settings, target),
                required=True,
            )
        )
    )
    baseline_lookup = baselines.set_index([config.STATION_COL, "dayofweek", "slot_of_day"]).sort_index()

    return LocalTargetBundle(
        target=target,
        root=Path("s3-artifacts") / settings.run_id / target,
        model=model,
        encoder=encoder,
        baselines=baselines,
        baseline_lookup=baseline_lookup,
        metrics=_read_json_s3(s3_client, settings.pipeline_bucket, f"{run_prefix}/train/metrics.json", {}),
        data_summary=_read_json_s3(s3_client, settings.pipeline_bucket, f"{run_prefix}/data/data_summary.json", {}),
        tiers=_read_json_s3(s3_client, settings.pipeline_bucket, f"{run_prefix}/data/tiers.json", {}),
        fairness_report=_read_json_s3(
            s3_client,
            settings.pipeline_bucket,
            f"{run_prefix}/fairness/fairness_report.json",
            {},
        ),
        drift_summary=_read_json_s3(
            s3_client,
            settings.pipeline_bucket,
            f"{run_prefix}/drift/drift_summary.json",
            {},
        ),
        registered_model=_read_json_s3(
            s3_client,
            settings.pipeline_bucket,
            f"{run_prefix}/register/registered_model.json",
            {},
        ),
        shap_importance=_read_csv_s3(
            s3_client,
            settings.pipeline_bucket,
            f"{run_prefix}/explain/shap_importance.csv",
        ),
    )


def load_s3_bundles(settings: S3ArtifactConfig | None = None) -> dict[str, LocalTargetBundle]:
    """Load departure and arrival bundles directly from S3."""
    settings = settings or s3_artifact_config()
    s3_client = boto3.client("s3", region_name=settings.region)
    return {target: _load_target_bundle(s3_client, settings, target) for target in config.TARGETS}


def s3_source_summary(settings: S3ArtifactConfig | None = None) -> dict[str, str]:
    settings = settings or s3_artifact_config()
    return {
        "run_id": settings.run_id,
        "region": settings.region,
        "pipeline_bucket": settings.pipeline_bucket,
        "pipeline_prefix": settings.pipeline_prefix,
        "data_bucket": settings.data_bucket,
        "baseline_prefix": settings.baseline_prefix,
    }
