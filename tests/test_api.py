"""Tests for the FastAPI prediction service (local mode, no network).

Forces ``BIXI_SERVING_MODE=local`` so the app loads the committed artifact
bundle under ``artifacts/streamlit-community-cloud/cloud-2024/`` — no AWS, same
no-network style as the other ``tests/test_bixi_*`` suites.
"""

import os

os.environ.setdefault("BIXI_SERVING_MODE", "local")

import pytest
from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)


def _first_station() -> str:
    stations = client.get("/stations").json()["stations"]
    assert stations, "expected at least one common station"
    return stations[0]


def test_health_ok():
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["mode"] == "local"
    assert set(body["targets"]) == {"departure", "arrival"}


def test_stations_non_empty():
    stations = client.get("/stations").json()["stations"]
    assert isinstance(stations, list) and len(stations) > 0
    assert all(isinstance(name, str) for name in stations)


def test_info_reports_registered_models():
    info = client.get("/info").json()
    assert set(info.keys()) == {"departure", "arrival"}
    for target, payload in info.items():
        assert "metrics" in payload
        assert payload["registered_model"].get("name") == f"bixi-demand-{target}"


def test_predict_both_targets_nonnegative():
    station = _first_station()
    response = client.post(
        "/predict",
        json={"station_name": station, "timestamp": "2025-06-15T08:30:00"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["station_name"] == station
    preds = body["predictions"]
    assert set(preds.keys()) == {"departure", "arrival"}
    assert all(isinstance(v, float) and v >= 0.0 for v in preds.values())


def test_predict_single_target_with_weather():
    station = _first_station()
    response = client.post(
        "/predict",
        json={
            "station_name": station,
            "timestamp": "2025-06-15T18:00:00",
            "target": "departure",
            "weather": {
                "temperature_2m": 2.0,
                "precipitation": 5.0,
                "wind_speed_10m": 30.0,
                "relative_humidity_2m": 90.0,
                "weather_code": 61.0,
            },
        },
    )
    assert response.status_code == 200
    preds = response.json()["predictions"]
    assert list(preds.keys()) == ["departure"]
    assert preds["departure"] >= 0.0


def test_predict_unknown_station_returns_404():
    response = client.post(
        "/predict",
        json={"station_name": "NOPE_NOT_A_REAL_STATION", "timestamp": "2025-06-15T08:30:00"},
    )
    assert response.status_code == 404


def test_predict_bad_input_returns_422():
    # Missing required `station_name` -> pydantic validation error.
    response = client.post("/predict", json={"timestamp": "2025-06-15T08:30:00"})
    assert response.status_code == 422
