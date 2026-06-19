"""Unit tests for Phase-3 station clustering (synthetic data, no network).

These exercise the pure functions only (``build_station_profiles``,
``compare_and_select``, ``label_clusters``, ``cluster_drift``); the S3/MLflow
orchestration in ``run_clustering`` is not touched here.
"""

import numpy as np
import pandas as pd
import pytest

from bixi import cluster


def _make_demand(target: str, n_stations: int = 24, days: int = 10,
                 seed: int = 0) -> pd.DataFrame:
    """Synthetic cleaned 15-min demand table with three station archetypes.

    Shape differs from tests/test_bixi_pipeline.py's ``_make_df`` (that one builds
    feature tables; this one builds station/time/demand demand tables).
    """
    rng = np.random.default_rng(seed)
    times = pd.date_range("2024-06-03", periods=days * 96, freq="15min")  # starts Monday
    hours = times.hour
    rows = []
    for i in range(n_stations):
        archetype = i % 3            # 0: commuter-origin, 1: destination, 2: flat
        base = 0.5 + (i % 5) * 0.4
        for t, h in zip(times, hours):
            morning = h in cluster.MORNING_HOURS
            evening = h in cluster.EVENING_HOURS
            if target == "departure":
                lam = base * (3 if (archetype == 0 and morning)
                              else 2 if (archetype == 1 and evening) else 1)
            else:
                lam = base * (3 if (archetype == 1 and morning)
                              else 2 if (archetype == 0 and evening) else 1)
            d = rng.poisson(lam)
            if d > 0:
                rows.append((f"st{i}", t, 45.5 + i * 0.001, -73.5 - i * 0.001, float(d)))
    return pd.DataFrame(rows, columns=["station_name", "time_15min",
                                       "latitude", "longitude", "demand"])


@pytest.fixture(scope="module")
def profiles_2024():
    return cluster.build_station_profiles({
        "departure": _make_demand("departure", seed=1),
        "arrival": _make_demand("arrival", seed=2),
    })


def test_build_station_profiles_contract(profiles_2024):
    p = profiles_2024
    assert p["station_name"].is_unique
    assert len(p) == 24
    for col in cluster.PROFILE_FEATURES + ["dep_intensity", "arr_intensity",
                                           "latitude", "longitude", "station_name"]:
        assert col in p.columns
    assert p[cluster.PROFILE_FEATURES].isna().sum().sum() == 0


def test_compare_and_select_picks_valid_model(profiles_2024):
    cm = cluster.compare_and_select(profiles_2024)
    assert 2 <= cm.n_clusters <= 8
    assert cm.centroids.shape == (cm.n_clusters, len(cluster.PROFILE_FEATURES))
    assert len(cm.labels) == len(profiles_2024)
    assert np.isfinite(cm.scores["silhouette"])
    assert -1.0 <= cm.scores["silhouette"] <= 1.0
    assert cm.candidates  # every scorable candidate recorded


def test_label_clusters_contract(profiles_2024):
    cm = cluster.compare_and_select(profiles_2024)
    labels = cluster.label_clusters(profiles_2024, cm)
    assert len(labels) == len(profiles_2024)
    assert set(labels["demand_level"]).issubset({"low", "medium", "high"})
    assert set(labels["rebalancing_flag"]).issubset(
        {"departure-heavy", "arrival-heavy", "balanced"})
    assert labels["cluster_label"].str.len().gt(0).all()
    for col in ["station_name", "latitude", "longitude", "cluster", "cluster_label"]:
        assert col in labels.columns


def test_cluster_drift_keys_and_ranges(profiles_2024):
    cm = cluster.compare_and_select(profiles_2024)
    profiles_2025 = cluster.build_station_profiles({
        "departure": _make_demand("departure", seed=3),
        "arrival": _make_demand("arrival", seed=4),
    })
    drift = cluster.cluster_drift(profiles_2024, profiles_2025, cm, "2025_may")
    for key in ["period", "n_common_stations", "feature_psi", "feature_ks",
                "assignment_stability", "adjusted_rand_index",
                "centroid_drift_mean", "centroid_drift_max", "drift_flags"]:
        assert key in drift
    assert drift["n_common_stations"] == 24
    assert set(drift["feature_psi"]) == set(cluster.PROFILE_FEATURES)
    assert 0.0 <= drift["assignment_stability"] <= 1.0
