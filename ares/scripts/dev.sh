#!/usr/bin/env bash
# ARES development launcher — starts backend + frontend together.
# Usage:  ./scripts/dev.sh [--sim]
#   --sim   explicitly enable the SIMULATED market-data feed (demo/testing).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND="$ROOT/backend"
FRONTEND="$ROOT/frontend"

if [[ "${1:-}" == "--sim" ]]; then
  export ARES_MARKET_DATA__MODE=simulation
  echo "[ares] SIMULATION market data enabled — prices are labeled SIMULATED, not live."
fi

if [[ ! -d "$BACKEND/.venv" ]]; then
  echo "[ares] Creating Python venv and installing backend dependencies…"
  python3 -m venv "$BACKEND/.venv"
  "$BACKEND/.venv/bin/pip" install -q -r "$BACKEND/requirements.txt"
fi

if [[ ! -d "$FRONTEND/node_modules" ]]; then
  echo "[ares] Installing frontend dependencies…"
  (cd "$FRONTEND" && npm install --no-audit --no-fund)
fi

cleanup() { kill 0 2>/dev/null || true; }
trap cleanup EXIT INT TERM

echo "[ares] Starting backend on :8000…"
(cd "$BACKEND" && exec .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000) &

echo "[ares] Starting frontend on :5173…"
(cd "$FRONTEND" && exec npm run dev) &

echo "[ares] ARES is starting. Open http://localhost:5173"
wait
