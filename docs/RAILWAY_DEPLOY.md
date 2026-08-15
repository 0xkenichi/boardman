# Boardman API + Telegram Bot — Railway Deploy

**Goal:** run the Boardman API **and** the Telegram bot on Railway 24/7, off the
laptop. The laptop currently runs everything behind a throwaway Cloudflare quick
tunnel (URL changes on restart, dies on reboot, drops requests — see the
"looks dated" admin stats). Railway replaces that with a real, always-on host.

**What ships with this repo:**
- `railway.toml` — builder `DOCKERFILE` using `Dockerfile.akash`, healthcheck on
  `/api/healthz`, restart policy ALWAYS.
- `Dockerfile.akash` — runs `deploy/start_akash.py`, which starts **both** the
  API (uvicorn :8000) and the bot (`python -m gaming.src.bot.main`, polling).
  If either process exits, the container exits and Railway restarts it.

> One service, one volume, one set of variables. Nothing else is needed.

---

## 0. Prereqs

- Railway account + CLI:
  ```bash
  curl -fsSL https://railway.app/install.sh | sh
  railway login
  ```
- You'll create the project from this repo root. The CLI links the current
  directory.

---

## 1. Create the project + first deploy

```bash
railway init          # creates a project linked to this folder
railway up            # first deploy (uses railway.toml + Dockerfile.akash)
```

> **Or** connect GitHub (Project → Settings → Connect GitHub Repo). Pushes to
> `main` auto-deploy with the same `railway.toml`.

Give Railway a public domain (needed for Vercel → API calls):
```bash
railway domain
```
Note the URL, e.g. `https://boardman-api-production.up.railway.app`.

---

## 2. Variables (secrets)

Set these on the Railway service. **Use the same values as your laptop `.env`**
(master key must match what Vercel sends, or every Vercel → API call 401s).

```bash
railway variable set \
  TELEGRAM_BOT_TOKEN_BOARDMAN="..." \
  TELEGRAM_BOT_USERNAME_MYBOARDMAN="myboardmanOfficialBot" \
  SUPABASE_URL="..." \
  SUPABASE_SERVICE_ROLE_KEY="..." \
  BOARDMAN_API_KEY="..." \
  CLAWSTATION_BOT_MODE="polling" \
  CLAW_DEFAULT_CHAIN="arc" \
  NETWORK="testnet" \
  PORT="8000" \
  BOARDMAN_AGENTIC_DATA="/app/data/agentic" \
  SPECTATOR_ONCHAIN="1" \
  CLAW_ADMIN_TELEGRAM_IDS="6277067771" \
  REMATCH_WEB_URL="https://boardman.playingsidequest.fun" \
  BOARDMAN_URL="https://boardman.playingsidequest.fun" \
  REMATCH_LEADERBOARD_URL="https://boardman.playingsidequest.fun/leaderboard" \
  RAILWAY_RUN_UID="0"
```

Also copy over, **only if they're set on the laptop** (values identical):
- Circle: `CIRCLE_API_KEY`, `CIRCLE_CLIENT_KEY`, `CIRCLE_ENTITY_SECRET`,
  `CIRCLE_WALLET_SET_ID`, `CIRCLE_WEBHOOK_SECRET` (required once webhooks are used)
- Agent brains: `ASI_ONE_API_KEY_RAJA`, `ASI_ONE_API_KEY_NERO`,
  `GEMINI_API_KEY_RAJA`, `GEMINI_API_KEY_NERO` (+ `BOARDMAN_LLM_REASONERS`)
- On-chain (only if `BOARDMAN_AGENTIC_ONCHAIN=1`): `BOARDMAN_RESOLVER_KEY`,
  `BOARDMAN_FUNDER_KEY`
- Lichess gym: `LICHESS_RAJA_API_TOKEN`, `LICHESS_NERO_API_TOKEN`
- Builder keys file: `BOARDMAN_STACK_API_KEYS` (if any)

Notes:
- `RAILWAY_RUN_UID=0` is **required**: the image runs as a non-root user
  (`USER rematch`) but Railway volumes mount as root. Without this, the app
  can't write to the volume.
- `start_akash.py` hard-fails at boot if `TELEGRAM_BOT_TOKEN_BOARDMAN`
  (or the legacy `TELEGRAM_BOT_TOKEN_*`) is missing — that's intentional.

