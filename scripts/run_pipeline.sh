#!/usr/bin/env bash
# Submit the BIXI pipeline to AWS Batch (cloud training).
#
#   ./scripts/run_pipeline.sh                         # full rebuild, both targets
#   ./scripts/run_pipeline.sh --from train            # resume from training
#   ./scripts/run_pipeline.sh --targets departure --only drift --force
#
# Reads the CDK outputs + SSM params produced by `cdk deploy`.
set -euo pipefail
REGION="${AWS_DEFAULT_REGION:-us-east-2}"

out() { aws cloudformation describe-stacks --stack-name "$1" --region "$REGION" \
  --query "Stacks[0].Outputs[?OutputKey=='$2'].OutputValue" --output text; }

QUEUE="$(out BixiBatch JobQueueName)"
JOBDEF="$(out BixiBatch JobDefinitionName)"
BUCKET="$(aws ssm get-parameter --name /bixi/pipeline-bucket --region "$REGION" \
  --query Parameter.Value --output text)"
DATA_BUCKET="$(aws ssm get-parameter --name /bixi/data-bucket --region "$REGION" \
  --query Parameter.Value --output text)"
MLFLOW="$(aws ssm get-parameter --name /bixi/mlflow-tracking-uri --region "$REGION" \
  --query Parameter.Value --output text 2>/dev/null || echo '')"

ARGS=("$@")
[ ${#ARGS[@]} -eq 0 ] && ARGS=(--from ingest --targets both --run-id cloud-2024 --n-trials 40)

CMD_JSON="$(python3 -c 'import json,sys; print(json.dumps(sys.argv[1:]))' "${ARGS[@]}")"
OVERRIDES="$(python3 - "$CMD_JSON" "$MLFLOW" "$BUCKET" "$DATA_BUCKET" <<'PY'
import json, sys
cmd = json.loads(sys.argv[1])
env = [
    {"name": "BIXI_PIPELINE_BUCKET", "value": sys.argv[3]},
    {"name": "BIXI_DATA_BUCKET", "value": sys.argv[4]},
]
if sys.argv[2]:
    env.append({"name": "MLFLOW_TRACKING_URI", "value": sys.argv[2]})
print(json.dumps({"command": cmd, "environment": env}))
PY
)"

echo "Queue=$QUEUE JobDef=$JOBDEF MLflow=$MLFLOW"
echo "DataBucket=$DATA_BUCKET PipelineBucket=$BUCKET"
echo "Command: ${ARGS[*]}"
aws batch submit-job --region "$REGION" \
  --job-name "bixi-pipeline-$(date +%s)" \
  --job-queue "$QUEUE" --job-definition "$JOBDEF" \
  --container-overrides "$OVERRIDES" \
  --query '{jobId:jobId,jobName:jobName}'
