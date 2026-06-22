# BIXI Demand MLOps Platform

Production-grade MLOps platform that forecasts **15-minute** bike-sharing demand for
**every** BIXI station in Montreal (~1,100+ stations), separately for **departures**
and **arrivals**, and serves the models through interactive Streamlit apps. The
project turns a course-1 notebook prototype into a resumable, cloud-native pipeline
with full experiment tracking, a model registry, explainability, fairness analysis,
four-type drift monitoring, containerization, CI/CD, and AWS infrastructure-as-code.

**Deployment status**

- Local Streamlit deployment (Community Cloud, packaged artifacts): https://bixidemandlocal.streamlit.app/
- Cloud serving: AWS runtime resources have been removed; the reproducible deployment pipeline is retained in this repository.

---

## What the platform does

- **15-minute resolution** demand instead of hourly — 4× finer, far more useful for
  operational rebalancing.
- **Departures and arrivals predicted separately** through one shared pipeline run
  twice, surfacing rebalancing pressure (high-departure / low-arrival stations).
- **Net-flow rebalancing layer** that combines both forecasts into an operational
  priority list — which stations will run **empty (need bikes)** or **overflow
  (need docks)** over a representative weekday, ranked by severity.
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
- **Containerized** training and serving images, a **GitHub Actions** CI pipeline,
  and **AWS CDK** infrastructure (VPC, S3, MLflow on EC2, AWS Batch training,
  and FastAPI on App Runner).

---

## Architecture

```text
GitHub ──push──► GitHub Actions CI
                 ├── pytest
                 ├── build AWS Batch training image
                 ├── build App Runner FastAPI image
                 └── build EC2 Streamlit image + API contract smoke test

AWS training and model lifecycle (us-east-2, provisioned by CDK):
  BixiNetwork  VPC (public subnets, no NAT)
  BixiStorage  S3 pipeline bucket + SSM parameter
  BixiMlflow   MLflow tracking server on EC2 + S3 artifact store
  BixiBatch    ECR training image + AWS Batch compute and job definition
  BixiServe    ECR API image + App Runner FastAPI + IAM + Secrets Manager API key

Version A — long-term fallback:
  Browser -> Streamlit Community Cloud (app.py) -> packaged local artifacts

Version B — AWS cloud serving:
  Browser -> EC2 Elastic IP:8501
          -> Streamlit Docker container (app_fastapi_ec2.py)
              ├── Open-Meteo forecast API (cached for 24 hours)
              └── HTTPS + X-API-Key
                  -> App Runner FastAPI (api/main.py)
                      -> App Runner IAM role
                          ├── CDK pipeline S3: model, encoder, metrics, monitoring
                          └── insy684 S3: serving baseline parquet files
```

The EC2 UI contains no model and has no direct S3 dependency. App Runner loads the
Phase-2 bundles once at service startup and performs feature engineering, prediction,
monitoring lookup, and rebalancing. Version A remains functional after AWS resources
are removed because its artifacts are committed under `artifacts/`.

> **App Runner lifecycle note (2026):** this repository documents a service that was
> successfully deployed before teardown using an account with App Runner access. AWS
> no longer accepts new App Runner customers and recommends ECS Express Mode for new deployments. The API
> container and HTTP contract are portable to ECS without changing either model logic
> or the Streamlit client.

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
│   ├── explain.py                  # SHAP + LIME artifacts
│   ├── fairness.py                 # error-parity fairness report
│   ├── drift.py                    # Evidently 4-type drift reports
│   ├── registry.py                 # MLflow tracking + registry promotion
│   ├── inference.py                # load production model + predict contract
│   ├── rebalancing.py              # net-flow rebalancing priorities (dep+arr -> ranking)
│   ├── fastapi_client.py            # HTTP client + bundle proxies for the API-backed UI
│   ├── streamlit_local_serving.py  # local/packaged-artifact serving helpers
│   └── streamlit_s3_serving.py     # App Runner S3 model-bundle loader
├── app.py                          # Streamlit app (Community Cloud, packaged artifacts)
├── app_fastapi_ec2.py              # EC2 Streamlit UI backed only by FastAPI
├── api/main.py                     # FastAPI /predict service (App Runner serving tier)
├── artifacts/streamlit-community-cloud/cloud-2024/   # committed serving artifacts
├── docker/
│   ├── Dockerfile.train            # AWS Batch / local training & pipeline image
│   ├── Dockerfile.streamlit_fastapi # FastAPI-backed EC2 Streamlit image
│   └── Dockerfile.api              # FastAPI serving image (App Runner)
├── infra/                          # AWS CDK app
│   ├── app.py                      # BixiNetwork / BixiStorage / BixiMlflow / BixiBatch / BixiServe
│   └── bixi_infra/                 # network / storage / mlflow / batch / serve stacks
├── scripts/                        # deploy_infra.sh, run_pipeline.sh, teardown.sh, ...
├── docs/                           # design, deployment, monitoring, and AWS evidence
│   └── aws_deployment_evidence/    # archived, sanitized deployment screenshots
├── notebooks/02_modeling_drift.ipynb
├── tests/                          # pytest suite (synthetic data, no network)
├── requirements.txt                # Streamlit serving deps
├── requirements-streamlit-api.txt  # FastAPI-backed Streamlit UI deps
├── requirements-api.txt            # FastAPI serving deps
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
├── bixi-serving-artifacts/           # App Runner baselines (+ packaged fallback source)
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

