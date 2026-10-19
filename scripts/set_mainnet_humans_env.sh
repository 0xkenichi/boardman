#!/usr/bin/env bash
# Put the humans-realm (Arc mainnet, real money) settings on the production VM
# without any secret appearing on screen, in chat or in shell history.
# NOT run by CI or agents. See docs/MAINNET_HUMANS_CUTOVER.md for the order.
#
#   bash scripts/set_mainnet_humans_env.sh             # settings only; real money stays OFF
#   bash scripts/set_mainnet_humans_env.sh --enable    # also REAL_MONEY_ENABLED=1 (type REAL MONEY)
#   bash scripts/set_mainnet_humans_env.sh --disable   # rollback: REAL_MONEY_ENABLED=0 only
#   BOARDMAN_VM=ubuntu@1.2.3.4 bash scripts/set_mainnet_humans_env.sh
#
# Secret (typed blind, blank keeps what is there): CIRCLE_API_KEY_LIVE.
# Not secret (typed visibly, blank keeps): the Arc mainnet escrow address, the
# keystore entry name of the mainnet resolver, the Circle USDC token ids on
# ARC and BASE, and the two real-money caps. The entity secret is NEVER typed:
# scripts/circle_mainnet_setup.py generates it on the VM.
#
# Only the named keys are replaced in ~/boardman/.env; only the API, bot and
# house containers are restarted.
set -euo pipefail
VM="${BOARDMAN_VM:-ubuntu@150.230.112.144}"
MODE="${1:-}"

emit() { printf '%s=%s\n' "$1" "$2"; }
LINES=""
add() { [ -n "$2" ] && LINES+="$(emit "$1" "$2")"$'\n' || true; }

if [ "$MODE" = "--disable" ]; then
  LINES="$(emit REAL_MONEY_ENABLED 0)"$'\n'
else
  read -rs -p "Circle LIVE API key (LIVE_API_KEY:..., hidden; blank = keep): " KEY; echo
  if [ -n "$KEY" ]; then
    case "$KEY" in LIVE_API_KEY:*) ;; *) echo "not a LIVE_API_KEY: key; nothing changed" >&2; unset KEY; exit 1;; esac
  fi
  read -r -p "BoardmanEscrow v2 address on Arc mainnet (blank = keep): " ESCROW
  if [ -n "$ESCROW" ] && ! [[ "$ESCROW" =~ ^0x[0-9a-fA-F]{40}$ ]]; then echo "bad address" >&2; exit 1; fi
  read -r -p "Mainnet resolver keystore entry name [resolver_arc_mainnet]: " RESOLVER
  RESOLVER="${RESOLVER:-resolver_arc_mainnet}"
  if [[ "$RESOLVER" =~ ^(0x)?[0-9a-fA-F]{64}$ ]]; then
    echo "That is a private key, not an entry name. Rotate it NOW; nothing changed." >&2; exit 1
  fi
  read -r -p "Circle USDC token id on ARC (blank = keep): " TOK_ARC
  read -r -p "Circle USDC token id on BASE (blank = keep): " TOK_BASE
  read -r -p "Max real-money stake per player per match, USD [25]: " CAP_MATCH
  read -r -p "Max real-money staked per player per 24 h, USD [100]: " CAP_DAY
  add CIRCLE_API_KEY_LIVE "${KEY:-}"
  add BOARDMAN_ESCROW_ADDRESS_ARC_MAINNET "$ESCROW"
  add BOARDMAN_RESOLVER_KEY_MAINNET "$RESOLVER"
  add CIRCLE_USDC_TOKEN_ID_ARC_MAINNET "$TOK_ARC"
  add CIRCLE_USDC_TOKEN_ID_BASE_MAINNET "$TOK_BASE"
  add BOARDMAN_HUMANS_MAX_STAKE_USDC "${CAP_MATCH:-25}"
  add BOARDMAN_HUMANS_DAILY_STAKE_USDC "${CAP_DAY:-100}"
  add BOARDMAN_HUMANS_CHAIN arc_mainnet
  add BOARDMAN_ARENA_CHAIN arc
  if [ "$MODE" = "--enable" ]; then
    echo "This switches on REAL MONEY human challenges on Arc mainnet."
    read -r -p "Type REAL MONEY to confirm: " CONFIRM
    [ "$CONFIRM" = "REAL MONEY" ] || { echo "not confirmed; nothing changed" >&2; unset KEY; exit 1; }
    add REAL_MONEY_ENABLED 1
    add GEO_FENCE_STRICT 1
  fi
fi

KEYS="$(printf '%s' "$LINES" | cut -d= -f1 | paste -sd'|' -)"
[ -n "$KEYS" ] || { echo "nothing to change"; exit 0; }
printf '%s' "$LINES" | ssh -o BatchMode=yes "$VM" "set -e; cd ~/boardman; umask 077
  grep -vE '^($KEYS)=' .env > .env.new || true
  printf '\n# Humans realm / Arc mainnet (set by scripts/set_mainnet_humans_env.sh)\n' >> .env.new
  cat >> .env.new
  chmod 600 .env.new && mv .env.new .env
  sg docker -c 'docker compose up -d --force-recreate --no-deps boardman-api boardman-bot boardman-house' >/dev/null 2>&1
  echo 'VM .env updated (keys: $KEYS); containers restarted.'"
unset KEY
echo "Check (no values shown): ssh $VM \"grep -oE '^(CIRCLE_API_KEY_LIVE|REAL_MONEY_ENABLED|BOARDMAN_[A-Z_]+MAINNET)=' ~/boardman/.env\""
