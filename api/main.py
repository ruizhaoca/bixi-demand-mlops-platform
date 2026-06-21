"""BIXI demand prediction API (FastAPI).

A thin REST tier over the existing model bundles in ``src/bixi``. It reuses the
exact same prediction contract as the two Streamlit apps — ``build_feature_row``
+ ``predict_one`` from a loaded bundle — so the numbers match across every
serving surface. No new ML logic lives here.

Serving mode is chosen at startup by ``BIXI_SERVING_MODE``:

* ``local`` (default) — load the artifacts committed under
  ``artifacts/streamlit-community-cloud/cloud-2024/`` (no AWS). Used by tests and
  as the in-container fallback.
* ``s3`` — load the same bundle shape from S3 using the instance IAM role
  (App Runner). Driven by ``BIXI_RUN_ID`` / ``BIXI_PIPELINE_BUCKET`` /
  ``BIXI_DATA_BUCKET`` / ``AWS_REGION`` (see ``bixi.streamlit_s3_serving``).
"""

from __future__ import annotations

import os
import json
import secrets
import sys
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

# Make the ``bixi`` package importable whether or not ``src`` is already on the
# path. The Docker image sets ``PYTHONPATH=/app/src`` and pytest uses the repo
# ``conftest.py``; this shim covers a bare ``uvicorn api.main:app`` from the repo
# root so every run mode behaves identically.
_SRC = Path(__file__).resolve().parent.parent / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import pandas as pd  # noqa: E402  (after the sys.path shim above)
from fastapi import Depends, FastAPI, Header, HTTPException  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

from bixi import config  # noqa: E402
from bixi.rebalancing import NEUTRAL_WEATHER, compute_rebalancing  # noqa: E402
from bixi.streamlit_local_serving import (  # noqa: E402
    LocalTargetBundle,
    common_stations,
    load_local_bundles,
)

MODE = os.getenv("BIXI_SERVING_MODE", "local").lower()
API_KEY = os.getenv("BIXI_API_KEY", "")


def _load_bundles() -> dict[str, LocalTargetBundle]:
    """Load the per-target model bundles once, per the configured mode."""
    if MODE == "s3":
        # Imported lazily so ``local`` mode (tests / CI) never needs boto3 set up.
        from bixi.streamlit_s3_serving import load_s3_bundles

        return load_s3_bundles()
    return load_local_bundles()


BUNDLES: dict[str, LocalTargetBundle] = _load_bundles()

app = FastAPI(
    title="BIXI Demand API",
    version="1.0.0",
    description=(
        "REST prediction service for the BIXI 15-minute demand models "
        "(departure + arrival). Reuses the same model bundles as the Streamlit "
        "apps; this is the App Runner serving tier."
    ),
)


# --------------------------------------------------------------------------- #
# Schemas
# --------------------------------------------------------------------------- #
class Weather(BaseModel):
    """Weather inputs the model expects. Defaults describe a clear, calm slot."""

    temperature_2m: float = Field(default=15.0, description="Air temperature (°C).")
    precipitation: float = Field(default=0.0, ge=0.0, description="Precipitation (mm).")
    wind_speed_10m: float = Field(default=5.0, ge=0.0, description="Wind speed at 10 m (km/h).")
    relative_humidity_2m: float = Field(default=60.0, description="Relative humidity (%).")
    weather_code: float = Field(default=0.0, description="WMO weather code (0 = clear).")


class PredictRequest(BaseModel):
    station_name: str = Field(..., description="BIXI station name (see GET /stations).")
    timestamp: datetime = Field(..., description="ISO-8601 timestamp; slot/dow derived from it.")
    target: Literal["departure", "arrival", "both"] = "both"
    weather: Weather = Field(default_factory=Weather)


class PredictResponse(BaseModel):
    station_name: str
    timestamp: datetime
    predictions: dict[str, float]
    engineered_features: dict[str, dict[str, Any]]


class BatchPredictRequest(BaseModel):
    requests: list[PredictRequest] = Field(min_length=1, max_length=192)


class BatchPredictResponse(BaseModel):
    results: list[PredictResponse]


class RebalancingRequest(BaseModel):
    dayofweek: int = Field(default=1, ge=0, le=6)
    month: int = Field(default=6, ge=1, le=12)
    weather: Weather = Field(default_factory=lambda: Weather(**NEUTRAL_WEATHER))
    station_name: str | None = None


def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    """Require ``X-API-Key`` only when the deployment configures a key."""
    if API_KEY and (x_api_key is None or not secrets.compare_digest(x_api_key, API_KEY)):
        raise HTTPException(status_code=401, detail="Invalid or missing API key.")


PROTECTED = [Depends(require_api_key)]


def _targets(target: str) -> tuple[str, ...]:
    return config.TARGETS if target == "both" else (target,)