## Rebalancing priorities

The departure and arrival forecasts are only operationally useful **together**. The
net-flow layer (`src/bixi/rebalancing.py`) combines them into a rebalancing plan: for
a representative weekday it computes `net_flow = arrival_pred − departure_pred` per
station per 15-minute slot, cumulates it across the day to a relative occupancy
trajectory, and reads each station's **peak deficit** (bikes needed / stockout risk)
and **peak surplus** (docks needed / overflow risk). Stations are ranked by severity
and tagged **needs bikes** or **needs docks** — a daily priority list for where a
rebalancing truck adds the most value. It is scored under a neutral weather vector
because net flow is robust to weather level (rain depresses departures and arrivals
together). Version A computes from committed bundles; Version B requests the same
calculation from FastAPI, using S3-backed bundles loaded by App Runner.

```bash
PYTHONPATH=src python -m bixi.rebalancing            # print the top-20 priorities (Tuesday)
PYTHONPATH=src python -m bixi.rebalancing --dayofweek 4 --top 30 --write-csv
```

The Streamlit **Rebalancing Priorities** page renders this as a pressure map (colored
by need, sized by risk), a ranked table, and a per-station occupancy trajectory.

**Limitation:** the trip data has no dock capacity or real-time occupancy, so the
trajectory starts from a common zero reference. This is a **relative** risk ranking
and priority order — not exact stockout clock-times or absolute fill levels. Design
details: [`docs/phase3_rebalancing.md`](docs/phase3_rebalancing.md).

---

## Streamlit apps

The Streamlit deployments offer: a multi-day demand forecast (Open-Meteo weather),
a **rebalancing-priorities** page (net-flow map, ranked priority list, per-station
occupancy trajectory), custom-input single predictions, and a model-monitoring page
(SHAP, fairness, drift).

- **`app.py`** — Streamlit Community Cloud. Loads model artifacts committed under
  `artifacts/streamlit-community-cloud/cloud-2024/`; needs no AWS at runtime.
  ```bash
  pip install -r requirements.txt
  streamlit run app.py
  ```
- **`app_fastapi_ec2.py`** — API-backed EC2 deployment. The UI loads no model or S3
  artifacts; predictions, generated features, monitoring metadata, and rebalancing
  results come from the App Runner FastAPI service. See
  [`docs/fastapi_streamlit_deployment_guide.md`](docs/fastapi_streamlit_deployment_guide.md).

---

## Prediction API (FastAPI · App Runner)

The cloud-serving backend is a thin **FastAPI** REST service (`api/main.py`) over the
**same** model bundles as the Streamlit apps — `build_feature_row` + `predict_one`,
no new ML logic, so predictions match across every surface. It is containerized via
`docker/Dockerfile.api` and provisioned on **AWS App Runner** by the `BixiServe` CDK
stack (`infra/bixi_infra/serve_stack.py`).

Serving mode is chosen at startup by `BIXI_SERVING_MODE`: `local` (default — the
committed `artifacts/streamlit-community-cloud/cloud-2024/` bundle, no AWS) or `s3`
(App Runner reads the bundle from S3 via the instance IAM role).

