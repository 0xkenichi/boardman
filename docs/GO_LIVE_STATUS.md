# Rematch — live status (2026-08-03)

## What works now

| URL | Status |
|-----|--------|
| https://playingsidequest.fun/rematch | Marketing docs **200** |
| https://playingsidequest.fun/rematch/app | Mini-app **200** (demo + live Stack) |
| https://rematch-web.vercel.app | Same mini-app on dedicated project |
| Telegram bot | Running locally (polling) |
| Stack / rematch web API | Running locally, tunnel → Vercel BFF |

Live wallet/games via BFF → `STACK_API_URL` (Cloudflare quick tunnel to laptop API).

Verified smoke:

- `POST /api/rematch/app/session` demo → session cookie
- `GET /api/rematch/app/me` → real Circle wallet snapshot (`demo: false`)
- `GET /api/rematch/app/games` → catalog from Stack v1
- Match create validates opponent exists in Supabase

## Architecture (current)

```
Browser → playingsidequest.fun/rematch/*  (Vercel play-sidequest)
       → /api/rematch/* BFF (Next.js, STACK_API_KEY server-only)
       → STACK_API_URL (cloudflared tunnel) → laptop :8000 Rematch API
Telegram → bot process (local, same .env / Supabase / Circle)
```

Dedicated: `rematch-web.vercel.app` (same BFF + STACK).

## You still need to do

### 1. DNS for subdomain (optional)

In Unstoppable Domains DNS for `playingsidequest.fun`:

```
CNAME  rematch  →  d8b0d86327c82831.vercel-dns-017.com.
```

(or `A rematch → 76.76.21.21`)

Project already has `rematch.playingsidequest.fun` attached to `rematch-web`.

### 2. BotFather domain

```
/setdomain → playingsidequest.fun
```

(for Telegram Login Widget on apex)

### 3. Stable API host (replace laptop tunnel)

Tunnel dies when this machine sleeps/reboots. Long-term:

```bash
# once: fly auth login
export PATH="$HOME/.fly/bin:$PATH"
cd /path/to/rematch
fly launch --config deploy/fly.toml --no-deploy --name rematch-api
# set secrets from .env (see docs/FLY_SETUP_REMATCH.md)
fly deploy --config deploy/fly.toml --dockerfile Dockerfile.akash
# then:
vercel env add STACK_API_URL production   # https://rematch-api.fly.dev
```

### 4. Keep local API+bot up (until Fly)

```bash
# already running via:
#   /tmp/start_rematch_api.sh  → :8000
#   /tmp/start_rematch_bot.sh
#   cloudflared tunnel → trycloudflare.com
# logs: /tmp/clawstation-logs/{api,bot,tunnel}.log
```

Only **one** bot process may poll Telegram.

### 5. Production hardening (when ready)

- Set `REMATCH_ALLOW_DEMO_LOGIN` / `NEXT_PUBLIC_ALLOW_DEMO_LOGIN` off
- Point `STACK_API_URL` at Fly (not tunnel)
- Review geo-fence list for real player countries (Stack BFF already bypasses geo)

## Local processes

| PID file | Role |
|----------|------|
| `/tmp/clawstation-logs/api.pid` | uvicorn Rematch Stack |
| `/tmp/clawstation-logs/bot.pid` | Telegram bot |
| `/tmp/clawstation-logs/tunnel.pid` | cloudflared quick tunnel |

Restart API:

```bash
kill $(cat /tmp/clawstation-logs/api.pid)
nohup /tmp/start_rematch_api.sh >>/tmp/clawstation-logs/api.log 2>&1 &
echo $! > /tmp/clawstation-logs/api.pid
```

## Code repos

- Rematch product: this repo (`rematch`) — API, bot, `frontend/` for rematch-web
- Apex site: `Documents/sideQuest` — ships `/rematch/*` mini-app + BFF on playingsidequest.fun
