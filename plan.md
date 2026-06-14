# BIXI Demand MLOps Platform — Master Build Plan

> **Course:** INSY 695 — Enterprise Data Science & ML in Production II (McGill, Desautels)
> **Repo:** https://github.com/ruizhaoca/bixi-demand-mlops-platform
> **Live demo (current, course-1 version):** https://bixidashboard.streamlit.app/
> **Milestones:** Final presentation **June 19, 2026** · Final submission (MyCourses) **June 21, 2026**
> **Goal of this plan:** ship a production-grade MLOps platform that demonstrably touches **every** graded
> course topic, deployed to AWS via **infrastructure-as-code**, so the project earns a **100% grade**.

This plan **supersedes** the loose division in `INSY684 Group Project/Methodology Improvement & Labor
Division Plan.docx` and `BIXI_AWS_Fargate_Proposal.docx` wherever they conflict. Those documents remain
the source of the *technical* intent (15-minute granularity, departure/arrival split, all-stations,
Evidently drift, MLflow). This plan reorganizes the *work* into **one self-contained phase per teammate**,
each shipped as its own Pull Request, and pins deployment to **AWS CDK (IaC)** instead of manual console steps.

---

## 0. Team & ownership

| Phase | Owner | GitHub handle | Theme |
|------:|-------|---------------|-------|
| 1 | **Sarah Liu** | _confirm handle_ | Foundation & Data Engineering |
| 2 | **Othmane Zizi** | `othmane-zizi-pro` | Predictive Modeling · MLflow · AutoML · Responsible AI |
| 3 | **Ruihe Zhang** (a.k.a. Louis) | `mudkipython` | Clustering · Dimensionality Reduction · Drift Monitoring |
| 4 | **Rui Zhao** | `ruizhaoca` | Serving · Containerization · CI/CD · AWS IaC · Docs & Presentation |

> **Action item for the deck:** confirm Sarah's GitHub username. The final presentation must list every
> member's GitHub id (see §9), so this is a hard requirement, not a nicety.

**Why this division (vs. the docx):** the docx put Sarah+Louis jointly on data and Rui on *both* clustering
and the app. To satisfy "one phase per person" and keep PRs cleanly reviewable, we give Sarah the whole data
layer, hand the **unsupervised + monitoring** work (clustering, dimensionality reduction, drift) to Ruihe as
a single coherent phase, keep Othmane on the predictive model, and consolidate **serving + deployment +
docs** under Rui. Each phase is independently demoable and maps to a distinct cluster of course topics.

---

## 1. What we are building (the value-add)

The base repo is the **course-1 BIXI project**: three notebooks (cleaning/EDA/FE, K-Means clustering,
LightGBM training) plus a Streamlit app on Streamlit Community Cloud. It has **no MLOps**: no MLflow, no
Docker, no CI/CD, no tests, no model registry, no drift monitoring, no cloud IaC, no API. **That gap is
exactly the graded work for INSY 695-2 — we build all of it.**

On top of productionizing, we **improve the methodology** (these are graded "improvement" points):

1. **15-minute granularity** instead of hourly → 4× temporal resolution, far more operationally useful.
2. **Departure vs. arrival demand predicted separately** (one shared pipeline run twice) instead of a single
   conflated `total_demand`.
3. **All ~1,100+ stations** instead of only the top 400.
4. **Lagged + leakage-safe features** instead of naive historical means; explicit leakage analysis.
5. **Multi-model + AutoML selection** instead of a single hand-picked LightGBM.
6. Full **MLflow tracking + registry**, **Evidently drift (4 types)**, **SHAP explainability**,
   **fairness analysis**, **causal inference**, all wired into a **FastAPI + Streamlit** app deployed on
   **AWS ECS Fargate behind an ALB**, provisioned and reproducible via **AWS CDK**.

---

## 2. Target architecture

