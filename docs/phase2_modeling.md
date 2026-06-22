# Phase 2 — Predictive Modeling, MLflow, Explainability, Fairness & Drift

Owner: **Othmane Zizi** (`othmane-zizi-pro`).

This phase turns the Phase-1 15-minute feature tables into a production-grade,
**fully cloud-deployable and resumable** modeling pipeline: multi-model + AutoML +
Bayesian HPO, MLflow tracking & registry, SHAP/LIME explainability, fairness
analysis, and 4-type drift — trained in the cloud on AWS Batch, all provisioned
with AWS CDK.

## 1. Pipeline (`src/bixi/`, `python -m bixi.pipeline`)

Stages, each checkpointed to S3 with a `_SUCCESS` marker so any run resumes from
any step:

```
ingest -> features -> serving -> data -> train -> explain -> fairness -> drift -> register
```

| Stage | What it does |
|---|---|
| `ingest` | Download public BIXI trips and Open-Meteo weather, then build cleaned 15-minute demand tables in the CDK data bucket. |
| `features` | Build leakage-safe train/validation/test feature tables. |
| `serving` | Build compact station/weekday/slot baselines for future online predictions. |
| `data` | load each split, **filter to its intended (year, month)** (hardens against the Phase-1 date spillover), fit **leakage-safe** station encodings on TRAIN only, persist encoder + tiers. |
| `train` | naive baseline → LightGBM (L2/Poisson/Tweedie) + XGBoost + HistGB candidates → **FLAML AutoML** → **Optuna** HPO; select best by validation RMSE; evaluate on test; log everything to MLflow. |
| `explain` | SHAP global (beeswarm/bar) + local (waterfall) + LIME; artifacts → S3. |
| `fairness` | prediction-error parity across demand tiers and geographic zones; disparity flags + mitigation notes. |
| `drift` | Evidently feature/target/prediction/concept drift, 2024 ref vs May & Oct 2025; HTML reports → S3. |
| `register` | register the best model in the MLflow Model Registry and set the `production` alias. |

Run the whole thing, or resume / run one step:

```bash
# whole pipeline, both targets, in the cloud (AWS Batch)
./scripts/run_pipeline.sh

# resume from training; re-run only drift
./scripts/run_pipeline.sh --run-id cloud-2024 --from train
./scripts/run_pipeline.sh --run-id cloud-2024 --only drift --force

# fast local subsample (identical code path)
python -m bixi.pipeline --from data --targets departure --run-id smoke \
  --local-dir ~/bixi_data --sample-stations 80 --n-trials 8 --flaml-budget 30
```

## 2. Modeling decisions

* **Two targets, one pipeline:** run per `departure` / `arrival` (operationally
  distinct — rebalancing cares about both).
* **Target = 15-minute `demand`** (zero-inflated counts) → we expose Poisson and
  Tweedie objectives alongside L2 and always clip predictions at 0. RMSE is the
  selection metric; we also report MAE, R² and Poisson deviance per split.
* **Splits (temporal, leakage-safe):** train = 2024, validation = May-2025,
  test = Oct-2025. 2025 baselines reference matching 2024 periods (Phase 1).
* **Advanced encoding:** high-cardinality `station_name` → frequency + smoothed
  target encoding, **fit on TRAIN only**; unseen stations fall back to global
  stats. `time_15min` is never a feature (ordering only).
* **Model selection:** a naive historical-average baseline, five candidate
  families, FLAML AutoML, and Optuna-tuned LightGBM all compete on validation
  RMSE; the winner is registered.

## 3. Responsible AI

* **Explainability:** SHAP (global + local) and LIME, saved as artifacts for the
  Streamlit Explainability page.
* **Fairness:** error parity (RMSE/MAE/R²/bias) across demand tiers (low/med/high)
  and geographic zones; disparity ratios are flagged with mitigation notes.

## 4. Drift — and an honest data caveat

All four drift types are computed (Evidently HTML + scipy KS flags). **But** BIXI
exposes trip history only to ~Apr-2026 and we use **2024 as the baseline for all
years** (2025/2026 historical-baseline features are derived from matching 2024
periods). That structurally limits how much engineered-feature drift can exist, so
drift here is an **analysis under known data constraints, with human review — not a
live monitor**. We deliberately do **not** ship a weekly cron (it cannot get fresh
labelled data). The concept-drift check flags an R² drop below threshold on new
labelled data.

## 5. Cloud architecture (all via AWS CDK, `infra/`)

| Stack | Resource |
|---|---|
| `BixiNetwork` | VPC, public subnets, **no NAT** (≈$0). |
| `BixiStorage` | CDK-managed data bucket plus pipeline/model artifact bucket. |
| `BixiMlflow` | MLflow tracking server on EC2 `t3.medium` + S3 artifact store, Elastic IP, SG locked to the team CIDR. |
| `BixiBatch` | ECR training image (built by CDK) + AWS Batch managed EC2 compute + job definition. |
| `BixiServe` | App Runner FastAPI, ECR image, read-only S3 IAM role, and Secrets Manager API key. |
| `BixiUi` | EC2 Streamlit container, Elastic IP, and Systems Manager access. |

Deploy from an empty account/region after merging to `main`:

```powershell
.\scripts\deploy_from_scratch.ps1 -AwsProfile bixi -Region us-east-2
```

The orchestrator deploys storage/training first, waits for Batch to succeed, and
then deploys App Runner and the EC2 UI. `./scripts/teardown.sh` destroys every BIXI
stack and both buckets. No pre-existing S3 data is required.

## 6. Known data issues flagged to Phase 1 (Rui)

Found while loading the feature tables (handled at load time; flagged for a clean
source fix — see `scripts/fix_misranged_features.py`):

* `2025_may_arrival_features` spans **May–Nov 2025** (not just May);
  `2025_oct_arrival_features` spans **Oct 2025–Jan 2026**. The departure files are
  correctly single-month. Month-filtered, arrivals match departures (totals within
  0.5%), so the data is correct — only the exported range is wrong.
* The 2024 files spill a few hours/days into 2025, and the 2024 grid appears to
  start at 05:00 (UTC-style) while the 2025 monthly files start 00:00 (local) —
  worth confirming the 2025 `hist_avg_demand` alignment to 2024 periods.
