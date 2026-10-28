#!/usr/bin/env bash
# Videl-Api Development Startup Script
set -euo pipefail

echo "========================================"
echo "  Videl-Api v3.2.0 - Dev Server"
echo "========================================"

# Activate virtualenv if it exists
if [ -d .venv ]; then
  echo "Activating virtual environment..."
  source .venv/bin/activate
fi

# Ensure directories exist
mkdir -p downloads logs

# Load environment variables from .env if present
if [ -f .env ]; then
  echo "Loading .env..."
  export $(grep -v '^#' .env | grep -v '^$' | xargs)
fi

# Start the server
echo "Starting Videl-Api on http://0.0.0.0:8000"
echo "WebApp: http://localhost:8000/app"
echo "API Docs: http://localhost:8000/docs"
echo ""
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
