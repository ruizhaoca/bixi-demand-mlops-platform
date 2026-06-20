# Plan — FastAPI `/predict` service + AWS App Runner (CDK)

**Goal:** make the deck's "App Runner · FastAPI API" serving tier *real*. Add a FastAPI
prediction service that reuses the existing model contract, containerize it, provision it on
**AWS App Runner** via CDK (a new `BixiServe` stack), and wire it into CI — **without** touching
the model, the training pipeline, or the two existing Streamlit deployments (Community Cloud +
EC2). Deliver as **one PR** against `main`. **Do not run `cdk deploy`** (that is the gated
human step — Rui/Othmane run it with SSO creds).

> Why this exists: the presentation (slide 5 / 14 / 15 / 16) now shows serving as
> **Streamlit Community Cloud (UI) + EC2 Streamlit (UI) + App Runner FastAPI (API)**. The first
> two exist in the repo; this PR builds the third. Professor's own outline lists
> `API – FastAPI – AppRunner / Cloud Run` under Serving, so this is directly graded.

---

## 0. Context you must reuse (do not reinvent)

The prediction logic already exists — the API is mostly *wiring*:

- **`src/bixi/streamlit_local_serving.py`** — `load_local_bundles(artifact_root=…)` loads the
  committed artifacts under `artifacts/streamlit-community-cloud/cloud-2024/` (no AWS). Returns
  `{target: LocalTargetBundle}`. `LocalTargetBundle` has:
  - `.stations` → sorted station names
  - `.build_feature_row(station_name, timestamp: pd.Timestamp, weather: Mapping)` → feature dict
  - `.predict_one(row) -> float` (already clips negatives to 0)
  - `.metrics`, `.registered_model`
  - helpers: `common_stations(bundles)`, `timestamp_for(date, slot_of_day)`, `slot_label(slot)`
- **`src/bixi/streamlit_s3_serving.py`** — `load_s3_bundles(settings=None)` loads the same
  bundle shape from S3 using the instance IAM role (env-driven via `s3_artifact_config()`:
  `BIXI_RUN_ID`, `BIXI_PIPELINE_BUCKET`, `BIXI_DATA_BUCKET`, `BIXI_PIPELINE_PREFIX`,
  `BIXI_BASELINE_PREFIX`, `AWS_REGION`).
- **`src/bixi/config.py`** — `TARGETS = ("departure","arrival")`, `STATION_COL = "station_name"`,
  `AWS_REGION` (default `us-east-2`), `DATA_BUCKET` (`insy684`), `PIPELINE_PREFIX` (`bixi-mlops`).
- Weather fields the model expects: `temperature_2m`, `precipitation`, `wind_speed_10m`,
  `relative_humidity_2m`, `weather_code`.
- **CDK pattern to copy:** `infra/bixi_infra/batch_stack.py` shows `DockerImageAsset`
  (`directory=REPO_ROOT, file="docker/Dockerfile.*", platform=Platform.LINUX_AMD64`), an IAM role,
  `pipeline_bucket.grant_read*`, SSM grant, and `CfnOutput`. `infra/app.py` wires the stacks.
- **CI:** `.github/workflows/ci.yml` installs `requirements.txt` + `requirements-train.txt` +
  `pytest`, runs `pytest -q tests/`, builds the train + streamlit_ec2 images.
- **Dockerfile to copy:** `docker/Dockerfile.streamlit_ec2` (python:3.12-slim, `PYTHONPATH=/app/src`,
  `libgomp1` for lightgbm, HEALTHCHECK, CMD).

> NOTE: `infra/cdk.out/asset.*/api/main.py` etc. are **stale build output from a removed
> pre-refactor FastAPI** (it imports `src/predictor.py` / `src/s3_io.py` that no longer exist).
> **Do not resurrect it.** Build fresh against `src/bixi/`.

---

## 1. Deliverables (new/changed files)

1. **`api/__init__.py`**, **`api/main.py`** — the FastAPI app (details in §2).
2. **`requirements-api.txt`** — API runtime deps (§3).
3. **`docker/Dockerfile.api`** — container for the API (§3).
4. **`infra/bixi_infra/serve_stack.py`** — `BixiServe` App Runner stack (§4).
5. **`infra/app.py`** — instantiate `ServeStack` (+ `add_dependency(storage)`).
6. **`infra/requirements.txt`** — only if you choose the alpha L2 construct (see §4); the L1
   `aws_apprunner.CfnService` path needs **no** new dependency (recommended).
7. **`tests/test_api.py`** — TestClient tests in **local** mode, no network (§5).
8. **`.github/workflows/ci.yml`** — install API deps, build + smoke-test the API image (§6).
9. **Docs:** short serving section in `README.md` (API endpoints + how it fits the 3-tier serving
   story) and keep this plan file.
