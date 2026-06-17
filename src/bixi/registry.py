"""MLflow tracking + Model Registry helpers.

Conventions reused by Phase 3 (clustering): one experiment per target
(``bixi-demand-<target>``) and one registered model per target, promoted via the
MLflow 3.x **alias** ``production`` (stages are deprecated in 3.x).

All helpers degrade gracefully: if the tracking server is unreachable the run
still completes against a local ``./mlruns`` store so training never hard-fails.
"""

from __future__ import annotations

import os

import mlflow
from mlflow.tracking import MlflowClient

from . import config


def _http_reachable(uri: str, timeout: float = 5.0) -> bool:
    import socket
    from urllib.parse import urlparse

    p = urlparse(uri)
    host, port = p.hostname, p.port or (443 if p.scheme == "https" else 80)
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def init_mlflow() -> str:
    # Remote server (CDK MlflowStack) when provided; else a local SQLite store.
    # MLflow 3.x deprecated the bare ./mlruns file store, so we use sqlite locally.
    # If a remote http(s) server is configured but unreachable, fall back to
    # local sqlite so training never hard-fails on a tracking-server outage.
    uri = config.MLFLOW_TRACKING_URI or os.getenv("MLFLOW_TRACKING_URI", "")
    if uri.startswith("http") and not _http_reachable(uri):
        print(f"WARNING: MLflow server {uri} unreachable; falling back to local sqlite.")
        uri = ""
    if not uri:
        uri = "sqlite:///mlflow.db"
    mlflow.set_tracking_uri(uri)
    return mlflow.get_tracking_uri()


def set_experiment(target: str):
    return mlflow.set_experiment(config.experiment_name(target))


def log_metrics(prefix: str, m: dict) -> None:
    mlflow.log_metrics({f"{prefix}_{k}": float(v) for k, v in m.items()
                        if v == v})  # skip NaN


def log_model(model, name: str = "model"):
    """Log a scikit-learn-compatible model (LGBM/XGB/HGB/FLAML).

    cloudpickle is required: the default skops format cannot serialize some
    estimator internals. Uses ``artifact_path`` (MLflow 2.x API).
    """
    import mlflow.sklearn

    return mlflow.sklearn.log_model(
        model, artifact_path=name,
        serialization_format=mlflow.sklearn.SERIALIZATION_FORMAT_CLOUDPICKLE,
    )


def register_production(mlflow_run_id: str, target: str,
                        artifact_name: str = "model") -> dict:
    """Register the run's model and point the ``production`` alias at it."""
    name = config.registered_model_name(target)
    client = MlflowClient()
    try:
        client.create_registered_model(name)
    except Exception:
        pass  # already exists

    model_uri = f"runs:/{mlflow_run_id}/{artifact_name}"
    mv = mlflow.register_model(model_uri, name)
    info = {"name": name, "version": mv.version, "run_id": mlflow_run_id}
    try:
        client.set_registered_model_alias(name, "production", mv.version)
        info["alias"] = "production"
    except Exception as e:  # very old servers may still use stages
        try:
            client.transition_model_version_stage(name, mv.version, "Production")
            info["stage"] = "Production"
        except Exception:
            info["alias_error"] = str(e)
    return info
