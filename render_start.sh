#!/usr/bin/env bash
# Render web service entrypoint (also referenced from render.yaml).
set -euo pipefail
cd "$(dirname "$0")/../backend"
export PYTHONUNBUFFERED=1
PY="${PYTHON:-python}"
if ! command -v "$PY" >/dev/null 2>&1; then
  PY=python3
fi
"$PY" --version
exec "$PY" -m uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --log-level info
