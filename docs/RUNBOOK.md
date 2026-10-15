# Boardman Operations Runbook

Production topology:

```
browser ──▶ boardman.playingsidequest.fun (Vercel, frontend/)
                │  server routes call BOARDMAN_API_URL with BOARDMAN_API_KEY
                ▼
           Railway service (Dockerfile.akash → deploy/start_akash.py)
             ├─ api      uvicorn :8000  (critical: if it dies the container restarts)
             ├─ bot      Telegram bot, polling          (restarted with backoff)
             ├─ house    scripts/run_house_session.py   (restarted with backoff)
             └─ webhooks 3 chess + 7 football builders on 127.0.0.1:18761-18777
           Volume /data  →  /data/agentic  (ledger.json, matches.json, agents.json,
                                            spectator_books.json, house_log.db,
                                            secrets_agent_*.json, house_heartbeat.json)
           Arc chain: BoardmanEscrow / SpectatorPool hold the real USDC
```

`/data/agentic` is the off-chain book of record. If it is lost, balances
reset to zero while the escrow contracts still hold locked USDC. Treat the
volume like a database.

Health endpoints:

| Path | Purpose | Auth |
|---|---|---|
| `/api/healthz` | Liveness + Supabase ping. Railway's deploy health check uses it. | none |
| `/api/health/deep` | Readiness: event-loop lag, data dir write probe + marker, house-session heartbeat, supervised processes. **503 = act.** `status: degraded` = look soon. | none |
| `/api/stack/agentic/health` | Agentic layer summary (no paths, no key status). | none |
| `/api/stack/agentic/house/status` | Operator view: schedule, bankrolls, webhooks, last settlement. | API key |

---

## 1. Restore the backend on Railway

Symptom of the October outage: `https://boardman-api-production.up.railway.app`
answers `{"message":"Application not found"}` with header
`x-railway-fallback: true`. The service behind that generated domain was
deleted or renamed, so every Vercel server route that proxies to it
(`/api/agentic/house-play`, `/house-schedule`, …) hangs or fails.

### 1.1 Find out what is left

1. Railway dashboard → the Boardman project. Check whether the service still
   exists under another name (renamed services get a new `*.up.railway.app`
   domain) and whether a **volume** still exists in the project (volumes
   outlive deleted services only until the project is deleted; look under
   the project canvas and Settings → Volumes).
2. If the old volume exists, **do not delete it**. Note its current mount
   path: older docs mounted it at `/app/data` (state in `/app/data/agentic`).
3. If you have a laptop copy of `data/agentic/`, take a tarball now:
   `tar -C data -czf ~/boardman-data-$(date +%F).tar.gz agentic` and keep it
   somewhere encrypted. It contains agent wallet secrets.

### 1.2 Create (or repair) the service

1. New → GitHub Repo → `0xkenichi/boardman`, branch `main` **after the
   `integration/wave1` PR is merged** (until then, deploy `integration/wave1`). Railway picks up
   `railway.toml` (builder DOCKERFILE, `Dockerfile.akash`, start command
   `python /app/deploy/start_akash.py`, health check `/api/healthz`,
   restart ALWAYS, `drainingSeconds = 30`).
2. Settings → Deploy → **Replicas: 1**. The JSON store and `house_log.db`
   are single-writer; two replicas (or a second house session anywhere else
   against the same data) will corrupt state.
3. Settings → Networking → note the port `8000` (the app reads `PORT`).

### 1.3 Volume

1. Right-click the canvas → **Add Volume** (or attach the surviving one) →
   attach to the service → mount path **`/data`**.
   - Re-using an old volume that was mounted at `/app/data`: just change its
     mount path to `/data`. Its `agentic/` folder then appears at
     `/data/agentic`, which is the new default.
2. Enable **volume backups** (Volume → Backups → daily schedule).
3. Size: 1 GB is plenty today; `house_log.db` grows with games played.

### 1.4 Variables (names only — copy values from the password manager)

Persistence / process control (new):

- `RAILWAY_RUN_UID` = `0` — volumes mount root-owned; the supervisor fixes
  ownership of `/data/agentic` and drops every child to the `rematch` user.
- `REQUIRE_PERSISTENT_DATA` = `1` — refuse to boot if `/data/agentic` is not
  a writable mounted volume carrying the `.boardman-data-volume` marker.
- `BOARDMAN_DATA_INIT` = `1` — **only** for the very first boot on a
  brand-new empty volume (writes the marker). Remove it right after. A volume
  that already holds `ledger.json`/`matches.json`/`agents.json`/
  `house_log.db` adopts the marker automatically.
- `BOARDMAN_AGENTIC_DATA` — leave unset (image default `/data/agentic`).
  If an old value `/app/data/agentic` is still set, delete it.
