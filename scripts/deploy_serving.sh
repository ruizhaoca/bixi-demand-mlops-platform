#!/usr/bin/env bash
# Deploy the API and EC2 UI only after the full Batch pipeline has succeeded.
set -euo pipefail

REGION="${AWS_DEFAULT_REGION:-us-east-2}"
RUN_ID="${BIXI_RUN_ID:-cloud-2024}"
ALLOW_CIDR="${BIXI_UI_CIDR:-0.0.0.0/0}"
REPO_REF="${BIXI_REPO_REF:-main}"
DEPLOYMENT_ID="${BIXI_DEPLOYMENT_ID:-$(date +%s)}"

cd "$(dirname "$0")/../infra"
export CDK_DEFAULT_ACCOUNT="$(aws sts get-caller-identity --query Account --output text)"
export CDK_DEFAULT_REGION="$REGION"

npx --yes aws-cdk@2 deploy BixiServe BixiUi \
  --require-approval never \
  -c run_id="$RUN_ID" \
  -c ui_cidr="$ALLOW_CIDR" \
  -c repo_ref="$REPO_REF" \
  -c deployment_id="$DEPLOYMENT_ID"

aws cloudformation describe-stacks --stack-name BixiUi --region "$REGION" \
  --query "Stacks[0].Outputs[?OutputKey=='StreamlitUrl'].OutputValue" --output text