def _feature_rows(request: PredictRequest) -> dict[str, dict[str, Any]]:
    timestamp = pd.Timestamp(request.timestamp)
    weather = request.weather.model_dump()
    rows: dict[str, dict[str, Any]] = {}
    for target in _targets(request.target):
        bundle = BUNDLES.get(target)
        if bundle is None:  # pragma: no cover - both targets always load
            raise HTTPException(status_code=404, detail=f"No model bundle for target {target!r}.")
        try:
            rows[target] = bundle.build_feature_row(request.station_name, timestamp, weather)
        except KeyError as exc:
            detail = exc.args[0] if exc.args else "Unknown station or missing baseline."
            raise HTTPException(status_code=404, detail=detail) from exc
    return rows


def _score_request(request: PredictRequest) -> PredictResponse:
    rows = _feature_rows(request)
    predictions = {
        target: BUNDLES[target].predict_one(row)
        for target, row in rows.items()
    }
    return PredictResponse(
        station_name=request.station_name,
        timestamp=request.timestamp,
        predictions=predictions,
        engineered_features=rows,
    )


def _json_records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    """Convert pandas/numpy values to strict JSON-compatible records."""
    return json.loads(frame.to_json(orient="records"))


@lru_cache(maxsize=32)
def _cached_rebalancing(
    dayofweek: int,
    month: int,
    temperature_2m: float,
    precipitation: float,
    wind_speed_10m: float,
    relative_humidity_2m: float,
    weather_code: float,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    weather = {
        "temperature_2m": temperature_2m,
        "precipitation": precipitation,
        "wind_speed_10m": wind_speed_10m,
        "relative_humidity_2m": relative_humidity_2m,
        "weather_code": weather_code,
    }
    return compute_rebalancing(
        BUNDLES,
        dayofweek=dayofweek,
        month=month,
        weather=weather,
    )


# --------------------------------------------------------------------------- #
# Endpoints
# --------------------------------------------------------------------------- #
@app.get("/health")
def health() -> dict:
    """Liveness probe (App Runner health check hits this)."""
    return {"status": "ok", "mode": MODE, "targets": list(BUNDLES.keys())}


@app.get("/stations", dependencies=PROTECTED)
def stations() -> dict:
    """Station names available across every target (intersection)."""
    return {"stations": common_stations(BUNDLES)}


@app.get("/info", dependencies=PROTECTED)
def info() -> dict:
    """Per-target evaluation metrics + the registered production model."""
    return {
        target: {
            "metrics": bundle.metrics,
            "registered_model": bundle.registered_model,
        }
        for target, bundle in BUNDLES.items()
    }


@app.get("/monitoring", dependencies=PROTECTED)
def monitoring() -> dict:
    """Return the metadata needed by the Streamlit monitoring page."""
    return {
        target: {
            "metrics": bundle.metrics,
            "data_summary": bundle.data_summary,
            "tiers": bundle.tiers,
            "fairness_report": bundle.fairness_report,
            "drift_summary": bundle.drift_summary,
            "registered_model": bundle.registered_model,
            "shap_importance": _json_records(bundle.shap_importance),
        }
        for target, bundle in BUNDLES.items()
    }


@app.post("/features", dependencies=PROTECTED)
def features(request: PredictRequest) -> dict:
    """Build model features without scoring, for UI feature previews."""
    return {"engineered_features": _feature_rows(request)}


@app.post("/predict", response_model=PredictResponse, dependencies=PROTECTED)
def predict(request: PredictRequest) -> PredictResponse:
    """Predict 15-minute demand for a station at a timestamp.

    Builds the feature row from the 2024 serving baseline + supplied weather and
    scores the production model. Predictions are non-negative (the bundle clips).
    """
    return _score_request(request)


@app.post("/predict/batch", response_model=BatchPredictResponse, dependencies=PROTECTED)
def predict_batch(request: BatchPredictRequest) -> BatchPredictResponse:
    """Score up to two full 96-slot days in one HTTP request."""
    return BatchPredictResponse(results=[_score_request(item) for item in request.requests])


@app.post("/rebalancing", dependencies=PROTECTED)
def rebalancing(request: RebalancingRequest) -> dict:
    """Return ranked station risks and an optional station trajectory."""
    weather = request.weather
    netflow_df, risk_df = _cached_rebalancing(
        request.dayofweek,
        request.month,
        weather.temperature_2m,
        weather.precipitation,
        weather.wind_speed_10m,
        weather.relative_humidity_2m,
        weather.weather_code,
    )
    trajectory: list[dict[str, Any]] = []
    if request.station_name is not None:
        station_rows = netflow_df[netflow_df[config.STATION_COL] == request.station_name]
        if station_rows.empty:
            raise HTTPException(status_code=404, detail=f"Unknown station {request.station_name!r}.")
        trajectory = _json_records(station_rows)
    return {
        "dayofweek": request.dayofweek,
        "month": request.month,
        "priorities": _json_records(risk_df),
        "trajectory": trajectory,
    }