In the deployed cloud service, `/health` is public. Every data and prediction
endpoint requires an `X-API-Key`; CDK creates the key in AWS Secrets Manager and
injects it into App Runner without committing it to the repository.

```bash
pip install -r requirements-api.txt
uvicorn api.main:app --port 8000          # BIXI_SERVING_MODE=local by default
curl localhost:8000/health
curl -X POST localhost:8000/predict -H 'content-type: application/json' \
  -d '{"station_name": "Métro Mont-Royal (Utilités publiques / Rivard)",
       "timestamp": "2025-06-15T08:30:00", "target": "both"}'
```

| Method & path | Purpose |
|---|---|
| `GET /health` | Liveness (App Runner health check) — status, mode, targets |
| `GET /stations` | Station names available across both targets |
| `GET /info` | Per-target eval metrics + registered production model |
| `GET /monitoring` | Metrics, fairness, drift, registry, and SHAP metadata |
| `POST /features` | Engineered feature preview without scoring |
| `POST /predict` | Departure/arrival demand for a station at a timestamp (+ optional weather) |
| `POST /predict/batch` | Up to 192 predictions in one request (two full days) |
| `POST /rebalancing` | Ranked station risks and optional 96-slot station trajectory |

Unknown station/baseline → `404`; invalid body → `422` (pydantic). Deploy is the
gated step `cdk deploy BixiServe` (SSO creds) — see below.

---

## Docker

```bash
# Training / pipeline image (used by AWS Batch; runnable locally)
docker build -f docker/Dockerfile.train -t bixi-pipeline .
docker run --rm bixi-pipeline --help

# FastAPI-backed EC2 Streamlit UI
docker build -f docker/Dockerfile.streamlit_fastapi -t bixi-streamlit-fastapi .

# FastAPI prediction image (App Runner); runs local mode off the baked bundle
docker build -f docker/Dockerfile.api -t bixi-api .
docker run --rm -e BIXI_SERVING_MODE=local -p 8000:8000 bixi-api   # curl :8000/health
```

---

## Tests & CI

The serving and training images intentionally use separate dependency sets. For a
shared local test environment, install them in the same order as CI; the deployed
Docker images remain isolated and install only their own runtime requirements.

```bash
pip install -r requirements.txt
pip install -r requirements-streamlit-api.txt
pip install -r requirements-api.txt
pip install -r requirements-train.txt
pip install pytest
pytest -q tests/
```

GitHub Actions (`.github/workflows/ci.yml`) runs on pull requests to `main`, pushes,
and manual dispatch: it installs deps, runs the test suite, builds the training,
FastAPI-backed Streamlit and API images, then smoke-tests the
pipeline, API, and Streamlit-to-FastAPI contract without AWS.
Team guide: [`docs/github_actions_guide.md`](docs/github_actions_guide.md).

---

## Documentation

- Phase-2 modeling design & decisions: [`docs/phase2_modeling.md`](docs/phase2_modeling.md)
- Phase-3 net-flow rebalancing layer: [`docs/phase3_rebalancing.md`](docs/phase3_rebalancing.md)
- EC2 Streamlit + App Runner FastAPI deployment: [`docs/fastapi_streamlit_deployment_guide.md`](docs/fastapi_streamlit_deployment_guide.md)
- Archived AWS deployment screenshots: [`docs/aws_deployment_evidence/`](docs/aws_deployment_evidence/)
- GitHub Actions / CI: [`docs/github_actions_guide.md`](docs/github_actions_guide.md)

### Security

No AWS credentials are committed. Local infrastructure commands use IAM Identity
Center (SSO); AWS Batch and App Runner use service IAM roles. The EC2 Streamlit UI
does not access S3 and receives only the App Runner URL and API key at runtime.
`.env` and Streamlit secrets are git-ignored; `.env.example` is an empty template.

---

## Team

Repository: **bixi-demand-mlops-platform**

| Name | GitHub |
|------|--------|
| Othmane Zizi | [othmane-zizi-pro](https://github.com/othmane-zizi-pro) |
| Sarah Liu | [sarahliu-mma](https://github.com/sarahliu-mma) |
| Ruihe Zhang (Louis) | [Mudkipython](https://github.com/Mudkipython) |
| Rui Zhao | [ruizhaoca](https://github.com/ruizhaoca) |