- Optional: `BOARDMAN_PROCS` (default `webhooks,api,bot,house`),
  `BOARDMAN_HOUSE_SESSION` (`0` disables the session),
  `BOARDMAN_HOUSE_GAMES`, `BOARDMAN_HOUSE_MOVE_DELAY`, `BOARDMAN_HOUSE_PAUSE`,
  `BOARDMAN_HOUSE_MIN_STAKE`, `BOARDMAN_HOUSE_POLL_NO_FUNDS_SEC`,
  `BOARDMAN_HOUSE_HEARTBEAT_MAX_AGE_SEC` (default 120),
  `BOARDMAN_HOUSE_PHASE_MAX_SEC` (default 2700),
  `BOARDMAN_HEALTH_LOOP_LAG_FAIL_SEC` (default 5).

Required for boot / core:

- `TELEGRAM_BOT_TOKEN_BOARDMAN` (boot fails without it while the bot role runs)
- `TELEGRAM_BOT_USERNAME_MYBOARDMAN`, `TELEGRAM_BOT_USERNAME_BOARDMAN`
- `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` (`/api/healthz` pings Supabase and
  returns **503 without them** — it is Railway's health check, so set both
  **before the first deploy** or the service never goes healthy)
- `BOARDMAN_API_KEY` (and/or `REMATCH_API_KEY`) — must equal the value Vercel
  sends; `BOARDMAN_STACK_API_KEYS` / `BOARDMAN_STACK_API_KEYS_FILE` for
  builder keys
- `CLAWSTATION_BOT_MODE` = `polling`, `CLAW_DEFAULT_CHAIN` = `arc`, `NETWORK`
- `CLAW_ADMIN_TELEGRAM_IDS`, `BOARDMAN_OPS_TELEGRAM_ID`
- `REMATCH_WEB_URL`, `BOARDMAN_URL`, `REMATCH_LEADERBOARD_URL`, `FRONTEND_URL`

On-chain (only with `BOARDMAN_AGENTIC_ONCHAIN=1` / `SPECTATOR_ONCHAIN=1`):

- `BOARDMAN_AGENTIC_ONCHAIN`, `SPECTATOR_ONCHAIN`, `SPECTATOR_CHAIN`
- `BOARDMAN_RESOLVER_KEY`, `BOARDMAN_FUNDER_KEY`
- `BOARDMAN_ESCROW_ADDRESS_ARC`, `SPECTATOR_ESCROW_ADDRESS`,
  `BOARDMAN_HOUSE_WALLET`, `BOARDMAN_FEE_RECIPIENT`
- `ARC_RPC_URL`, `ARC_USDC_ADDRESS`

Payments / Circle (if used): `CIRCLE_API_KEY`, `CIRCLE_CLIENT_KEY`,
`CIRCLE_ENTITY_SECRET`, `CIRCLE_WALLET_SET_ID`, `CIRCLE_WEBHOOK_SECRET`,
`PAYSTACK_SECRET_KEY`, `PAYSTACK_PUBLIC_KEY`.

Safety limits: `CLAW_PAUSED` (`0` normally), `CLAW_MAX_STAKE_USDC`,
`CLAW_MAX_WITHDRAW_USDC`, `CLAW_DAILY_WITHDRAW_CAP_USDC`.

Demo faucet: `BOARDMAN_DEMO_FAUCET` — leave **unset** on Railway. It decides
whether the book-entry ledger may mint demo USDC:

| Value | Testnet chain | Mainnet chain |
| --- | --- | --- |
| unset | House agents and AI/house clubs are topped up for matches and season entries. Marketplace buyers are **not**: they pay from their real ledger balance or Circle wallet, or get a 402 and nothing moves. | Off. House matches and season entries use real balances only. |
| `0` / `off` | Off. A house match that can't fund refuses to open; an unpayable season entry is recorded unpaid. | Off. |
| `1` / `on` | Local demos only: also tops up marketplace buyers. Never set it on a shared deploy. | **Refused** and logged at CRITICAL. The faucet never runs on mainnet. |

"Mainnet" is the money chain only (`NETWORK=mainnet`, `CLAW_DEFAULT_CHAIN=arc_mainnet`,
or a `SPECTATOR_CHAIN`/`BOARDMAN_SETTLEMENT_RAIL` that resolves to Arc mainnet),
the same check the spectator kill switch uses. `BOARDMAN_ENV=production` on a
testnet deploy is not mainnet. On mainnet the marketplace also refuses the
book-entry rail: a sale needs bound Circle wallets or it fails with a clear
error (no silent fallback).

Agent brains (optional): `ASI_ONE_API_KEY`, `ASI_ONE_API_KEY_RAJA`,
`ASI_ONE_API_KEY_NERO`, `GEMINI_API_KEY`, `GEMINI_API_KEY_RAJA`,
`GEMINI_API_KEY_NERO`, `BOARDMAN_LLM_REASONERS`, `BOARDMAN_LLM_AGENTS`,
`BOARDMAN_ASI_AGENTS`, `LICHESS_RAJA_API_TOKEN`, `LICHESS_NERO_API_TOKEN`.

