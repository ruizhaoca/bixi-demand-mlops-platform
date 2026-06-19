"""Inference contract for serving (Streamlit serving handoff).

Loads the trained model + the fitted station encoder and scores a feature frame.
Two load paths:
  * ``from_s3(run_id, target)``  — the pipeline checkpoint (best_model.pkl + encoder.pkl)
  * ``from_mlflow(target)``      — the MLflow ``production`` alias (+ encoder from S3)

The serving layer builds a DataFrame containing the Phase-1 raw feature columns
(``config.RAW_FEATURE_COLS``) plus ``station_name``, then calls ``predict_frame``;
the encoder adds the leakage-safe station encodings and the model scores it.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import config, io
from .data import StationEncoder
from .models import clip_nonneg


class DemandModel:
    def __init__(self, model, encoder: StationEncoder, meta: dict | None = None):
        self.model = model
        self.encoder = encoder
        self.meta = meta or {}

    @classmethod
    def from_s3(cls, run_id: str, target: str) -> "DemandModel":
        model = io.get_pickle(f"{config.stage_prefix(run_id, target, 'train')}/best_model.pkl")
        encoder = io.get_pickle(f"{config.stage_prefix(run_id, target, 'data')}/encoder.pkl")
        try:
            meta = io.get_json(f"{config.stage_prefix(run_id, target, 'train')}/metrics.json")
        except Exception:
            meta = {}
        return cls(model, encoder, meta)

    @classmethod
    def from_mlflow(cls, target: str, run_id: str) -> "DemandModel":
        import mlflow.sklearn

        from .registry import init_mlflow
        init_mlflow()
        model = mlflow.sklearn.load_model(
            f"models:/{config.registered_model_name(target)}@production")
        encoder = io.get_pickle(f"{config.stage_prefix(run_id, target, 'data')}/encoder.pkl")
        return cls(model, encoder)

    def predict_frame(self, df: pd.DataFrame) -> np.ndarray:
        """Score a frame with raw feature columns + ``station_name``."""
        enc = self.encoder.transform(df)
        X = enc[config.MODEL_FEATURES].astype("float32")
        return clip_nonneg(self.model.predict(X))

    def predict_one(self, features: dict) -> float:
        return float(self.predict_frame(pd.DataFrame([features]))[0])