```
                          ┌─────────────────────────────────────────────┐
   GitHub (main)  ──push──►│ GitHub Actions CI/CD                          │
                          │  lint → pytest → build image → push ECR → deploy│
                          └───────────────┬─────────────────────────────────┘
                                          │ (CDK-provisioned infra)
            ┌─────────────────────────────▼───────────────────────────────┐
            │ AWS (ca-central-1), all via AWS CDK (Python)                  │
            │                                                               │
            │  Amazon ECR ── image ──► ECS Fargate Service ──► ALB (HTTPS)  │
            │                              │  (FastAPI + Streamlit)         │
            │                              ├──► CloudWatch Logs/metrics      │
            │                              └──► reads model from S3 / MLflow │
            │                                                               │
            │  EC2 t3.small  ── MLflow Tracking Server ──► S3 (artifacts)    │
            │  S3 buckets: mlflow-artifacts, drift-reports, data, model-reg  │
            └───────────────────────────────────────────────────────────────┘
```

**Region:** `ca-central-1` (Montreal). **IaC tool:** **AWS CDK in Python** (keeps one language across the
whole repo; `cdk synth`/`cdk deploy` from Othmane's machine). Terraform is an acceptable substitute if the
team prefers it, but **do not mix** — pick CDK and stay there. All AWS resources, IAM roles, security groups,
the ALB, ACM cert, ECR repo, ECS service/task, the MLflow EC2 box, and S3 buckets are defined as code under
`infra/`. **Nothing is clicked in the console.**

---

## 3. Course-requirements coverage matrix (the 100% checklist)

Every graded topic from `instructions_final_project` and the Section 5.9 presentation map is owned by a phase.
A phase is **not done** until its row(s) here are green and demonstrable (notebook output, MLflow run,
screenshot, test, or live endpoint).

| Course topic | Phase | How we satisfy it |
|---|:--:|---|
| Advanced imputation | 1 | KNN / MICE (IterativeImputer) for weather & demand gaps; missingness indicators |
| Feature engineering | 1 | 15-min slot/dow/month baselines, **lagged** features, weather joins, holiday flags |
| Data/Information leakage analysis | 1 | Strict temporal split; baselines computed only from 2024; leakage audit notebook |
| Advanced encoding / **entity embeddings** | 1 | Target/frequency encoding for high-cardinality `station_id`; entity-embedding option |
| Dimensionality reduction | 3 | PCA / UMAP on station-behaviour vectors; variance/importance feature selection |
| Clustering (unsupervised) | 3 | K-Means baseline **vs** GMM/Agglomerative/DBSCAN; auto-select by silhouette/DB/CH |
| Semi-supervised / self-learning | 2 | Self-training / pseudo-labelling option on sparse low-volume stations *(stretch)* |
| Causal inference | 2 | DoWhy: does a holiday / bad-weather flag *causally* shift demand? refutation tests |
| Product & data management | 1,4 | Data dictionary, config-driven pipeline, README run-modes, GitHub Project board |
| Hyperparameter tuning + **AutoML** | 2 | Optuna Bayesian HPO (logged to MLflow) **+ FLAML** AutoML model search |
| Explainability | 2 | SHAP global + local (force plots), LIME; surfaced on a Streamlit Explainability page |
| Fairness & Ethical AI | 2 | Error parity (RMSE/MAE) across demand tiers / boroughs; underserved-area check |
| Using GitHub toolset | all | feature branches, PRs, reviews, Project board, GitHub Secrets, Releases |
| CI/CD | 4 | GitHub Actions: lint → test → build → push ECR → deploy ECS (zero-downtime) |
| Docker containers | 4 | Dockerfile + `.dockerignore`; image versioned by commit SHA; local `docker compose` |
| MLflow / model tracking | 2,3 | Tracking server on EC2+S3; params/metrics/artifacts; Model Registry (Staging/Prod) |
| Feature / Target / Concept / Prediction drift | 3 | Evidently AI, all 4 types; weekly GitHub Actions cron; HTML reports to S3 |
| Model performance | 2 | R²/RMSE/MAE per split; logged + tracked over versions in MLflow |
| ML model serving & deployment | 4 | FastAPI REST endpoint + Streamlit UI on ECS Fargate behind ALB (HTTPS) |
| Cloud-native application | 4 | Serverless Fargate, ALB, auto-scaling, 12-factor config, CloudWatch |
| (Stretch) Batch/stream + Spark | 1,3 | Note the lineage to the Kafka/Spark assignment; optional PySpark feature job |
| (Stretch) Security | 4 | Secrets in GitHub Secrets / SSM, least-privilege IAM, `.gitignore` hygiene, image scan |

If any row is at risk near the deadline, the owner flags it in the PR and we descope the marked *stretch*
items first — never a core graded topic.

---

## 4. How to authenticate to GitHub from your coding agent (everyone, once)

Every teammate runs their coding agent (Claude Code) locally. Do this **once** per machine so the agent can
branch, commit, push, and open PRs on your behalf.

### Option A — GitHub CLI (recommended)
```bash
# 1. Install gh:  https://cli.github.com  (macOS: brew install gh)
# 2. Authenticate (opens a browser; choose HTTPS):
gh auth login
#    → GitHub.com → HTTPS → "Login with a web browser" → paste one-time code
# 3. Let gh manage git credentials:
gh auth setup-git
# 4. Verify:
gh auth status        # should show: Logged in to github.com as <your-handle>
```
After this, the agent can run `git push` and `gh pr create` with no further prompts.

### Option B — Personal Access Token (if you can't use the browser flow)
```bash
# Create a fine-grained PAT at github.com → Settings → Developer settings → Tokens
#   Repository access: ruizhaoca/bixi-demand-mlops-platform
#   Permissions: Contents: Read/Write, Pull requests: Read/Write
git config --global credential.helper store
# First push will prompt for username + paste the PAT as the password (stored thereafter).
```

### One-time repo clone
```bash
gh repo clone ruizhaoca/bixi-demand-mlops-platform
cd bixi-demand-mlops-platform
git config user.name  "<Your Name>"
git config user.email "<your-noreply-or-account-email>"   # use your GitHub no-reply email to keep PII off commits
```

> **Access:** all four members must be **collaborators** on `ruizhaoca/bixi-demand-mlops-platform` with
> *Write* permission (Rui adds them under repo *Settings → Collaborators*). If you only have read access,
> fork the repo and open PRs from the fork instead.

---

## 5. Branching, PR & board conventions (everyone)

- **`main` is always stable** — the instructor must be able to clone and run it. Never push to `main` directly.
- **One feature branch per phase:** `phase-1-data-foundation`, `phase-2-modeling`, `phase-3-clustering-drift`,
  `phase-4-serving-deploy`. Sub-work can use `feat/<short-desc>` branches that merge into the phase branch.
- **One PR per phase**, opened against `main`, reviewed by ≥1 teammate, CI green, then squash-merge.
- **Commits:** small, conventional (`feat:`, `fix:`, `test:`, `docs:`, `ci:`, `infra:`).
- **Project board:** a GitHub Project ("BIXI MLOps") with columns Todo / In-Progress / Review / Done; one
  card per phase deliverable. This is itself graded under "GitHub toolset" — keep it updated.
- **Branch protection on `main`:** require PR + passing CI before merge (Rui configures in Phase 4, or earlier).
- **Secrets** (AWS keys, MLflow URI) live in **GitHub Secrets** and local `.env` (git-ignored) — never committed.
- **Authorship — commits and PRs must appear as the human, not the coding agent.** Every commit, branch, and
  Pull Request is authored by the teammate driving the agent (their name + their own GitHub account), **never**
  by Claude / the coding agent. Concretely, before working: set `git config user.name`/`user.email` to *your*
  identity (your GitHub no-reply email), and **do not** add agent attribution to commits or PRs — no
  `Co-Authored-By: Claude`/agent trailer in commit messages and no "Generated with …" footer in PR
  descriptions. The agent does the typing; the human owns the contribution. (Verify with `git log` and
  `gh pr view` that the author is you, not the agent, before merging.)

### Standard PR open command (any phase)
```bash
git checkout -b phase-N-<theme>
# ...work, commit...
git push -u origin phase-N-<theme>
gh pr create --base main --title "Phase N: <theme>" \
  --body "Closes the Phase N deliverables in plan.md. See acceptance criteria there."
```

---

## 6. The four phases

> Dependency order: **1 → 2 → 3 → 4.** Phase 1 must merge first (everyone consumes its datasets). Phases 2 and
> 3 may run **in parallel** off `main` once Phase 1 is in, but each still ships as its own PR. Phase 4
> integrates everything last. Each phase ends with a **handoff prompt** (§7) to paste into the next person's agent.

### Phase 1 — Sarah Liu · Foundation & Data Engineering
**Branch:** `phase-1-data-foundation`

**Build:**
1. **Production repo scaffold** (this unblocks everyone):
   ```
   src/bixi/            # importable package
     config.py          # paths, dates, split boundaries, region — single source of truth
     data/ingest.py     # download+unzip BIXI 2024 / May-2025 / Oct-2025 trips + 15-min weather
     data/clean.py      # dtypes, dedupe, invalid-trip removal, outlier handling
     features/build.py  # 15-min binning, dep/arr split, baselines, lags, encoding
     features/impute.py # KNN / MICE imputers (fit on train only)
   notebooks/01_eda_feature_engineering.ipynb   # narrative EDA + leakage audit
   tests/test_features.py, tests/test_clean.py
   pyproject.toml, Makefile, .pre-commit-config.yaml, .gitignore, .env.example
   data/  (git-ignored large data; commit small samples + schema only)
   ```
2. **Ingest** 2024 + May/Oct 2025 BIXI trips and **15-minute** weather (find a 15-min/hourly source; if only
   hourly, repeat across the four 15-min slots — document the choice). Download directly from the BIXI/weather
   open-data URLs in code, not by hand.
3. **Clean & reshape:** all stations; split into **departures** and **arrivals** datasets sharing one pipeline.
4. **Advanced imputation:** KNN / IterativeImputer (MICE) + missingness indicators. *(course topic)*
5. **Feature engineering:** `station_slot_demand_24` (0–95), `station_dow_demand_24`, `station_month_demand_24`,
   `slot/dow/month`, `is_holiday`, weather features, **lagged demand** features. *(course topic)*
6. **Leakage analysis:** baselines computed **only** from 2024; 2025 features reference matching 2024 periods;
   temporal split honored; write the leakage audit in the notebook. *(course topic)*
7. **Advanced encoding:** target/frequency encoding for `station_id`; provide an **entity-embedding** hook for
   Phase 2. *(course topic)*
8. **Feature selection / multicollinearity** (VIF / importance), then persist versioned, leakage-safe feature
   tables (parquet) for departures and arrivals.
9. **Tests** for clean + feature builders; `make data` reproduces the datasets end-to-end.

**Acceptance:** `make data` regenerates both feature tables from raw; notebook renders with EDA + leakage
audit; `pytest` green; matrix rows for imputation/FE/leakage/encoding satisfied; `.env.example` documents every
required variable. **Output handed off:** `data/features_departures.parquet`, `data/features_arrivals.parquet`
+ their schema/data dictionary.

---

### Phase 2 — Othmane Zizi · Predictive Modeling, MLflow, AutoML & Responsible AI
**Branch:** `phase-2-modeling`

**Build:**
1. **Training pipeline** `src/bixi/models/train.py` consuming Phase-1 feature tables (runs once for departures,
   once for arrivals).
2. **Multi-model comparison + AutoML:** LightGBM baseline **plus** alternatives, and **FLAML** AutoML search;
   the pipeline **auto-selects** the best model for serving. *(course topics: model performance, AutoML)*
3. **Optuna** Bayesian HPO with every trial logged to MLflow. *(course topic: HPO)*
4. **MLflow** stand-up (this phase defines the conventions Ruihe reuses): `mlflow.set_tracking_uri(...)`,
   experiments per target, `log_params/metrics/model`, then **register** the best run to the Model Registry and
   transition to **Production**. Tracking URI comes from env/Secrets (works locally now, points to EC2 server
   once Phase 4 deploys it). *(course topic: MLflow / tracking / registry)*
5. **Evaluation:** R²/RMSE/MAE per split (2024 train / May-25 val / Oct-25 test), logged & compared.
6. **Explainability:** SHAP global + local (force plots) and LIME; save plots as artifacts for the app. *(topic)*
7. **Fairness & ethical AI:** compare prediction error across demand tiers / boroughs; flag underserved-area
   degradation; write up mitigation options. *(course topic)*
8. **Causal inference (DoWhy):** estimate the causal effect of `is_holiday` / `bad_weather` on demand with
   refutation tests — distinct from feature importance. *(course topic, currently missing entirely)*
9. *(Stretch)* semi-supervised self-training for sparse low-volume stations.
10. **Tests** for train/inference contracts; an `inference.py` that loads the Production model and predicts.

**Acceptance:** MLflow shows all Optuna trials + a registered Production model per target; SHAP/LIME, fairness,
and DoWhy outputs saved as artifacts; matrix rows for HPO/AutoML/MLflow/explainability/fairness/causal/model-
performance satisfied; `pytest` green. **Output handed off:** registered models + artifact paths + the
predict() contract serving will call.

---

### Phase 3 — Ruihe Zhang (Louis) · Clustering, Dimensionality Reduction & Drift Monitoring
**Branch:** `phase-3-clustering-drift`

**Build:**
1. **Dimensionality reduction** `src/bixi/cluster/reduce.py`: PCA / UMAP on per-station behaviour vectors
   (15-min demand profiles) for clustering + visualization. *(course topic)*
2. **Clustering model comparison** `src/bixi/cluster/train.py`: K-Means baseline **vs** GMM / Agglomerative /
   DBSCAN; **auto-select** best by silhouette / Davies-Bouldin / Calinski-Harabasz; log all to MLflow (reuse
   Phase-2 conventions). *(course topic)*
3. **Operational clustering framework:** group stations by departure/arrival intensity across **morning rush /
   evening rush / other**, surfacing rebalancing risk (e.g. high-departure-low-arrival). Persist
   `station_clusters.csv` for the app.
4. **Drift monitoring** `src/bixi/monitor/drift.py` with **Evidently AI**, covering **all four** drift types:
   - **Feature drift** — temperature, wind_speed, bad_weather, `station_slot_demand_24` (PSI>0.2 / KS p<0.05)
   - **Target drift** — demand per 15-min slot (Jensen-Shannon > 0.1)
   - **Prediction drift** — rolling 7-day model output shift (> 1.5 trips/slot)
   - **Concept drift** — R² on new labelled data vs 0.63 baseline (drop below 0.55 ⇒ retrain alert)
   *(course topic: all four drift types — a big scoring area)*
5. **Reference baseline** (2024, 15-min) uploaded to S3; drift HTML reports saved to S3.
6. **Weekly GitHub Actions cron** `.github/workflows/drift_check.yml` (Mon 09:00 UTC + manual dispatch) running
   the drift script against AWS Secrets.
7. **Tests** for cluster selection + drift thresholds.

**Acceptance:** clustering auto-selection logged to MLflow with `station_clusters.csv` produced; all 4 drift
types generate an Evidently report; the cron workflow runs (dispatch test passes); matrix rows for
dim-reduction/clustering/drift satisfied; `pytest` green. **Output handed off:** `station_clusters.csv`, drift
script + workflow, S3 reference/report locations for the app's Monitoring page.

---

### Phase 4 — Rui Zhao · Serving, Containerization, CI/CD, AWS IaC, Docs & Presentation
**Branch:** `phase-4-serving-deploy`

**Build:**
1. **FastAPI service** `src/bixi/serve/api.py`: `/predict` (loads MLflow Production model), `/health`,
   `/clusters`; pydantic request/response schemas. *(course topic: serving)*
2. **Streamlit app** `app.py` (refit from the base repo) with pages: **16-day forecast**, **custom input**,
   **clusters map** (PyDeck, dep/arr × time period), **Explainability** (Phase-2 SHAP), **Monitoring**
   (Phase-3 Evidently reports from S3). Calls the FastAPI backend.
3. **Docker:** `Dockerfile` (Python 3.12, deps, model files) + `.dockerignore`; `docker-compose.yml` for local
   API+UI. Image tagged by commit SHA. *(course topic)*
4. **CI/CD** `.github/workflows/deploy.yml`: on push to `main` → lint (ruff/black) → `pytest` → build → push to
   **ECR** → update **ECS** task/service (rolling, zero-downtime). Also a PR-CI workflow (lint+test only).
   *(course topic)*
5. **AWS IaC** under `infra/` with **AWS CDK (Python)** — every resource as code:
   - `EcrStack` (image repo), `NetworkStack` (VPC/subnets/SGs),
   - `FargateStack` (ECS cluster, task def, service, **ALB + ACM HTTPS**, CloudWatch logs, auto-scaling),
   - `MlflowStack` (EC2 t3.small tracking server + **S3** artifact bucket, locked to team IPs),
   - `StorageStack` (S3 for data, drift-reports, model-registry), least-privilege IAM roles.
   `cdk synth` must succeed in CI; `cdk deploy` is run by Othmane (see §8).
6. **README** with the two run-modes: (a) full pipeline from scratch with your own cloud creds; (b) local
   Streamlit using prepared input files only. Plus architecture diagram + per-phase summaries. *(product mgmt)*
7. **Branch protection + Project board** finalized; **Release tag** `v1.0-final`.
8. **LaTeX report → PDF via tectonic** covering **Section 5.9 Solution Presentation** (see §9) + the
   **presentation deck**. The report aggregates each owner's phase write-up.

**Acceptance:** `docker compose up` runs API+UI locally; CI is green on a PR; `cdk synth` succeeds; README
documents both run-modes; `report.pdf` builds via tectonic and covers all 5.9 sections; deck lists team, GitHub
ids, repo name. **This is the integration phase — it is done only when the full stack works end-to-end.**

---

## 7. Handoff prompts (copy-paste into the next person's agent)

Each prompt is self-contained: it tells the agent where to pick up from `plan.md`, what already exists, and
the exact acceptance bar. Paste verbatim.

### ▶ Kickoff — Phase 1 (Sarah)
```
You are working on the BIXI Demand MLOps Platform (repo: ruizhaoca/bixi-demand-mlops-platform).
Read plan.md in the repo root, then execute PHASE 1 (Sarah · Foundation & Data Engineering) exactly as
specified in §6. First authenticate to GitHub per §4, then create branch `phase-1-data-foundation`.
Build the production scaffold, ingest 2024 + May/Oct-2025 BIXI trips + 15-min weather, clean to all stations,
split into departures/arrivals, do advanced imputation (KNN/MICE), 15-min feature engineering with lagged
features, a leakage audit, advanced encoding for station_id, feature selection, and pytest tests. Meet every
Phase-1 acceptance criterion in §6, keep secrets out of git (.env is git-ignored), then open ONE PR titled
"Phase 1: Data Foundation" against main and stop. Do not start later phases.
```

### ▶ Handoff — Phase 1 ➜ Phase 2 (to Othmane)
```
Phase 1 (Data Foundation) is merged. You are on the BIXI MLOps repo. Read plan.md, then execute PHASE 2
(Othmane · Predictive Modeling, MLflow, AutoML, Responsible AI) per §6. Branch from updated main as
`phase-2-modeling`. Consume data/features_departures.parquet and data/features_arrivals.parquet (schema in
the Phase-1 data dictionary). Build the multi-model + FLAML AutoML training pipeline with Optuna HPO, stand up
MLflow tracking + Model Registry (Production stage) using env-based tracking URI, full eval metrics, SHAP+LIME
explainability, a fairness error-parity analysis, and a DoWhy causal-inference study. Add tests and an
inference.py that loads the Production model. Meet all Phase-2 acceptance criteria in §6, open ONE PR
"Phase 2: Predictive Modeling & Responsible AI" against main, and stop.
```

### ▶ Handoff — Phase 2 ➜ Phase 3 (to Ruihe / Louis)
```
Phases 1–2 are merged. You are on the BIXI MLOps repo. Read plan.md, then execute PHASE 3
(Ruihe/Louis · Clustering, Dimensionality Reduction & Drift Monitoring) per §6. Branch from updated main as
`phase-3-clustering-drift`. Reuse the MLflow conventions Othmane established in Phase 2. Do PCA/UMAP
dimensionality reduction, compare K-Means vs GMM/Agglomerative/DBSCAN with automatic best-model selection,
build the departure/arrival × time-period operational clustering and write station_clusters.csv, then
implement Evidently drift monitoring for ALL FOUR drift types (feature/target/prediction/concept) with the
2024 15-min reference uploaded to S3 and a weekly GitHub Actions cron (.github/workflows/drift_check.yml).
Add tests. Meet all Phase-3 acceptance criteria in §6, open ONE PR "Phase 3: Clustering & Drift Monitoring"
against main, and stop.
```

### ▶ Handoff — Phase 3 ➜ Phase 4 (to Rui)
```
Phases 1–3 are merged. You are on the BIXI MLOps repo. Read plan.md, then execute PHASE 4
(Rui · Serving, Containerization, CI/CD, AWS IaC, Docs & Presentation) per §6. Branch from updated main as
`phase-4-serving-deploy`. Build the FastAPI service (loads the MLflow Production model), the multi-page
Streamlit app (forecast / custom input / clusters map / Explainability / Monitoring), Dockerfile +
docker-compose, GitHub Actions CI/CD (lint→test→build→push ECR→deploy ECS) plus a PR-CI workflow, and the full
AWS CDK (Python) infrastructure under infra/ (ECR, VPC, Fargate+ALB+ACM, EC2 MLflow+S3, storage S3,
least-privilege IAM). Write the README with both run-modes, configure branch protection + the Project board,
cut Release v1.0-final, and produce the LaTeX→PDF (tectonic) report covering EnterpriseDataScience Section 5.9
plus the presentation deck (team names, GitHub ids, repo name). `cdk synth` must pass in CI; do NOT run
`cdk deploy` yourself — that is Othmane's gated step (§8). Meet all Phase-4 acceptance criteria in §6, open ONE
PR "Phase 4: Serving, CI/CD & AWS IaC" against main, and stop.
```

---

## 8. Deployment runbook (Othmane runs this with AWS credentials)

When the four phases are merged and `cdk synth` is green, deploying is a single gated step. **When Othmane says
"deploy," the agent should do exactly this:**

```bash
# 0. Prereqs (once): Node ≥18, AWS CDK (npm i -g aws-cdk), Python deps in infra/, Docker running.
# 1. Configure AWS creds (Othmane's account), region ca-central-1:
aws configure            # or export AWS_PROFILE / AWS_ACCESS_KEY_ID + AWS_SECRET_ACCESS_KEY
aws sts get-caller-identity      # confirm the right account

cd infra/
pip install -r requirements.txt
cdk bootstrap aws://<ACCOUNT_ID>/ca-central-1     # first time only

# 2. Review then provision infra (review the diff before applying):
cdk diff
cdk deploy --all --require-approval any-change    # ECR, VPC, S3, EC2 MLflow, Fargate+ALB+ACM

# 3. Build & push the app image (or let GitHub Actions deploy.yml do it on next push to main):
#    outputs: ECR repo URI, ALB DNS/HTTPS URL, MLflow EC2 URL  (printed as CDK outputs)

# 4. Smoke test:
curl https://<ALB_URL>/health        # FastAPI health
open  https://<ALB_URL>/             # Streamlit UI

# 5. Set GitHub Secrets so CI/CD + drift cron work:
#    AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, MLFLOW_TRACKING_URI, ECR/ECS names (from CDK outputs)
```

**Teardown** (avoid AWS charges after grading): `cdk destroy --all` (stop the EC2 MLflow box first if kept).

> Decision pinned: **AWS CDK (Python)**. If the team switches to Terraform, the runbook becomes
> `terraform init / plan / apply` under `infra/` and the rest is unchanged.

---

## 9. Report & presentation (Section 5.9 Solution Presentation)

The final presentation (20%) and the LaTeX report must cover the EnterpriseDataScience **Section 5.9 Solution
Presentation** map (`INSY684 Group Project/5.9. Solution Presentation Map.png` and the PDF deck). Cover at least:

- **Business problem & value** — BIXI rebalancing; why 15-min granularity + dep/arr split matters operationally.
- **Data** — sources, volume, cleaning, imputation, feature engineering, leakage handling.
- **Methodology** — multi-model + AutoML, HPO, clustering, dimensionality reduction, causal inference.
- **Results** — metrics per split, SHAP insights, fairness findings, cluster operational map.
- **MLOps & architecture** — MLflow, Docker, CI/CD, ECS Fargate + ALB, IaC, drift monitoring (4 types).
- **Responsible AI** — explainability, fairness, ethics.
- **Live demo** — the deployed app + MLflow UI + an Evidently drift report.
- **Roadmap / limitations** — what's next.

**Mandatory deck slide (submission requirement):** team name, **every member's name + GitHub id**
(`othmane-zizi-pro`, `mudkipython`, `ruizhaoca`, _Sarah's handle — confirm_), and the **repo name**
`bixi-demand-mlops-platform`. Only **one** teammate submits on MyCourses with this info.

**Report toolchain:** write in LaTeX, compile with **tectonic** (`tectonic report/report.tex`) → `report.pdf`.

---

## 10. Local dev quickstart (everyone)

```bash
gh repo clone ruizhaoca/bixi-demand-mlops-platform && cd bixi-demand-mlops-platform
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt          # plus -e . once pyproject lands in Phase 1
cp .env.example .env                      # fill in AWS / MLflow values; .env is git-ignored
pre-commit install                        # lint/format on commit
make data        # Phase 1 onward: regenerate feature tables
make train       # Phase 2 onward
make app         # run Streamlit locally
pytest           # run the test suite
```

---

### Status checklist
- [ ] Phase 1 — Data Foundation (Sarah) · PR merged
- [ ] Phase 2 — Predictive Modeling & Responsible AI (Othmane) · PR merged
- [ ] Phase 3 — Clustering & Drift Monitoring (Ruihe) · PR merged
- [ ] Phase 4 — Serving, CI/CD & AWS IaC (Rui) · PR merged
- [ ] `cdk deploy` run by Othmane · app live behind ALB
- [ ] Report (tectonic PDF) + presentation deck · ready for June 19
- [ ] One teammate submits on MyCourses · June 21
