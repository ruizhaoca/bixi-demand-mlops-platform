"""HTTP client and bundle-compatible proxies for the FastAPI Streamlit UI."""

from __future__ import annotations

import datetime as dt
import os
from dataclasses import dataclass
from typing import Any, Mapping

import numpy as np
import pandas as pd
import requests


TARGET_LABELS = {"departure": "Departure", "arrival": "Arrival"}
DEFAULT_TIMEOUT = 30.0
NEUTRAL_WEATHER: dict[str, float] = {
    "temperature_2m": 18.0,
    "precipitation": 0.0,
    "wind_speed_10m": 10.0,
    "relative_humidity_2m": 60.0,
    "weather_code": 1.0,
}


class ApiClientError(RuntimeError):
    """A user-presentable FastAPI transport or response error."""


class ApiFeatureRow(dict):
    """Feature-row placeholder carrying the API request context out of band."""

    def __init__(
        self,
        station_name: str,
        timestamp: pd.Timestamp,
        target: str,
        weather: Mapping[str, float],
    ) -> None:
        super().__init__()
        self.station_name = station_name
        self.timestamp = pd.Timestamp(timestamp)
        self.target = target
        self.weather = {key: float(value) for key, value in weather.items()}

    def payload(self) -> dict[str, Any]:
        return {
            "station_name": self.station_name,
            "timestamp": self.timestamp.isoformat(),
            "target": self.target,
            "weather": self.weather,
        }


