"""No-network tests for the FastAPI-backed Streamlit client and proxies."""

from __future__ import annotations

import pandas as pd
import pytest

from bixi.fastapi_client import (
    ApiClientError,
    FastApiClient,
    load_api_bundles,
)


class FakeResponse:
    def __init__(self, body, status_code: int = 200):
        self._body = body
        self.status_code = status_code
        self.ok = status_code < 400
        self.text = str(body)

    def json(self):
        return self._body


class FakeSession:
    def __init__(self):
        self.headers = {}
        self.calls = []

    def request(self, method, url, timeout, **kwargs):
        path = "/" + url.split("/", 3)[-1]
        self.calls.append((method, path, kwargs))
        if path == "/health":
            return FakeResponse({"status": "ok", "mode": "s3", "targets": ["departure", "arrival"]})
        if path == "/stations":
            return FakeResponse({"stations": ["Station A", "Station B"]})
        if path == "/monitoring":
            payload = {
                "metrics": {"best_model": "LightGBM"},
                "data_summary": {},
                "tiers": {},
                "fairness_report": {},
                "drift_summary": {},
                "registered_model": {},
                "shap_importance": [],
            }
            return FakeResponse({"departure": payload, "arrival": payload})
        if path == "/features":
            request = kwargs["json"]
            return FakeResponse(
                {"engineered_features": {request["target"]: self._features(request)}}
            )
        if path == "/predict":
            request = kwargs["json"]
            return FakeResponse(self._prediction(request))
        if path == "/predict/batch":
            requests = kwargs["json"]["requests"]
            return FakeResponse({"results": [self._prediction(request) for request in requests]})
        if path == "/rebalancing":
            return FakeResponse({"priorities": [], "trajectory": [], "dayofweek": 1, "month": 6})
        return FakeResponse({"detail": "not found"}, status_code=404)

    @staticmethod
    def _features(request):
        return {
            "station_name": request["station_name"],
            "dayofweek": 1,
            "month": 6,
            "hist_avg_demand": 2.5,
            **request["weather"],
        }

    def _prediction(self, request):
        target = request["target"]
        return {
            "station_name": request["station_name"],
            "timestamp": request["timestamp"],
            "predictions": {target: 1.25},
            "engineered_features": {target: self._features(request)},
        }


def test_load_api_bundles_and_predict_one_mutates_feature_preview():
    session = FakeSession()
    client = FastApiClient("https://api.example", session=session)
    bundle = load_api_bundles(client)["departure"]
    row = bundle.build_feature_row(
        "Station A",
        pd.Timestamp("2026-06-21 08:30"),
        {
            "temperature_2m": 20,
            "precipitation": 0,
            "wind_speed_10m": 10,
            "relative_humidity_2m": 60,
            "weather_code": 1,
        },
    )
    prediction = bundle.predict_one(row)
    assert prediction == 1.25
    assert row["station_name"] == "Station A"
    assert row["hist_avg_demand"] == 2.5


def test_predict_rows_uses_one_batch_request():
    session = FakeSession()
    bundle = load_api_bundles(FastApiClient("https://api.example", session=session))["arrival"]
    rows = [
        bundle.build_feature_row(
            "Station A",
            pd.Timestamp("2026-06-21 08:30") + pd.Timedelta(minutes=15 * index),
            {
                "temperature_2m": 20,
                "precipitation": 0,
                "wind_speed_10m": 10,
                "relative_humidity_2m": 60,
                "weather_code": 1,
            },
        )
        for index in range(4)
    ]
    predictions = bundle.predict_rows(rows)
    batch_calls = [call for call in session.calls if call[1] == "/predict/batch"]
    assert predictions.tolist() == [1.25] * 4
    assert len(batch_calls) == 1
    assert len(batch_calls[0][2]["json"]["requests"]) == 4


def test_api_key_header_is_configured():
    session = FakeSession()
    FastApiClient("https://api.example", api_key="secret", session=session)
    assert session.headers["X-API-Key"] == "secret"


def test_http_error_becomes_api_client_error():
    class ErrorSession(FakeSession):
        def request(self, method, url, timeout, **kwargs):
            return FakeResponse({"detail": "service unavailable"}, status_code=503)

    client = FastApiClient("https://api.example", session=ErrorSession())
    with pytest.raises(ApiClientError, match="HTTP 503"):
        client.health()

