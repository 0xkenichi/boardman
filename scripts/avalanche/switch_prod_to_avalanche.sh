#!/usr/bin/env bash
# Switch the production Boardman (Oracle VM + Vercel site) to the Avalanche build.
#
# What it does, on the VM (ubuntu@150.230.112.144, ~/boardman):
#   0. stops, changing nothing, if tracked files on the VM have local edits
#   1. backs up .env to ~/backups/env.before-avalanche.<stamp>
#   2. checks out origin/avalanche (the Avalanche build) instead of main
#   3. sets the chain env: Fuji is the only offered chain, the default and the
#      arena chain, with the Fuji BoardmanEscrow v2 + SpectatorPool v2; the
#      (still off) real-money realm points at C-Chain mainnet
#   4. sets BOARDMAN_RESOLVER_KEY to the Fuji escrow resolver. The key is read
#      from .fuji/wallets.json on this Mac and piped over ssh; it is never
#      printed. Testnet-only key.
#   5. rebuilds and restarts api, bot and house, waits for /api/healthz, prints
#      the money realms and the gas tank's address and Fuji AVAX balance
# Then, from this Mac, it deploys the site (defaults to Avalanche) to Vercel,
# using the main checkout's Vercel project link.
#
# Dry run by default; it also takes a read-only look at the VM. Nothing
# changes until you pass APPLY=1:
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

# The site deploys from this checkout's frontend/. A worktree has no Vercel
# project link (.vercel is git-ignored), and `vercel --prod --yes` without one
# would create a new project. Copy the link from the main checkout.
VLINK="$ROOT/frontend/.vercel/project.json"
MAIN_CHECKOUT="$(dirname "$(git -C "$ROOT" rev-parse --path-format=absolute --git-common-dir)")"
if [ ! -f "$VLINK" ] && [ -f "$MAIN_CHECKOUT/frontend/.vercel/project.json" ]; then
  mkdir -p "$ROOT/frontend/.vercel"
  cp "$MAIN_CHECKOUT/frontend/.vercel/project.json" "$VLINK"
fi
if [ -z "${SKIP_SITE:-}" ]; then
  [ -f "$VLINK" ] || { echo "no Vercel project link at $VLINK (run 'vercel link' in frontend/)" >&2; exit 1; }
fi

echo "Avalanche build switch"
echo "  VM:        $HOST (~/boardman -> origin/avalanche)"
echo "  escrow:    $ESCROW"
echo "  pool:      $POOL"
echo "  resolver:  $RESOLVER_ADDR (key piped from $W, not printed)"
echo "  site:      $([ -n "${SKIP_SITE:-}" ] && echo skipped || echo "scripts/deploy_frontend.sh from this checkout (Vercel link ok)")"
if [ "${APPLY:-}" != "1" ]; then
  echo
  echo "VM now (read-only look):"
  ssh -o ConnectTimeout=20 "$HOST" 'cd ~/boardman \
    && echo "  code:      $(git rev-parse --abbrev-ref HEAD) $(git log --oneline -1)" \
    && echo "  edits:     $(git status --porcelain --untracked-files=no | wc -l | tr -d " ") tracked file(s) changed on the VM (must be 0)" \
    && echo "  disk free: $(df -h / | awk "NR==2{print \$4}")"' </dev/null \
    || echo "  (could not reach the VM over ssh)"
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

echo "== preflight"
if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
  echo "The VM has uncommitted edits to tracked files. Nothing was changed:" >&2
  git status --short --untracked-files=no >&2
  exit 1
fi

echo "== backup"
mkdir -p ~/backups
stamp=$(date -u +%Y%m%dT%H%M%S)
cp .env ~/backups/env.before-avalanche.$stamp
chmod 600 ~/backups/env.before-avalanche.$stamp
echo "saved ~/backups/env.before-avalanche.$stamp"

echo "== code"
git fetch -q origin +refs/heads/avalanche:refs/remotes/origin/avalanche   # the VM clone tracks main only
git checkout -q -B avalanche origin/avalanche
git log --oneline -1

echo "== settings"
keys="CLAW_ENABLED_CHAINS|CLAW_DEFAULT_CHAIN|BOARDMAN_ARENA_CHAIN|BOARDMAN_HUMANS_CHAIN|CLAW_ESCROW_ADDRESS_AVALANCHE|SPECTATOR_ESCROW_ADDRESS_AVALANCHE|BOARDMAN_RESOLVER_KEY|NEXT_PUBLIC_SETTLEMENT_CHAIN"
# Drop the old values in place (cat > keeps .env's owner and mode).
kept=$(grep -vE "^($keys)=" .env || true)
printf '%s\n' "$kept" > .env
{
  echo "CLAW_ENABLED_CHAINS=avalanche"
  echo "CLAW_DEFAULT_CHAIN=avalanche"
  echo "BOARDMAN_ARENA_CHAIN=avalanche"
  echo "BOARDMAN_HUMANS_CHAIN=avalanche_mainnet"
  echo "CLAW_ESCROW_ADDRESS_AVALANCHE=$ESCROW"
  echo "SPECTATOR_ESCROW_ADDRESS_AVALANCHE=$POOL"
  echo "BOARDMAN_RESOLVER_KEY=$RESOLVER_KEY"
} >> .env
grep -E "^($keys)=" .env | sed -E "s/^(BOARDMAN_RESOLVER_KEY)=.*/\1=<set>/"

echo "== build + restart"
# </dev/null: this script itself arrives on stdin; no command may read it.
docker compose build -q </dev/null
docker compose up -d --force-recreate boardman-api boardman-bot boardman-house </dev/null

echo "== wait for the API"
for _ in $(seq 1 60); do
  curl -sf --max-time 3 http://127.0.0.1:8000/api/healthz </dev/null >/dev/null && break
  sleep 3
done
curl -s --max-time 10 http://127.0.0.1:8000/api/health/deep </dev/null \
  | python3 -c "import json,sys; print('realms:', json.dumps(json.load(sys.stdin)['checks'].get('money_realms')))" \
  || echo "deep health not readable yet"

echo "== gas tank (tops up players' Fuji wallets with AVAX)"
docker compose exec -T boardman-api python - <<'PY' || echo "could not read the gas tank"
import os
from eth_account import Account
from web3 import Web3
k = (os.getenv("ADMIN_PRIVATE_KEY") or os.getenv("GAS_TANK_PRIVATE_KEY") or "").strip()
if not k:
    print("no ADMIN_PRIVATE_KEY / GAS_TANK_PRIVATE_KEY: players' Fuji wallets will get no AVAX gas")
else:
    a = Account.from_key(k if k.startswith("0x") else "0x" + k).address
    rpc = os.getenv("AVALANCHE_FUJI_RPC_URL") or "https://api.avax-test.network/ext/bc/C/rpc"
    w3 = Web3(Web3.HTTPProvider(rpc, request_kwargs={"timeout": 20}))
    print(f"gas tank {a}: {w3.eth.get_balance(a) / 1e18:.4f} AVAX on Fuji (fund it if under 0.1)")
PY
REMOTE
} | ssh -o ConnectTimeout=20 "$HOST" "IFS= read -r RESOLVER_KEY && export RESOLVER_KEY ESCROW=$ESCROW POOL=$POOL && bash -s"

if [ -z "${SKIP_SITE:-}" ]; then
  echo "== site"
  "$ROOT/scripts/deploy_frontend.sh"
fi
echo "Avalanche build is live. Back out with the steps at the top of this script."
