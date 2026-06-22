# Rebuild and deploy EC2 Streamlit + App Runner FastAPI

This guide starts from an empty AWS environment. It does not require an existing
S3 bucket, model, feature table, EC2 instance, or API service.

```text
Public BIXI/Open-Meteo data
  -> CDK data bucket
  -> AWS Batch full pipeline
  -> CDK pipeline bucket (models and monitoring)
  -> App Runner FastAPI
  -> EC2 Streamlit + Elastic IP
```

The packaged-artifact `app.py` deployment is independent and remains available
after every AWS resource is removed.

## 1. Prerequisites

Run deployment commands after this code has been merged to `main`. The EC2
bootstrap deliberately checks out `main`, not a temporary feature branch.

Install on the deployment laptop:

- Docker Desktop with a running Linux engine;
- AWS CLI v2 and an IAM Identity Center profile;
- Node.js with `npm`/`npx`;
- Python 3.12 in a clean virtual or Conda environment.

Verify:

```powershell
docker version
aws --version
node --version
python --version
aws sso login --profile bixi
aws sts get-caller-identity --profile bixi
```

App Runner must already be available to the AWS account. AWS recommends ECS
Express Mode for accounts that can no longer create a new App Runner service.

## 2. One-command deployment

From the repository root in PowerShell:

```powershell
.\scripts\deploy_from_scratch.ps1 `
  -AwsProfile bixi `
  -Region us-east-2 `
  -RunId cloud-2024 `
  -MlflowAllowCidr "<your-public-ip>/32" `
  -UiAllowCidr "0.0.0.0/0" `
  -RepoRef main
```

The script performs these operations in order:

1. authenticates with AWS IAM Identity Center;
2. bootstraps CDK;
3. deploys `BixiNetwork`, `BixiStorage`, `BixiMlflow`, and `BixiBatch`;
4. submits and waits for the complete Batch pipeline;
5. stops immediately if Batch fails;
6. deploys `BixiServe` only after model and baseline artifacts exist;
7. deploys `BixiUi`, which builds and starts Streamlit on EC2;
8. prints the public Streamlit URL.

The full pipeline is:

```text
ingest -> features -> serving -> data -> train
       -> explain -> fairness -> drift -> register
```

## 3. Resources created

`BixiStorage` creates two private, encrypted buckets:

- Data bucket: downloaded trips/weather, cleaned demand, feature tables, and
  serving baselines;
- Pipeline bucket: encoders, models, metrics, MLflow artifacts, explainability,
  fairness, drift, and registry metadata.

Their generated names are stored in:

```text
/bixi/data-bucket
/bixi/pipeline-bucket
```

Batch has read/write access to both buckets. App Runner has read-only access.
The EC2 UI has no S3 permission and receives only the API URL and permission to
read its API key from Secrets Manager during bootstrap.

## 4. Manual deployment

Use Git Bash or WSL for the shell scripts:

```bash
export AWS_PROFILE=bixi
export AWS_DEFAULT_REGION=us-east-2
export BIXI_ALLOW_CIDR=<your-public-ip>/32
export BIXI_RUN_ID=cloud-2024

aws sso login --profile "$AWS_PROFILE"
./scripts/deploy_infra.sh
./scripts/run_pipeline.sh
```

Wait for the submitted Batch job to reach `SUCCEEDED`. Do not deploy App Runner
while the job is running because the API loads S3 model bundles at startup.

Then deploy the serving tier:

```bash
export BIXI_UI_CIDR=0.0.0.0/0
export BIXI_REPO_REF=main
./scripts/deploy_serving.sh
```

## 5. Verify the deployment

Read the URLs from CloudFormation:

```powershell
$apiUrl = aws cloudformation describe-stacks `
  --profile bixi --region us-east-2 --stack-name BixiServe `
  --query "Stacks[0].Outputs[?OutputKey=='ApiServiceUrl'].OutputValue | [0]" `
  --output text

$streamlitUrl = aws cloudformation describe-stacks `
  --profile bixi --region us-east-2 --stack-name BixiUi `
  --query "Stacks[0].Outputs[?OutputKey=='StreamlitUrl'].OutputValue | [0]" `
  --output text

Invoke-RestMethod "$apiUrl/health"
$streamlitUrl
```

The Streamlit container can take several minutes to build during first boot.
Use Systems Manager Session Manager instead of opening SSH, then inspect:

```bash
sudo tail -f /var/log/cloud-init-output.log
sudo docker ps
curl -fsS http://localhost:8501/_stcore/health; echo
```

## 6. Redeploy after a code change

Merge the change to `main`, then run:

```bash
export AWS_PROFILE=bixi
export AWS_DEFAULT_REGION=us-east-2
export BIXI_RUN_ID=cloud-2024
export BIXI_REPO_REF=main
./scripts/deploy_serving.sh
```

The deployment ID changes on every run, replacing the EC2 UI so its bootstrap
always checks out the latest `main`. App Runner is rebuilt from the current local
checkout.

## 7. Delete all BIXI resources

```bash
export AWS_PROFILE=bixi
export AWS_DEFAULT_REGION=us-east-2
./scripts/teardown.sh
```

This permanently deletes both CDK buckets and every BIXI application stack.
`CDKToolkit` and shared CDK asset images remain so a later rebuild can bootstrap
faster. The Community Cloud packaged-artifact deployment is unaffected.

## Security

- Never commit API keys, AWS credentials, `.env`, Streamlit secrets, or PEM files.
- Restrict MLflow to the administrator's `/32` CIDR.
- Port `8501` may be public for a demo; restrict `UiAllowCidr` for private use.
- EC2 uses IMDSv2 and Systems Manager; no SSH key pair is required.
- App Runner, EC2, Elastic IP, Batch, ECR, S3, and Secrets Manager can incur cost.
