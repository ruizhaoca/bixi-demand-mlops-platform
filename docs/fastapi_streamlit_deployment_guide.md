# FastAPI-backed Streamlit deployment

This guide deploys the cloud-serving version without changing the packaged
Streamlit Community Cloud fallback.

```text
Browser
  -> EC2 Streamlit container (app_fastapi_ec2.py)
      -> HTTPS App Runner FastAPI
          -> S3 Phase-2 artifacts through the App Runner instance role
```

The EC2 UI does not load models, use boto3, or read S3. Open-Meteo weather is
still fetched and cached by Streamlit, then sent to FastAPI with each request.

## Preserved deployment

The following Community Cloud files are independent and are not part of this
deployment:

```text
app.py
requirements.txt
runtime.txt
src/bixi/streamlit_local_serving.py
artifacts/streamlit-community-cloud/
```

## 1. Validate locally

Build and start the API in local-artifact mode:

```powershell
docker build -f docker/Dockerfile.api -t bixi-api .
docker run -d --rm --name bixi-api-local `
  -e BIXI_SERVING_MODE=local `
  -p 8000:8000 bixi-api

Invoke-RestMethod http://localhost:8000/health
```

In a second terminal, run the FastAPI-backed UI:

```powershell
$env:BIXI_API_URL = "http://host.docker.internal:8000"
docker build -f docker/Dockerfile.streamlit_fastapi -t bixi-streamlit-fastapi .
docker run --rm -p 8502:8501 `
  -e BIXI_API_URL=$env:BIXI_API_URL `
  bixi-streamlit-fastapi
```

Open `http://localhost:8502`, then stop the API container:

```powershell
docker stop bixi-api-local
```

## 2. Deploy the App Runner API

Run CDK from the laptop with Docker Desktop running and AWS SSO authenticated:

```powershell
$env:AWS_PROFILE = "<your-sso-profile>"
$env:AWS_DEFAULT_REGION = "us-east-2"
aws sso login --profile $env:AWS_PROFILE
$env:CDK_DEFAULT_ACCOUNT = (aws sts get-caller-identity --query Account --output text)
$env:CDK_DEFAULT_REGION = "us-east-2"

cd infra
python -m pip install -r requirements.txt
npx --yes aws-cdk@2 bootstrap "aws://$($env:CDK_DEFAULT_ACCOUNT)/us-east-2"
npx --yes aws-cdk@2 synth BixiServe
npx --yes aws-cdk@2 diff BixiServe
npx --yes aws-cdk@2 deploy BixiServe
```

Deploy `BixiServe`, not `--all`. CDK creates or updates:

- the FastAPI image asset in ECR;
- the `bixi-api` App Runner service;
- the ECR access role and S3 runtime role;
- a Secrets Manager API key;
- the `/health` health check and public HTTPS service URL.

The service uses `1 vCPU / 2 GB` so the two model bundles and all-station
rebalancing calculation have predictable headroom.

Existing S3 artifacts are reused; no model upload is required.

## 3. Read and verify the outputs

From PowerShell:

```powershell
$apiUrl = aws cloudformation describe-stacks `
  --stack-name BixiServe --region us-east-2 `
  --query "Stacks[0].Outputs[?OutputKey=='ApiServiceUrl'].OutputValue | [0]" `
  --output text

$secretArn = aws cloudformation describe-stacks `
  --stack-name BixiServe --region us-east-2 `
  --query "Stacks[0].Outputs[?OutputKey=='ApiKeySecretArn'].OutputValue | [0]" `
  --output text

$apiKey = aws secretsmanager get-secret-value `
  --secret-id $secretArn --region us-east-2 `
  --query SecretString --output text

Invoke-RestMethod "$apiUrl/health"
Invoke-RestMethod "$apiUrl/stations" -Headers @{"X-API-Key"=$apiKey}
```

`/health` is public for App Runner health checks. All data and prediction
endpoints require `X-API-Key` when the App Runner secret is configured.

## 4. Deploy the new UI beside the old EC2 UI

Connect to the existing EC2 instance, update the repo, and set the two values
obtained above:

```bash
cd ~/bixi-demand-mlops-platform
git fetch origin
git checkout main
git pull --ff-only origin main

export BIXI_API_URL="https://<app-runner-service-url>"
export BIXI_API_KEY="<secret-value>"
HOST_PORT=8502 bash scripts/run_streamlit_fastapi_ec2_container.sh
```

Temporarily allow inbound TCP `8502` from your IP in the EC2 security group and
open `http://<elastic-ip>:8502`. The existing direct-S3 UI remains on `8501`.

Check the new deployment:

```bash
docker ps
docker logs --tail 100 bixi-streamlit-fastapi
curl -fsS http://localhost:8502/_stcore/health
```

## 5. Cut over to port 8501

After every page passes validation:

```bash
docker stop bixi-streamlit-ec2
docker rm bixi-streamlit-fastapi
export BIXI_API_URL="https://<app-runner-service-url>"
export BIXI_API_KEY="<secret-value>"
HOST_PORT=8501 bash scripts/run_streamlit_fastapi_ec2_container.sh
```

The existing Elastic IP and inbound TCP `8501` rule remain unchanged. Do not
open port `8000` on EC2; the API is reached over App Runner HTTPS port `443`.

## Rollback

```bash
docker stop bixi-streamlit-fastapi
docker start bixi-streamlit-ec2
```

The Community Cloud packaged-artifact URL is a separate long-term fallback and
is unaffected by App Runner or EC2 changes.
