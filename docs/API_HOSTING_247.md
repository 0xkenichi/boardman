# Boardman API — 24/7 Hosting Walkthrough

**Goal:** get the Boardman API (the FastAPI service that runs the House /
Raja vs Nero / Play match) running on a public, always-on host, then point
the deployed frontend at it so the live site's "Play match" works.

**Why this exists:** the frontend is deployed on Vercel, but the API has been
running only on a local machine behind a throwaway Cloudflare quick tunnel.
Quick-tunnel URLs change on every restart, so the live site shows
"House is offline". This doc replaces the tunnel with a real host.

---

## TL;DR — pick a host

| Option | Cost | 24/7? | Effort | Notes |
|---|---|---|---|---|
| **Railway** (chosen) | Hobby ~$5/mo | ✅ yes | Low | `railway.toml` + `Dockerfile.akash` already in repo; volume for `data/agentic`. See `docs/RAILWAY_DEPLOY.md`. |
| **Fly.io** | Free tier (3 small VMs) | ✅ yes | Low | Config already in repo (`deploy/fly.toml`). |
| **Akash** | Cheap (~$2–5/mo in AKT) | ✅ yes | Medium | Image auto-built on push; deploy via console. |
| **Render free** | Free | ⚠️ sleeps after idle | Low | Needs an external pinger (cron-job.org) to stay awake. |
| **Hetzner VPS** | ~€5/mo | ✅ yes | Medium | Classic `DEPLOY.md` path: Docker Compose + Caddy. |

> Every option runs the same command: `uvicorn gaming.src.backend.main:app --host 0.0.0.0 --port 8000`
> (the Dockerfile default). Health check: `GET /api/healthz`.

---

## Option A — Fly.io (recommended, free + truly 24/7)

1. **Install the CLI and sign up (free):**
   ```bash
   curl -L https://fly.io/install.sh | sh
   fly auth signup   # or: fly auth login
   ```

2. **Launch from the repo root** (the repo already has `deploy/fly.toml` + `deploy/start_fly.sh`):
   ```bash
   fly launch --config deploy/fly.toml --no-deploy --name boardman-api
   ```

3. **Secrets.** The API needs the same env the bot/backend uses. From the local
   `.env` (never commit it):
   ```bash
   fly secrets set --config deploy/fly.toml \
     SUPABASE_URL=... \
     SUPABASE_SERVICE_ROLE_KEY=... \
     REMATCH_API_KEY=... \
     STACK_API_KEY=... \
     BOARDMAN_STACK_API_KEYS=... \
     CLAWSTATION_BOT_MODE=polling \
     CLAW_DEFAULT_CHAIN=arc \
     NETWORK=testnet
   ```
   > Demo/ledger mode runs without real Circle keys; add `CIRCLE_*` keys when
   > you want real on-chain settlement.

4. **Deploy:**
   ```bash
   fly deploy --config deploy/fly.toml --dockerfile Dockerfile.akash
   ```

5. **Verify:**
   ```bash
   fly open   # or curl the assigned URL
   curl https://boardman-api.fly.dev/api/healthz
   ```
   `deploy/fly.toml` already pins `min_machines_running = 1` and
   `auto_stop_machines = "off"` → the API stays up 24/7 and restarts on crash.

---

## Option B — Akash (cheap, image auto-builds)

1. The GitHub workflow `.github/workflows/akash-image.yml` already builds
   `ghcr.io/<owner>/rematch:latest` on every push to `main` (paths under
   `src/**`, `config/**`, etc.). Make the package public: GitHub → Packages →
   `rematch` → Package settings → Change visibility → Public.

2. Fill in the SDL env from your `.env`:
   ```bash
   cp deploy/akash/deploy.generated.yml deploy/akash/deploy.yml
   # edit env vars in deploy.yml to match your .env
   ```

3. Deploy via the console:
   - https://console.akash.network/ → Deploy → upload `deploy/akash/deploy.yml`
   - Accept a lease; note the public URI Akash assigns.

4. Set a health check / keep-alive on the assigned URI (`/api/healthz`).

---

## Option C — Hetzner VPS (classic, ~€5/mo)

Follow `DEPLOY.md` end to end — it's the same app:

1. Hetzner CX22, Ubuntu 24.04, ports 22/80/443 open, DNS A record pointed at it.
2. Install Docker (section 2 of `DEPLOY.md`).
3. `cp .env.example .env`, fill required secrets, then:
   ```bash
   docker compose -f docker-compose.yml up -d --build
   ```
4. Caddy (section 4) gives you HTTPS with Let's Encrypt.
5. Verify: `curl https://your-domain/api/healthz`.

---

## Connect the deployed frontend (required for all options)

The Vercel frontend calls the API through `BOARDMAN_API_URL`. Point it at your
new public host (in `frontend/`):

```bash
cd frontend
vercel env rm BOARDMAN_API_URL production --yes
echo "https://your-api-host" | vercel env add BOARDMAN_API_URL production --yes
vercel --prod --yes      # redeploy so the env change takes effect
```

Verify the live site now reaches the House:

```bash
curl https://boardman.playingsidequest.fun/api/agentic/house-play
# → {"ok":true,"match":null,...}  (previously: "House API is offline")
```

---

## Keeping it running 24/7 — the checklist

- **Auto-restart on crash:** Fly (`min_machines_running=1`), Docker (`restart:
  unless-stopped` in compose), Akash (SDL health checks), Render (free sleeps —
  add a cron-job.org ping every 10 min to `/api/healthz`).
- **Uptime monitor:** UptimeRobot / cron-job.org on `https://<host>/api/healthz`.
- **Logs:**
  ```bash
  fly logs --config deploy/fly.toml            # Fly
  docker compose logs -f --tail 100 clawstation-api   # VPS
  ```
- **Secrets:** keep `.env` out of git; set them as platform secrets, never in
  the image.
- **The quick tunnel is temporary:** `scripts/_start_tunnel_detached.py` starts
  a Cloudflare quick tunnel for local testing; its URL changes on restart and
  it dies on reboot — fine for dev, not for production.

---

## After you're live

- Update the Telegram bot's `WEBHOOK_URL` / `MINIAPP_URL` if you want
  mini-app links to point at the hosted API.
- Watch `data/agentic/matches.json` — with a real host you may want a
  persistent volume for match/ledger state (Fly volumes or a VPS disk).