Chess engines need no variables: the image ships Stockfish
(`STOCKFISH_PATH=/usr/games/stockfish`) and, when its build succeeded,
Ethereal for Sheila at `/app/engines/Ethereal/src/ethereal`.

### 1.5 Seed the data (only if the volume is new)

```bash
railway link                     # pick the project + service
railway volume files upload ~/boardman-data-YYYY-MM-DD.tar.gz /boardman-data.tar.gz
railway ssh
#   in the container:
mkdir -p /data && tar -xzf /data/boardman-data.tar.gz -C /data && rm /data/boardman-data.tar.gz
ls -la /data/agentic             # ledger.json, matches.json, agents.json, house_log.db …
exit
railway redeploy                 # boot adopts the existing state and writes the marker
```

Before seeding, list tables stuck in `playing`/`locked` on the laptop copy
and decide per table (see §3) — do not carry silent stuck locks into prod.

### 1.6 Deploy and verify

1. Deploy. In the logs expect, in order: `[akash] roles: …`,
   `data dir OK (volume, writable, marker present): /data/agentic`,
   `webhooks listening: raja, nero, sheila, bluelock, …, tinkerer` (ten names),
   `starting API on :8000`, `starting Telegram bot`, `starting house session`.
   A line starting `[akash] FATAL:` explains exactly what is missing.
2. `curl -s https://<service>.up.railway.app/api/healthz` → `"status":"ok"`.
3. `curl -s https://<service>.up.railway.app/api/health/deep` → HTTP 200 and
   `checks.house_session.phase` advancing over a few minutes.
4. `curl -s https://<service>.up.railway.app/api/stack/agentic/public/metrics?limit=3`
   → the seeded matches.
5. Telegram: only one bot may poll. Stop any laptop bot before this point.

### 1.7 Custom domain (prevents a repeat of this outage)

1. Railway service → Settings → Networking → **Custom Domain** →
   `api.boardman.playingsidequest.fun` (or similar).
2. Add the CNAME Railway shows at the DNS provider; wait for the certificate.
3. Point Vercel at the custom domain (§2), never at `*.up.railway.app` —
   generated domains change when a service is recreated or renamed.

### 1.8 Monitoring

- Uptime monitor (UptimeRobot, Better Stack, …) on
  `https://api.<domain>/api/health/deep`, every 1–5 min, alert on non-200.
- Second monitor on the public site `https://boardman.playingsidequest.fun/`.
- Railway → Observability: alert on restarts. The supervisor logs every
  child exit as `[akash] <name> exited code=… — restart in Ns`.

---

## 2. Vercel environment (frontend/)

Project → Settings → Environment Variables (Production, and Preview if
previews should reach a backend). Names only:

Backend link (server-only, required):

- `BOARDMAN_API_URL` — `https://api.<domain>` (custom domain from §1.7)
- `BOARDMAN_API_KEY` — same value as the backend's `BOARDMAN_API_KEY`
- Legacy aliases still read if the above are absent — delete them once the
  new names are set so nothing silently wins: `REMATCH_API_URL`,
  `REMATCH_API_KEY`, `STACK_API_URL`, `STACK_API_KEY`, `REMATCH_API_BASE`

Sessions / auth (server-only):

- `REMATCH_SESSION_SECRET` (falls back to the API key if unset — set it)
- `REMATCH_ALLOW_DEMO_LOGIN`, `REMATCH_DEMO_PROFILE_ID` (leave unset in prod)
- `REMATCH_PROFILE_LOOKUP_URL`
- `ADMIN_TELEGRAM_IDS`, `CLAW_ADMIN_TELEGRAM_IDS`
- `TELEGRAM_BOT_TOKEN_BOARDMAN`, `TELEGRAM_BOT_TOKEN_MYBOARDMAN`,
  `TELEGRAM_BOT_TOKEN_CLAWSTATION`, `TELEGRAM_BOT_TOKEN` (Telegram login
  verification)
- `BOARDMAN_SITE_HOSTS` — host allow-list from the auth-hardening branch;
  set it to `boardman.playingsidequest.fun` when that change ships (not read
  by `main` yet)

Supabase (server-only): `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`,
`SUPABASE_SERVICE_KEY`, `SUPABASE_ANON_KEY`, `SUPABASE_ANON`

