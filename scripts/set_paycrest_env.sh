#!/usr/bin/env bash
# Put the Paycrest credentials on the production VM without them ever
# appearing on screen, in chat, or in shell history. The naira rail stays OFF.
#
#   bash scripts/set_paycrest_env.sh            # credentials only, PAYCREST_ENABLED=0
#   bash scripts/set_paycrest_env.sh --enable   # also switch the rail ON (asks to confirm)
#   BOARDMAN_VM=ubuntu@1.2.3.4 bash scripts/set_paycrest_env.sh
#
# Asks for the Paycrest API key and API secret (typed blind; the secret signs
# webhooks), and optionally the Circle relayer wallet ids that pay the CCTP
# mint gas. Writes them into the VM's ~/boardman/.env (replacing earlier
# PAYCREST_ lines) and restarts only the API container.
#
# --enable sets PAYCREST_ENABLED=1 and REAL_MONEY_ENABLED=1. Do not use it
# until every item in docs/payments/PAYCREST.md "REAL-MONEY GO-LIVE GATE" is
# true; you will be asked to type REAL MONEY to confirm.
set -euo pipefail
VM="${BOARDMAN_VM:-ubuntu@150.230.112.144}"
ENABLE=0
[ "${1:-}" = "--enable" ] && ENABLE=1

read -rs -p "Paycrest API key (dashboard > Settings, hidden): " KEY; echo
read -rs -p "Paycrest API secret (signs webhooks, hidden): " SECRET; echo
[ -n "$KEY" ] && [ -n "$SECRET" ] || { echo "missing a value" >&2; exit 1; }
read -r  -p "Circle wallet id of the Arc relayer (pays mint gas in USDC; blank to skip): " ARC_RELAYER
read -r  -p "Circle wallet id of the Base relayer (blank to skip): " BASE_RELAYER

FLAG=0
if [ "$ENABLE" = "1" ]; then
  echo "This switches on REAL MONEY naira top-ups and cash-outs for players."
  read -r -p "Type REAL MONEY to confirm: " CONFIRM
  [ "$CONFIRM" = "REAL MONEY" ] || { echo "not confirmed; nothing changed" >&2; unset KEY SECRET; exit 1; }
  FLAG=1
fi

{
  printf 'PAYCREST_API_KEY=%s\n' "$KEY"
  printf 'PAYCREST_API_SECRET=%s\n' "$SECRET"
  [ -n "$ARC_RELAYER" ] && printf 'PAYCREST_ARC_RELAYER_WALLET_ID=%s\n' "$ARC_RELAYER"
  [ -n "$BASE_RELAYER" ] && printf 'PAYCREST_BASE_RELAYER_WALLET_ID=%s\n' "$BASE_RELAYER"
  printf 'PAYCREST_ENABLED=%s\n' "$FLAG"
  [ "$FLAG" = "1" ] && printf 'REAL_MONEY_ENABLED=1\n'
  true
} | ssh -o BatchMode=yes "$VM" "set -e; cd ~/boardman; umask 077
  KEEP='^(PAYCREST_[A-Z_]+)='
  [ '$FLAG' = '1' ] && KEEP='^(PAYCREST_[A-Z_]+|REAL_MONEY_ENABLED)='
  grep -vE \"\$KEEP\" .env > .env.new || true
  printf '\n# Paycrest naira rail (set by scripts/set_paycrest_env.sh)\n' >> .env.new
  cat >> .env.new
  chmod 600 .env.new && mv .env.new .env
  sg docker -c 'docker compose up -d --force-recreate --no-deps boardman-api' >/dev/null 2>&1
  echo 'VM .env updated; API restarted.'"
unset KEY SECRET

if [ "$FLAG" = "1" ]; then STATE="ON (real money)"; else STATE="OFF (PAYCREST_ENABLED=0)"; fi
cat <<EOF

Naira rail is now: $STATE

In the Paycrest dashboard (app.paycrest.io) > Settings > Webhook:
  URL:  https://boardman-api.playingsidequest.fun/webhooks/paycrest
The route answers 404 until the rail is ON, so set the URL just before
switching on. Check with:  ssh $VM 'grep -c ^PAYCREST_ ~/boardman/.env'
EOF