class FastApiClient:
    def __init__(
        self,
        base_url: str,
        *,
        api_key: str = "",
        timeout: float = DEFAULT_TIMEOUT,
        session: requests.Session | None = None,
    ) -> None:
        base_url = base_url.strip().rstrip("/")
        if not base_url:
            raise ValueError("BIXI_API_URL is required for the FastAPI Streamlit deployment.")
        self.base_url = base_url
        self.timeout = timeout
        self.session = session or requests.Session()
        if api_key:
            self.session.headers.update({"X-API-Key": api_key})

    @classmethod
    def from_env(cls) -> "FastApiClient":
        timeout = float(os.getenv("BIXI_API_TIMEOUT", str(DEFAULT_TIMEOUT)))
        return cls(
            os.getenv("BIXI_API_URL", ""),
            api_key=os.getenv("BIXI_API_KEY", ""),
            timeout=timeout,
        )

    def _request(self, method: str, path: str, **kwargs) -> Any:
        timeout = kwargs.pop("timeout", self.timeout)
        try:
            response = self.session.request(
                method,
                f"{self.base_url}{path}",
                timeout=timeout,
                **kwargs,
            )
        except requests.RequestException as exc:
            raise ApiClientError(f"FastAPI request failed: {exc}") from exc

        if not response.ok:
            try:
                detail = response.json().get("detail", response.text)
            except ValueError:
                detail = response.text
            raise ApiClientError(f"FastAPI returned HTTP {response.status_code}: {detail}")
        try:
            return response.json()
        except ValueError as exc:
            raise ApiClientError("FastAPI returned a non-JSON response.") from exc

    def health(self) -> dict[str, Any]:
        return self._request("GET", "/health")

    def stations(self) -> list[str]:
        return self._request("GET", "/stations")["stations"]

    def monitoring(self) -> dict[str, Any]:
        return self._request("GET", "/monitoring")

    def features(
        self,
        station_name: str,
        timestamp: pd.Timestamp,
        target: str,
        weather: Mapping[str, float] = NEUTRAL_WEATHER,
    ) -> dict[str, Any]:
        payload = ApiFeatureRow(station_name, timestamp, target, weather).payload()
        body = self._request("POST", "/features", json=payload)
        return body["engineered_features"][target]

    def predict(self, row: ApiFeatureRow) -> tuple[float, dict[str, Any]]:
        body = self._request("POST", "/predict", json=row.payload())
        return body["predictions"][row.target], body["engineered_features"][row.target]

    def predict_batch(self, rows: list[ApiFeatureRow]) -> list[tuple[float, dict[str, Any]]]:
        body = self._request(
            "POST",
            "/predict/batch",
            json={"requests": [row.payload() for row in rows]},
        )
        return [
            (result["predictions"][row.target], result["engineered_features"][row.target])
            for row, result in zip(rows, body["results"])
        ]

    def rebalancing(
        self,
        dayofweek: int,
        *,
        month: int = 6,
        station_name: str | None = None,
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        payload: dict[str, Any] = {"dayofweek": dayofweek, "month": month}
        if station_name is not None:
            payload["station_name"] = station_name
        body = self._request(
            "POST",
            "/rebalancing",
            json=payload,
            timeout=max(self.timeout, 180.0),
        )
        trajectory = pd.DataFrame.from_records(body["trajectory"])
        priorities = pd.DataFrame.from_records(body["priorities"])
        return trajectory, priorities


@dataclass
class ApiTargetBundle:
    """Minimal bundle interface expected by the existing Streamlit page code."""

    target: str
    client: FastApiClient
    station_names: tuple[str, ...]
    metadata: dict[str, Any]

    @property
    def label(self) -> str:
        return TARGET_LABELS[self.target]

    @property
    def stations(self) -> list[str]:
        return list(self.station_names)

    @property
    def metrics(self) -> dict:
        return self.metadata.get("metrics", {})

    @property
    def data_summary(self) -> dict:
        return self.metadata.get("data_summary", {})

    @property
    def tiers(self) -> dict:
        return self.metadata.get("tiers", {})

    @property
    def fairness_report(self) -> dict:
        return self.metadata.get("fairness_report", {})

    @property
    def drift_summary(self) -> dict:
        return self.metadata.get("drift_summary", {})

    @property
    def registered_model(self) -> dict:
        return self.metadata.get("registered_model", {})

    @property
    def shap_importance(self) -> pd.DataFrame:
        return pd.DataFrame.from_records(self.metadata.get("shap_importance", []))

    def get_baseline_row(self, station_name: str, timestamp: pd.Timestamp) -> dict[str, Any]:
        return self.client.features(station_name, timestamp, self.target)

    def build_feature_row(
        self,
        station_name: str,
        timestamp: pd.Timestamp,
        weather: Mapping[str, float],
    ) -> ApiFeatureRow:
        return ApiFeatureRow(station_name, timestamp, self.target, weather)

    def predict_one(self, row: dict) -> float:
        if not isinstance(row, ApiFeatureRow):
            raise TypeError("FastAPI predictions require an ApiFeatureRow.")
        prediction, features = self.client.predict(row)
        row.clear()
        row.update(features)
        return float(prediction)

    def predict_rows(self, rows: list[dict]) -> np.ndarray:
        if any(not isinstance(row, ApiFeatureRow) for row in rows):
            raise TypeError("FastAPI batch predictions require ApiFeatureRow values.")
        typed_rows = [row for row in rows if isinstance(row, ApiFeatureRow)]
        results = self.client.predict_batch(typed_rows)
        predictions = []
        for row, (prediction, features) in zip(typed_rows, results):
            row.clear()
            row.update(features)
            predictions.append(float(prediction))
        return np.asarray(predictions, dtype="float64")


def load_api_bundles(client: FastApiClient | None = None) -> dict[str, ApiTargetBundle]:
    client = client or FastApiClient.from_env()
    health = client.health()
    if health.get("status") != "ok":
        raise ApiClientError(f"FastAPI health check failed: {health}")
    stations = tuple(client.stations())
    monitoring = client.monitoring()
    return {
        target: ApiTargetBundle(target, client, stations, monitoring.get(target, {}))
        for target in TARGET_LABELS
    }


def common_stations(bundles: Mapping[str, ApiTargetBundle]) -> list[str]:
    station_sets = [set(bundle.stations) for bundle in bundles.values()]
    return sorted(set.intersection(*station_sets)) if station_sets else []


def slot_label(slot_of_day: int) -> str:
    hour = slot_of_day // 4
    minute = (slot_of_day % 4) * 15
    return f"{hour:02d}:{minute:02d}"


def timestamp_for(date_value: dt.date, slot_of_day: int) -> pd.Timestamp:
    return pd.Timestamp(date_value) + pd.Timedelta(minutes=15 * slot_of_day)