Payments / chain / agents (server-only): `PAYSTACK_SECRET_KEY`,
`ARC_RPC_URL`, `ARC_USDC_ADDRESS`, `ASI_ONE_API_KEY`, `ASI_API_KEY`,
`ASI_ONE_BASE_URL`, `ASI_ONE_MODEL`, `GEMINI_API_KEY`, `GEMINI_API_KEY_NERO`,
`GEMINI_MODEL`, `GOOGLE_API_KEY`, `GOOGLE_GENERATIVE_AI_API_KEY`,
`BOARDMAN_LLM_AGENTS`, `BOARDMAN_LLM_REASONERS`, `BOARDMAN_NERO_REASONERS`,
`BOARDMAN_ASI_AGENTS`, `BOARDMAN_AGENTIC_DATA` (local dev only — leave unset
on Vercel)

Public (shipped to the browser — never put a secret here):
`NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`,
`NEXT_PUBLIC_ARC_RPC_URL`, `NEXT_PUBLIC_ARC_USDC_ADDRESS`,
`NEXT_PUBLIC_BOT_USERNAME`, `NEXT_PUBLIC_TELEGRAM_BOT_NAME`,
`NEXT_PUBLIC_TELEGRAM_BOT_USERNAME`, `NEXT_PUBLIC_TELEGRAM_BOT_URL`,
`NEXT_PUBLIC_TELEGRAM_GROUP_URL`, `NEXT_PUBLIC_REMATCH_TG_GROUP`,
`NEXT_PUBLIC_MINIPAY_ENTRY_URL`, `NEXT_PUBLIC_SITE_HOST` (wallet sign-in
message domain — `boardman.playingsidequest.fun`), `NEXT_PUBLIC_ALLOW_DEMO_LOGIN`
(unset in prod)

Regenerate this list with:

```bash
grep -rhoE 'process\.env\.[A-Z0-9_]+' frontend --include='*.ts' --include='*.tsx' \
  --include='*.js' --include='*.mjs' --exclude-dir=node_modules --exclude-dir=.next \
  | sort -u
```

After changing variables: Deployments → latest production → **Redeploy**
(env changes do not apply to existing deployments). Verify:
`curl -s https://boardman.playingsidequest.fun/api/agentic/house-play` returns
JSON quickly instead of hanging.

---

## 3. Pause, manual resolve, cancel

All commands below run inside the container (`railway ssh`, then `cd /app`)
unless they are HTTP calls. `$API` is the backend URL and `$KEY` the master
API key (read it from the password manager into your shell; do not paste it
into tickets or chat).

### 3.1 Pause levels (least to most disruptive)

1. **Stop opening new house games** (keeps everything else live):
   ```bash
   curl -s -X POST "$API/api/stack/agentic/house/schedule" \
     -H "X-Rematch-Key: $KEY" -H 'Content-Type: application/json' \
     -d '{"enabled": false}'
   ```
   The session finishes the table in progress, then idles
   (`phase: schedule_paused` in `/api/health/deep`). Resume with
   `{"enabled": true}`.
2. **Freeze user money movement** (stakes, withdrawals): set Railway variable
   `CLAW_PAUSED=1` and redeploy. The Telegram `/pause` admin command only
   pauses the bot process and is lost on restart — use the variable for
   anything that must hold.
3. **Stop the house session process entirely**: `BOARDMAN_HOUSE_SESSION=0`,
   redeploy. Deep health then reports the session as `disabled`.
4. **Freeze new escrow deposits on-chain**: the escrow owner calls `pause()`
   on `BoardmanEscrow` / `SpectatorPool` (owner wallet, from the hardware or
   ops wallet — never from the server). `createMatch`/`joinMatch` stop;
   `resolveMatch`/`cancelMatch` keep working so locked funds can still be
   released.
5. **Full stop**: Railway → service → remove the active deployment (the
   volume stays). Restore with Redeploy.

### 3.2 A table settled off-chain but is still LOCKED on-chain

```bash
python scripts/verify_onchain_settlement.py                  # exit 1 lists problems
python scripts/settle_stuck_matches.py --match agm_xxx       # dry run, prints the plan
python scripts/settle_stuck_matches.py --match agm_xxx --apply
```

Draws refund both sides (`cancelMatch`); otherwise the winner is paid
(`resolveMatch`). Needs `BOARDMAN_RESOLVER_KEY`. Re-run the verify script
afterwards; it must exit 0 for that match.

### 3.3 Cancel a table that never produced a result

For `open` / `locked` / `partial_lock` / `queued` / `lock_failed` tables with
no result (refunds the ledger, and the escrow via `cancelMatch` whenever the
escrow holds a stake on-chain — status OPEN, LOCKED or DISPUTED; an escrow
that is already RESOLVED/CANCELLED is left alone, and one that was never
created is skipped unless a lock tx for it may still mine, in which case the
abort waits and retries):

```bash
python -c "from gaming.src.stack.agentic.house import get_house; \
print(get_house().abort_never_started('agm_xxx', reason='ops_manual'))"
```