10. *(OPTIONAL, only if time permits — keep it behind a flag, don't break existing apps):* let the
    Streamlit app call the API when `BIXI_API_URL` is set, else fall back to in-process bundles.

---

## 2. `api/main.py` — the service

Load bundles **once at startup**, mode chosen by env `BIXI_SERVING_MODE` (`local` default for
safety/tests; `s3` in App Runner):

```python
mode = os.getenv("BIXI_SERVING_MODE", "local").lower()
BUNDLES = load_s3_bundles() if mode == "s3" else load_local_bundles()
```

Endpoints:

- **`GET /health`** → `{"status":"ok","mode":mode,"targets":[...]}` (App Runner health check hits this).
- **`GET /stations`** → `{"stations": common_stations(BUNDLES)}`.
- **`GET /info`** → per-target `metrics` + `registered_model` (val/test RMSE, R², production alias).
- **`POST /predict`** → main endpoint. Pydantic request:
  - `target: Literal["departure","arrival","both"] = "both"`
  - `station_name: str`
  - `timestamp: datetime` (ISO 8601)  *(accept this; derive slot/dow inside `build_feature_row`)*
  - `weather: Weather` with the 5 fields above (give sane defaults, e.g. clear/calm).
  - Response: `{"station_name":…, "timestamp":…, "predictions": {"departure": float, "arrival": float}}`
    (only requested targets). Build the row with `bundle.build_feature_row(station_name,
    pd.Timestamp(timestamp), weather.dict())` then `bundle.predict_one(row)`.
  - **Errors:** missing station/baseline raises `KeyError` → return **404** with a clear message;
    Pydantic handles **422** for bad input.

Keep it small and typed (pydantic models `Weather`, `PredictRequest`, `PredictResponse`). No new ML
logic — only call existing bundle methods.

---

## 3. Container

**`requirements-api.txt`** (pin to the SAME versions as `requirements.txt` so the model unpickles
identically) — the model-loading subset + the web server:
```
pandas==3.0.3
numpy==2.4.6
pyarrow==24.0.0
scikit-learn==1.9.0
lightgbm==4.6.0
boto3==1.43.33
fastapi==0.115.*
uvicorn[standard]==0.32.*
```
*(streamlit/plotly are NOT needed by the API.)*

**`docker/Dockerfile.api`** — mirror `Dockerfile.streamlit_ec2`:
- `FROM python:3.12-slim`; `ENV PYTHONPATH=/app/src`, `AWS_DEFAULT_REGION=us-east-2`.
- `apt-get install libgomp1 ca-certificates curl` (lightgbm needs libgomp).
- `pip install -r requirements-api.txt`.
- `COPY src/ ./src/`, `COPY api/ ./api/`, **and `COPY artifacts/streamlit-community-cloud/
  ./artifacts/streamlit-community-cloud/`** (bakes the ~9 MB local bundle so `local` mode works
  in-container as a fallback even though App Runner runs `s3` mode).
- `EXPOSE 8000`; `HEALTHCHECK … curl -fsS http://localhost:8000/health`.
- `CMD ["uvicorn","api.main:app","--host","0.0.0.0","--port","8000"]`.

---

## 4. `infra/bixi_infra/serve_stack.py` — App Runner via CDK

**Recommended: L1 `aws_apprunner.CfnService`** (stable, no extra CDK dependency). Build the image
with `DockerImageAsset` (same pattern as `batch_stack.py`), give App Runner an **access role**
(`build.apprunner.amazonaws.com`) with ECR pull, and an **instance role**
(`tasks.apprunner.amazonaws.com`) with **read** on the pipeline + data buckets (for `s3` mode) and
SSM `/bixi/*`.

```python
class ServeStack(Stack):
    def __init__(self, scope, cid, *, pipeline_bucket, data_bucket_name="insy684", run_id="cloud-2024", **kw):
        super().__init__(scope, cid, **kw)
        image = DockerImageAsset(self, "ApiImage", directory=REPO_ROOT,
                                 file="docker/Dockerfile.api", platform=Platform.LINUX_AMD64)
        access_role = iam.Role(self, "AccessRole",
            assumed_by=iam.ServicePrincipal("build.apprunner.amazonaws.com"))
        image.repository.grant_pull(access_role)
        instance_role = iam.Role(self, "InstanceRole",
            assumed_by=iam.ServicePrincipal("tasks.apprunner.amazonaws.com"))
        pipeline_bucket.grant_read(instance_role)
        s3.Bucket.from_bucket_name(self, "DataBucket", data_bucket_name).grant_read(instance_role)
        instance_role.add_to_policy(iam.PolicyStatement(actions=["ssm:GetParameter"],
            resources=[f"arn:aws:ssm:{self.region}:{self.account}:parameter/bixi/*"]))
        env = [apprunner.CfnService.KeyValuePairProperty(name=k, value=v) for k, v in {
            "BIXI_SERVING_MODE": "s3", "BIXI_RUN_ID": run_id,
            "BIXI_PIPELINE_BUCKET": pipeline_bucket.bucket_name,
            "BIXI_DATA_BUCKET": data_bucket_name, "AWS_REGION": self.region,
        }.items()]
        svc = apprunner.CfnService(self, "Service", service_name="bixi-api",
            source_configuration=apprunner.CfnService.SourceConfigurationProperty(
                authentication_configuration=apprunner.CfnService.AuthenticationConfigurationProperty(
                    access_role_arn=access_role.role_arn),
                auto_deployments_enabled=False,
                image_repository=apprunner.CfnService.ImageRepositoryProperty(
                    image_identifier=image.image_uri, image_repository_type="ECR",
                    image_configuration=apprunner.CfnService.ImageConfigurationProperty(
                        port="8000", runtime_environment_variables=env))),
            instance_configuration=apprunner.CfnService.InstanceConfigurationProperty(
                cpu="0.25 vCPU", memory="0.5 GB", instance_role_arn=instance_role.role_arn),
            health_check_configuration=apprunner.CfnService.HealthCheckConfigurationProperty(
                protocol="HTTP", path="/health", interval=10, timeout=5,
                healthy_threshold=1, unhealthy_threshold=5))
        CfnOutput(self, "ApiUrl", value=f"https://{svc.attr_service_url}")
```
Verify `image.image_uri` / property names against the installed `aws-cdk-lib` (>=2.160). If you
prefer the L2 `aws_apprunner_alpha.Service`, add `aws-cdk.aws-apprunner-alpha` to
`infra/requirements.txt` and use `Source.from_asset(asset=image, image_configuration=…)` — but the
L1 path above is the safe default.

**Wire into `infra/app.py`:**
```python
from bixi_infra.serve_stack import ServeStack
serve = ServeStack(app, "BixiServe", pipeline_bucket=storage.bucket,
                   data_bucket_name=data_bucket, env=env)
serve.add_dependency(storage)
```
App Runner needs **no VPC** (reaches S3 over the public AWS API).

---

## 5. Tests — `tests/test_api.py` (no network)

Use FastAPI's `TestClient`, force **local** mode so it loads committed artifacts:
```python
os.environ.setdefault("BIXI_SERVING_MODE", "local")
from fastapi.testclient import TestClient
from api.main import app
client = TestClient(app)
```
Assert: `/health` 200 & `status=="ok"`; `/stations` non-empty; `/predict` on the **first common
station** with a valid timestamp + default weather returns non-negative floats for both targets;
an unknown station returns **404**. Mirror the existing synthetic/no-network style in
`tests/test_bixi_*`.

---

## 6. CI — extend `.github/workflows/ci.yml`

- Add `pip install -r requirements-api.txt` to the install step.
- `pytest -q tests/` already picks up `test_api.py` (keep it scoped to `tests/`).
- Add: `docker build -f docker/Dockerfile.api -t bixi-api .`
- Add a smoke test: run the container in local mode and curl `/health`, e.g.
  `docker run -d -e BIXI_SERVING_MODE=local -p 8000:8000 --name bixi-api bixi-api` →
  poll `http://localhost:8000/health` → assert 200 → stop. (Or `docker run --rm bixi-api python -c
  "from api.main import app"` as a minimal import smoke if networking in CI is fussy.)

---

## 7. Acceptance criteria (all must pass before opening the PR)

- [ ] `uvicorn api.main:app` runs locally; `curl localhost:8000/health` → ok; `POST /predict`
      returns sensible non-negative departure/arrival numbers for a real station.
- [ ] `pytest -q tests/` green (incl. `test_api.py`, local mode, no network).
- [ ] `docker build -f docker/Dockerfile.api -t bixi-api .` succeeds; container `/health` ok.
- [ ] `cd infra && pip install -r requirements.txt && cdk synth` succeeds with the new **BixiServe**
      stack (CloudFormation renders; **no deploy**).
- [ ] CI green on the PR.
- [ ] Existing Streamlit apps (Community Cloud `app.py`, EC2 `app_ec2.py`) and the pipeline are
      **untouched and still pass** their tests.

## 8. Out of scope / guardrails

- ❌ **No `cdk deploy`** — gated human step (Rui/Othmane, SSO). PR stops at `cdk synth`.
- ❌ Don't remove/alter the EC2 Streamlit or Community Cloud serving, the model, or training.
- ❌ Don't edit the presentation deck.
- ✅ Keep secrets out of git (`.env` is git-ignored). No static AWS keys in code.

## 9. After merge (NOT in this PR — for the deploy runbook)

`cd infra && aws sso login --profile bixi && cdk deploy BixiServe` → copy the printed `ApiUrl` into
deck slides 5 / 15 / 16, and (optionally) set `BIXI_API_URL` on the Streamlit apps so the UI calls
the live API. Teardown with `cdk destroy BixiServe`.

---

### Branch / PR
- Branch: `feat/fastapi-apprunner-serving` off `main`.
- One PR against `main`, title: **"Serving: FastAPI /predict + App Runner CDK stack"**.
- Body: link this plan, list endpoints, paste `cdk synth` + `pytest` output, note "no cdk deploy".
- **Authorship:** all commits + the PR are authored by the human running the agent (their name +
  GitHub account). **No agent attribution** — no `Co-Authored-By: …agent`, no "Generated with…"
  footer.
