# BIXI Demand MLOps Platform
**Local Streamlit demo:** https://bixidemandlocal.streamlit.app/

Cloud serving: AWS runtime resources have been removed; the reproducible deployment pipeline is retained in this repository.

---
<img width="4590" height="2581" alt="1" src="https://github.com/user-attachments/assets/6271a915-1e19-4b5e-870a-ef03cb6eb006" />

---
<img width="4843" height="2724" alt="2" src="https://github.com/user-attachments/assets/3629d6bf-80b5-4f2a-83b5-628707765b87" />

---
## Project Overview
Production-grade MLOps platform that forecasts **15-minute** bike-sharing demand for **every** BIXI station in Montreal (~1,100+ stations), separately for **departures** and **arrivals**, and serves the models through interactive Streamlit apps. The project implements a resumable, cloud-native pipeline with full experiment tracking, a model registry, explainability, fairness analysis, four-type drift monitoring, containerization, CI/CD, and AWS infrastructure-as-code.

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
  BixiStorage  S3 data + pipeline buckets + SSM parameters
  BixiMlflow   MLflow tracking server on EC2 + S3 artifact store
  BixiBatch    ECR training image + AWS Batch compute and job definition
  BixiServe    ECR API image + App Runner FastAPI + IAM + Secrets Manager API key
  BixiUi       EC2 Streamlit container + Elastic IP + SSM access

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
                          └── CDK data S3: raw, cleaned, features, serving baselines
```

The EC2 UI contains no model and has no direct S3 dependency. App Runner loads the Phase-2 bundles once at service startup and performs feature engineering, prediction, monitoring lookup, and rebalancing. Version A remains functional after AWS resources are removed because its artifacts are committed under `artifacts/`.

> **App Runner lifecycle note (2026):** this rebuild path requires an AWS account
> that already has App Runner access. For new customers, the same API container and
> HTTP contract can be deployed with ECS Express Mode instead.

```
ingest -> features -> serving -> data -> train -> explain -> fairness -> drift -> register
```

- `ingest` — download the raw BIXI trip archives + Open-Meteo weather and clean trips
  into 15-minute station demand tables (`bixi.ingest` + `bixi.demand_ingestion_cleaning`).
- `features` — build the leakage-safe feature tables (`bixi.feature_engineering`).
- `serving` — build compact future-inference baselines (`bixi.serving_baselines`).
- `data` — range-filter, leakage-safe station encoding, demand tiers (`bixi.data`).
- `train` — candidates + FLAML + Optuna, select best, log to MLflow (`bixi.models`).
- `explain` / `fairness` / `drift` — SHAP+LIME, error parity, Evidently 4-type drift.
- `register` — promote the best run to the `production` alias (`bixi.registry`).

The default run starts at `ingest` and reconstructs every cloud artifact from public
BIXI and Open-Meteo data. S3 success markers still support `--from` and `--only`
when resuming a partially completed run.

---

## Repository structure

```
├── src/bixi/                       # the pipeline package
│   ├── config.py                   # central config + data/feature contract + stages
│   ├── io.py                       # S3 + local I/O helpers (default boto3 chain)
│   ├── ingest.py                   # ingest stage: weather + trips + demand cleaning
│   ├── demand_ingestion_cleaning.py# raw trip download/extract -> 15-min demand CSVs
│   ├── feature_engineering.py      # features stage: leakage-safe feature tables
│   ├── serving_baselines.py       # serving stage: online baseline lookup
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
│   ├── app.py                      # BixiNetwork / Storage / MLflow / Batch / Serve / Ui
│   └── bixi_infra/                 # all CDK stack definitions
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

## Rebuild from an empty AWS environment

No existing bucket, feature table, model, API, or EC2 instance is required. The
pipeline reconstructs every cloud artifact from public BIXI and Open-Meteo data.

### Automated deployment (recommended)

From Windows PowerShell, the orchestrator bootstraps CDK, creates the rebuild
infrastructure, waits for the full Batch pipeline, and only then deploys App Runner
and the EC2 Streamlit UI:

