#!/usr/bin/env bash
# Replace the Circle TESTNET API key (and optionally the testnet client key) on
# the production VM without the keys ever appearing on screen, in chat, or in
# shell history. Mainnet keys (CIRCLE_API_KEY_LIVE, ...) are not touched.
#
#   bash scripts/rotate_circle_testnet_keys.sh
#   BOARDMAN_VM=ubuntu@1.2.3.4 bash scripts/rotate_circle_testnet_keys.sh
#
# Order:
#   1. Circle console (testnet): create a new API key (and client key if you
#      rotate that too). Do NOT delete the old ones yet.
#   2. Run this script. It checks the new API key against Circle first, then
#      writes it, restarts the API/bot/house, and checks the server can still
#      see the Boardman wallet set.
#   3. Only after "Rotation OK": delete the old keys in the Circle console.
#
# The entity secret belongs to the Circle account, not to an API key, so the
# existing wallets keep working with the new key.
set -euo pipefail
VM="${BOARDMAN_VM:-ubuntu@150.230.112.144}"
CIRCLE_API="${CIRCLE_API_BASE:-https://api.circle.com}"

read -rs -p "New testnet API key (starts TEST_API_KEY:, hidden): " API_KEY; echo
case "$API_KEY" in
  TEST_API_KEY:*) ;;
  LIVE_API_KEY:*) echo "That is a LIVE key. This script only rotates the testnet key." >&2; exit 1 ;;
  *) echo "Expected a key starting with TEST_API_KEY:" >&2; exit 1 ;;
esac
read -rs -p "New testnet client key (starts TEST_CLIENT_KEY:, Enter to keep the old one): " CLIENT_KEY; echo
if [ -n "$CLIENT_KEY" ]; then
  case "$CLIENT_KEY" in
    TEST_CLIENT_KEY:*) ;;
    *) echo "Expected a client key starting with TEST_CLIENT_KEY:" >&2; exit 1 ;;
  esac
fi

echo "== checking the new API key with Circle"
# The key goes to curl on stdin, never on the command line (ps would show it).
code=$(printf 'Authorization: Bearer %s\n' "$API_KEY" \
  | curl -s -o /dev/null -w '%{http_code}' -m 20 -H @- "$CIRCLE_API/v1/w3s/wallets?pageSize=1")
if [ "$code" != "200" ]; then
  echo "Circle rejected the new key (HTTP $code). Nothing was changed." >&2
  exit 1
fi
echo "   Circle accepted it."

ROTATE_CLIENT="${CLIENT_KEY:+1}"
echo "== saving on the server"
{
  printf 'CIRCLE_API_KEY=%s\n' "$API_KEY"
  if [ -n "$CLIENT_KEY" ]; then printf 'CIRCLE_CLIENT_KEY=%s\n' "$CLIENT_KEY"; fi
} | ssh -o ConnectTimeout=20 "$VM" "ROTATE_CLIENT='$ROTATE_CLIENT'; export ROTATE_CLIENT; "'set -euo pipefail; cd ~/boardman; umask 077
  mkdir -p ~/backups
  stamp=$(date -u +%Y%m%dT%H%M%S)
  cp .env ~/backups/env.before-circle-rotation.$stamp
  keys="CIRCLE_API_KEY"
  [ -n "${ROTATE_CLIENT:-}" ] && keys="CIRCLE_API_KEY|CIRCLE_CLIENT_KEY"
  grep -vE "^($keys)=" .env > .env.new || true
  printf "\n# Circle testnet keys (rotated %s by scripts/rotate_circle_testnet_keys.sh)\n" "$stamp" >> .env.new
  cat >> .env.new
  chmod 600 .env.new && mv .env.new .env
  echo "   saved (old .env backed up to ~/backups/env.before-circle-rotation.$stamp)"

  echo "== restarting"
  docker compose up -d --force-recreate --no-deps boardman-api boardman-bot boardman-house >/dev/null 2>&1
  for _ in $(seq 1 60); do
    curl -sf --max-time 3 http://127.0.0.1:8000/api/healthz >/dev/null && break
    sleep 3
  done

  echo "== checking the server with the new key"
  docker compose exec -T boardman-api python - <<PY
import json, os, sys, urllib.request
key = os.environ.get("CIRCLE_API_KEY", "")
base = os.environ.get("CIRCLE_API_BASE", "https://api.circle.com")
ws = os.environ.get("CIRCLE_WALLET_SET_ID", "")
def get(path):
    req = urllib.request.Request(base + path, headers={"Authorization": "Bearer " + key})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)
try:
    if ws:
        get("/v1/w3s/walletSets/" + ws)
        print("   new key sees the Boardman wallet set")
    else:
        get("/v1/w3s/wallets?pageSize=1")
        print("   new key works (no CIRCLE_WALLET_SET_ID to check)")
except Exception as exc:
    print("   CHECK FAILED:", type(exc).__name__, str(exc)[:120])
    sys.exit(1)
PY
'
unset API_KEY CLIENT_KEY
cat <<EOF

Rotation OK. Now in the Circle console (testnet), delete the OLD API key
${ROTATE_CLIENT:+and the old client key }(keep the new ones you just created).
EOF
