#!/usr/bin/env bash
# Videl-Api Docker Startup Script
set -euo pipefail

echo "========================================"
echo "  Videl-Api v3.2.0 - Docker Startup"
echo "========================================"

# Wait for dependencies if needed
if [ "${WAIT_FOR_ARIA2C:-false}" = "true" ]; then
  echo "Waiting for aria2c at ${ARIA2C_RPC_URL:-http://aria2c:6800/jsonrpc}..."
  for i in $(seq 1 30); do
    if curl -sf "${ARIA2C_RPC_URL:-http://aria2c:6800/jsonrpc}" >/dev/null 2>&1; then
      echo "aria2c is ready."
      break
    fi
    echo "  attempt $i/30 - aria2c not ready, waiting 2s..."
    sleep 2
  done
fi

# Ensure directories exist
mkdir -p /app/downloads /app/logs

# Set log level default
export VIDEL_LOG_LEVEL="${VIDEL_LOG_LEVEL:-INFO}"
export VIDEL_LOG_FORMAT="${VIDEL_LOG_FORMAT:-console}"

echo "Starting Videl-Api on ${API_HOST:-0.0.0.0}:${API_PORT:-8000}"
echo "Log level: ${VIDEL_LOG_LEVEL}"
echo "Log format: ${VIDEL_LOG_FORMAT}"
echo "Download dir: ${DOWNLOAD_DIR:-/app/downloads}"
echo ""

# Start the application
exec python -m uvicorn main:app \
  --host "${API_HOST:-0.0.0.0}" \
  --port "${API_PORT:-8000}" \
  --workers "${UVICORN_WORKERS:-1}" \
  --log-level "${UVICORN_LOG_LEVEL:-info}"
