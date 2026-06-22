#!/usr/bin/env bash
# Delete every BIXI application stack, including both CDK-managed S3 buckets.
# The CDK bootstrap stack and shared CDK asset repository are intentionally kept.
set -euo pipefail

REGION="${AWS_DEFAULT_REGION:-us-east-2}"
cd "$(dirname "$0")/../infra"
export CDK_DEFAULT_ACCOUNT="$(aws sts get-caller-identity --query Account --output text)"
export CDK_DEFAULT_REGION="$REGION"
export JSII_SILENCE_WARNING_UNTESTED_NODE_VERSION=1

echo ">> Destroying all BIXI stacks and their data (irreversible)..."
npx --yes aws-cdk@2 destroy --all --force
echo ">> All BIXI application stacks were deleted."
echo "   CDKToolkit and shared CDK asset images remain for future deployments."
