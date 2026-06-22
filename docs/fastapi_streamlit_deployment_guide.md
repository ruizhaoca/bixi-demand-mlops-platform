# EC2 Streamlit + App Runner FastAPI deployment

This is the cloud-serving deployment for the BIXI application. It is independent
from the packaged-artifact app on Streamlit Community Cloud.

```text
Browser
  -> EC2 public IP:8501
      -> Streamlit container (app_fastapi_ec2.py)
          -> HTTPS App Runner FastAPI
              -> Phase-2 model and baseline artifacts in S3
```

Streamlit fetches and caches Open-Meteo forecasts, but it never loads models or
accesses S3. App Runner loads the model bundles from S3 through its IAM role and
returns engineered features, predictions, monitoring metadata, and rebalancing
results through FastAPI.

## 1. Prerequisites

On the deployment laptop:

- Docker Desktop with a running Linux engine;
- AWS CLI v2 and an authenticated IAM Identity Center profile;
- Node.js with `npm`/`npx`;
- Python 3.12 in a clean virtual or Conda environment.

Confirm the tools:

```powershell
docker version
aws --version
node --version
python --version
```

The Python version must be 3.12. On Windows, use `python`, not a Windows Store
`python3` alias.

Configure and verify AWS SSO:

```powershell
aws configure sso
aws sso login --profile <sso-profile>
aws sts get-caller-identity --profile <sso-profile>
```

## 2. Optional local validation

From the repository root, start the API in packaged-artifact mode:

```powershell
docker build -f docker/Dockerfile.api -t bixi-api .
docker run -d --rm --name bixi-api-local `
  -e BIXI_SERVING_MODE=local `
  -p 8000:8000 bixi-api
Invoke-RestMethod http://localhost:8000/health
```

In a second PowerShell terminal, start the API-backed Streamlit image:

```powershell
docker build -f docker/Dockerfile.streamlit_fastapi -t bixi-streamlit-fastapi .
docker run --rm -p 8501:8501 `
  -e BIXI_API_URL=http://host.docker.internal:8000 `
  bixi-streamlit-fastapi
```

Open `http://localhost:8501`, then stop the API container:

```powershell
docker stop bixi-api-local
```

## 3. Deploy FastAPI to App Runner

Run this section on the deployment laptop, not on EC2. Activate the Python 3.12
environment and set the AWS context:

```powershell
$env:AWS_PROFILE = "<sso-profile>"
$env:AWS_DEFAULT_REGION = "us-east-2"
$env:CDK_DEFAULT_REGION = "us-east-2"
aws sso login --profile $env:AWS_PROFILE
$env:CDK_DEFAULT_ACCOUNT = aws sts get-caller-identity `
  --profile $env:AWS_PROFILE --query Account --output text
```

Install CDK Python dependencies and deploy only `BixiServe`:

```powershell
cd infra
python -m pip install -r requirements.txt
npx --yes aws-cdk@2 --app "python app.py" bootstrap "aws://$($env:CDK_DEFAULT_ACCOUNT)/us-east-2"
npx --yes aws-cdk@2 --app "python app.py" synth BixiServe
npx --yes aws-cdk@2 --app "python app.py" diff BixiServe
npx --yes aws-cdk@2 --app "python app.py" deploy BixiServe
```

Do not deploy `--all`. The `BixiServe` stack creates or updates:

- the FastAPI Docker image asset in ECR;
- the `bixi-api` App Runner service;
- ECR access and S3 read-only runtime IAM roles;
- a Secrets Manager API key;
- a public HTTPS service with a `/health` check.

App Runner uses `1 vCPU / 2 GB`. Existing S3 artifacts are reused; no model
upload is required.

## 4. Read and verify the App Runner outputs

From local PowerShell:

```powershell
$apiUrl = aws cloudformation describe-stacks `
  --profile $env:AWS_PROFILE `
  --stack-name BixiServe --region us-east-2 `
  --query "Stacks[0].Outputs[?OutputKey=='ApiServiceUrl'].OutputValue | [0]" `
  --output text

$secretArn = aws cloudformation describe-stacks `
  --profile $env:AWS_PROFILE `
  --stack-name BixiServe --region us-east-2 `
  --query "Stacks[0].Outputs[?OutputKey=='ApiKeySecretArn'].OutputValue | [0]" `
  --output text

