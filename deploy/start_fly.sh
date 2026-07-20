#!/usr/bin/env bash
# Single Fly machine: API (health checks) + Telegram bot (polling).
# Exit if bot dies so Fly restarts the machine.
set -euo pipefail
cd /app

export PYTHONUNBUFFERED=1
export CLAWSTATION_BOT_MODE="${CLAWSTATION_BOT_MODE:-polling}"
export PORT="${PORT:-8000}"

echo "[fly] starting API on :${PORT}"
uvicorn gaming.src.backend.main:app --host 0.0.0.0 --port "${PORT}" &
API_PID=$!

echo "[fly] starting Rematch bot (polling)"
python -m gaming.src.bot.main &
BOT_PID=$!

# If either exits, stop the other and fail (Fly will restart)
wait -n "$API_PID" "$BOT_PID"
STATUS=$?
echo "[fly] process exited status=$STATUS — shutting down"
kill "$API_PID" "$BOT_PID" 2>/dev/null || true
exit "$STATUS"
