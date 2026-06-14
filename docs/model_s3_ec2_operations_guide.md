# Model, S3, FastAPI, Docker, and EC2 Operations Guide

This guide summarizes the current MLOps deployment path and explains how future modeling work should update model artifacts, upload them to S3, restart the API, and validate the deployed service.

## 1. Completed Work

The existing model workflow has been converted into a backend service that can be called through HTTP API endpoints instead of only being used locally or inside Streamlit.

Completed:

- Added the FastAPI backend.
- Added S3 artifact loading.
- Added a Dockerfile to package the FastAPI backend as a container.
- Added GitHub Actions CI to run tests and Docker build checks.
- Uploaded the current model artifacts to S3.
- Verified locally that the API can load the model from S3.
- Installed Docker on EC2, built the image, and ran the container.
- Verified that the EC2 public endpoint returns predictions successfully.

Current endpoints:

```text
GET  http://18.118.143.165:8000/health
GET  http://18.118.143.165:8000/stations
POST http://18.118.143.165:8000/predict
GET  http://18.118.143.165:8000/docs
```

Verified:

```text
GET /health
{"status":"ok","model_source":"s3","station_count":400}
```

```text
POST /predict
predicted_total_demand = 11.88
model_source = s3
```

## 2. Current Architecture

```text
User / Streamlit / API client
        |
        | HTTP request
        v
FastAPI running inside Docker on EC2
        |
        | boto3, using EC2 IAM Role
        v
S3 bucket: insy684
        |
        | model artifacts
        v
LightGBM model + metadata
        |
        v
Prediction JSON response
```

Important principle:

- GitHub stores code.
- S3 stores large datasets and model artifacts.
- EC2 runs the API server.
- IAM Role gives EC2 permission to read S3.
- We should not put AWS access keys in code, notebooks, README files, or GitHub.

## 3. Important AWS Resources

Region:

```text
us-east-2
```

S3 bucket:

```text
insy684
```

Current model artifact paths:

```text
s3://insy684/bixi-models/model_lightgbm.txt
s3://insy684/bixi-models/meta_lightgbm.pkl
```

EC2:

```text
Public IPv4: 18.118.143.165
SSH username: ubuntu
API port: 8000
```

EC2 IAM Role:

```text
bixi-ec2-s3-read-role
```

The IAM Role must be attached to the EC2 instance and must allow S3 read access to the model artifact paths.

## 4. Files Added For MLOps

Main API and serving files:

```text
api/main.py
src/predictor.py
src/s3_io.py
Dockerfile
.dockerignore
.env.example
```

Tests and CI:

```text
tests/test_api.py
.github/workflows/ci.yml
docs/github_actions_guide.md
```

AWS/deployment docs:

```text
docs/aws_deployment_checklist.md
docs/model_s3_ec2_operations_guide.md
```

## 5. How The API Loads The Model

The backend can load artifacts from either local files or S3.

Local mode:

```bash
MODEL_SOURCE=local
LOCAL_MODEL_PATH=model_lightgbm.txt
LOCAL_META_PATH=meta_lightgbm.pkl
```

S3 mode:

```bash
MODEL_SOURCE=s3
S3_BUCKET=insy684
MODEL_KEY=bixi-models/model_lightgbm.txt
META_KEY=bixi-models/meta_lightgbm.pkl
AWS_REGION=us-east-2
```

On EC2, we do not pass AWS access keys. `boto3` uses the EC2 IAM Role automatically.

## 6. Model Artifact Contract

The current API expects two files:

```text
model_lightgbm.txt
meta_lightgbm.pkl
```

`model_lightgbm.txt` is the trained LightGBM model saved in text format.

`meta_lightgbm.pkl` is a pickle file containing metadata used to build the API input features.

The metadata must contain these keys:

```text
station
all_features
categorical_features
station_hour_demand_24
station_dow_demand_24
station_month_demand_24
global_hour_demand_24
global_dow_demand_24
global_month_demand_24
```

The current API request body is:

```json
{
  "station": "10e avenue / Masson",
  "date": "2026-01-01",
  "hour": 8,
  "is_holiday": 0,
  "temperature": 22.5,
  "feels_like": 23.0,
  "wind_speed": 12.0,
  "bad_weather": 0
}
```

The current model features are built from:

```text
station
hour
dow
month
is_holiday
bad_weather
station_hour_demand_24
station_dow_demand_24
station_month_demand_24
temperature
feels_like
wind_speed
```

If the modeling team changes the feature set, update these files together:

```text
src/predictor.py
api/main.py
tests/test_api.py
README.md
```

Do not only upload a new model if the feature schema changed. The API code must match the model schema.

## 7. For Modeling Teammates: How To Update The Model

### Step 1: Train The New Model

Train the model in the notebook or training script.

The final model should still be exported as:

```text
model_lightgbm.txt
meta_lightgbm.pkl
```

Recommended model export pattern:

```python
model.booster_.save_model("model_lightgbm.txt")

with open("meta_lightgbm.pkl", "wb") as f:
    pickle.dump(meta, f)
```

Before uploading, test locally:

```bash
python -m pytest -q
```

### Step 2: Upload The New Artifacts To S3

If using AWS Console:

1. Open S3.
2. Open bucket `insy684`.
3. Open folder `bixi-models/`.
4. Upload the new `model_lightgbm.txt`.
5. Upload the new `meta_lightgbm.pkl`.

If using AWS CLI:

```bash
aws s3 cp model_lightgbm.txt s3://insy684/bixi-models/model_lightgbm.txt
aws s3 cp meta_lightgbm.pkl s3://insy684/bixi-models/meta_lightgbm.pkl
```

Optional versioned layout:

```text
s3://insy684/bixi-models/v2/model_lightgbm.txt
s3://insy684/bixi-models/v2/meta_lightgbm.pkl
```

