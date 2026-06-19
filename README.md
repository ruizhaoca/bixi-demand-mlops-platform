# BIXI Demand MLOps Platform

Production-grade MLOps platform that forecasts **15-minute** bike-sharing demand for
**every** BIXI station in Montreal (~1,100+ stations), separately for **departures**
and **arrivals**, and serves the models through interactive Streamlit apps. The
project turns a course-1 notebook prototype into a resumable, cloud-native pipeline
with full experiment tracking, a model registry, explainability, fairness analysis,
four-type drift monitoring, containerization, CI/CD, and AWS infrastructure-as-code.

**Live demos**

- Local Streamlit deployment (Community Cloud, packaged artifacts): https://bixidemandlocal.streamlit.app/
- EC2 Streamlit deployment (S3-backed artifacts): http://3.16.250.166:8501/

---

## What the platform does

- **15-minute resolution** demand instead of hourly — 4× finer, far more useful for
  operational rebalancing.
- **Departures and arrivals predicted separately** through one shared pipeline run
  twice, surfacing rebalancing pressure (high-departure / low-arrival stations).
- **All stations**, not just the busiest few.
- **Leakage-safe features**: temporal (cyclical 15-min slot, day-of-week, month),
  historical 2024 profile baselines built **leave-one-out** on the training rows,
  and merged 15-minute weather.
- **Advanced encoding** of the high-cardinality `station_name` (frequency + smoothed
  target encoding), **fit on train only**.
- **Multi-model selection**: LightGBM / XGBoost candidates **+ FLAML AutoML** search
  **+ Optuna** Bayesian HPO; the best model by validation RMSE is selected and
  promoted automatically.
- **MLflow** experiment tracking + Model Registry (`production` alias).
- **SHAP + LIME** explainability, **fairness** error-parity analysis across demand
  tiers and geography, and **Evidently** drift reports (feature / target /
  prediction / concept).
- **Operational station clustering** (cross-target): groups stations by their
  departure/arrival demand shape, auto-selecting among K-Means / GMM / Agglomerative /
  DBSCAN, and flags **rebalancing risk** (departure-heavy vs arrival-heavy) with a
  cluster feature-drift analysis.
- **Containerized** training and serving images, a **GitHub Actions** CI pipeline,
  and **AWS CDK** infrastructure (VPC, S3, MLflow on EC2, AWS Batch training).

---

## Architecture

```
GitHub ──push──► GitHub Actions CI  (pytest + build training & Streamlit images)

AWS (us-east-2), provisioned by AWS CDK (infra/):
  BixiNetwork  VPC (public subnets, no NAT)
  BixiStorage  S3 pipeline bucket (checkpoints / artifacts / reports) + SSM param
  BixiMlflow   MLflow tracking server on EC2 + S3 artifact store
  BixiBatch    ECR training image + AWS Batch compute + job definition

  AWS Batch runs `python -m bixi.pipeline` (docker/Dockerfile.train) over the full
  dataset, reading source data from s3://insy684 and writing checkpoints, models,
  explainability/fairness/drift artifacts to the CDK pipeline bucket; runs + models
  are tracked in MLflow.

Serving:
  app.py      Streamlit Community Cloud — committed artifacts (no AWS at runtime)
  app_ec2.py  EC2 Streamlit container — loads the same artifacts from S3
```

The pipeline is **staged and resumable**. Each stage writes a `_SUCCESS` marker to
`s3://<pipeline-bucket>/bixi-mlops/runs/<run-id>/<target>/<stage>/`, so a run can be
resumed from any step. The identical code runs locally on a station subsample and on
AWS Batch over the full dataset.

```
ingest -> features -> data -> train -> explain -> fairness -> drift -> register
```

- `ingest` — download the raw BIXI trip archives + Open-Meteo weather and clean trips
  into 15-minute station demand tables (`bixi.ingest` + `bixi.demand_ingestion_cleaning`).
- `features` — build the leakage-safe feature tables (`bixi.feature_engineering`).
- `data` — range-filter, leakage-safe station encoding, demand tiers (`bixi.data`).
- `train` — candidates + FLAML + Optuna, select best, log to MLflow (`bixi.models`).
- `explain` / `fairness` / `drift` — SHAP+LIME, error parity, Evidently 4-type drift.
- `register` — promote the best run to the `production` alias (`bixi.registry`).

`ingest` and `features` are the from-scratch rebuild stages; the **default run starts
at `data`** because the cleaned data and feature tables already live in S3.

---

## Repository structure

