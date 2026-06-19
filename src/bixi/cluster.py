"""Operational station clustering (Phase 3) — cross-target.

Groups all BIXI stations by their **departure + arrival** demand profile across the
day, so operations can reason about station *types* and **rebalancing risk**
(commuter-origin "departure-heavy" vs commuter-destination "arrival-heavy"
stations). It is deliberately a **standalone, cross-target** capability (one model
over both targets) rather than a per-target pipeline stage, because rebalancing is
inherently a departure-vs-arrival comparison.

What it does
------------
1. **Profiles** — per station, mean demand per 15-min slot within time-of-day
   buckets (morning rush, evening rush, other) for each of {departure, arrival}.
2. **Model comparison + auto-select** — K-Means, GaussianMixture, Agglomerative
   (k = 2..8) and DBSCAN (eps grid), scored by silhouette (primary),
   Davies-Bouldin and Calinski-Harabasz; the best is selected automatically.
3. **Operational labels** — each cluster is labelled by demand level (low/medium/
   high) and rebalancing tendency, and written to ``station_clusters.csv``.
4. **Cluster feature-drift** — 2024 vs 2025 (May/Oct): per-feature input shift
   (PSI + KS), cluster-assignment stability (+ Adjusted Rand Index), and centroid
   drift.

Inputs are the lightweight cleaned 15-minute demand tables
(``<DATA_PREFIX>/{period}_{target}_demand_15min.csv``) produced by the ingest
stage — not the heavy feature parquets — so this runs locally in seconds.

The clustering/scoring/drift logic is split into **pure, S3-free functions**
(``build_station_profiles``, ``compare_and_select``, ``label_clusters``,
``cluster_drift``) that are unit-tested on in-memory frames; only ``main`` /
``run_clustering`` touch S3 and MLflow.

Run::

    python -m bixi.cluster --run-id cloud-2024            # against S3 (needs creds)
    python -m bixi.cluster --run-id dev --local-dir ~/bixi_data
"""

from __future__ import annotations

import argparse
import io as _io
import os
import tempfile
import time
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from . import config, io
from .feature_engineering import demand_key

# Time-of-day buckets (local Montreal hour from the cleaned demand timestamps).
MORNING_HOURS = (6, 7, 8, 9)
EVENING_HOURS = (15, 16, 17, 18)
BUCKETS = ("morning", "evening", "other")

# The clustering feature space: mean demand per 15-min slot in each bucket, per target.
PROFILE_FEATURES = [f"{p}_{b}" for p in ("dep", "arr") for b in BUCKETS]

# Periods (year_label used in the demand-table keys).
TRAIN_PERIOD = "2024"
EVAL_PERIODS = ("2025_may", "2025_oct")

K_RANGE = range(2, 9)
DBSCAN_EPS = (0.5, 0.8, 1.0, 1.5, 2.0)
RANDOM_STATE = 42


def log(message: str) -> None:
    print(message, flush=True)


# --------------------------------------------------------------------------- #
# 1. Station profiles  (pure)
# --------------------------------------------------------------------------- #
def _bucket_of(hour: pd.Series) -> np.ndarray:
    return np.where(hour.isin(MORNING_HOURS), "morning",
                    np.where(hour.isin(EVENING_HOURS), "evening", "other"))


def _target_profile(df: pd.DataFrame, prefix: str) -> pd.DataFrame:
    """Per-station mean demand per 15-min slot within each time bucket, plus the
    station's overall mean demand (``<prefix>_intensity``). No geo here."""
    d = df.copy()
    hour = pd.to_datetime(d["time_15min"]).dt.hour
    d["bucket"] = _bucket_of(hour)
    grid = (
        d.groupby(["station_name", "bucket"])["demand"].mean()
        .unstack("bucket")
        .reindex(columns=list(BUCKETS))
        .fillna(0.0)
    )
    grid.columns = [f"{prefix}_{c}" for c in grid.columns]
    grid[f"{prefix}_intensity"] = d.groupby("station_name")["demand"].mean()
    return grid


