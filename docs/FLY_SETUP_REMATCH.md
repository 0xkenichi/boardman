# Rematch bot on Fly.io — simple 24/7 setup

**This is the practical option** for your repo: you already have `flyctl`, a Dockerfile, and deploy config.

- **Cost:** Fly free allowance / very cheap shared VM (check current [pricing](https://fly.io/docs/about/pricing/)). Often needs a card on file; free credit is limited — still the **simplest “always on”** path for this project.
- **What runs:** Telegram bot (polling) + small API for health checks.
- **True forever-free alternative:** Oracle Cloud Always Free (harder signup) — see bottom.

---

## 0. Prerequisites (on your Mac)

1. **Fly CLI** (you already have `fly` / `flyctl`).
2. **Docker Desktop** running (Fly builds with Docker).
3. **GitHub** access to this repo (optional if you deploy from local).
4. **Stop the local bot** so only Fly talks to Telegram:

```bash
ps aux | grep 'gaming/src/bot/main.py' | grep -v grep
# if a line appears:
kill <PID>
```

Only **one** bot process may poll Telegram.

---

## 1. Log in to Fly

```bash
fly auth login
```

Browser opens → log in / create account.

---

## 2. Go to the project root

```bash
cd /Users/mac/sideQuest/sideQuest/.worktrees/clawstation-foundation
```

Confirm files exist:

```bash
ls gaming/Dockerfile gaming/deploy/fly.toml gaming/deploy/start_fly.sh
```

---

## 3. Create the app (once)

```bash
fly launch --config gaming/deploy/fly.toml --no-deploy --copy-config --name rematch-bot
```

- If the name `rematch-bot` is taken, pick another (e.g. `rematch-sq-bot`).
- Say **no** to extra Postgres/Redis (you use Supabase).
- Region: default `iad` is fine (or closest to you).

---

## 4. Put secrets on Fly (required)

**Do not** commit `.env`. Copy values from your local `.env` into Fly:

```bash
cd /Users/mac/sideQuest/sideQuest/.worktrees/clawstation-foundation

# Minimum set (edit if a name differs in your .env)
fly secrets set \
  TELEGRAM_BOT_TOKEN_CLAWSTATION="PASTE_TOKEN" \
  TELEGRAM_BOT_TOKEN="PASTE_TOKEN" \
  SUPABASE_URL="PASTE" \
  SUPABASE_SERVICE_ROLE_KEY="PASTE" \
  SUPABASE_SERVICE_KEY="PASTE" \
  CIRCLE_API_KEY="PASTE" \
  CIRCLE_ENTITY_SECRET="PASTE" \
  CIRCLE_WALLET_SET_ID="PASTE" \
  CIRCLE_CLIENT_KEY="PASTE" \
  ADMIN_PRIVATE_KEY="PASTE" \
  ADMIN_WALLET_ADDRESS="PASTE" \
  NVIDIA_NIM_KEY="PASTE" \
  CLAW_ESCROW_ADDRESS_ARC="PASTE" \
  CLAW_ESCROW_ADDRESS_AVALANCHE="PASTE" \
  CLAW_ESCROW_ADDRESS_BASE_SEPOLIA="PASTE" \
  --config gaming/deploy/fly.toml
```

**Easier way (if you’re careful):**

```bash
# Export only non-empty needed keys from .env then:
set -a && source .env && set +a
fly secrets set \
  TELEGRAM_BOT_TOKEN_CLAWSTATION="$TELEGRAM_BOT_TOKEN_CLAWSTATION" \
  TELEGRAM_BOT_TOKEN="${TELEGRAM_BOT_TOKEN_CLAWSTATION:-$TELEGRAM_BOT_TOKEN}" \
  SUPABASE_URL="$SUPABASE_URL" \
  SUPABASE_SERVICE_ROLE_KEY="$SUPABASE_SERVICE_ROLE_KEY" \
  SUPABASE_SERVICE_KEY="${SUPABASE_SERVICE_KEY:-$SUPABASE_SERVICE_ROLE_KEY}" \
  CIRCLE_API_KEY="$CIRCLE_API_KEY" \
  CIRCLE_ENTITY_SECRET="$CIRCLE_ENTITY_SECRET" \
  CIRCLE_WALLET_SET_ID="$CIRCLE_WALLET_SET_ID" \
  CIRCLE_CLIENT_KEY="$CIRCLE_CLIENT_KEY" \
  ADMIN_PRIVATE_KEY="$ADMIN_PRIVATE_KEY" \
  ADMIN_WALLET_ADDRESS="$ADMIN_WALLET_ADDRESS" \
  NVIDIA_NIM_KEY="$NVIDIA_NIM_KEY" \
  CLAW_ESCROW_ADDRESS_ARC="$CLAW_ESCROW_ADDRESS_ARC" \
  CLAW_ESCROW_ADDRESS_AVALANCHE="$CLAW_ESCROW_ADDRESS_AVALANCHE" \
  CLAW_ESCROW_ADDRESS_BASE_SEPOLIA="$CLAW_ESCROW_ADDRESS_BASE_SEPOLIA" \
  --config gaming/deploy/fly.toml
```

List secrets (names only):

```bash
fly secrets list --config gaming/deploy/fly.toml
```

---

## 5. Deploy

```bash
cd /Users/mac/sideQuest/sideQuest/.worktrees/clawstation-foundation
fly deploy --config gaming/deploy/fly.toml
```

First build can take several minutes.

---

## 6. Confirm it’s running

```bash
# Machine status
fly status --config gaming/deploy/fly.toml

# Live logs (look for "Start polling")
fly logs --config gaming/deploy/fly.toml

# Health (API)
fly open --config gaming/deploy/fly.toml
# or:
curl -s "https://rematch-bot.fly.dev/api/healthz"
```

**Telegram check:** message the bot `/start`. It should reply as **Rematch · sideQuest**.

---

## 7. Know when it dies (free monitoring)

1. Note your health URL: `https://YOUR-APP-NAME.fly.dev/api/healthz`
2. Create a free monitor at [UptimeRobot](https://uptimerobot.com) or [cron-job.org](https://cron-job.org)
3. Ping every **5 minutes**
4. Email/Telegram alert if it fails

---

## 8. Day-to-day commands

| Action | Command |
|--------|---------|
| Logs | `fly logs --config gaming/deploy/fly.toml` |
| Restart | `fly apps restart rematch-bot` |
| Redeploy after code change | `fly deploy --config gaming/deploy/fly.toml` |
| SSH shell | `fly ssh console --config gaming/deploy/fly.toml` |
| Scale to 1 machine | `fly scale count 1 --config gaming/deploy/fly.toml` |

---

## 9. Common failures

| Problem | Fix |
|---------|-----|
| `Conflict: terminated by other getUpdates` | Kill local Mac bot (`kill` the python process) |
| Deploy build fails on Docker | Open Docker Desktop, retry |
| Bot silent after deploy | `fly logs` — missing secret or crash loop |
| Health check fails | Wait 1–2 min after deploy; check `/api/healthz` path exists |
| App name taken | Change `app = "..."` in `fly.toml` |

---

## 10. If Fly free allowance is gone / too expensive

**Oracle Cloud Always Free** (real free VPS, more setup):

1. https://www.oracle.com/cloud/free/ → create free account  
2. Create **Ubuntu** VM (Ampere A1 free shape if available)  
3. SSH in:

```bash
sudo apt update && sudo apt install -y git python3-venv python3-pip
git clone https://github.com/playingsidequest-dotplay/sideQuest.git
cd sideQuest
git checkout clawstation   # or your bot branch
# copy .env securely (scp from Mac)
python3 -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements.txt -r gaming/src/backend/requirements.txt
# run under systemd or:
nohup python -m gaming.src.bot.main > bot.log 2>&1 &
```

4. Use **systemd** so it restarts on reboot (ask if you want a unit file).

---

## Checklist

- [ ] Local bot **stopped**
- [ ] `fly auth login`
- [ ] App created (`rematch-bot` or your name)
- [ ] Secrets set
- [ ] `fly deploy` succeeded
- [ ] Logs show **Start polling**
- [ ] `/start` works in Telegram
- [ ] Uptime monitor on `/api/healthz`

---

*Config files: `gaming/deploy/fly.toml`, `gaming/deploy/start_fly.sh`*
