"""Tests for the FastAPI prediction service (local mode, no network).

Forces ``BIXI_SERVING_MODE=local`` so the app loads the committed artifact
bundle under ``artifacts/streamlit-community-cloud/cloud-2024/`` — no AWS, same
no-network style as the other ``tests/test_bixi_*`` suites.
"""

import os

os.environ.setdefault("BIXI_SERVING_MODE", "local")

import pytest
import pandas as pd
from fastapi.testclient import TestClient

import api.main as api_main
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
    assert set(body["engineered_features"]) == {"departure", "arrival"}
    assert body["engineered_features"]["departure"]["station_name"] == station


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


def test_features_returns_engineered_row_without_prediction():
    station = _first_station()
    response = client.post(
        "/features",
        json={
            "station_name": station,
            "timestamp": "2025-06-15T08:30:00",
            "target": "departure",
        },
    )
    assert response.status_code == 200
    row = response.json()["engineered_features"]["departure"]
    assert row["station_name"] == station
    assert row["dayofweek"] == 6
    assert "hist_avg_demand" in row


def test_batch_prediction_preserves_request_order():
    station = _first_station()
    response = client.post(
        "/predict/batch",
        json={
            "requests": [
                {
                    "station_name": station,
                    "timestamp": "2025-06-15T08:30:00",
                    "target": "departure",
                },
                {
                    "station_name": station,
                    "timestamp": "2025-06-15T08:45:00",
                    "target": "departure",
                },
            ]
        },
    )
    assert response.status_code == 200
    results = response.json()["results"]
    assert len(results) == 2
    assert results[0]["timestamp"].startswith("2025-06-15T08:30:00")
    assert results[1]["timestamp"].startswith("2025-06-15T08:45:00")


def test_monitoring_returns_streamlit_metadata():
    response = client.get("/monitoring")
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"departure", "arrival"}
    for payload in body.values():
        assert "metrics" in payload
        assert "fairness_report" in payload
        assert "drift_summary" in payload
        assert isinstance(payload["shap_importance"], list)


def test_rebalancing_returns_priorities_and_requested_trajectory(monkeypatch):
    netflow = pd.DataFrame(
        [
            {
                "station_name": "Station A",
                "slot_of_day": 0,
                "latitude": 45.5,
                "longitude": -73.5,
                "dep_pred": 1.0,
                "arr_pred": 2.0,
                "net_flow": 1.0,
            }
        ]
    )
    risk = pd.DataFrame(
        [
            {
                "priority": 1,
                "station_name": "Station A",
                "latitude": 45.5,
                "longitude": -73.5,
                "peak_deficit": 0.0,
                "deficit_slot": 0,
                "peak_surplus": 1.0,
                "surplus_slot": 0,
                "net_daily": 1.0,
                "throughput": 3.0,
                "risk_score": 1.0,
                "direction": "needs docks",
            }
        ]
    )
    monkeypatch.setattr(api_main, "_cached_rebalancing", lambda *args: (netflow, risk))
    response = client.post(
        "/rebalancing",
        json={"dayofweek": 1, "station_name": "Station A"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["priorities"][0]["station_name"] == "Station A"
    assert body["trajectory"][0]["net_flow"] == 1.0


def test_optional_api_key_protects_data_endpoints_but_not_health(monkeypatch):
    monkeypatch.setattr(api_main, "API_KEY", "demo-secret")
    assert client.get("/health").status_code == 200
    assert client.get("/stations").status_code == 401
    assert client.get("/stations", headers={"X-API-Key": "demo-secret"}).status_code == 200
