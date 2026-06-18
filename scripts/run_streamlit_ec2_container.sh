#!/usr/bin/env bash
# Build and run the EC2-only Streamlit container.
#
# This script is intended to run on the EC2 instance. It does not pass AWS keys.
# S3 access should come from the EC2 IAM role attached to the instance.

set -euo pipefail

IMAGE_NAME="${IMAGE_NAME:-bixi-streamlit-ec2}"
CONTAINER_NAME="${CONTAINER_NAME:-bixi-streamlit-ec2}"
HOST_PORT="${HOST_PORT:-8501}"

export AWS_DEFAULT_REGION="${AWS_DEFAULT_REGION:-us-east-2}"
export AWS_REGION="${AWS_REGION:-$AWS_DEFAULT_REGION}"
export BIXI_RUN_ID="${BIXI_RUN_ID:-cloud-2024}"
export BIXI_PIPELINE_BUCKET="${BIXI_PIPELINE_BUCKET:-bixistorage-pipelinebucketb967bd35-icnkid23rfsa}"
export BIXI_PIPELINE_PREFIX="${BIXI_PIPELINE_PREFIX:-bixi-mlops}"
export BIXI_DATA_BUCKET="${BIXI_DATA_BUCKET:-insy684}"
export BIXI_BASELINE_PREFIX="${BIXI_BASELINE_PREFIX:-bixi-serving-artifacts}"

docker build -f docker/Dockerfile.streamlit_ec2 -t "$IMAGE_NAME" .
docker rm -f "$CONTAINER_NAME" >/dev/null 2>&1 || true
docker run -d \
  --name "$CONTAINER_NAME" \
  --restart unless-stopped \
  -p "$HOST_PORT:8501" \
  -e AWS_DEFAULT_REGION \
  -e AWS_REGION \
  -e BIXI_RUN_ID \
  -e BIXI_PIPELINE_BUCKET \
  -e BIXI_PIPELINE_PREFIX \
  -e BIXI_DATA_BUCKET \
  -e BIXI_BASELINE_PREFIX \
  "$IMAGE_NAME"

echo "Started $CONTAINER_NAME on http://<EC2-public-ip>:$HOST_PORT"
echo "Check logs with: docker logs -f $CONTAINER_NAME"
