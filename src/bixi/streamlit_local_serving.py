"""Local packaged-artifact serving helpers for the Streamlit app.

This module is intentionally S3-free at prediction time. It loads the artifacts
committed under ``artifacts/streamlit-community-cloud`` so the app can run on
Streamlit Community Cloud after AWS resources are removed.
"""

from __future__ import annotations

import json
import pickle
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

import numpy as np
import pandas as pd

from . import config
from .data import StationEncoder  # noqa: F401  # required for encoder.pkl unpickling


TARGET_LABELS = {"departure": "Departure", "arrival": "Arrival"}
DEFAULT_RUN_ID = "cloud-2024"
DEFAULT_ARTIFACT_ROOT = Path("artifacts") / "streamlit-community-cloud" / DEFAULT_RUN_ID


@dataclass
class LocalTargetBundle:
    target: str
    root: Path
    model: object
    encoder: object
    baselines: pd.DataFrame
    baseline_lookup: pd.DataFrame
    metrics: dict
    data_summary: dict
    tiers: dict
    fairness_report: dict
    drift_summary: dict
    registered_model: dict
    shap_importance: pd.DataFrame

    @property
    def label(self) -> str:
        return TARGET_LABELS.get(self.target, self.target.title())

    @property
    def stations(self) -> list[str]:
        return sorted(self.baselines[config.STATION_COL].drop_duplicates().astype(str).tolist())

    def get_baseline_row(self, station_name: str, timestamp: pd.Timestamp) -> dict:
        slot_of_day = int(timestamp.hour * 4 + timestamp.minute // 15)
        dayofweek = int(timestamp.dayofweek)
        key = (station_name, dayofweek, slot_of_day)
        try:
            row = self.baseline_lookup.loc[key]
        except KeyError as exc:
            raise KeyError(
                f"No 2024 serving baseline for station={station_name!r}, "
                f"dayofweek={dayofweek}, slot_of_day={slot_of_day}."
            ) from exc
        if isinstance(row, pd.DataFrame):
            row = row.iloc[0]
        return {
            config.STATION_COL: station_name,
            "latitude": float(row["latitude"]),
            "longitude": float(row["longitude"]),
            "dayofweek": dayofweek,
            "month": int(timestamp.month),
            "slot_sin": float(row["slot_sin"]),
            "slot_cos": float(row["slot_cos"]),
            "hist_avg_demand": float(row["hist_avg_demand"]),
            "baseline_prev_15min": float(row["baseline_prev_15min"]),
            "baseline_prev_1h": float(row["baseline_prev_1h"]),
            "baseline_yesterday_same_slot": float(row["baseline_yesterday_same_slot"]),
        }

    def build_feature_row(
        self,
        station_name: str,
        timestamp: pd.Timestamp,
        weather: Mapping[str, float],
    ) -> dict:
        row = self.get_baseline_row(station_name, timestamp)
        row.update(
            {
                "temperature_2m": float(weather["temperature_2m"]),
                "precipitation": float(weather["precipitation"]),
                "wind_speed_10m": float(weather["wind_speed_10m"]),
                "relative_humidity_2m": float(weather["relative_humidity_2m"]),
                "weather_code": float(weather["weather_code"]),
            }
        )
        return row

    def predict_rows(self, rows: list[dict]) -> np.ndarray:
        frame = pd.DataFrame(rows)
        encoded = self.encoder.transform(frame)
        x = encoded[config.MODEL_FEATURES].astype("float32")
        pred = np.asarray(self.model.predict(x), dtype="float64")
        return np.clip(pred, 0.0, None)

    def predict_one(self, row: dict) -> float:
        return float(self.predict_rows([row])[0])


def _read_json(path: Path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _load_pickle(path: Path):
    with path.open("rb") as file:
        return pickle.load(file)


def _load_shap_importance(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=["feature", "mean_abs_shap"])
    return pd.read_csv(path)


def load_target_bundle(artifact_root: str | Path, target: str) -> LocalTargetBundle:
    root = Path(artifact_root) / target
    model = _load_pickle(root / "train" / "best_model.pkl")
    encoder = _load_pickle(root / "data" / "encoder.pkl")
    baselines = pd.read_parquet(root / "data" / "serving_baselines.parquet")
    baseline_lookup = baselines.set_index([config.STATION_COL, "dayofweek", "slot_of_day"]).sort_index()
    return LocalTargetBundle(
        target=target,
        root=root,
        model=model,
        encoder=encoder,
        baselines=baselines,
        baseline_lookup=baseline_lookup,
        metrics=_read_json(root / "metadata" / "metrics.json", {}),
        data_summary=_read_json(root / "metadata" / "data_summary.json", {}),
        tiers=_read_json(root / "metadata" / "tiers.json", {}),
        fairness_report=_read_json(root / "monitoring" / "fairness_report.json", {}),
        drift_summary=_read_json(root / "monitoring" / "drift_summary.json", {}),
        registered_model=_read_json(root / "metadata" / "registered_model.json", {}),
        shap_importance=_load_shap_importance(root / "monitoring" / "shap_importance.csv"),
    )


def load_local_bundles(artifact_root: str | Path = DEFAULT_ARTIFACT_ROOT) -> dict[str, LocalTargetBundle]:
    artifact_root = Path(artifact_root)
    return {target: load_target_bundle(artifact_root, target) for target in config.TARGETS}


def common_stations(bundles: Mapping[str, LocalTargetBundle]) -> list[str]:
    station_sets = [set(bundle.stations) for bundle in bundles.values()]
    if not station_sets:
        return []
    return sorted(set.intersection(*station_sets))


def slot_label(slot_of_day: int) -> str:
    hour = slot_of_day // 4
    minute = (slot_of_day % 4) * 15
    return f"{hour:02d}:{minute:02d}"


def timestamp_for(date_value, slot_of_day: int) -> pd.Timestamp:
    hour = slot_of_day // 4
    minute = (slot_of_day % 4) * 15
    return pd.Timestamp(
        year=date_value.year,
        month=date_value.month,
        day=date_value.day,
        hour=hour,
        minute=minute,
    )