def build_station_profiles(demand_by_target: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Build the per-station clustering matrix from cleaned demand tables.

    ``demand_by_target`` maps ``"departure"``/``"arrival"`` to a frame with columns
    ``station_name, time_15min, latitude, longitude, demand``. Returns one row per
    station with ``PROFILE_FEATURES`` + ``dep_intensity``/``arr_intensity`` +
    ``latitude``/``longitude`` + ``station_name`` (stations missing in one target
    get 0 there, so the outer set of stations is preserved).
    """
    dep = _target_profile(demand_by_target["departure"], "dep")
    arr = _target_profile(demand_by_target["arrival"], "arr")
    prof = dep.join(arr, how="outer").fillna(0.0)

    geo = (
        pd.concat([demand_by_target["departure"], demand_by_target["arrival"]])
        .groupby("station_name")[["latitude", "longitude"]].first()
    )
    prof = prof.join(geo, how="left")
    prof[["latitude", "longitude"]] = prof[["latitude", "longitude"]].fillna(0.0)
    return prof.reset_index()


# --------------------------------------------------------------------------- #
# 2. Model comparison + auto-select  (pure)
# --------------------------------------------------------------------------- #
@dataclass
class ClusterModel:
    algorithm: str
    n_clusters: int
    scaler: object
    centroids: np.ndarray          # (k, d) in standardized space
    cluster_ids: list              # cluster id per centroid row (sorted)
    feature_cols: list
    labels: np.ndarray             # label per profile row (fit order)
    scores: dict                   # selected silhouette / davies_bouldin / calinski_harabasz
    model: object = None           # fitted estimator (for pickling), best-effort
    candidates: list = field(default_factory=list)


def _internal_scores(X: np.ndarray, labels: np.ndarray) -> dict | None:
    """silhouette / Davies-Bouldin / Calinski-Harabasz, or None if not scorable."""
    from sklearn.metrics import (calinski_harabasz_score, davies_bouldin_score,
                                 silhouette_score)

    mask = labels != -1  # drop DBSCAN noise
    uniq = np.unique(labels[mask])
    if len(uniq) < 2 or len(uniq) >= mask.sum():
        return None
    Xm, lm = X[mask], labels[mask]
    return {
        "silhouette": float(silhouette_score(Xm, lm)),
        "davies_bouldin": float(davies_bouldin_score(Xm, lm)),
        "calinski_harabasz": float(calinski_harabasz_score(Xm, lm)),
    }


def _centroids(X: np.ndarray, labels: np.ndarray) -> tuple[np.ndarray, list]:
    ids = sorted(int(c) for c in np.unique(labels) if c != -1)
    cents = np.vstack([X[labels == c].mean(axis=0) for c in ids])
    return cents, ids


def _candidate_models():
    """Yield (algorithm, k, eps, estimator) candidates."""
    from sklearn.cluster import DBSCAN, AgglomerativeClustering, KMeans
    from sklearn.mixture import GaussianMixture

    for k in K_RANGE:
        yield "kmeans", k, None, KMeans(n_clusters=k, n_init=10, random_state=RANDOM_STATE)
        yield "gmm", k, None, GaussianMixture(n_components=k, random_state=RANDOM_STATE)
        yield "agglomerative", k, None, AgglomerativeClustering(n_clusters=k)
    for eps in DBSCAN_EPS:
        yield "dbscan", None, eps, DBSCAN(eps=eps, min_samples=5)


def compare_and_select(profiles: pd.DataFrame, feature_cols: list[str] | None = None) -> ClusterModel:
    """Fit every candidate, score it, and auto-select the best.

    Selection ranks by silhouette (desc), tie-broken by Calinski-Harabasz (desc)
    then Davies-Bouldin (asc).
    """
    from sklearn.preprocessing import StandardScaler

    feature_cols = feature_cols or PROFILE_FEATURES
    scaler = StandardScaler()
    X = scaler.fit_transform(profiles[feature_cols].to_numpy(dtype="float64"))

    candidates: list[dict] = []
    fitted: dict[int, tuple] = {}
    for algorithm, k, eps, est in _candidate_models():
        try:
            labels = est.fit_predict(X) if hasattr(est, "fit_predict") else est.fit(X).predict(X)
        except Exception as e:  # pragma: no cover - defensive
            log(f"  [cluster] {algorithm} k={k} eps={eps} skipped: {e}")
            continue
        scores = _internal_scores(X, np.asarray(labels))
        if scores is None:
            continue
        n_clusters = len(set(int(c) for c in labels if c != -1))
        rec = {"algorithm": algorithm, "k": k, "eps": eps, "n_clusters": n_clusters, **scores}
        idx = len(candidates)
        candidates.append(rec)
        fitted[idx] = (est, np.asarray(labels))

    if not candidates:
        raise RuntimeError("No clustering candidate produced >=2 scorable clusters.")

    best_idx = max(range(len(candidates)), key=lambda i: (
        candidates[i]["silhouette"], candidates[i]["calinski_harabasz"],
        -candidates[i]["davies_bouldin"]))
    best, (best_est, best_labels) = candidates[best_idx], fitted[best_idx]
    cents, ids = _centroids(X, best_labels)

    log(f"[cluster] selected {best['algorithm']} (k={best['n_clusters']}) "
        f"silhouette={best['silhouette']:.3f} db={best['davies_bouldin']:.3f} "
        f"ch={best['calinski_harabasz']:.0f}")
    return ClusterModel(
        algorithm=best["algorithm"], n_clusters=best["n_clusters"], scaler=scaler,
        centroids=cents, cluster_ids=ids, feature_cols=list(feature_cols),
        labels=best_labels,
        scores={k: best[k] for k in ("silhouette", "davies_bouldin", "calinski_harabasz")},
        model=best_est, candidates=candidates)


def _assign_nearest(X: np.ndarray, centroids: np.ndarray, cluster_ids: list) -> np.ndarray:
    """Assign each row to the nearest centroid; returns cluster ids."""
    d = np.linalg.norm(X[:, None, :] - centroids[None, :, :], axis=2)
    return np.asarray(cluster_ids)[d.argmin(axis=1)]


# --------------------------------------------------------------------------- #
# 3. Operational labelling  (pure)
# --------------------------------------------------------------------------- #
_DEMAND_LEVELS = ["low", "medium", "high"]


def label_clusters(profiles: pd.DataFrame, cm: ClusterModel,
                   rebalance_ratio: float = 0.15) -> pd.DataFrame:
    """Attach cluster id + operational labels to each station.

    ``demand_level`` ranks clusters by total (dep+arr) intensity into low/medium/
    high; ``rebalancing_flag`` compares morning departures vs arrivals per cluster.
    """
    out = profiles.copy()
    out["cluster"] = cm.labels
    out["total_intensity"] = out["dep_intensity"] + out["arr_intensity"]

    grp = out.groupby("cluster")
    cl_intensity = grp["total_intensity"].mean().sort_values()
    # rank clusters into 3 demand levels by their mean total intensity
    order = list(cl_intensity.index)
    level_map = {}
    n = len(order)
    for rank, cid in enumerate(order):
        level_map[cid] = _DEMAND_LEVELS[min(rank * 3 // max(n, 1), 2)]

    net_morning = grp.apply(
        lambda g: (g["dep_morning"].mean() - g["arr_morning"].mean())
        / (g["dep_morning"].mean() + g["arr_morning"].mean() + 1e-9),
        include_groups=False,
    )

    def _flag(cid: int) -> str:
        r = float(net_morning.loc[cid])
        if r > rebalance_ratio:
            return "departure-heavy"
        if r < -rebalance_ratio:
            return "arrival-heavy"
        return "balanced"

    out["demand_level"] = out["cluster"].map(level_map)
    out["rebalancing_flag"] = out["cluster"].map({c: _flag(c) for c in order})
    out["cluster_label"] = out["demand_level"].str.capitalize() + " demand · " + out["rebalancing_flag"]

    cols = (["station_name", "latitude", "longitude", "cluster", "cluster_label",
             "demand_level", "rebalancing_flag", "dep_intensity", "arr_intensity"]
            + PROFILE_FEATURES)
    return out[cols]


# --------------------------------------------------------------------------- #
# 4. Cluster feature-drift  (pure)
# --------------------------------------------------------------------------- #
def _psi(ref: np.ndarray, cur: np.ndarray, bins: int = 10) -> float:
    edges = np.unique(np.quantile(np.asarray(ref, float), np.linspace(0, 1, bins + 1)))
    if len(edges) < 3:
        return 0.0
    edges[0], edges[-1] = -np.inf, np.inf
    ref_pct = np.histogram(ref, edges)[0].astype(float)
    cur_pct = np.histogram(cur, edges)[0].astype(float)
    ref_pct = np.clip(ref_pct / max(ref_pct.sum(), 1), 1e-6, None)
    cur_pct = np.clip(cur_pct / max(cur_pct.sum(), 1), 1e-6, None)
    return float(np.sum((cur_pct - ref_pct) * np.log(cur_pct / ref_pct)))


def cluster_drift(profiles_2024: pd.DataFrame, profiles_2025: pd.DataFrame,
                  cm: ClusterModel, period: str) -> dict:
    """Cluster feature-drift between the 2024 reference and a 2025 period.

    Reports per-feature input shift (PSI + KS), cluster-assignment stability
    (fraction of common stations keeping their cluster + Adjusted Rand Index), and
    centroid drift (mean/max displacement, KMeans reference geometry).
    """
    from scipy.stats import ks_2samp
    from scipy.optimize import linear_sum_assignment
    from sklearn.cluster import KMeans
    from sklearn.metrics import adjusted_rand_score

    fc = cm.feature_cols
    a = profiles_2024.set_index("station_name")
    b = profiles_2025.set_index("station_name")
    common = a.index.intersection(b.index)
    a, b = a.loc[common], b.loc[common]

    feature_psi = {f: _psi(a[f].to_numpy(), b[f].to_numpy()) for f in fc}
    feature_ks = {f: {"stat": float(ks_2samp(a[f], b[f]).statistic),
                      "pvalue": float(ks_2samp(a[f], b[f]).pvalue)} for f in fc}

    # assignment stability vs the fitted 2024 clustering
    labels_2024 = dict(zip(profiles_2024["station_name"], cm.labels))
    ref_labels = np.array([labels_2024[s] for s in common])
    cur_std = cm.scaler.transform(b[fc].to_numpy(dtype="float64"))
    cur_assigned = _assign_nearest(cur_std, cm.centroids, cm.cluster_ids)
    assignment_stability = float(np.mean(ref_labels == cur_assigned)) if len(common) else float("nan")

    # ARI between 2024 assignment and a fresh 2025 refit (same k)
    k = cm.n_clusters
    ref_std = cm.scaler.transform(a[fc].to_numpy(dtype="float64"))
    ari = float("nan")
    cent_mean = cent_max = float("nan")
    if len(common) > k:
        cur_refit = KMeans(n_clusters=k, n_init=10, random_state=RANDOM_STATE).fit(cur_std)
        ari = float(adjusted_rand_score(ref_labels, cur_refit.labels_))
        ref_refit = KMeans(n_clusters=k, n_init=10, random_state=RANDOM_STATE).fit(ref_std)
        cost = np.linalg.norm(ref_refit.cluster_centers_[:, None, :]
                              - cur_refit.cluster_centers_[None, :, :], axis=2)
        ri, ci = linear_sum_assignment(cost)
        matched = cost[ri, ci]
        cent_mean, cent_max = float(matched.mean()), float(matched.max())

    return {
        "period": period,
        "n_common_stations": int(len(common)),
        "feature_psi": feature_psi,
        "feature_ks": feature_ks,
        "assignment_stability": assignment_stability,
        "adjusted_rand_index": ari,
        "centroid_drift_mean": cent_mean,
        "centroid_drift_max": cent_max,
        "drift_flags": {
            "input_shift": bool(any(v > 0.2 for v in feature_psi.values())),  # PSI>0.2 = notable
            "unstable_assignment": bool(assignment_stability == assignment_stability
                                        and assignment_stability < 0.8),
        },
    }


# --------------------------------------------------------------------------- #
# I/O + orchestration  (S3 / MLflow / matplotlib)
# --------------------------------------------------------------------------- #
def load_demand_table(period: str, target: str, local_dir: str | None = None) -> pd.DataFrame:
    """Read a cleaned 15-minute demand table (local dir if present, else S3)."""
    cols = ["station_name", "time_15min", "latitude", "longitude", "demand"]
    if local_dir:
        path = os.path.join(local_dir, f"{period}_{target}_demand_15min.csv")
        if os.path.exists(path):
            return pd.read_csv(path, usecols=cols)
    key = demand_key(period, target)
    return pd.read_csv(_io.BytesIO(io.get_bytes(key, bucket=config.DATA_BUCKET)), usecols=cols)


def _profiles_for_period(period: str, local_dir: str | None) -> pd.DataFrame:
    return build_station_profiles(
        {t: load_demand_table(period, t, local_dir=local_dir) for t in config.TARGETS}
    )


def _psi_plot(drift: dict[str, dict], path: str) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    feats = PROFILE_FEATURES
    fig, ax = plt.subplots(figsize=(9, 4.5))
    width = 0.8 / max(len(drift), 1)
    for i, (period, d) in enumerate(drift.items()):
        vals = [d["feature_psi"][f] for f in feats]
        ax.bar(np.arange(len(feats)) + i * width, vals, width, label=period)
    ax.axhline(0.2, color="red", ls="--", lw=1, label="PSI=0.2")
    ax.set_xticks(np.arange(len(feats)) + width * (len(drift) - 1) / 2)
    ax.set_xticklabels(feats, rotation=30, ha="right")
    ax.set_ylabel("PSI (2024 -> period)")
    ax.set_title("Cluster feature-drift (input distribution shift)")
    ax.legend()
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


def run_clustering(run_id: str, local_dir: str | None = None, force: bool = False) -> dict:
    """End-to-end: profiles -> compare/select -> label -> drift -> persist + MLflow."""
    prefix = config.cluster_prefix(run_id)
    summary_key = f"{prefix}/cluster_summary.json"
    if not force and not local_dir and io.exists(summary_key):
        log(f"[cluster] {summary_key} already exists — skip (use --force to redo).")
        return io.get_json(summary_key)

    t0 = time.time()
    log("[cluster] building 2024 station profiles...")
    profiles_2024 = _profiles_for_period(TRAIN_PERIOD, local_dir)
    cm = compare_and_select(profiles_2024)
    clusters = label_clusters(profiles_2024, cm)

    log("[cluster] computing cluster feature-drift...")
    drift = {}
    for period in EVAL_PERIODS:
        try:
            drift[period] = cluster_drift(profiles_2024, _profiles_for_period(period, local_dir), cm, period)
        except Exception as e:  # a missing period shouldn't fail the whole run
            log(f"[cluster] drift for {period} skipped: {e}")

    # PCA 2D projection for visualization
    from sklearn.decomposition import PCA
    X = cm.scaler.transform(profiles_2024[cm.feature_cols].to_numpy(dtype="float64"))
    pcs = PCA(n_components=2, random_state=RANDOM_STATE).fit_transform(X)
    pca_df = pd.DataFrame({"station_name": profiles_2024["station_name"],
                           "pc1": pcs[:, 0], "pc2": pcs[:, 1], "cluster": cm.labels})

    summary = {
        "run_id": run_id,
        "algorithm": cm.algorithm,
        "n_clusters": cm.n_clusters,
        "n_stations": int(len(clusters)),
        "scores": cm.scores,
        "candidates": cm.candidates,
        "cluster_sizes": {str(k): int(v) for k, v in clusters["cluster"].value_counts().items()},
        "demand_levels": {k: int(v) for k, v in clusters["demand_level"].value_counts().items()},
        "rebalancing": {k: int(v) for k, v in clusters["rebalancing_flag"].value_counts().items()},
        "feature_cols": cm.feature_cols,
        "drift": drift,
        "seconds": round(time.time() - t0, 1),
    }

    _persist(run_id, prefix, clusters, pca_df, cm, summary, drift)
    log(f"[cluster] done in {summary['seconds']}s — {cm.n_clusters} clusters over "
        f"{summary['n_stations']} stations.")
    return summary


def _persist(run_id: str, prefix: str, clusters: pd.DataFrame, pca_df: pd.DataFrame,
             cm: ClusterModel, summary: dict, drift: dict) -> None:
    with tempfile.TemporaryDirectory() as d:
        csv_path = os.path.join(d, "station_clusters.csv")
        clusters.to_csv(csv_path, index=False)
        pca_path = os.path.join(d, "pca_projection.csv")
        pca_df.to_csv(pca_path, index=False)
        psi_path = os.path.join(d, "psi_drift.png")
        if drift:
            try:
                _psi_plot(drift, psi_path)
            except Exception as e:
                log(f"[cluster] PSI plot skipped: {e}")
                psi_path = None

        # S3 outputs
        io.upload_file(csv_path, f"{prefix}/station_clusters.csv")
        io.write_parquet_s3(f"{prefix}/station_clusters.parquet", clusters)
        io.upload_file(pca_path, f"{prefix}/pca_projection.csv")
        io.put_pickle(f"{prefix}/scaler.pkl", cm.scaler)
        io.put_pickle(f"{prefix}/cluster_model.pkl", cm.model)
        io.put_json(f"{prefix}/cluster_summary.json", summary)
        io.put_json(f"{prefix}/cluster_drift.json", drift)
        if psi_path and os.path.exists(psi_path):
            io.upload_file(psi_path, f"{prefix}/psi_drift.png")

        _log_mlflow(run_id, cm, summary, d)


def _log_mlflow(run_id: str, cm: ClusterModel, summary: dict, artifact_dir: str) -> None:
    try:
        import mlflow

        from . import registry
        registry.init_mlflow()
        mlflow.set_experiment(config.CLUSTER_EXPERIMENT)
        with mlflow.start_run(run_name=f"clustering-{run_id}"):
            mlflow.set_tags({"run_id": run_id, "phase": "3-clustering", "scope": "cross-target"})
            for cand in cm.candidates:
                tag = cand["k"] if cand["k"] is not None else f"eps{cand['eps']}"
                with mlflow.start_run(run_name=f"{cand['algorithm']}-{tag}", nested=True):
                    mlflow.log_params({"algorithm": cand["algorithm"], "k": cand["k"],
                                       "eps": cand["eps"], "n_clusters": cand["n_clusters"]})
                    mlflow.log_metrics({m: float(cand[m]) for m in
                                        ("silhouette", "davies_bouldin", "calinski_harabasz")})
            mlflow.log_params({"selected_algorithm": cm.algorithm,
                               "selected_n_clusters": cm.n_clusters})
            mlflow.log_metrics({f"selected_{m}": float(v) for m, v in cm.scores.items()})
            mlflow.log_artifacts(artifact_dir)
    except Exception as e:  # MLflow must never block the artifact write
        log(f"[cluster] MLflow logging skipped: {e}")


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description="BIXI cross-target station clustering")
    ap.add_argument("--run-id", default="cloud-2024")
    ap.add_argument("--local-dir", help="dir with local *_demand_15min.csv (dev)")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args(argv)
    run_clustering(args.run_id, local_dir=args.local_dir, force=args.force)


if __name__ == "__main__":
    main()
