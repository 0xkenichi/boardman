#!/usr/bin/env bash
# Deploy the Boardman frontend to Vercel production and keep
# boardman.playingsidequest.fun pointing at the NEW deployment.
#
# Why the alias step: `vercel alias set <domain>` pins the domain to a
# deployment; later `vercel --prod` deploys update boardman-six.vercel.app
# but NOT the pinned custom domain. This script re-points it every time.
#
# Usage:  scripts/deploy_frontend.sh            (uses logged-in session)
#         VERCEL_TOKEN=vcp_... scripts/deploy_frontend.sh
set -euo pipefail
cd "$(dirname "$0")/../frontend"

TOKEN_ARG=()
[ -n "${VERCEL_TOKEN:-}" ] && TOKEN_ARG=(--token="$VERCEL_TOKEN")

OUT=$(vercel --prod --yes ${TOKEN_ARG[@]+"${TOKEN_ARG[@]}"})
echo "$OUT"

NEW_URL=$(echo "$OUT" | grep -oE "https://boardman-[a-z0-9]+-playingsidequest[^ ]*\.vercel\.app" | head -1)
if [ -n "$NEW_URL" ]; then
  vercel alias set "$NEW_URL" boardman.playingsidequest.fun ${TOKEN_ARG[@]+"${TOKEN_ARG[@]}"}
  echo "✓ boardman.playingsidequest.fun -> $NEW_URL"
else
  echo "⚠ could not parse the production URL from deploy output — re-run alias manually" >&2
  exit 1
fi
