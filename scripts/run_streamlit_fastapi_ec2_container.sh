#!/usr/bin/env bash
# Build and run the FastAPI-backed Streamlit UI on the existing EC2 instance.

set -euo pipefail

IMAGE_NAME="${IMAGE_NAME:-bixi-streamlit-fastapi}"
CONTAINER_NAME="${CONTAINER_NAME:-bixi-streamlit-fastapi}"
HOST_PORT="${HOST_PORT:-8501}"

: "${BIXI_API_URL:?Set BIXI_API_URL to the App Runner service URL}"
: "${BIXI_API_KEY:?Set BIXI_API_KEY to the App Runner API key}"
export BIXI_API_TIMEOUT="${BIXI_API_TIMEOUT:-120}"
export BIXI_API_KEY

echo "Checking the protected App Runner endpoint..."
if ! curl -fsS \
  -H "X-API-Key: $BIXI_API_KEY" \
  "${BIXI_API_URL%/}/stations" >/dev/null; then
  echo "App Runner validation failed. Check BIXI_API_URL and BIXI_API_KEY." >&2
  exit 1
fi

docker build -f docker/Dockerfile.streamlit_fastapi -t "$IMAGE_NAME" .
docker rm -f "$CONTAINER_NAME" >/dev/null 2>&1 || true
docker run -d \
  --name "$CONTAINER_NAME" \
  --restart unless-stopped \
  -p "$HOST_PORT:8501" \
  -e BIXI_API_URL \
  -e BIXI_API_TIMEOUT \
  -e BIXI_API_KEY \
  "$IMAGE_NAME"

echo "Started $CONTAINER_NAME on http://<EC2-public-ip>:$HOST_PORT"
echo "FastAPI backend: $BIXI_API_URL"
echo "Check logs with: docker logs -f $CONTAINER_NAME"
