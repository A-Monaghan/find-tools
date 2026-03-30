#!/usr/bin/env sh
# Expose the FastAPI app via localtunnel. Start the server first: python run_fastapi.py
# Uses PORT from .env if set, else 5000. Override: ./share_localtunnel.sh 8080

cd "$(dirname "$0")"
# Use first arg, or PORT from .env, or 5000
if [ -n "$1" ]; then
  PORT="$1"
elif [ -f .env ] && grep -q '^PORT=' .env 2>/dev/null; then
  PORT=$(grep '^PORT=' .env | head -1 | cut -d= -f2)
fi
PORT="${PORT:-5000}"
echo "Tunnelling port $PORT — ensure the app is running."
exec npx localtunnel --port "$PORT"
