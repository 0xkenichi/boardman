#!/usr/bin/env bash
# Run ClawStation for free on your own machine (Mac/Linux) 24/7 while the lid stays open
# or when connected to power + caffeinate. For true always-on free hosts, see FREE_24_7.md
#
# Usage (from repo root / worktree root):
#   chmod +x gaming/deploy/start_free_local.sh
#   ./gaming/deploy/start_free_local.sh

set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

if [[ ! -f .env ]]; then
  echo "Missing .env in $ROOT"
  exit 1
fi

# shellcheck disable=SC1091
set -a && source .env && set +a

export CLAWSTATION_BOT_MODE="${CLAWSTATION_BOT_MODE:-polling}"
export CLAW_DEFAULT_CHAIN="${CLAW_DEFAULT_CHAIN:-arc}"
export CLAW_MAX_STAKE_USDC="${CLAW_MAX_STAKE_USDC:-25}"
export CLAW_MAX_WITHDRAW_USDC="${CLAW_MAX_WITHDRAW_USDC:-50}"
export CLAW_DAILY_WITHDRAW_CAP_USDC="${CLAW_DAILY_WITHDRAW_CAP_USDC:-100}"
export CLAW_PAUSED="${CLAW_PAUSED:-0}"
export WALLET_WATCH_INTERVAL_SEC="${WALLET_WATCH_INTERVAL_SEC:-45}"
export LOG_LEVEL="${LOG_LEVEL:-INFO}"
export PYTHONUNBUFFERED=1

mkdir -p /tmp/clawstation-logs
API_LOG=/tmp/clawstation-logs/api.log
BOT_LOG=/tmp/clawstation-logs/bot.log

PY="${ROOT}/.venv/bin/python"
if [[ ! -x "$PY" ]]; then
  PY=python3
fi

echo "[free-local] starting API → $API_LOG"
nohup "$PY" -m uvicorn gaming.src.backend.main:app --host 0.0.0.0 --port "${PORT:-8000}" \
  >>"$API_LOG" 2>&1 &
echo $! > /tmp/clawstation-logs/api.pid

echo "[free-local] starting bot → $BOT_LOG"
nohup "$PY" -m gaming.src.bot.main >>"$BOT_LOG" 2>&1 &
echo $! > /tmp/clawstation-logs/bot.pid

# macOS: prevent sleep while charging / plugged in (no-op on Linux)
if command -v caffeinate >/dev/null 2>&1; then
  nohup caffeinate -dims -w "$(cat /tmp/clawstation-logs/bot.pid)" >>/tmp/clawstation-logs/caffeinate.log 2>&1 &
  echo "[free-local] caffeinate attached (Mac sleep prevention)"
fi

echo "[free-local] API pid=$(cat /tmp/clawstation-logs/api.pid) BOT pid=$(cat /tmp/clawstation-logs/bot.pid)"
echo "[free-local] health: curl -s localhost:8000/api/healthz"
echo "[free-local] stop:   kill \$(cat /tmp/clawstation-logs/*.pid)"
