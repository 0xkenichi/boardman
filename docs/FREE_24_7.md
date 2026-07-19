# Free 24/7 ClawStation (no paid VPS required)

You can run the bot **for free**. Trade-offs: free hosts sleep, rate-limit, or need a credit card on file (Oracle). Pick one path below.

---

## Priority order (recommended)

| Option | Cost | Always on? | Difficulty | Best for |
|--------|------|------------|------------|----------|
| **A. Your Mac + this script** | $0 | While Mac is awake | Easy | Dev / beta with you online |
| **B. Oracle Cloud Always Free** | $0 forever | Yes | Medium | Real 24/7 free VPS |
| **C. Render free + cron-job.org** | $0 | Mostly (wakes on ping) | Easy | API + light bot |
| **D. Fly.io free allowance** | $0 (limited) | Yes until quota | Medium | Small always-on |
| **E. Railway free trial** | $0 trial | Yes during trial | Easy | Short demos |

---

## A. Local free (fastest — already works)

```bash
cd /path/to/clawstation-foundation
chmod +x gaming/deploy/start_free_local.sh
./gaming/deploy/start_free_local.sh
```

- Keep Mac plugged in; script uses `caffeinate` to reduce sleep.
- Logs: `/tmp/clawstation-logs/`
- Stop: `kill $(cat /tmp/clawstation-logs/*.pid)`

**Limits:** sleep, Wi‑Fi drops, lid close = bot offline. Fine for testing, not for real mainnet money.

---

## B. Oracle Cloud Always Free (best free 24/7)

1. Sign up: https://www.oracle.com/cloud/free/ (needs card, **$0 charged** if you stay in free tier)
2. Create **Ampere A1** free VM (Ubuntu 22.04)
3. SSH in, install Docker:

```bash
sudo apt update && sudo apt install -y docker.io docker-compose-v2 git
sudo usermod -aG docker $USER && newgrp docker
```

4. Clone repo, copy `.env`, then:

```bash
docker compose -f gaming/docker-compose.yml up -d --build
```

5. Open security list ports 22, 80, 443, 8000 if needed.

This is the closest thing to a **free real VPS**.

---

## C. Render free + free keep-alive

1. Push repo to GitHub (free)
2. Render.com → New Blueprint → `gaming/deploy/render.yaml`
3. Add **secrets** in Render dashboard (bot token, Supabase, Circle…)
4. Free web services **sleep after ~15 min idle**
5. Keep awake with free ping: https://cron-job.org  
   - URL: `https://YOUR-APP.onrender.com/api/healthz`  
   - Every **10 minutes**

**Note:** Free **workers** may not always be available. If bot worker fails, run bot on your Mac with polling while API is on Render, or use Oracle.

---

## D. Fly.io

```bash
# install flyctl, then from repo root:
fly auth login
fly launch --config gaming/deploy/fly.toml --no-deploy
fly secrets set TELEGRAM_BOT_TOKEN_CLAWSTATION=... SUPABASE_URL=... # etc
fly deploy --config gaming/deploy/fly.toml
```

Watch free allowance; stop machines you don't need.

---

## E. Combined single process (save free resources)

If you only get **one** free container, run **bot only** (wallet watch + settle jobs live in the bot scheduler). API is optional for Circle webhooks.

```bash
python -m gaming.src.bot.main
```

Deposit detection still works via **balance poller** (no webhook required).

---

## Safety env (set on any host — free)

```bash
CLAW_PAUSED=0
CLAW_MAX_STAKE_USDC=25
CLAW_MAX_WITHDRAW_USDC=50
CLAW_DAILY_WITHDRAW_CAP_USDC=100
CLAW_WITHDRAW_PER_HOUR=5
CLAW_CHALLENGE_PER_HOUR=10
CLAW_ADMIN_TELEGRAM_IDS=YOUR_TELEGRAM_NUMERIC_ID
WALLET_WATCH_INTERVAL_SEC=45
CLAW_DEFAULT_CHAIN=arc
CLAWSTATION_BOT_MODE=polling
```

Admin commands (your Telegram ID in `CLAW_ADMIN_TELEGRAM_IDS`):
- `/pause` — freeze challenges, locks, withdraws  
- `/unpause` — reopen  
- `/safety` — show limits (anyone)

---

## Free monitoring

| Tool | Use |
|------|-----|
| [cron-job.org](https://cron-job.org) | Ping health every 10m |
| [UptimeRobot free](https://uptimerobot.com) | Alert if down (50 monitors free) |
| Telegram `/safety` | Check pause + caps |

---

## What you still need (always free tiers)

- **Supabase** free project (you already use it)
- **Circle** sandbox / free developer account for testnet
- **Telegram** bot token (free)
- **Testnet USDC** faucets (free)

---

## When you have $5–6/month later

Buy the cheapest Hetzner/DigitalOcean droplet — still use the same Docker compose. Zero code changes.