```
├── src/bixi/                       # the pipeline package
│   ├── config.py                   # central config + data/feature contract + stages
│   ├── io.py                       # S3 + local I/O helpers (default boto3 chain)
│   ├── ingest.py                   # ingest stage: weather + trips + demand cleaning
│   ├── demand_ingestion_cleaning.py# raw trip download/extract -> 15-min demand CSVs
│   ├── feature_engineering.py      # features stage: leakage-safe feature tables
│   ├── data.py                     # range filter, station encoding, demand tiers
│   ├── models.py                   # candidates, FLAML AutoML, Optuna HPO, metrics
│   ├── pipeline.py                 # resumable staged runner (python -m bixi.pipeline)
│   ├── cluster.py                  # cross-target station clustering (python -m bixi.cluster)
│   ├── explain.py                  # SHAP + LIME artifacts
│   ├── fairness.py                 # error-parity fairness report
│   ├── drift.py                    # Evidently 4-type drift reports
│   ├── registry.py                 # MLflow tracking + registry promotion
│   ├── inference.py                # load production model + predict contract
│   ├── streamlit_local_serving.py  # local/packaged-artifact serving helpers
│   └── streamlit_s3_serving.py     # S3-backed serving helpers (EC2)
├── app.py                          # Streamlit app (Community Cloud, packaged artifacts)
├── app_ec2.py                      # Streamlit entrypoint (EC2 + S3 artifacts)
├── artifacts/streamlit-community-cloud/cloud-2024/   # committed serving artifacts
├── docker/
│   ├── Dockerfile.train            # AWS Batch / local training & pipeline image
│   └── Dockerfile.streamlit_ec2    # EC2 Streamlit serving image
├── infra/                          # AWS CDK app
│   ├── app.py                      # BixiNetwork / BixiStorage / BixiMlflow / BixiBatch
│   └── bixi_infra/                 # network_stack / storage_stack / mlflow_stack / batch_stack
├── scripts/                        # deploy_infra.sh, run_pipeline.sh, teardown.sh, ...
├── docs/                           # design + ops guides (+ presentation assets)
├── notebooks/02_modeling_drift.ipynb
├── tests/                          # pytest suite (synthetic data, no network)
├── requirements.txt                # Streamlit serving deps
├── requirements-train.txt          # pipeline / training deps
└── runtime.txt                     # Python 3.12
```

---

## Where every asset lives (S3 + MLflow)

Two buckets. **`insy684`** is persistent (source data + backups, *not* CDK-managed).
The **CDK pipeline bucket** holds the pipeline outputs + MLflow artifacts and is
**deleted on `cdk destroy`** — `scripts/teardown.sh` backs it up to `insy684` first.
Its name is in SSM `/bixi/pipeline-bucket` and the `BixiStorage` CDK output.

```
s3://insy684/                         # PERSISTENT (source data + backups)
├── bixi-data/{2024,2025,2026}/       # raw BIXI open-data trip CSVs
├── weather-data/                     # 15-min Montreal weather (Open-Meteo)
├── processed-data/                   # 15-min demand CSVs + feature tables (parquet)
├── bixi-serving-artifacts/           # serving baselines for the Streamlit apps
└── bixi-mlops-backup/                # created by scripts/teardown.sh

s3://<CDK pipeline bucket>/           # EPHEMERAL (cloud run outputs)
├── bixi-mlops/runs/<run-id>/<target>/    # <target> = departure | arrival
│   ├── data/      encoder.pkl, tiers.json, data_summary.json
│   ├── train/     best_model.pkl, metrics.json  (R²/RMSE/MAE per split)
│   ├── explain/   shap_*.png/csv, lime_instance_*.html
│   ├── fairness/  fairness_report.json
│   ├── drift/     {feature,target,prediction}_drift_*.html, concept_*.html, drift_summary.json
│   └── register/  registered_model.json
├── mlflow/<experiment_id>/           # MLflow run artifacts
└── mlflow-bootstrap/                 # MLflow EC2 bootstrap logs (debug)
```

**MLflow** (CDK output `BixiMlflow.MlflowPublicUrl`): experiments
`bixi-demand-departure` / `bixi-demand-arrival` (every candidate + FLAML + Optuna
run); each best model registered with the **`production`** alias.

---

## Running the pipeline

### Full rebuild from scratch (one command)

Downloads + cleans raw trips, builds features, then trains/evaluates/monitors and
registers — for both targets:

```bash
python -m bixi.pipeline --from ingest --targets both --run-id rebuild
```

### Lean cloud run (data already in S3)

```bash
# default stages: data -> train -> explain -> fairness -> drift -> register
python -m bixi.pipeline --targets both --run-id cloud-2024 --n-trials 40
# resume a step:        --from train      |   re-run one stage:   --only drift --force
```

### On AWS Batch

```bash
BIXI_ALLOW_CIDR=<your-ip>/32 ./scripts/deploy_infra.sh   # provision infra (CDK)
./scripts/run_pipeline.sh --targets both --run-id cloud-2024   # submit Batch job
./scripts/teardown.sh                                     # backup + cdk destroy
```

