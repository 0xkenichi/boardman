# Deploy Rematch on Akash (24/7)

**Goal:** Always-on Telegram bot + API without leaving it on your laptop.  
**Resources:** CPU only (~0.5 vCPU, 512Mi RAM). **No GPU.**  
**Product context:** `docs/PRODUCT_STRATEGY_1V1_PUBLIC_FIAT.md`

---

## What runs in the container

| Process | Role |
|---------|------|
| `uvicorn gaming.src.backend.main:app` | Health + API on `:8000` |
| `python -m gaming.src.bot.main` | Telegram bot (**polling**) |

Entrypoint: `deploy/start_akash.sh`  
Image: `Dockerfile.akash`

Polling mode means **no public webhook URL is required** for the bot. Expose port 80 only for health checks (`/api/healthz`).

---

## Prerequisites

1. Docker (Desktop, Colima, or any builder)  
2. Docker Hub (or GHCR) account to push the image  
3. Akash Console: https://console.akash.network/ (card / AKT funding)  
4. Secrets (same as local `.env`):

| Required | Purpose |
|----------|---------|
| `TELEGRAM_BOT_TOKEN_CLAWSTATION` | Bot token |
| `SUPABASE_URL` | DB |
| `SUPABASE_SERVICE_ROLE_KEY` | DB write |
| `CIRCLE_API_KEY` | Wallets |
| `CIRCLE_ENTITY_SECRET` | Circle |
| `CIRCLE_WALLET_SET_ID` | Wallet set |

Optional: `CIRCLE_CLIENT_KEY`, `CLAW_ADMIN_TELEGRAM_IDS`, caps, etc. (see `.env.example`).

---

## Step 1 — Build image

### Option A — GitHub Actions (recommended if local Docker is broken)

```bash
# From a machine with git auth to the rematch repo:
git add Dockerfile.akash deploy/start_akash.sh deploy/akash docs/AKASH_DEPLOY.md \
  docs/PRODUCT_STRATEGY_1V1_PUBLIC_FIAT.md .github/workflows/akash-image.yml README.md
git commit -m "Add Akash deploy image and product strategy docs"
git push origin HEAD

# Or trigger manually: GitHub → Actions → "Akash image" → Run workflow
```

Image published to:

```text
ghcr.io/playingsidequest-dotplay/rematch:latest
```

Make the GHCR package **public** (Packages → rematch → Package settings), or pass registry credentials in Akash Console.

### Option B — Local Docker / Colima

```bash
cd /path/to/rematch   # this repo

# macOS if brew perms are broken first:
#   sudo chown -R "$(whoami)" /opt/homebrew
#   brew install colima docker docker-buildx
#   colima start

export DOCKERHUB_USER=yourname   # or use GHCR tags instead
./deploy/akash/build_and_push.sh
```

Quick local smoke (before push):

```bash
docker run --rm -p 8000:8000 --env-file .env YOUR_DOCKERHUB_USER/rematch:latest
# another terminal:
curl -s http://localhost:8000/api/healthz
# Telegram: /start on the bot
```

Private image: set registry credentials in Akash Console when deploying.

### Option C — Render SDL with secrets (local helper)

```bash
export DOCKERHUB_USER=yourname   # or leave and edit image in generated file to ghcr.io/...
./deploy/akash/render_sdl_from_env.sh
# Upload deploy/akash/deploy.generated.yml in Console (contains secrets — never commit)
```

---

## Step 3 — Edit SDL

File: `deploy/akash/deploy.yml`

1. Replace `YOUR_DOCKERHUB_USER/rematch:latest` with your real image.  
2. Fill env vars (Console UI is safer than committing secrets).  
3. Keep `CLAWSTATION_BOT_MODE=polling` unless you configure a public HTTPS webhook.

---

## Step 4 — Deploy on Akash Console (recommended)

1. Open https://console.akash.network/  
2. Fund / connect wallet (or use Console credit-card flow if available)  
3. **Upload SDL** → select `deploy/akash/deploy.yml`  
4. Paste secrets into env fields  
5. Create deployment → wait for **bids**  
6. Accept a provider bid (cheapest reliable CPU is fine)  
7. Wait until status is **running**  
8. Copy the public URI (e.g. `https://xxxxx.provider.akash...`)  
9. Health check:

```bash
curl -sS "https://YOUR_AKASH_URI/api/healthz"
```

10. Message the bot on Telegram — it should answer while the pod is up.

### CLI alternative (optional)

```bash
# Install provider-services (Akash CLI) — see https://akash.network/docs/
provider-services tx deployment create deploy/akash/deploy.yml \
  --from YOUR_WALLET \
  --node https://rpc.akashnet.net:443 \
  --chain-id akashnet-2
```

Console is usually enough for a single bot.

---

## Step 5 — After deploy checklist

| Check | How |
|-------|-----|
| Health | `curl …/api/healthz` |
| Bot live | `/start` in Telegram |
| Safety caps | `CLAW_MAX_STAKE_USDC`, `CLAW_PAUSED` |
| Logs | Akash Console → deployment logs |
| Redeploy | Push new image tag → update SDL image → close/recreate or update deployment |

---

## Cost & sizing notes

- **0.5 CPU / 512Mi** is the default in `deploy.yml` (raise to **1 CPU / 1Gi** if OOM).  
- Pricing is provider-dependent; thin CPU apps are often **a few dollars/month** class.  
- Do **not** request GPU for this bot.  
- One replica (`count: 1`) — two bots with the same token will fight over polling.

---

## Safety defaults (set on Akash env)

```bash
CLAW_PAUSED=0
CLAW_MAX_STAKE_USDC=25
CLAW_MAX_WITHDRAW_USDC=50
CLAW_DAILY_WITHDRAW_CAP_USDC=100
CLAW_DEFAULT_CHAIN=arc
CLAWSTATION_BOT_MODE=polling
NETWORK=testnet
```

Admin: set `CLAW_ADMIN_TELEGRAM_IDS` to your numeric Telegram ID for `/pause` `/unpause`.

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| Image pull fail | Public image, or registry credentials; tag must exist on Hub |
| Bot silent | Wrong/missing `TELEGRAM_BOT_TOKEN_CLAWSTATION`; check logs |
| Two bots fighting | Only one deployment with that token; stop local `start_free_local.sh` |
| Health 5xx | Supabase/Circle env missing; read API logs |
| OOMKill | Bump memory to 1Gi in SDL |
| No bids | Raise `pricing.amount` or loosen placement |

---

## Stop / migrate

- Close deployment in Akash Console to stop spend.  
- Same image works on Fly/Render/Hetzner later (`Dockerfile.akash` + `start_akash.sh`).

---

## Files in this repo

| Path | Role |
|------|------|
| `Dockerfile.akash` | Production image for Akash |
| `deploy/start_akash.sh` | API + bot process supervisor |
| `deploy/akash/deploy.yml` | Akash SDL |
| `docs/PRODUCT_STRATEGY_1V1_PUBLIC_FIAT.md` | Why we ship this way |
| `.env.example` | Secret names |

---

## Never forget

Always-on Rematch = **this container on Akash**, not your laptop.  
Product stays testnet-safe until fiat + mainnet rails are intentional.
