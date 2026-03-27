#!/usr/bin/env bash
# Start the FastAPI app using the repo-root venv (./venv). Docker is optional for DB/Qdrant/Redis only.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="${ROOT}/venv/bin/python"
if [[ ! -x "$PY" ]]; then
  echo "No interpreter at ${PY}" >&2
  echo "Create venv with Python 3.12 (3.13 breaks pinned qdrant-client), then install deps:" >&2
  echo "  cd \"${ROOT}\" && python3.12 -m venv venv && ./venv/bin/pip install -r backend/requirements.txt" >&2
  exit 1
fi
# CWD = repo root so pydantic loads ./.env (backend only uses env_file ".env").
cd "${ROOT}"
export PYTHONPATH="${ROOT}/backend"
exec "$PY" -m uvicorn main:app --host 0.0.0.0 --port 8000 "$@"
