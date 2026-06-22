"""Unit tests for the Phase-2 modeling pipeline (synthetic data, no network)."""

import numpy as np
import pandas as pd
import pytest

from bixi import config, data, fairness, models, serving_baselines


def _make_df(year: int, month: int, n_stations: int = 8, slots: int = 200,
             seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    times = pd.date_range(f"{year}-{month:02d}-01", periods=slots, freq="15min")
    frames = []
    for i in range(n_stations):
        n = len(times)
        frames.append(pd.DataFrame({
            "station_name": f"st{i}",
            "time_15min": times,
            "latitude": 45.5 + i * 0.01,
            "longitude": -73.5 - i * 0.01,
            "demand": rng.poisson(0.5 + i * 0.1, n).astype(float),
            "dayofweek": times.dayofweek,
            "month": times.month,
            "slot_sin": np.sin(np.arange(n)),
            "slot_cos": np.cos(np.arange(n)),
            "hist_avg_demand": rng.random(n),
            "baseline_prev_15min": rng.random(n),
            "baseline_prev_1h": rng.random(n),
            "baseline_yesterday_same_slot": rng.random(n),
            "temperature_2m": rng.normal(15, 5, n),
            "precipitation": rng.random(n),
            "wind_speed_10m": rng.random(n) * 20,
            "relative_humidity_2m": rng.integers(30, 90, n),
            "weather_code": rng.integers(0, 5, n),
        }))
    return pd.concat(frames, ignore_index=True)


def test_split_spec_naming():
    s = config.split_specs("departure")
    assert s["train"].file_stem == "2024_departure_features"
    assert s["val"].months == (5,)
    with pytest.raises(ValueError):
        config.split_specs("nope")


def test_default_pipeline_is_a_full_rebuild():
    assert config.DEFAULT_STAGES == config.ALL_STAGES
    assert config.DEFAULT_STAGES[:3] == ["ingest", "features", "serving"]


def test_filter_to_range_drops_spillover():
    df = pd.concat([_make_df(2024, 12, slots=100), _make_df(2025, 1, slots=100)],
                   ignore_index=True)
    spec = config.SplitSpec("train", "x", 2024, None)
    out = data.filter_to_range(df, spec)
    assert (pd.to_datetime(out["time_15min"]).dt.year == 2024).all()
    assert len(out) < len(df)


def test_encoder_is_leakage_safe_and_no_nan():
    train = _make_df(2024, 6)
    enc = data.StationEncoder().fit(train)
    val = _make_df(2025, 5)
    val.loc[0, "station_name"] = "UNSEEN_STATION"
    out = enc.transform(val)
    assert out.loc[0, "station_target_enc"] == pytest.approx(enc.global_target)
    assert out.loc[0, "station_freq"] == 0.0
    assert out[config.ENCODED_COLS].isna().sum().sum() == 0


def test_prepare_xy_contract():
    train = _make_df(2024, 6)
    enc = data.StationEncoder().fit(train)
    tiers = data.fit_demand_tiers(train)
    X, y, meta = data.prepare_xy(train, enc, tiers)
    assert list(X.columns) == config.MODEL_FEATURES
    assert X.isna().sum().sum() == 0
    assert len(X) == len(y) == len(meta)
    assert "demand_tier" in meta.columns


def test_metrics_and_clip():
    y = np.array([0.0, 1.0, 2.0, 3.0])
    assert models.metrics(y, y)["rmse"] == pytest.approx(0.0)
    assert (models.clip_nonneg(np.array([-1.0, 2.0])) >= 0).all()


def test_fit_predict_and_fairness():
    train = _make_df(2024, 6)
    enc = data.StationEncoder().fit(train)
    tiers = data.fit_demand_tiers(train)
    X, y, meta = data.prepare_xy(train, enc, tiers)
    model, pred = models.fit_predict("lgbm_l2", X, y, X, params={"n_estimators": 30})
    assert len(pred) == len(y) and (pred >= 0).all()
    rep = fairness.fairness_report(meta, y, pred)
    assert "overall" in rep and "flags" in rep
    assert "by_demand_tier" in rep


def test_build_serving_baselines_has_online_contract():
    frame = _make_df(2024, 6, n_stations=2, slots=7 * 96 * 2)
    result = serving_baselines.build_serving_baselines(frame)
    expected = {
        "station_name",
        "dayofweek",
        "slot_of_day",
        "latitude",
        "longitude",
        "slot_sin",
        "slot_cos",
        "hist_avg_demand",
        "baseline_prev_15min",
        "baseline_prev_1h",
        "baseline_yesterday_same_slot",
    }
    assert set(result.columns) == expected
    assert result[list(expected - {"station_name"})].isna().sum().sum() == 0
    assert serving_baselines.serving_key("cloud-2024", "arrival") == (
        "bixi-serving-artifacts/cloud-2024/arrival/serving_baselines.parquet"
    )
