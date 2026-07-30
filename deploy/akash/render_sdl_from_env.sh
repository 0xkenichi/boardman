#!/usr/bin/env bash
# Render deploy.yml with image + env from .env for Akash Console paste.
# Writes to deploy/akash/deploy.generated.yml (gitignored pattern via .env.* style —
# this file should NOT be committed; it contains secrets).
#
# Usage:
#   export DOCKERHUB_USER=yourname
#   ./deploy/akash/render_sdl_from_env.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

if [[ ! -f .env ]]; then
  echo "Missing .env in $ROOT"
  exit 1
fi

TAG="${TAG:-latest}"
# Prefer explicit IMAGE, then Docker Hub user, then GHCR default for this org
if [[ -n "${IMAGE:-}" ]]; then
  :
elif [[ -n "${DOCKERHUB_USER:-}" ]]; then
  IMAGE="${DOCKERHUB_USER}/rematch:${TAG}"
else
  IMAGE="ghcr.io/playingsidequest-dotplay/rematch:${TAG}"
fi
OUT="$ROOT/deploy/akash/deploy.generated.yml"
echo "Using image: $IMAGE"

# shellcheck disable=SC1091
set -a
# shellcheck source=/dev/null
source .env
set +a

# Prefer service role; fall back to service key
SUPABASE_SERVICE_ROLE_KEY="${SUPABASE_SERVICE_ROLE_KEY:-${SUPABASE_SERVICE_KEY:-}}"
TELEGRAM_BOT_TOKEN_CLAWSTATION="${TELEGRAM_BOT_TOKEN_CLAWSTATION:-${TELEGRAM_BOT_TOKEN:-}}"

require() {
  local n="$1" v="$2"
  if [[ -z "$v" ]]; then
    echo "Missing required env: $n"
    exit 1
  fi
}

require TELEGRAM_BOT_TOKEN_CLAWSTATION "$TELEGRAM_BOT_TOKEN_CLAWSTATION"
require SUPABASE_URL "$SUPABASE_URL"
require SUPABASE_SERVICE_ROLE_KEY "$SUPABASE_SERVICE_ROLE_KEY"
require CIRCLE_API_KEY "$CIRCLE_API_KEY"
require CIRCLE_ENTITY_SECRET "$CIRCLE_ENTITY_SECRET"
require CIRCLE_WALLET_SET_ID "$CIRCLE_WALLET_SET_ID"

cat >"$OUT" <<EOF
---
version: "2.0"

services:
  rematch:
    image: ${IMAGE}
    expose:
      - port: 8000
        as: 80
        to:
          - global: true
        accept:
          - http
          - https
    env:
      - TELEGRAM_BOT_TOKEN_CLAWSTATION=${TELEGRAM_BOT_TOKEN_CLAWSTATION}
      - TELEGRAM_BOT_USERNAME_CLAWSTATION=${TELEGRAM_BOT_USERNAME_CLAWSTATION:-ClawStationOfficialBot}
      - SUPABASE_URL=${SUPABASE_URL}
      - SUPABASE_SERVICE_ROLE_KEY=${SUPABASE_SERVICE_ROLE_KEY}
      - SUPABASE_SERVICE_KEY=${SUPABASE_SERVICE_KEY:-${SUPABASE_SERVICE_ROLE_KEY}}
      - CIRCLE_API_KEY=${CIRCLE_API_KEY}
      - CIRCLE_CLIENT_KEY=${CIRCLE_CLIENT_KEY:-}
      - CIRCLE_ENTITY_SECRET=${CIRCLE_ENTITY_SECRET}
      - CIRCLE_WALLET_SET_ID=${CIRCLE_WALLET_SET_ID}
      - CLAWSTATION_BOT_MODE=${CLAWSTATION_BOT_MODE:-polling}
      - CLAW_DEFAULT_CHAIN=${CLAW_DEFAULT_CHAIN:-arc}
      - CLAW_MAX_STAKE_USDC=${CLAW_MAX_STAKE_USDC:-25}
      - CLAW_MAX_WITHDRAW_USDC=${CLAW_MAX_WITHDRAW_USDC:-50}
      - CLAW_DAILY_WITHDRAW_CAP_USDC=${CLAW_DAILY_WITHDRAW_CAP_USDC:-100}
      - CLAW_PAUSED=${CLAW_PAUSED:-0}
      - WALLET_WATCH_INTERVAL_SEC=${WALLET_WATCH_INTERVAL_SEC:-45}
      - LOG_LEVEL=${LOG_LEVEL:-INFO}
      - PORT=8000
      - NETWORK=${NETWORK:-testnet}
      - PYTHONUNBUFFERED=1
      - BLOCKED_REGIONS_FILE=/app/config/blocked_regions.json
      - REMATCH_WEB_URL=${REMATCH_WEB_URL:-https://playingsidequest.fun/rematch}

profiles:
  compute:
    rematch:
      resources:
        cpu:
          units: 0.5
        memory:
          size: 512Mi
        storage:
          size: 1Gi
  placement:
    akash:
      pricing:
        rematch:
          denom: uakt
          amount: 10000

deployment:
  rematch:
    akash:
      profile: rematch
      count: 1
EOF

echo "Wrote $OUT (contains secrets — do not commit)"
echo "Upload this file in Akash Console → Upload SDL"
