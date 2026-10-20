#!/usr/bin/env bash
# Switch the production house to quick-fire friendlies.
#
#   next table opens as soon as a game settles (after_game, 0s gap)
#   2-minute betting lobby, then kickoff
#   betting closes 30s after kickoff, or at 24 plies, whichever comes first
#
# Run from your Mac:  bash scripts/set_friendlies.sh
# Override:  LOBBY_SEC=120 CLOSE_SEC=30 CLOSE_PLIES=24 GAP_SEC=0 bash scripts/set_friendlies.sh
# Back out:  restore ~/backups/env.before-friendlies.* on the VM and set the
#            schedule back from the admin desk.
set -euo pipefail

HOST="${BOARDMAN_VM:-ubuntu@150.230.112.144}"
LOBBY_SEC="${LOBBY_SEC:-120}"
CLOSE_SEC="${CLOSE_SEC:-30}"
CLOSE_PLIES="${CLOSE_PLIES:-24}"
GAP_SEC="${GAP_SEC:-0}"

ssh -o ConnectTimeout=20 "$HOST" \
  LOBBY_SEC="$LOBBY_SEC" CLOSE_SEC="$CLOSE_SEC" CLOSE_PLIES="$CLOSE_PLIES" GAP_SEC="$GAP_SEC" \
  bash -s <<'REMOTE'
set -euo pipefail
cd ~/boardman

echo "== pull"
git pull -q --ff-only origin main
git log --oneline -1

echo "== settings"
mkdir -p ~/backups
stamp=$(date -u +%Y%m%dT%H%M%S)
cp .env ~/backups/env.before-friendlies.$stamp
chmod 600 ~/backups/env.before-friendlies.$stamp
sed -i -E '/^BOARDMAN_(BET_WINDOW_SEC|BOOK_CLOSE_SEC|BOOK_CLOSE_PLIES)=/d' .env
{
  echo "BOARDMAN_BET_WINDOW_SEC=$LOBBY_SEC"
  echo "BOARDMAN_BOOK_CLOSE_SEC=$CLOSE_SEC"
  echo "BOARDMAN_BOOK_CLOSE_PLIES=$CLOSE_PLIES"
} >> .env
grep -E '^BOARDMAN_(BET_WINDOW_SEC|BOOK_CLOSE_SEC|BOOK_CLOSE_PLIES)=' .env

echo "== build + restart"
docker compose build -q
docker compose up -d --force-recreate boardman-api boardman-bot boardman-house

echo "== wait for the API"
for _ in $(seq 1 60); do
  curl -sf --max-time 3 http://127.0.0.1:8000/api/healthz >/dev/null && break
  sleep 3
done

echo "== schedule"
K=$(grep -E '^REMATCH_API_KEY=' .env | cut -d= -f2- | tr -d "\"'")
curl -s --max-time 20 -X POST -H "X-Rematch-Key: $K" -H "Content-Type: application/json" \
  -d "{\"cadence_sec\":$GAP_SEC,\"cadence_mode\":\"after_game\",\"enabled\":true}" \
  http://127.0.0.1:8000/api/stack/agentic/house/schedule >/dev/null
curl -s --max-time 20 -H "X-Rematch-Key: $K" http://127.0.0.1:8000/api/stack/agentic/house/schedule \
  | python3 -c "import json,sys;d=json.load(sys.stdin);s=d.get('schedule',{});print('mode',s.get('cadence_mode'),'gap',s.get('cadence_sec'),'next',d.get('next_game_at'))"

echo "== house log"
sleep 5
docker compose logs --since 2m boardman-house 2>&1 | grep -E "recovery|next game|started house" | tail -5
echo "Friendlies on: ${LOBBY_SEC}s lobby, betting closes ${CLOSE_SEC}s in (or ply ${CLOSE_PLIES})."
REMOTE