It refuses `playing` tables and tables that already have a result — those
must be settled, not cancelled. Pause the schedule (§3.1 step 1) first so
the session does not race you.

### 3.4 A table stuck in `playing`

1. Check `/api/stack/agentic/house/status` and the logs for that match id.
2. The API re-seats orphaned `playing`/`locking`/`locked` tables on start
   (`rescue_orphans`); a restart of the service is the first fix.
3. If it still does not move, drive it explicitly:
   `curl -X POST "$API/api/stack/agentic/house/matches/agm_xxx/play" -H "X-Rematch-Key: $KEY" -H 'Content-Type: application/json' -d '{"wait": false}'`.
4. Only if the game can never finish: record the decision in the incident
   log, then settle it as a draw on-chain via §3.2 after marking the result.

### 3.5 Spectator tickets: which balance pays

Every ticket in a chess spectator book records the rail its stake came from
(`bets[].funding`), and settlement / void pays it back on that rail only:

| funding | taken by | paid / refunded by |
|---|---|---|
| `profile` | web + Telegram (`/api/rematch/web/spectator/bet`): Circle pull or `play_adjust` | `play_adjust:<i>` / `abort:play_adjust:<i>` journal steps |
| `ledger` | stack API (`/matches/{id}/spectator/bet`, `/house/matches/{id}/bets`): ledger debit `spectator_bet`, same transaction as the ticket | agentic-ledger credit in the `spectator_settle` / `abort:spectator` step |
| `onchain` | SpectatorPool deposit (projected) | the pool (`claim`); never the ledger |

Tickets booked before the field existed count as `profile`. The platform
fee, rounding dust and any share with nobody to receive it are credited to
`0xboardman_agentic_treasury` (reason `spectator_fee`); `payouts.house_take`
on the book is that amount. A market nobody backed (no ticket on the winning
side, or no draw ticket on a draw) refunds every ticket and seed, as the pool
does. To audit one book: the sum of `payouts.bettors` + `creators` +
`seed_refunds` + `draw_book.agent_split` + `house_take` equals the sum of
`bets` + `payouts.funded_seeds`, to the micro.

### 3.6 Wallet bridge: transfers stuck between play balance and football wallet

`POST /api/stack/agentic/football/wallet/deposit|withdraw` moves USDC between
a player's **play balance** (on-chain play address + `play_adjust.json`
overlay — the number the bot shows) and their **football wallet**
(`owner:<profile_id>` in the agentic ledger). Each transfer is a row in
`wallet_bridge_transfers` (key `<profile_id>|<idempotency_key>`):

| status | meaning | money |
|---|---|---|
| `pending` | deposit row written, play balance not (yet) debited | nothing moved, or the debit just landed |
| `debited` | first side moved (deposit: play balance; withdraw: ledger) | in flight — held by the row |
| `reversing` | ops asked to undo it | being given back |
| `completed` / `failed` / `reversed` | done | conserved |

A crash between the two sides leaves `pending`/`debited`. The **reconciler**
finishes them: the house maintenance tick runs it every ~5 min on rows older
than `BOARDMAN_BRIDGE_STALE_SEC` (default 300). Each step is idempotent
(play-balance moves are keyed `bridge:<transfer>:debit|credit|reverse` in
`play_adjust.json` → `applied`; ledger moves commit with their status
change), so running it again, or alongside the tick, is always safe.

Inspect:

```bash
# open transfers (any age), as JSON — read-only
curl -s "$API/api/stack/agentic/admin/wallet-bridge/pending" -H "X-Rematch-Key: $MASTER_KEY"
# inside the container: dry run lists what would happen
python scripts/reconcile_wallet_bridge.py --all
# one player's history
python scripts/reconcile_wallet_bridge.py --party <profile_id>
```

Act:

```bash
python scripts/reconcile_wallet_bridge.py --apply                 # finish stale rows
python scripts/reconcile_wallet_bridge.py --all --apply           # include fresh rows (only when no request is live)
python scripts/reconcile_wallet_bridge.py --reverse '<profile_id>|<key>' --apply   # undo instead
```

What "finish" does: deposit `pending` → if the play debit landed, credit the
ledger, else mark `failed`; deposit `debited` → credit the ledger; withdraw
`debited` → credit the play balance. `--reverse` gives back whichever side
moved. Check afterwards: `ledger_txs` rows with `ref = '<transfer_key>'`
(`bridge_deposit`, `bridge_withdraw`, `bridge_withdraw_reversed`) and
`play_adjust.json` → `applied["bridge:<transfer_key>:…"]`.

Deposits are refused on mainnet (the football wallet is book-entry, testnet
only); withdrawals always work so money can come back out.

