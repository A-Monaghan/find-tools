#!/usr/bin/env bash
# Run FastAPI backend using a local venv (created on first run if missing).
cd "$(dirname "$0")"
VENV_BIN="./venv/bin"
if [ ! -x "${VENV_BIN}/python3" ]; then
  echo "Creating venv in $(pwd)/venv …"
  python3 -m venv venv
fi
"${VENV_BIN}/pip" install -q -r requirements.txt
exec "${VENV_BIN}/python3" run_fastapi.py
