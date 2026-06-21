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
import sys
from datetime import datetime
from pathlib import Path
from typing import Literal

# Make the ``bixi`` package importable whether or not ``src`` is already on the
# path. The Docker image sets ``PYTHONPATH=/app/src`` and pytest uses the repo
# ``conftest.py``; this shim covers a bare ``uvicorn api.main:app`` from the repo
# root so every run mode behaves identically.
_SRC = Path(__file__).resolve().parent.parent / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import pandas as pd  # noqa: E402  (after the sys.path shim above)
from fastapi import FastAPI, HTTPException  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

from bixi import config  # noqa: E402
from bixi.streamlit_local_serving import (  # noqa: E402
    LocalTargetBundle,
    common_stations,
    load_local_bundles,
)

MODE = os.getenv("BIXI_SERVING_MODE", "local").lower()


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


# --------------------------------------------------------------------------- #
# Endpoints
# --------------------------------------------------------------------------- #
@app.get("/health")
def health() -> dict:
    """Liveness probe (App Runner health check hits this)."""
    return {"status": "ok", "mode": MODE, "targets": list(BUNDLES.keys())}


@app.get("/stations")
def stations() -> dict:
    """Station names available across every target (intersection)."""
    return {"stations": common_stations(BUNDLES)}


@app.get("/info")
def info() -> dict:
    """Per-target evaluation metrics + the registered production model."""
    return {
        target: {
            "metrics": bundle.metrics,
            "registered_model": bundle.registered_model,
        }
        for target, bundle in BUNDLES.items()
    }


@app.post("/predict", response_model=PredictResponse)
def predict(request: PredictRequest) -> PredictResponse:
    """Predict 15-minute demand for a station at a timestamp.

    Builds the feature row from the 2024 serving baseline + supplied weather and
    scores the production model. Predictions are non-negative (the bundle clips).
    """
    targets = config.TARGETS if request.target == "both" else (request.target,)
    timestamp = pd.Timestamp(request.timestamp)
    weather = request.weather.model_dump()

    predictions: dict[str, float] = {}
    for target in targets:
        bundle = BUNDLES.get(target)
        if bundle is None:  # pragma: no cover - both targets always load
            raise HTTPException(status_code=404, detail=f"No model bundle for target {target!r}.")
        try:
            row = bundle.build_feature_row(request.station_name, timestamp, weather)
        except KeyError as exc:
            # KeyError.__str__ wraps the message in quotes; args[0] is the clean text.
            detail = exc.args[0] if exc.args else "Unknown station or missing baseline."
            raise HTTPException(status_code=404, detail=detail) from exc
        predictions[target] = bundle.predict_one(row)

    return PredictResponse(
        station_name=request.station_name,
        timestamp=request.timestamp,
        predictions=predictions,
    )