$apiKey = (aws secretsmanager get-secret-value `
  --profile $env:AWS_PROFILE `
  --secret-id $secretArn --region us-east-2 `
  --query SecretString --output text).Trim()

$apiKey.Length
$apiKey -match '^[A-Za-z0-9]{40}$'
Invoke-RestMethod "$apiUrl/health"
Invoke-RestMethod "$apiUrl/stations" -Headers @{"X-API-Key"=$apiKey}
```

The key checks should print `40` and `True`. `/health` is public; every data and
prediction endpoint requires `X-API-Key`. Never commit or publish the secret.

Copy the clean key to the local clipboard:

```powershell
Set-Clipboard -Value $apiKey
```

## 5. Create or prepare EC2

Create an Ubuntu EC2 instance in `us-east-2`. `t3.medium` is the recommended
minimum for the Streamlit UI. Configure:

- a public subnet and public IPv4 address;
- inbound TCP `8501` from `0.0.0.0/0` for a public demo, or a restricted CIDR;
- SSH/EC2 Instance Connect access restricted to the administrator;
- outbound HTTPS `443` so Streamlit can reach App Runner and Open-Meteo;
- an Elastic IP if the public URL must remain stable.

The Streamlit EC2 instance does not need S3 permissions because only App Runner
accesses the artifacts.

Connect with EC2 Instance Connect or SSH and install Docker/Git:

```bash
sudo apt update
sudo apt install -y docker.io git curl
sudo systemctl enable --now docker
sudo usermod -aG docker "$USER"
```

Log out and reconnect once, then verify:

```bash
docker version
```

## 6. Deploy Streamlit directly on port 8501

Clone the repository or update an existing clean checkout:

```bash
git clone https://github.com/ruizhaoca/bixi-demand-mlops-platform.git
cd bixi-demand-mlops-platform
git checkout main
git pull --ff-only origin main
```

Set the App Runner URL:

```bash
export BIXI_API_URL="https://<app-runner-service-url>"
export BIXI_API_TIMEOUT="120"
```

Enter the API key without putting it in shell history:

```bash
read -r -s BIXI_API_KEY
```

Paste only the 40-character key, press Enter, then validate and export it:

```bash
BIXI_API_KEY=$(printf '%s' "$BIXI_API_KEY" | tr -cd 'A-Za-z0-9')
export BIXI_API_KEY
test "${#BIXI_API_KEY}" -eq 40 || { echo "API key must be 40 characters"; exit 1; }
```

Build and start Streamlit directly on the public port:

```bash
HOST_PORT=8501 bash scripts/run_streamlit_fastapi_ec2_container.sh
```

The script verifies the protected App Runner `/stations` endpoint before it
replaces the Streamlit container.

## 7. Verify the deployment

On EC2:

```bash
docker ps
docker logs --tail 100 bixi-streamlit-fastapi
curl -fsS http://localhost:8501/_stcore/health
docker exec bixi-streamlit-fastapi sh -c \
  'curl -fsS -o /dev/null -w "%{http_code}\n" -H "X-API-Key: $BIXI_API_KEY" "$BIXI_API_URL/stations"'
```

Expected results:

- container status is `healthy`;
- Streamlit health returns `ok`;
- the protected App Runner request returns `200`.

Open the public URL:

```text
http://<elastic-ip>:8501
```

Test single-slot prediction, full-day prediction, custom inputs, monitoring, and
rebalancing before the presentation.

## 8. Redeploy after a code change

After changes are merged to `main`, reconnect to EC2 and run:

```bash
cd ~/bixi-demand-mlops-platform
git checkout main
git pull --ff-only origin main
export BIXI_API_URL="https://<app-runner-service-url>"
export BIXI_API_TIMEOUT="120"
read -r -s BIXI_API_KEY
BIXI_API_KEY=$(printf '%s' "$BIXI_API_KEY" | tr -cd 'A-Za-z0-9')
export BIXI_API_KEY
HOST_PORT=8501 bash scripts/run_streamlit_fastapi_ec2_container.sh
```

If API code, dependencies, Dockerfile, or CDK configuration changed, deploy
`BixiServe` from the laptop first, then rebuild the EC2 Streamlit container.

## 9. Operations and security

- Docker uses `--restart unless-stopped`, so Streamlit restarts after an EC2 reboot.
- Keep EC2 running and the container healthy for the public URL to work.
- Keep App Runner running for predictions to work.
- Do not expose FastAPI on EC2 port `8000`; App Runner is reached over HTTPS `443`.
- Do not commit API keys, AWS credentials, `.env`, or PEM files.
- App Runner, EC2, Elastic IP, ECR, and Secrets Manager may incur AWS charges.
- The Community Cloud packaged-artifact deployment remains the long-term fallback.