**One wallet per person.** `owner:<profile_id>` is the only ledger key for a
person's football money: bridge, AFM bets/payouts/refunds, marketplace buys
and proceeds, stack-API chess tickets. AFM bets used to use the bare
`<profile_id>` key; that balance is folded in on the person's next bet, buy
or bridge call (`football_wallet_merge_out/_in` rows). After deploy, fold
everyone at once:

```bash
python scripts/merge_football_wallets.py          # dry run: who, how much, held back
python scripts/merge_football_wallets.py --apply
```

"Held back" is chess spectator winnings the old settlement credited to bare
ids without ever debiting a stake (minted). They stay on the bare key and are
never merged; decide case by case whether to zero them (incident log).

---

## 4. Daily reconciliation

Run once a day (and after every incident or deploy that touched money code).
Record the numbers in the ops log.

1. **Health**: `/api/health/deep` is 200; `processes.*.restarts` did not jump
   since yesterday; `house_session.games` increased (unless paused/no funds).
2. **Escrow vs book** (inside the container):
   ```bash
   python scripts/verify_onchain_settlement.py; echo "exit=$?"
   ```
   Exit 0 required. Every non-zero line becomes a §3.2 action.
3. **Locked money**: the escrow contract's `contractBalance()` must equal the
   sum of stakes of matches that are `LOCKED`/`OPEN`/`DISPUTED` on-chain.
   Compare with `/api/stack/agentic/admin/metrics-detail` (note: this route
   is not key-gated on `main` today — treat its output as sensitive). A
   positive difference with no open matches is stuck money — find it with
   the verify script.
4. **Agent bankrolls**: `/api/stack/agentic/house/status` `agents[].bankroll_usdc`
   against on-chain USDC of each wallet (Arc explorer). Off-chain balances
   above on-chain balances mean the ledger is ahead of the chain — stop and
   investigate before more games run.
5. **Stale tables**: no match should sit in `locking`/`locked`/`playing` for
   more than an hour, and none in `settle_failed`/`lock_failed` at all.
5b. **Wallet bridge**: `python scripts/reconcile_wallet_bridge.py` prints
   "no open transfers". Anything listed is older than 5 minutes and the tick
   has not finished it — follow §3.6.
6. **Backups**: the latest Railway volume backup is from the last 24h. Once a
   week, download one (`railway volume files download` or the dashboard) and
   check it untars and contains `ledger.json`.

---

## 5. Incident response: suspected key compromise

Keys that move money or impersonate the platform:

| Key | Where | Blast radius |
|---|---|---|
| `BOARDMAN_RESOLVER_KEY` / `RESOLVER_PRIVATE_KEY` | Railway | Can resolve any LOCKED escrow to either player |
| `BOARDMAN_FUNDER_KEY`, `GAS_TANK_PRIVATE_KEY`, `ADMIN_PRIVATE_KEY` | Railway / laptop | Drains those wallets |
| `secrets_agent_*.json` | volume `/data/agentic` | Drains agent / house wallets |
| Escrow owner wallet | ops / hardware wallet | `setResolver`, `setFeeRecipient`, `pause` |
| `BOARDMAN_API_KEY` / `REMATCH_API_KEY` / `BOARDMAN_STACK_API_KEYS` | Railway + Vercel | Full Stack API incl. house controls |
| `REMATCH_SESSION_SECRET` | Vercel | Forge user sessions |
| `TELEGRAM_BOT_TOKEN_*` | Railway + Vercel | Impersonate the bot |
| `SUPABASE_SERVICE_ROLE_KEY`, `CIRCLE_*`, `PAYSTACK_SECRET_KEY` | Railway / Vercel | User data, custodial wallets, fiat |
| `WHATSAPP_ACCESS_TOKEN`, `WHATSAPP_APP_SECRET` | API server | Message players as Boardman; forge inbound WhatsApp messages |

1. **Contain (minutes)**
   - Escrow owner calls `pause()` on BoardmanEscrow and SpectatorPool.
   - `CLAW_PAUSED=1`, `BOARDMAN_HOUSE_SESSION=0` on Railway, redeploy.
   - If the resolver key is suspected: escrow owner calls
     `setResolver(<fresh address>)` **before** anything else — the old key
     can otherwise resolve every locked match to the attacker's side.
   - If an agent/house wallet secret is suspected: move remaining funds from
     that wallet to a fresh ops wallet using the owner of that key.
2. **Preserve evidence**: export Railway logs for the window, download a
   volume backup, note recent Vercel deployments and env changes, and the
   GitHub audit log. Do not wipe anything yet.
3. **Rotate** — every key in the affected row, then anything that shared a
   machine/file with it (`.env` on the laptop, Railway variables, Vercel
   variables). Order: chain keys (new resolver/funder/agent wallets, update
   `setResolver`), then `BOARDMAN_API_KEY` on Railway **and** Vercel in the
   same window (mismatch = every Vercel → API call 401s), then
   `REMATCH_SESSION_SECRET` (logs everyone out), then Telegram (BotFather →
   revoke), Supabase service role, Circle, Paystack.
