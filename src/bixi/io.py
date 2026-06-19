"""I/O helpers: S3 + local files, JSON/pickle artifacts and checkpoint markers.

Uses the default boto3 credential chain (SSO locally, IAM role on Batch/EC2).
The same functions work for local subsample dev (``local_dir``) and the cloud.
"""

from __future__ import annotations

import io as _io
import json
import os
import pickle
import tempfile
from typing import Any

import pandas as pd

from . import config


# --------------------------------------------------------------------------- #
# boto3
# --------------------------------------------------------------------------- #
# ``boto3`` is imported lazily (inside ``s3()``) so the Community Cloud serving
# app — which only reads the committed local artifacts and never touches S3 —
# does not load boto3/botocore at import time. This keeps the local serving
# import chain dependent only on numpy/pandas and avoids a whole class of
# import-time failures on Streamlit Community Cloud.
_CLIENT = None


def s3():
    global _CLIENT
    if _CLIENT is None:
        import boto3

        _CLIENT = boto3.client("s3", region_name=config.AWS_REGION)
    return _CLIENT


# --------------------------------------------------------------------------- #
# Low-level object helpers (default bucket = pipeline bucket)
# --------------------------------------------------------------------------- #
def _bucket(bucket: str | None) -> str:
    return bucket or config.PIPELINE_BUCKET


def exists(key: str, bucket: str | None = None) -> bool:
    try:
        s3().head_object(Bucket=_bucket(bucket), Key=key)
        return True
    except Exception:
        return False


def put_bytes(key: str, data: bytes, bucket: str | None = None, content_type: str | None = None) -> str:
    kwargs = {"Bucket": _bucket(bucket), "Key": key, "Body": data}
    if content_type:
        kwargs["ContentType"] = content_type
    s3().put_object(**kwargs)
    return f"s3://{_bucket(bucket)}/{key}"


def get_bytes(key: str, bucket: str | None = None) -> bytes:
    return s3().get_object(Bucket=_bucket(bucket), Key=key)["Body"].read()


def upload_file(local_path: str, key: str, bucket: str | None = None) -> str:
    s3().upload_file(local_path, _bucket(bucket), key)
    return f"s3://{_bucket(bucket)}/{key}"


def download_file(key: str, local_path: str, bucket: str | None = None) -> str:
    os.makedirs(os.path.dirname(local_path) or ".", exist_ok=True)
    s3().download_file(_bucket(bucket), key, local_path)
    return local_path


def put_json(key: str, obj: Any, bucket: str | None = None) -> str:
    return put_bytes(key, json.dumps(obj, indent=2, default=str).encode(),
                     bucket=bucket, content_type="application/json")


def get_json(key: str, bucket: str | None = None) -> Any:
    return json.loads(get_bytes(key, bucket=bucket).decode())


def put_pickle(key: str, obj: Any, bucket: str | None = None) -> str:
    return put_bytes(key, pickle.dumps(obj), bucket=bucket,
                     content_type="application/octet-stream")


def get_pickle(key: str, bucket: str | None = None) -> Any:
    return pickle.loads(get_bytes(key, bucket=bucket))


# --------------------------------------------------------------------------- #
# Parquet
# --------------------------------------------------------------------------- #
def read_parquet_s3(key: str, bucket: str | None = None, columns: list[str] | None = None) -> pd.DataFrame:
    """Stream a parquet object to a temp file and read it (column-pruned)."""
    with tempfile.NamedTemporaryFile(suffix=".parquet", delete=True) as tmp:
        s3().download_fileobj(_bucket(bucket), key, tmp)
        tmp.flush()
        return pd.read_parquet(tmp.name, columns=columns)


def read_feature_table(stem: str, local_dir: str | None = None,
                       columns: list[str] | None = None) -> pd.DataFrame:
    """Read a Phase-1 feature table by stem (e.g. ``2024_departure_features``).

    Prefers a local file under ``local_dir`` (dev); otherwise reads from
    ``s3://DATA_BUCKET/DATA_PREFIX/<stem>.parquet``.
    """
    if local_dir:
        local_path = os.path.join(local_dir, f"{stem}.parquet")
        if os.path.exists(local_path):
            return pd.read_parquet(local_path, columns=columns)
    key = f"{config.DATA_PREFIX}/{stem}.parquet"
    return read_parquet_s3(key, bucket=config.DATA_BUCKET, columns=columns)


def write_parquet_s3(key: str, df: pd.DataFrame, bucket: str | None = None) -> str:
    buf = _io.BytesIO()
    df.to_parquet(buf, index=False)
    return put_bytes(key, buf.getvalue(), bucket=bucket,
                     content_type="application/octet-stream")


# --------------------------------------------------------------------------- #
# Checkpoint markers (resumability)
# --------------------------------------------------------------------------- #
def write_success(run_id: str, target: str, stage: str, info: dict | None = None) -> str:
    key = config.success_key(run_id, target, stage)
    return put_json(key, info or {"stage": stage, "status": "ok"})


def has_success(run_id: str, target: str, stage: str) -> bool:
    return exists(config.success_key(run_id, target, stage))
