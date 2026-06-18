# Presentation assets (Phase 2)

Captured from the live MLflow 2.x UI and the pipeline's S3 artifacts (run `cloud-2024`).

| file | what it shows |
|---|---|
| `mlflow_departure_runs.png` | MLflow experiment `bixi-demand-departure` — 73 runs (candidates + FLAML + Optuna) |
| `mlflow_arrival_runs.png` | MLflow experiment `bixi-demand-arrival` — 57 runs |
| `mlflow_run_detail_departure.png` | a training run's params + metrics |
| `mlflow_model_registry.png` | Model Registry — both models registered |
| `mlflow_model_departure.png` | `bixi-demand-departure` v1 with the `@ production` alias |
| `drift_feature_departure_oct.png` | Evidently feature-drift dashboard (Oct-2025 vs 2024) |
| `drift_concept_departure_oct.png` | Evidently regression-quality (concept) dashboard |
| `shap_beeswarm_departure.png` / `shap_beeswarm_arrival.png` | SHAP global feature importance |
| `ec2_streamlit_container_running.png` | EC2 Docker container running the Streamlit app on port 8501 |

Full set of SHAP/LIME/drift artifacts + metrics: see the S3 layout in the root `README.md`.
