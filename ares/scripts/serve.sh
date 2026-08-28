#!/usr/bin/env bash
# ARES production launcher (no Docker).
#
#   ./scripts/serve.sh [--sim]
#
# Builds the frontend if needed and starts one process that serves both the API
# and the web app. Open http://<this-machine>:8000 from any device.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND="$ROOT/backend"
FRONTEND="$ROOT/frontend"
PORT="${ARES_SYSTEM__PORT:-8000}"

if [[ "${1:-}" == "--sim" ]]; then
  export ARES_MARKET_DATA__MODE=simulation
  echo "[ares] Simulated market data enabled — every price is labelled SIMULATED."
fi

if [[ ! -d "$BACKEND/.venv" ]]; then
  echo "[ares] Creating the Python environment…"
  python3 -m venv "$BACKEND/.venv"
  "$BACKEND/.venv/bin/pip" install -q -r "$BACKEND/requirements.txt"
fi

if [[ ! -f "$FRONTEND/dist/index.html" ]]; then
  echo "[ares] Building the web app…"
  (cd "$FRONTEND" && npm install --no-audit --no-fund && npm run build)
fi

# Bind to every interface so phones on the same network can reach it.
export ARES_SYSTEM__HOST="${ARES_SYSTEM__HOST:-0.0.0.0}"

echo "[ares] Starting on port $PORT — open http://localhost:$PORT"
if [[ -z "${ARES_ACCESS_TOKEN:-}" ]]; then
  echo "[ares] NOTE: no ARES_ACCESS_TOKEN set. Anyone who can reach this port can use ARES."
  echo "[ares]       Set one in .env before exposing it beyond your own machine."
fi

cd "$BACKEND"
exec .venv/bin/uvicorn app.main:app \
  --host "$ARES_SYSTEM__HOST" --port "$PORT" \
  --proxy-headers --forwarded-allow-ips '*'
