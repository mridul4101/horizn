#!/usr/bin/env bash
# start.sh – Launch FastAPI backend + Vite frontend together.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

# Activate venv
if [[ ! -d ".venv" ]]; then
    echo "❌  .venv not found. Run ./scripts/setup.sh first." >&2
    exit 1
fi
# shellcheck disable=SC1091
source .venv/bin/activate

# Read API_HOST / API_PORT from .env safely without sourcing
if [[ -f ".env" ]]; then
    _cfg_host=$(grep -E '^[[:space:]]*API_HOST=' .env | cut -d '=' -f2- | tr -d '"'\'' ' || true)
    _cfg_port=$(grep -E '^[[:space:]]*API_PORT=' .env | cut -d '=' -f2- | tr -d '"'\'' ' || true)
    [[ -n "${_cfg_host}" ]] && API_HOST="${_cfg_host}"
    [[ -n "${_cfg_port}" ]] && API_PORT="${_cfg_port}"
fi

API_HOST="${API_HOST:-127.0.0.1}"
API_PORT="${API_PORT:-8000}"

# ---------------------------------------------------------------------------
# Start FastAPI in background; remember its PID for cleanup
# ---------------------------------------------------------------------------
echo "🚀  Starting Horizn API on http://${API_HOST}:${API_PORT} …"
uvicorn horizn.api.main:app --host "$API_HOST" --port "$API_PORT" --reload &
UVICORN_PID=$!

# Trap Ctrl-C / SIGTERM → kill uvicorn before exiting
cleanup() {
    echo ""
    echo "🛑  Shutting down Horizn API (PID $UVICORN_PID)…"
    kill "$UVICORN_PID" 2>/dev/null || true
    wait "$UVICORN_PID" 2>/dev/null || true
    echo "    Done."
}
trap cleanup INT TERM

# ---------------------------------------------------------------------------
# Start Vite dev server in foreground (blocks until Ctrl-C)
# ---------------------------------------------------------------------------
if [[ -f "ui/package.json" ]]; then
    echo "🌐  Starting Vite UI…"
    npm run dev --prefix ui
else
    echo "⚠️   ui/package.json not found – skipping Vite (run after Worker 3 creates the UI)"
    # Keep script alive so uvicorn stays up for direct API testing
    wait "$UVICORN_PID"
fi
