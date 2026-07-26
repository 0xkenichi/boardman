#!/usr/bin/env bash
# Run Rematch / ClawStation on your laptop (Mac/Linux).
# Keep the lid open or plug in power; uses caffeinate on macOS.
#
# Usage (from rematch repo root):
#   chmod +x deploy/start_free_local.sh
#   ./deploy/start_free_local.sh

set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ ! -f .env ]]; then
  echo "Missing .env in $ROOT"
  echo "Copy .env.example → .env and fill TELEGRAM_BOT_TOKEN_CLAWSTATION, SUPABASE_*, CIRCLE_*"
  exit 1
fi

# Ensure monorepo-style imports resolve in this standalone checkout
if [[ ! -e gaming/src ]]; then
  mkdir -p gaming
  ln -sfn ../src gaming/src
  touch gaming/__init__.py
fi
if [[ ! -e backend ]]; then
  ln -sfn src/backend backend
fi
if [[ ! -e gaming/config ]]; then
  ln -sfn ../config gaming/config
fi
if [[ ! -e gaming/data ]]; then
  ln -sfn ../data gaming/data
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
export PYTHONPATH="${ROOT}${PYTHONPATH:+:$PYTHONPATH}"
export BLOCKED_REGIONS_FILE="${BLOCKED_REGIONS_FILE:-$ROOT/config/blocked_regions.json}"

mkdir -p /tmp/clawstation-logs
API_LOG=/tmp/clawstation-logs/api.log
BOT_LOG=/tmp/clawstation-logs/bot.log

PY="${ROOT}/.venv/bin/python"
if [[ ! -x "$PY" ]]; then
  PY=python3
fi

# Stop previous local instances if any
if [[ -f /tmp/clawstation-logs/api.pid ]]; then
  kill "$(cat /tmp/clawstation-logs/api.pid)" 2>/dev/null || true
fi
if [[ -f /tmp/clawstation-logs/bot.pid ]]; then
  kill "$(cat /tmp/clawstation-logs/bot.pid)" 2>/dev/null || true
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
echo "[free-local] health: curl -s localhost:8000/ || curl -s localhost:8000/api/healthz"
echo "[free-local] stop:   kill \$(cat /tmp/clawstation-logs/api.pid /tmp/clawstation-logs/bot.pid)"