If using versioned paths, update the EC2 container environment variables:

```text
MODEL_KEY=bixi-models/v2/model_lightgbm.txt
META_KEY=bixi-models/v2/meta_lightgbm.pkl
```

### Step 3: Restart The API Container

The FastAPI app caches the predictor after loading it. If model files are replaced in S3, the running container will not automatically reload them. Restart the container after uploading new artifacts.

SSH into EC2:

```bash
ssh -i bixi-ec2-key.pem ubuntu@18.118.143.165
```

Restart using the same S3 keys:

```bash
cd ~/bixi-demand-mlops-platform

sudo docker rm -f bixi-demand-api

sudo docker run -d \
  --name bixi-demand-api \
  -p 8000:8000 \
  -e AWS_REGION=us-east-2 \
  -e S3_BUCKET=insy684 \
  -e MODEL_SOURCE=s3 \
  -e MODEL_KEY=bixi-models/model_lightgbm.txt \
  -e META_KEY=bixi-models/meta_lightgbm.pkl \
  bixi-demand-api
```

If using versioned S3 keys, change `MODEL_KEY` and `META_KEY` in the command above.

### Step 4: Validate The New Model

Health check:

```bash
curl http://18.118.143.165:8000/health
```

Expected:

```json
{"status":"ok","model_source":"s3","station_count":400}
```

Prediction test:

```bash
curl -X POST http://18.118.143.165:8000/predict \
  -H "Content-Type: application/json" \
  -d '{
    "station": "10e avenue / Masson",
    "date": "2026-01-01",
    "hour": 8,
    "is_holiday": 0,
    "temperature": 22.5,
    "feels_like": 23.0,
    "wind_speed": 12.0,
    "bad_weather": 0
  }'
```

Expected response shape:

```json
{
  "station": "10e avenue / Masson",
  "date": "2026-01-01",
  "hour": 8,
  "predicted_total_demand": 11.88,
  "model_source": "s3",
  "features": {}
}
```

The number may change after retraining. The response should still return successfully.

## 8. How To Rebuild The Docker Image On EC2

Use this only after code changes, dependency changes, Dockerfile changes, or GitHub updates.

```bash
ssh -i bixi-ec2-key.pem ubuntu@18.118.143.165

cd ~/bixi-demand-mlops-platform
git pull

sudo docker rm -f bixi-demand-api
sudo docker build -t bixi-demand-api .

sudo docker run -d \
  --name bixi-demand-api \
  -p 8000:8000 \
  -e AWS_REGION=us-east-2 \
  -e S3_BUCKET=insy684 \
  -e MODEL_SOURCE=s3 \
  -e MODEL_KEY=bixi-models/model_lightgbm.txt \
  -e META_KEY=bixi-models/meta_lightgbm.pkl \
  bixi-demand-api
```

Check running containers:

```bash
sudo docker ps
```

Check logs:

```bash
sudo docker logs bixi-demand-api
```

## 9. Troubleshooting

### `curl: (7) Failed to connect`

Likely causes:

- Container is not running.
- EC2 Security Group does not allow port `8000`.
- Docker run failed.

Check:

```bash
sudo docker ps
sudo docker logs bixi-demand-api
```

### `OSError: libgomp.so.1`

Cause:

LightGBM requires the Linux runtime library `libgomp1`.

Fix:

The Dockerfile must include:

```dockerfile
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*
```

Then rebuild the Docker image.

### `NoCredentialsError`

Cause:

The running environment cannot find AWS credentials.

On EC2, this usually means the IAM Role is missing or not attached correctly.

Fix:

- Confirm EC2 has IAM Role `bixi-ec2-s3-read-role`.
- Confirm the role has S3 read permission for `s3://insy684/`.
- Do not put AWS access keys into the repo.

### `AccessDenied`

Cause:

IAM Role exists, but does not have permission to read the bucket or object path.

Fix:

Confirm the role can read:

```text
s3://insy684/bixi-models/model_lightgbm.txt
s3://insy684/bixi-models/meta_lightgbm.pkl
```

### `NoSuchKey`

Cause:

The S3 key is wrong or the artifact was uploaded to a different folder.

Fix:

Check these environment variables:

```text
MODEL_KEY
META_KEY
```

Check S3 object paths in AWS Console.

### Container exits immediately

Check logs:

```bash
sudo docker logs bixi-demand-api
```

The logs usually identify missing libraries, missing environment variables, or S3 permission errors.

## 10. Security Rules

Do not commit:

```text
.env
AWS access keys
SSH .pem files
local AWS credential files
large raw datasets
```

The `.gitignore` is configured to help prevent this.

If an AWS access key is accidentally shared in chat, GitHub, or a notebook, rotate or delete it immediately.

Production-style deployment should use:

```text
EC2 IAM Role -> S3 read access
```

not:

```text
hard-coded AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY
```

## 11. What To Tell The Team

Current status:

```text
The FastAPI backend is deployed on EC2 and loads model artifacts from S3.

Health endpoint:
http://18.118.143.165:8000/health

Swagger docs:
http://18.118.143.165:8000/docs

Model artifacts:
s3://insy684/bixi-models/model_lightgbm.txt
s3://insy684/bixi-models/meta_lightgbm.pkl

If the modeling team retrains the model, upload the new artifacts to S3 and restart the Docker container on EC2.
```

Recommended next improvements:

- Split API dependencies from Streamlit dependencies to reduce Docker image size.
- Add model version folders in S3, such as `bixi-models/v1/`, `bixi-models/v2/`.
- Add a `/model-info` endpoint that returns model version and artifact paths.
- Add GitHub Actions deployment later, after the team agrees on SSH key handling and deployment permissions.