---

## 3. Persistent volume (the whole data dir)

All state lives in `data/agentic/` (`matches.json`, `ledger.json`,
`agents.json`, `spectator_books.json`, `house_log.db`, `secrets_agent_*.json`,
…). The container resolves it as `/app/data/agentic`, so mount the volume at
**`/app/data`**.

```bash
railway volume add --mount /app/data --name boardman-data
```

> The CLI may prompt interactively for the service and mount path instead of
> taking flags — answer `boardman-api` (your service) and `/app/data`.

> **Important:** the mount path is `/app/data` — Railway's build root is `/app`
> and the app writes `./data` relative to it. Mounting at `/data` would NOT
> persist anything.
>
> UI alternative: right-click the canvas → Add Volume → attach to the service →
> mount path `/app/data`.

---

## 4. Seed the volume with the laptop's data (one time)

The volume is empty until you copy the state over. The data contains agent
wallet secrets — **never commit it to git**; copy it straight from the laptop:

```bash
# On the laptop, from the repo root:
tar -C data -czf /tmp/boardman-data.tar.gz agentic

# Upload to the volume:
railway volume files upload /tmp/boardman-data.tar.gz /boardman-data.tar.gz

# Extract inside the running container:
railway ssh --service <your-service-name>
#   (in the remote shell)
mkdir -p /app/data && tar -xzf /boardman-data.tar.gz -C /app/data && rm /boardman-data.tar.gz
```

**Easier alternative:** `railway volume browse /app/data` — interactive TUI where
you can drag-drop the contents of `data/agentic/` directly onto the volume.

Verify the data landed (remote shell): `ls -la /app/data/agentic` should show
`matches.json`, `agents.json`, `secrets_agent_boardman_house.json`, etc.

> Before seeding, decide what to do with the **stuck table** (`agm_a45ddee1a880`,
> "playing" since 2026-08-15 03:18 with an empty PGN — no moves ever recorded).
> Carry it over as-is, or mark it cancelled/aborted first so the fresh host
> starts clean. See the discussion in this session.

---

## 5. Verify the Railway host

```bash
curl https://<your-service>.up.railway.app/api/healthz
# → {"status":"ok","checks":{"supabase":"ok","circle":"ok"},"version":"0.1.0"}

curl https://<your-service>.up.railway.app/api/stack/agentic/public/metrics?limit=3
# → should return your seeded matches (via=stack_api numbers match the desk)
```

Check the bot is up in the deploy logs: `[akash] starting Rematch bot (polling)`
and no FATAL line.

**Telegram polling conflict:** only one bot instance should poll. Once the
Railway bot is confirmed running, stop the laptop's bot process or the two will
steal each other's updates.

---

## 6. Point the live site at Railway

Vercel (`frontend/`) talks to the API through `BOARDMAN_API_URL`:

```bash
cd frontend
vercel env rm BOARDMAN_API_URL production --yes
echo "https://<your-service>.up.railway.app" | vercel env add BOARDMAN_API_URL production --yes
vercel --prod --yes
```

Verify end-to-end:
```bash
curl https://boardman.playingsidequest.fun/api/agentic/house-play
# → {"ok":true,"match_id":"...","status":"settled"|"playing",...}
```

---

## 7. Turn off the laptop host

Once Vercel is pointed at Railway and the bot answers on Telegram:

```bash
# Stop the laptop API + bot + tunnel (or leave them for local dev only).
# kill the uvicorn / bot.main / cloudflared processes
```

The quick tunnel (`scripts/_start_tunnel_detached.py`) is dev-only; it dies on
reboot and its URL changes — do not use it for production.

---

## Operations

- **Logs:** `railway logs --service <svc>` (or the dashboard).
- **Restarts:** `restartPolicyType = "ALWAYS"` in `railway.toml` — crash or
  process death restarts the container automatically.
- **Backups:** Railway supports volume backups (dashboard). The `data/agentic`
  dir is the whole game state — back it up before any risky change.
- **Env changes:** `railway variable set KEY=VALUE` then redeploy
  (`railway redeploy` or `railway up`).
- **Bigger volume later:** Hobby/Pro plans can live-resize without downtime.
