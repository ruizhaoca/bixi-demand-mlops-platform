# Phase 3 — Operational Station Clustering

Groups all BIXI stations into operational segments from their **departure + arrival**
15-minute demand profiles, so operations can reason about station *types* and
**rebalancing risk**. It is a **standalone, cross-target** capability (one model over
both targets), not a per-target pipeline stage, because rebalancing is inherently a
departure-vs-arrival comparison.

Module: [`src/bixi/cluster.py`](../src/bixi/cluster.py). Run:

```bash
python -m bixi.cluster --run-id cloud-2024            # against S3 (needs AWS creds)
python -m bixi.cluster --run-id dev --local-dir ~/bixi_data   # local CSVs
```

## Input

The lightweight cleaned 15-minute demand tables produced by the ingest stage —
`processed-data/{period}_{target}_demand_15min.csv` (`station_name, time_15min,
latitude, longitude, demand`) — **not** the heavy feature parquets. Station-level
aggregates are tiny, so the whole job runs locally in seconds.

## Station profile (clustering features)

Per station, the **mean demand per 15-minute slot** within each time-of-day bucket,
for each target:

| Bucket | Hours |
|--------|-------|
| morning rush | 06–09 |
| evening rush | 15–18 |
| other | the rest |

→ 6 features: `dep_morning, dep_evening, dep_other, arr_morning, arr_evening,
arr_other`, plus `dep_intensity` / `arr_intensity` (overall per-target means).
Features are standardized (`StandardScaler`) before clustering.

## Model comparison + automatic selection

Candidates: **K-Means**, **GaussianMixture**, **Agglomerative** (k = 2..8 each) and
**DBSCAN** (eps grid). Each is scored by:

- **silhouette** (primary, higher is better),
- **Davies-Bouldin** (lower is better),
- **Calinski-Harabasz** (higher is better).

The best is selected automatically (silhouette desc, tie-broken by Calinski-Harabasz
then Davies-Bouldin). Every scorable candidate is logged as a nested MLflow run under
experiment `bixi-station-clusters`; the selected algorithm, k and scores are logged on
the parent run.

## Operational labels

Each cluster is labelled:

- **demand level** — clusters ranked by mean total (dep+arr) intensity into
  low / medium / high.
- **rebalancing flag** — from the morning net flow (`dep_morning − arr_morning`):
  **departure-heavy** (commuter origin, empties in the morning), **arrival-heavy**
  (commuter destination, fills up), or **balanced**.

Output: `station_clusters.csv` (and `.parquet`) with `station_name, latitude,
longitude, cluster, cluster_label, demand_level, rebalancing_flag, dep_intensity,
arr_intensity` + the 6 profile features. A PCA 2-D projection (`pca_projection.csv`)
is also produced for visualization.

## Cluster feature-drift (2024 → 2025)

Rebuilds the station profiles for 2025 May and Oct and reports, per period:

- **input distribution shift** — PSI (flag > 0.2) and KS per profile feature,
- **cluster-assignment stability** — fraction of common stations that keep their
  cluster when assigned by the fitted 2024 model (+ Adjusted Rand Index vs a fresh
  2025 refit; flag < 0.8),
- **centroid drift** — mean / max centroid displacement (KMeans reference geometry,
  Hungarian-matched in standardized space).

Saved as `cluster_drift.json` + a `psi_drift.png` bar plot.

## Outputs (S3)

Under `s3://<pipeline-bucket>/bixi-mlops/runs/<run-id>/clustering/`:
`station_clusters.csv/.parquet`, `cluster_model.pkl`, `scaler.pkl`,
`cluster_summary.json`, `cluster_drift.json`, `pca_projection.csv`, `psi_drift.png`.

The Streamlit **Station Clusters** page renders the committed
`station_clusters.parquet` as a Plotly map colored by cluster, with a per-cluster
summary table. Package the artifacts for Community Cloud with
`scripts/download_streamlit_local_artifacts.py`.

## Tests

[`tests/test_bixi_cluster.py`](../tests/test_bixi_cluster.py) covers the pure
functions (profiles, selection, labels, drift) on synthetic data — no network.