4. **Assess**: run §4 reconciliation; list every on-chain tx from the
   affected addresses since the suspected exposure; compare against
   `house_log.db`.
5. **Recover**: unpause in reverse order (contracts last), watch
   `/api/health/deep` and the first few settlements by hand.
6. **Write up** within 48h: timeline, root cause, which keys rotated, user
   impact and refunds owed.

Never paste key values into chat, tickets, commit messages or logs. The
health endpoints intentionally do not report which keys are configured.

---

## 6. Local / VPS stack (docker compose)

```bash
cp .env.example .env            # fill in values
BOARDMAN_DATA_INIT=1 docker compose up -d --build   # first run on a new volume only
docker compose up -d            # every run after that
curl -s localhost:8000/api/health/deep
```

For a local demo where anyone can click "buy" without depositing first, set
`BOARDMAN_DEMO_FAUCET=1` in `.env` (see §1.4; it is refused on mainnet).

`boardman-api` (webhooks + API), `boardman-bot` and `boardman-house` share
the named volume `boardman-data` at `/data`. `docker compose down` keeps it;
`docker compose down -v` deletes every balance — do not.

---

## 7. Running against Postgres

The agentic store (ledger, matches, books, LP pools, settlement journal,
leases, nonces) runs on SQLite unless a Postgres URL is set:
`BOARDMAN_DATABASE_URL` wins over `DATABASE_URL`. Production points it at
Supabase; `psycopg[binary]` must be installed (it is in
`src/backend/requirements.txt`).

- **Schema.** Apply `supabase/migrations/20261014120000_agentic_ledger.sql`
  once (it is idempotent). The app also creates anything missing on its
  first connection, but when the catalog already matches it runs no DDL,
  so a replica starting up never locks tables under live traffic.
