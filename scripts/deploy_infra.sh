#!/usr/bin/env bash
# Provision the rebuild/training infrastructure with AWS CDK.
#
#   export AWS_PROFILE=...            # or have temporary creds exported
#   export BIXI_ALLOW_CIDR=1.2.3.4/32 # who may reach MLflow :5000 / SSH
#   ./scripts/deploy_infra.sh
set -euo pipefail
cd "$(dirname "$0")/../infra"

export CDK_DEFAULT_ACCOUNT="$(aws sts get-caller-identity --query Account --output text)"
export CDK_DEFAULT_REGION="${AWS_DEFAULT_REGION:-us-east-2}"
: "${BIXI_ALLOW_CIDR:?Set BIXI_ALLOW_CIDR to the administrator public IP in CIDR form}"
ALLOW_CIDR="$BIXI_ALLOW_CIDR"

echo "Account=$CDK_DEFAULT_ACCOUNT Region=$CDK_DEFAULT_REGION allow_cidr=$ALLOW_CIDR"
pip install -q -r requirements.txt

npx --yes aws-cdk@2 bootstrap "aws://$CDK_DEFAULT_ACCOUNT/$CDK_DEFAULT_REGION"
npx --yes aws-cdk@2 deploy \
  BixiNetwork BixiStorage BixiMlflow BixiBatch \
  --require-approval never -c allow_cidr="$ALLOW_CIDR"
echo "Done. MLflow URL:"
aws cloudformation describe-stacks --stack-name BixiMlflow --region "$CDK_DEFAULT_REGION" \
  --query "Stacks[0].Outputs[?OutputKey=='MlflowPublicUrl'].OutputValue" --output text
echo "Next: ./scripts/run_pipeline.sh"
