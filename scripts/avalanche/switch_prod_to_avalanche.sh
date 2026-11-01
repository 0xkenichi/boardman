#!/usr/bin/env bash
# Switch the production Boardman (Oracle VM + Vercel site) to the Avalanche build.
#
# What it does, on the VM (ubuntu@150.230.112.144, ~/boardman):
#   1. backs up .env to ~/backups/env.before-avalanche.<stamp>
#   2. checks out origin/avalanche (the Avalanche build) instead of main
#   3. sets the chain env: Fuji is the only offered chain, the default and the
#      arena chain, with the Fuji BoardmanEscrow v2 + SpectatorPool v2
#   4. sets BOARDMAN_RESOLVER_KEY to the Fuji escrow resolver. The key is read
#      from .fuji/wallets.json on this Mac and piped over ssh; it is never
#      printed. Testnet-only key.
#   5. rebuilds and restarts api, bot and house, then checks /api/healthz
# Then, from this Mac, it deploys the site (defaults to Avalanche) to Vercel.
#
# Dry run by default. Nothing changes until you pass APPLY=1:
#   bash scripts/avalanche/switch_prod_to_avalanche.sh            # show the plan
#   APPLY=1 bash scripts/avalanche/switch_prod_to_avalanche.sh    # do it
#   APPLY=1 SKIP_SITE=1 bash scripts/avalanche/switch_prod_to_avalanche.sh   # VM only
#
# Back out (about 2 minutes): on the VM,
#   cd ~/boardman && cp ~/backups/env.before-avalanche.<stamp> .env \
#     && git checkout main && docker compose up -d --build
# and redeploy the site from main with scripts/deploy_frontend.sh.
#
# After the switch: if the arena runs on-chain (BOARDMAN_AGENTIC_ONCHAIN=1 on
# the VM), each contestant agent wallet needs a little Fuji AVAX and test USDC:
#   https://faucet.circle.com (USDC) and the Builder Hub faucet (AVAX).
set -euo pipefail

HOST="${BOARDMAN_VM:-ubuntu@150.230.112.144}"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
W="${FUJI_WALLETS:-$ROOT/.fuji/wallets.json}"
DEP="$ROOT/contracts/deployments/boardman_v2_avalancheFuji.json"
[ -f "$W" ] || { echo "no $W (the Fuji role wallets)" >&2; exit 1; }
[ -f "$DEP" ] || { echo "no $DEP" >&2; exit 1; }

ESCROW=$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['contracts']['BoardmanEscrow'])" "$DEP")
POOL=$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['contracts']['SpectatorPool'])" "$DEP")
RESOLVER_ADDR=$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['wallets']['resolver']['address'])" "$W")

echo "Avalanche build switch"
echo "  VM:        $HOST (~/boardman -> origin/avalanche)"
echo "  escrow:    $ESCROW"
echo "  pool:      $POOL"
echo "  resolver:  $RESOLVER_ADDR (key piped from $W, not printed)"
echo "  site:      $([ -n "${SKIP_SITE:-}" ] && echo skipped || echo "scripts/deploy_frontend.sh from this checkout")"
if [ "${APPLY:-}" != "1" ]; then
  echo
  echo "Dry run. Re-run with APPLY=1 to make these changes."
  exit 0
fi

# The resolver key goes over stdin as the first line (never on a command
# line or in a log); the remote shell reads it, then runs the script below.
{
  python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['wallets']['resolver']['private_key'])" "$W"
  cat <<'REMOTE'
set -euo pipefail
cd ~/boardman

echo "== backup"
mkdir -p ~/backups
stamp=$(date -u +%Y%m%dT%H%M%S)
cp .env ~/backups/env.before-avalanche.$stamp
chmod 600 ~/backups/env.before-avalanche.$stamp
echo "saved ~/backups/env.before-avalanche.$stamp"

echo "== code"
git fetch -q origin avalanche
git checkout -q -B avalanche origin/avalanche
git log --oneline -1

echo "== settings"
keys="CLAW_ENABLED_CHAINS|CLAW_DEFAULT_CHAIN|BOARDMAN_ARENA_CHAIN|CLAW_ESCROW_ADDRESS_AVALANCHE|SPECTATOR_ESCROW_ADDRESS_AVALANCHE|BOARDMAN_RESOLVER_KEY|NEXT_PUBLIC_SETTLEMENT_CHAIN"
sed -i -E "/^($keys)=/d" .env
{
  echo "CLAW_ENABLED_CHAINS=avalanche"
  echo "CLAW_DEFAULT_CHAIN=avalanche"
  echo "BOARDMAN_ARENA_CHAIN=avalanche"
  echo "CLAW_ESCROW_ADDRESS_AVALANCHE=$ESCROW"
  echo "SPECTATOR_ESCROW_ADDRESS_AVALANCHE=$POOL"
  echo "BOARDMAN_RESOLVER_KEY=$RESOLVER_KEY"
} >> .env
grep -E "^($keys)=" .env | sed -E "s/^(BOARDMAN_RESOLVER_KEY)=.*/\1=<set>/"

echo "== build + restart"
docker compose build -q
docker compose up -d --force-recreate boardman-api boardman-bot boardman-house

echo "== wait for the API"
for _ in $(seq 1 60); do
  curl -sf --max-time 3 http://127.0.0.1:8000/api/healthz >/dev/null && break
  sleep 3
done
curl -s --max-time 10 http://127.0.0.1:8000/api/healthz; echo
REMOTE
} | ssh -o ConnectTimeout=20 "$HOST" "IFS= read -r RESOLVER_KEY && export RESOLVER_KEY ESCROW=$ESCROW POOL=$POOL && bash -s"

if [ -z "${SKIP_SITE:-}" ]; then
  echo "== site"
  "$ROOT/scripts/deploy_frontend.sh"
fi
echo "Avalanche build is live. Back out with the steps at the top of this script."