```powershell
.\scripts\deploy_from_scratch.ps1 `
  -AwsProfile bixi `
  -Region us-east-2 `
  -MlflowAllowCidr "<your-public-ip>/32"
```

The EC2 bootstrap checks out `main` by default. Run this after the deployment code
has been merged to `main`.

### Manual AWS sequence

```bash
export AWS_PROFILE=bixi
export AWS_DEFAULT_REGION=us-east-2
export BIXI_ALLOW_CIDR=<your-public-ip>/32
export BIXI_RUN_ID=cloud-2024

aws sso login --profile "$AWS_PROFILE"
./scripts/deploy_infra.sh
./scripts/run_pipeline.sh
# Wait for the Batch job to reach SUCCEEDED.
BIXI_RUN_ID=cloud-2024 BIXI_REPO_REF=main ./scripts/deploy_serving.sh
```

The initial Batch run starts at `ingest` and continues through `register`. App
Runner and the EC2 UI are deliberately deployed only after Batch succeeds.

### Delete the rebuilt environment

```bash
export AWS_PROFILE=bixi
export AWS_DEFAULT_REGION=us-east-2
./scripts/teardown.sh
```

This deletes every BIXI stack and both CDK-managed buckets. The packaged Community
Cloud app remains available because its artifacts are committed to the repository.

---

## Results (selected model: LightGBM + Optuna, per split)

| Target | Split | R² | RMSE | MAE |
|--------|-------|----|------|-----|
| Departure | Validation (May 2025) | 0.327 | 0.994 | 0.565 |
| Departure | Test (Oct 2025) | 0.334 | 1.035 | 0.591 |
| Arrival | Validation (May 2025) | 0.339 | 0.976 | 0.554 |
| Arrival | Test (Oct 2025) | 0.339 | 1.026 | 0.585 |

Both targets select `lgbm_optuna`. SHAP attributes most signal to the 2024 historical baselines and the cyclical time-of-day features, with weather as a secondary driver.

---

## Streamlit apps

The Streamlit deployments offer: a multi-day demand forecast (Open-Meteo weather), a rebalancing-priorities page (net-flow map, ranked priority list, per-station occupancy trajectory), custom-input single predictions, and a model-monitoring page (SHAP, fairness, drift).

- **`app.py`** — Streamlit Community Cloud. Loads model artifacts committed under `artifacts/streamlit-community-cloud/cloud-2024/`; needs no AWS at runtime.
  ```bash
  pip install -r requirements.txt
  streamlit run app.py
  ```
- **`app_fastapi_ec2.py`** — API-backed EC2 deployment. The CDK-managed UI contains
  no model or S3 credentials; predictions, generated features, monitoring metadata,
  and rebalancing results come from App Runner. See
  [`docs/fastapi_streamlit_deployment_guide.md`](docs/fastapi_streamlit_deployment_guide.md).

---

## Prediction API (FastAPI · App Runner)

The cloud-serving backend is a thin **FastAPI** REST service (`api/main.py`) over the **same** model bundles as the Streamlit apps — `build_feature_row` + `predict_one`, no new ML logic, so predictions match across every surface. It is containerized via `docker/Dockerfile.api` and provisioned on **AWS App Runner** by the `BixiServe` CDK stack (`infra/bixi_infra/serve_stack.py`).

Serving mode is chosen at startup by `BIXI_SERVING_MODE`: `local` (default — the committed `artifacts/streamlit-community-cloud/cloud-2024/` bundle, no AWS) or `s3` (App Runner reads the bundle from S3 via the instance IAM role).

In the deployed cloud service, `/health` is public. Every data and prediction endpoint requires an `X-API-Key`; CDK creates the key in AWS Secrets Manager and
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

---

## Team

| Name | GitHub |
|------|--------|
| Othmane Zizi | [othmane-zizi-pro](https://github.com/othmane-zizi-pro) |
| Sarah Liu | [sarahliu-mma](https://github.com/sarahliu-mma) |
| Ruihe Zhang (Louis) | [Mudkipython](https://github.com/Mudkipython) |
| Rui Zhao | [ruizhaoca](https://github.com/ruizhaoca) |