- **Row-level security** is on for every table with no policies: only the
  owner / service role (the API's URL) can read or write, never the anon or
  authenticated keys. Do not add policies to these tables.
- **Pooler.** Server-side prepared statements are off, so the Supabase
  transaction-mode pooler URL works.

Run the tests against a real Postgres (opt-in; without it the suite stays
on SQLite):

```bash
docker run -d --name bm-pg -p 127.0.0.1:5432:5432 \
  -e POSTGRES_HOST_AUTH_METHOD=trust -e POSTGRES_DB=boardman_test postgres:16
pip install "psycopg[binary]"
BOARDMAN_TEST_DATABASE_URL=postgresql://postgres@127.0.0.1:5432/boardman_test \
  pytest -q tests/test_storage_*.py tests/test_ledger_*.py tests/test_settlement_*.py
docker rm -f bm-pg
```

The URL must be loopback (the tests stay hermetic). Each test gets its own
schema, dropped afterwards. Never point it at Supabase. CI runs the same
money/storage subset on a `postgres:16` service container (job
`python-postgres` in `.github/workflows/ci.yml`).

---

## 8. Chat channels (WhatsApp, Telegram core flows)

Design: `docs/channels/CHANNELS_DESIGN.md`. Meta setup click-path:
`docs/channels/WHATSAPP_SETUP.md`. Everything is off by default except the
Telegram web PIN.

### 8.1 Schema and backfill

1. Apply `supabase/migrations/20261016120000_channel_identities.sql` to the
   profiles database (Supabase). Idempotent.
2. `supabase/migrations/20261016120100_channels_state.sql` is the Postgres
   rendering of the channels state tables; the app also creates them on first
   use (SQLite or Postgres), so apply it only when the agentic store is Postgres.
3. `python scripts/backfill_channel_identities.py` (dry run, prints counts),
   then `--apply`. Safe to re-run. From then on the bot dual-writes every
   Telegram profile lookup.

**The bot and the API must share one agentic store** (the same
`BOARDMAN_DATABASE_URL`, or the same `BOARDMAN_AGENTIC_DATA` dir on one
machine): a withdraw link issued by the bot is confirmed by the API.

### 8.2 Variables

Flags (bot **and** API):

- `CHANNELS_CORE_FLOWS` — comma list of flows the shared core runs on every
  channel: `balance`, `deposit`, `link`, `withdraw`, the skill-match flows
  `challenge`, `match` (my matches, accept/decline, lock, cancel), `report`
  (result + screenshot + dispute) and `watch` (link to the web arena), or
  `all`. Default empty: Telegram keeps its legacy handlers. Rollback = clear
  it and restart.
- `CHANNELS_CORE_FLOWS_TELEGRAM`, `CHANNELS_CORE_FLOWS_WHATSAPP` — per-channel
  override. **Production: `CHANNELS_CORE_FLOWS_WHATSAPP=all`** with Telegram
  left empty. On Telegram `all` means the four Phase 0 flows only; the match
  flows switch there only when named (e.g. `all,challenge,match,report`).
- `WHATSAPP_ENABLED=1` also routes notices for WhatsApp-first players
  (WhatsApp identity, opted in, no Telegram chat or a lower
  `notify_priority`) from the bot jobs, settlement and Telegram handlers to
  WhatsApp: free-form inside the 24 h window, the approved template outside
  it. Telegram players get exactly the same DMs as before.
- `CHANNELS_APPROVAL_TTL_SEC` (300) — how long a "Lock $X USDC?" Yes/No
  prompt stays valid.
- `TELEGRAM_WITHDRAW_WEB_PIN` — default `1`: Telegram withdrawals confirm on
  `/app/withdraw/<token>` with a PIN; `/set_tx_password` and
  `/reset_tx_password` point to the web. `0` restores the typed password.
  **Deploy the frontend page before (or with) the backend.**
- `WHATSAPP_ENABLED` — `1` mounts `/webhooks/whatsapp` on the API. Default off.

WhatsApp (API server; values from the password manager):

- `WHATSAPP_APP_SECRET` (secret: webhook signature), `WHATSAPP_VERIFY_TOKEN`
  (secret: webhook handshake), `WHATSAPP_ACCESS_TOKEN` (secret: system-user
  token), `WHATSAPP_PHONE_NUMBER_ID`, `WHATSAPP_DISPLAY_NUMBER` (digits, for
  `wa.me` links; also set on the bot), optional `WHATSAPP_GRAPH_VERSION`.

Links and identity (bot and API):

- `CHANNELS_SITE_URL` — base for one-time links (default `BOARDMAN_URL`,
  else `https://boardman.playingsidequest.fun`).
- `CHANNELS_LINK_PEPPER` (secret) — HMAC key for link codes at rest. Set it
  once; changing it invalidates codes issued in the last 10 minutes only.
- `CHANNELS_IDENTITY_STORE` — leave unset (Supabase). `memory` is for local
  development without Supabase.

Tuning (defaults are fine): `CHANNELS_LINK_CODE_TTL_SEC` (600),
`CHANNELS_LINK_ISSUE_PER_HOUR` (5), `CHANNELS_LINK_REDEEM_PER_10MIN` (5),
`CHANNELS_LINK_WITHDRAW_HOLD_HOURS` (72: withdrawals from a newly linked chat
wait this long), `CHANNELS_WITHDRAW_LINK_TTL_SEC` (600),
`CHANNELS_WITHDRAW_LINKS_PER_HOUR` (5), `CHANNELS_PIN_TRIES_PER_HOUR` (10),
`CHANNELS_WA_MAX_AGE_SEC` (259200: older webhook deliveries are dropped),
`CHANNELS_EVIDENCE_STORE` (`local` | `supabase`), `CHANNELS_EVIDENCE_BUCKET`
(`match-evidence`, private), `CHANNELS_MEDIA_MAX_BYTES` (8 MiB).

Geo: `config/compliance/geo_fence.json` → `channel_signals`. WhatsApp phone
country codes are enforced; Telegram only logs (`enforce: false`).
`POST /api/channels/withdraw/*` is a geo-fenced money route.

### 8.3 Operations

- **Turn WhatsApp off fast:** `WHATSAPP_ENABLED=0` and restart the API (the
  webhook disappears; Meta retries, then gives up). Or clear
  `CHANNELS_CORE_FLOWS_WHATSAPP` to keep the webhook but offer nothing.
- **A player says "I didn't link that number":** look up
  `channel_identities` by profile, set `revoked_at` on the row, and pause
  withdrawals for the profile while you investigate.
- **Skill matches on WhatsApp:** challenges, accepts, locks, reports and
  settlement use the same services and escrow as Telegram
  (`src/channels/core/actions/matches.py`); a player can challenge by tag, by a
  WhatsApp number, or with an invite (`JOIN <code>` via `wa.me`, plus the web
  and Telegram links). Locking asks a Yes/No first; the Yes button carries a
  one-time nonce bound to that player, that chat and that message
  (`channel_tokens`, purpose `approve:lock`). Screenshots are copied at once to
  the evidence store (`evidence://…`); AI vision reads them from there.
  Spectator betting is never in the chat: "Watch & bet" links to `/arena`.
- **A WhatsApp dispute** flags the match like `/dispute` and DMs the Telegram
  admins (`admin_telegram_ids`); resolve it with the usual admin tools.
- **Merge requests for two funded profiles** are refused by design and come
  to support: move funds manually, then link.
- **Stuck withdraw link** (`channel_tokens.status = 'claimed'` with no result):
  the payout crashed mid-way. Check `gaming.wallet_debit_audit` and Circle for
  the transfer before doing anything; never reopen the token.

