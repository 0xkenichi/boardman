#!/usr/bin/env bash
# Single container: FastAPI (health) + Telegram bot (polling).
# Exit if either dies so Akash restarts the pod.
set -euo pipefail
cd /app

export PYTHONUNBUFFERED=1
export PYTHONPATH="${PYTHONPATH:-/app}"
export CLAWSTATION_BOT_MODE="${CLAWSTATION_BOT_MODE:-polling}"
export CLAW_DEFAULT_CHAIN="${CLAW_DEFAULT_CHAIN:-arc}"
export PORT="${PORT:-8000}"
export BLOCKED_REGIONS_FILE="${BLOCKED_REGIONS_FILE:-/app/config/blocked_regions.json}"

# gaming.src.* layout (also created in Dockerfile)
if [[ ! -e /app/gaming/src ]]; then
  mkdir -p /app/gaming
  ln -sfn /app/src /app/gaming/src
  touch /app/gaming/__init__.py
fi

echo "[akash] starting API on :${PORT}"
uvicorn gaming.src.backend.main:app --host 0.0.0.0 --port "${PORT}" &
API_PID=$!

echo "[akash] starting Rematch bot (polling)"
python -m gaming.src.bot.main &
BOT_PID=$!

cleanup() {
  kill "$API_PID" "$BOT_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

# If either exits, fail the container (orchestrator restarts)
wait -n "$API_PID" "$BOT_PID"
STATUS=$?
echo "[akash] process exited status=${STATUS} — shutting down"
exit "$STATUS"
