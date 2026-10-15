#!/usr/bin/env bash
# Turn on the WhatsApp channel on the production VM without secrets ever
# appearing on screen, in chat, or in shell history.
#
#   bash scripts/set_whatsapp_env.sh            # VM defaults to 150.230.112.144
#   BOARDMAN_VM=ubuntu@1.2.3.4 bash scripts/set_whatsapp_env.sh
#
# Asks for the Meta values (secrets are typed blind), writes them into the VM's
# ~/boardman/.env (replacing any earlier WhatsApp lines), generates a webhook
# verify token, enables every ported flow (skill matches included), and
# recreates the API and bot containers: the bot runs the jobs (refunds, report
# nudges, settlement) whose notices must reach WhatsApp players too. House
# games keep running; Telegram pauses for the few seconds of the restart.
set -euo pipefail
VM="${BOARDMAN_VM:-ubuntu@150.230.112.144}"

read -r  -p "Phone number ID (WhatsApp > API Setup > From): " PHONE_ID
read -r  -p "Display number shown to users, e.g. +15551234567: " DISPLAY
read -rs -p "Access token (hidden): " TOKEN; echo
read -rs -p "App secret (App settings > Basic, hidden): " APP_SECRET; echo
[ -n "$PHONE_ID" ] && [ -n "$TOKEN" ] && [ -n "$APP_SECRET" ] || { echo "missing a value" >&2; exit 1; }

VERIFY="$(openssl rand -hex 16)"
{
  printf 'WHATSAPP_ENABLED=1\n'
  printf 'WHATSAPP_PHONE_NUMBER_ID=%s\n' "$PHONE_ID"
  printf 'WHATSAPP_DISPLAY_NUMBER=%s\n' "$DISPLAY"
  printf 'WHATSAPP_ACCESS_TOKEN=%s\n' "$TOKEN"
  printf 'WHATSAPP_APP_SECRET=%s\n' "$APP_SECRET"
  printf 'WHATSAPP_VERIFY_TOKEN=%s\n' "$VERIFY"
  printf 'CHANNELS_CORE_FLOWS_WHATSAPP=all\n'
} | ssh -o BatchMode=yes "$VM" 'set -e; cd ~/boardman; umask 077
  grep -vE "^(WHATSAPP_[A-Z_]+|CHANNELS_CORE_FLOWS_WHATSAPP)=" .env > .env.new || true
  printf "\n# WhatsApp (set by scripts/set_whatsapp_env.sh)\n" >> .env.new
  cat >> .env.new
  chmod 600 .env.new && mv .env.new .env
  sg docker -c "docker compose up -d --force-recreate --no-deps boardman-api boardman-bot" >/dev/null 2>&1
  echo "VM .env updated; API and bot restarted."'
unset TOKEN APP_SECRET

cat <<EOF

Now in Meta: WhatsApp > Configuration > Webhook > Edit
  Callback URL:  https://boardman-api.playingsidequest.fun/webhooks/whatsapp
  Verify token:  $VERIFY
Then click "Verify and save", and under Webhook fields subscribe to: messages
EOF