### Fast local smoke test (station subsample, no Batch)

```bash
python -m bixi.pipeline --targets departure --run-id smoke \
    --local-dir ~/bixi_data --sample-stations 80 --n-trials 8 --flaml-budget 30
```

---

## Station clustering (cross-target)

A standalone capability that groups stations by their departure + arrival demand
profile across the day, auto-selects among K-Means / GMM / Agglomerative / DBSCAN
(silhouette / Davies-Bouldin / Calinski-Harabasz), labels each cluster by demand
level and **rebalancing risk** (departure-heavy vs arrival-heavy), and runs a cluster
feature-drift analysis. Outputs `station_clusters.csv` + an MLflow experiment
(`bixi-station-clusters`); surfaced on the Streamlit **Station Clusters** map page.

```bash
python -m bixi.cluster --run-id cloud-2024            # against S3 (needs AWS creds)
python -m bixi.cluster --run-id dev --local-dir ~/bixi_data   # local CSVs
```

Design & method: [`docs/phase3_clustering.md`](docs/phase3_clustering.md).

---

## Results (selected model: LightGBM + Optuna, per split)

15-minute slot-level demand is far noisier than hourly aggregates (many zero-demand
slots), so absolute R² is modest by design; errors are well under one trip per slot.

| Target | Split | R² | RMSE | MAE |
|--------|-------|----|------|-----|
| Departure | Validation (May 2025) | 0.327 | 0.994 | 0.565 |
| Departure | Test (Oct 2025) | 0.334 | 1.035 | 0.591 |
| Arrival | Validation (May 2025) | 0.339 | 0.976 | 0.554 |
| Arrival | Test (Oct 2025) | 0.339 | 1.026 | 0.585 |

Both targets select `lgbm_optuna`. SHAP attributes most signal to the 2024 historical
baselines and the cyclical time-of-day features, with weather as a secondary driver.

---

## Streamlit apps

Both apps share one UI and offer: a multi-day demand forecast (Open-Meteo weather),
custom-input single predictions, a **Station Clusters** map page (Plotly), and a
model-monitoring page (SHAP, fairness, drift).

- **`app.py`** — Streamlit Community Cloud. Loads model artifacts committed under
  `artifacts/streamlit-community-cloud/cloud-2024/`; needs no AWS at runtime.
  ```bash
  pip install -r requirements.txt
  streamlit run app.py
  ```
- **`app_ec2.py`** — EC2 deployment. Reuses `app.py`'s UI but loads the same Phase-2
  artifacts from S3. Containerized via `docker/Dockerfile.streamlit_ec2`; see
  [`docs/ec2_streamlit_deployment_guide.md`](docs/ec2_streamlit_deployment_guide.md).

---

## Docker

```bash
# Training / pipeline image (used by AWS Batch; runnable locally)
docker build -f docker/Dockerfile.train -t bixi-pipeline .
docker run --rm bixi-pipeline --help

# EC2 Streamlit serving image
docker build -f docker/Dockerfile.streamlit_ec2 -t bixi-streamlit .
```

---

## Tests & CI

```bash
pip install -r requirements-train.txt pytest
pytest -q tests/
```

GitHub Actions (`.github/workflows/ci.yml`) runs on pull requests to `main`, pushes,
and manual dispatch: it installs deps, runs the test suite, builds **both** Docker
images (training + Streamlit), and smoke-tests the pipeline image (`--help`, no AWS).
Team guide: [`docs/github_actions_guide.md`](docs/github_actions_guide.md).

---

## Documentation

- Phase-2 modeling design & decisions: [`docs/phase2_modeling.md`](docs/phase2_modeling.md)
- Phase-3 station clustering: [`docs/phase3_clustering.md`](docs/phase3_clustering.md)
- EC2 Streamlit deployment: [`docs/ec2_streamlit_deployment_guide.md`](docs/ec2_streamlit_deployment_guide.md)
- Model / S3 / EC2 operations: [`docs/model_s3_ec2_operations_guide.md`](docs/model_s3_ec2_operations_guide.md)
- GitHub Actions / CI: [`docs/github_actions_guide.md`](docs/github_actions_guide.md)

### Security

No AWS credentials are committed. Code uses the default boto3 credential chain — SSO
locally, an attached IAM role on EC2 / AWS Batch. `.env` is git-ignored; only
`.env.example` (a template) is tracked.

---

## Team

Repository: **bixi-demand-mlops-platform**

| Name | GitHub |
|------|--------|
| Othmane Zizi | [othmane-zizi-pro](https://github.com/othmane-zizi-pro) |
| Sarah Liu | [sarahliu-mma](https://github.com/sarahliu-mma) |
| Ruihe Zhang (Louis) | [Mudkipython](https://github.com/Mudkipython) |
| Rui Zhao | [ruizhaoca](https://github.com/ruizhaoca) |
