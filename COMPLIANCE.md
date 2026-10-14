# Boardman Compliance & Custody Posture

> **Not legal advice.** This file describes what the code does today and the
> technical controls around it. It was written by engineers, not lawyers.
> Every policy choice here needs review by gaming and fintech counsel; the
> open questions are in [`docs/legal/COUNSEL_BRIEF.md`](docs/legal/COUNSEL_BRIEF.md).

Last reconciled with code: 2026-10-14 (branch `docs/compliance-truth`).

Related documents:

| Document | Purpose |
|----------|---------|
| [`docs/legal/COUNSEL_BRIEF.md`](docs/legal/COUNSEL_BRIEF.md) | Brief and question list for outside counsel |
| [`docs/compliance/KYC_AML_PLAN.md`](docs/compliance/KYC_AML_PLAN.md) | Proposed KYC/AML thresholds, code hooks, spectator-betting kill switch spec |
| [`docs/LEGAL.md`](docs/LEGAL.md) | Working legal notes (risk framing, disclaimers) |
| [`docs/TERMS_OF_SERVICE.md`](docs/TERMS_OF_SERVICE.md) | Draft terms with `[COUNSEL: …]` markers |
| [`docs/MAINNET_GOLIVE_CHECKLIST.md`](docs/MAINNET_GOLIVE_CHECKLIST.md) | Go-live gate, including legal/compliance items |

---

## 1. Blocked jurisdictions

### Single source of truth

**`config/blocked_regions.json`** is the only blocked list, and it is tracked
in git. Every other copy is a symlink or a mirror of it:

- `gaming/config` is a local symlink to `config/` (the `gaming/` shim directory
  is gitignored and is materialised by the Dockerfiles as symlinks).
- `Dockerfile.akash` (used by Railway) and the Akash SDL set
  `BLOCKED_REGIONS_FILE=/app/config/blocked_regions.json`.
- Since this branch, the middleware's default path is the same file, resolved
  from the repo root. Before this fix, any process without
  `BLOCKED_REGIONS_FILE` (the plain `Dockerfile`, `docker compose` without the
  env, most local runs) resolved a path *outside* the repo and **blocked
  nobody**. Only the Railway/Akash image loaded the list.

### Current list (version 3, 33 countries)

| Region | Countries |
|--------|-----------|
| Americas | US, MX |
| Europe | GB, NL, DE, FR, IT, ES, RU, TR |
| Middle East / North Africa | AE, SA, QA, KW, IQ, IR, SY, YE, LY, EG |
| South / East / Southeast Asia | IN, PK, BD, CN, KP, KR, JP, SG, MY, TH, VN, ID |
| Oceania | AU |

**Nigeria (NG) is not blocked.** It was removed on 2026-08-13 (commit
`cf035e4`, "compliance: unblock Nigeria"). That commit message and the old
version of this file wrongly said the list became empty. It did not. The other
33 entries above stayed blocked, and they still are.

The list was built as a conservative testnet default. Counsel has not
reviewed it. See questions 4 and 5 in the counsel brief.

### Changing the list

1. Edit `config/blocked_regions.json` and bump `version`.
2. Update the table above and the summary in `docs/TERMS_OF_SERVICE.md` §4.
3. Record who approved it (compliance owner, and counsel for any removal) in
   the commit message.
4. Run `pytest tests/test_geo_fence.py tests/test_geo_fence_strict.py`.

---

## 2. Geo-fence

Implementation: `src/backend/middleware/geo_fence.py`. Route policy:
`config/compliance/geo_fence.json`.

### Detection

| Caller | Country source |
|--------|----------------|
| Browser / unkeyed HTTP | `cf-ipcountry`, then `x-vercel-ip-country`, then MaxMind GeoLite2 (`data/GeoLite2-Country.mmdb`, if present) |
| Vercel BFF (master API key) | **Only** the trusted header `x-boardman-client-country`. Edge headers and IP on that hop describe Vercel, not the user. |
| Third-party builder (non-master Stack key) | Same as unkeyed: edge headers, then MaxMind. The trusted header is ignored. |
| Telegram bot | **No real signal.** Telegram does not expose user IP. `/start` only checks `TELEGRAM_USER_COUNTRY`, a single process-wide env value meant for demos. |

The values `XX` and `T1` (Cloudflare unknown and Tor), and anything that is not
a two-letter code, count as "unknown".

### Money routes and strict mode

A money route deposits, bets, locks a stake, withdraws, buys, or makes a
spectator or LP move. They are listed by method and path pattern in
`config/compliance/geo_fence.json`. If that file is missing or malformed, every
mutating `/api/*` call counts as a money route.

`GEO_FENCE_STRICT` controls fail-closed behaviour:

- If it is set (`1`/`0`), that value wins.
- Otherwise it is **on** when the process looks like production: `BOARDMAN_ENV`,
  `APP_ENV` or `ENVIRONMENT` is `production`/`prod`/`mainnet`, or
  `NETWORK=mainnet`, or `CLAW_DEFAULT_CHAIN`/`BOARDMAN_SETTLEMENT_RAIL` is
  `arc_mainnet`. The hosted testnet stack sets none of these, so it stays
  lenient.

| Situation | Lenient (testnet) | Strict (production) |
|-----------|-------------------|---------------------|
| Health, docs, `/webhooks/*` | allowed | allowed |
| Country on blocked list | **451** `service_unavailable_in_region` | **451** |
| Money route, country unknown | allowed, logged | **451** `region_unverified` |
| Money route, blocked list unreadable | allowed, error logged | **503** `geo_fence_unavailable` |
| Non-money route, country unknown | allowed | allowed |
| API-key call to a non-money route | allowed | allowed |
| `GEO_FENCE_DISABLED=1` | everything allowed | ignored for money routes |

### Wiring status: not active for most money routes yet

`src/backend/main.py` is outside this branch's scope. Its middleware still
returns early, before any geo check, for any request with a valid API key and
for every `/api/stack/*` and `/api/rematch/web/*` path. That covers almost all
money routes, so **strict mode has no effect on them until `main.py` calls
`evaluate_request`**. This is the change needed:

```python
from gaming.src.backend.middleware.geo_fence import evaluate_request

@app.middleware("http")
async def geo_fence_middleware(request: Request, call_next):
    decision = evaluate_request(request)
    if not decision.allowed:
        logger.info("geo-fence denied reason=%s country=%s kind=%s path=%s",
                    decision.reason, decision.country, decision.money_kind, request.url.path)
        return JSONResponse(status_code=decision.status_code, content=decision.body())
    return await call_next(request)
```

`tests/test_geo_fence_strict.py::test_real_app_fences_stack_money_route_in_strict_mode`
is a strict `xfail`. It will fail as soon as this wiring lands, so whoever wires
it has to remove the marker.

### The BFF must forward the user's country

The Next.js BFF (`frontend/lib/stackServer.ts`, `rematchApiFetch`) sends the
master key but **no country**. Before strict mode is enabled, it must copy the
incoming request's `x-vercel-ip-country` into `x-boardman-client-country` on
every money-route call. Until it does, every BFF money call in strict mode will
get `region_unverified`. That is the intended fail-closed result, not a bug.

### Known gaps

1. **`main.py` wiring** (above).
2. **BFF country forwarding** (above).
3. **Telegram bot.** Stakes, sends, and withdrawals made through the bot have
   no geo signal. Options are in the KYC/AML plan (§5).
4. **Header spoofing.** `cf-ipcountry` and `x-vercel-ip-country` are trusted
   from any client. If the API host can be reached directly, without going
   through Cloudflare or Vercel, a caller can claim any country. Either restrict
   ingress to the edge, or set `edge_country_headers` to `[]` in the policy file
   and ship the MaxMind DB.
5. **VPNs.** IP geolocation does not detect VPNs. The terms prohibit them, but
   the code does not enforce that.
6. **Ops-initiated money moves** (resolver payouts under `/api/settlement/*`,
   AFM season/cup opening that collects entries, House lock/play) are not
   fenced. They are operator actions with no user location. Eligibility has to
   be enforced when the user commits money, for example at season join.

---

## 3. Custody: custodial in substance

The code does not support calling Boardman "non-custodial". As built:

- **User wallets are Circle Programmable Wallets in developer-controlled mode.**
  Boardman (sideQuest) holds the Circle entity secret and the wallet sets.
  Users never hold keys. Boardman's backend signs every transaction from a
  user's wallet: approve, stake lock, spectator deposit, P2P send, withdrawal.
  In substance, the company has unilateral control of user funds.
- **Off-chain balances.** `profiles.wallet_balance_usdc` (Supabase) is credited
  by the Circle deposit webhook and debited for spectator bets when the
  on-chain path is not used. The spectator, LP and agent "demo ledger" books
  (`src/stack/agentic/ledger.py`, `economy/lp.py`) are JSON files run by
  Boardman.
- **Funding rails.** USDC sent on Avalanche or Stellar goes to a Boardman ops
  address, and ops credits the user's Arc wallet. Naira top-ups through
  Paystack or bank transfer are collected by Boardman, and ops credits USDC
  manually at a quoted rate (`src/backend/services/fiat_topup.py`,
  `paystack.py`). Kobox is a referral partner for on- and off-ramp.
- **Escrow.** Stakes sit in `BoardmanEscrow`. The contract is not
  user-controlled: a Boardman-held resolver key chooses the winner or cancels,
  and the owner key can pause and retune fee tiers. Fee tiers apply at
  **resolve** time, so they can change between lock and resolve.
  `SpectatorPool.depositFor` lets the House deposit on a user's behalf.

Consequence: treat Boardman as a custodian of user funds and as an operator
that holds and moves value for others. That is the input to the money-
transmission and licensing questions in the counsel brief. The old phrase
"sideQuest never takes custody of user funds" has been removed from every doc.

---

## 4. Fees (source of truth: `contracts/contracts/core/`)

**Skill matches (`BoardmanEscrow`, tiered, on-chain).** The fee is charged on
the pot when the match resolves, based on the per-player stake S:

| Per-player stake | Platform fee |
|------------------|--------------|
| S < $5 | flat $0.50 per player ($1.00 off the pot) |
| $5 ≤ S ≤ $500 | 7% of the pot (`FEE_BPS = 700`) |
| S > $500 | 10% of the pot (`PREMIUM_FEE_BPS = 1000`) |

Minimum stake is $2 per player and maximum is $10,000. The owner can change the
tiers with `setFeeTiers`. Cancelled matches refund both stakes with no fee.

**Spectator pool (`SpectatorPool`, tiered on the whole pot).** Pot under $10:
min($1.00, 25% of pot). $10–$1,000: 7%. Above $1,000: 10%. A further 2%
creator pool goes to the agents' creators (75/25 winner/loser, 50/50 on a
draw). Draw tickets win the whole pool.

**Off-chain.** Creator fee on agent wins is 0–20% of winner gross (default 5%).
AFM manager sales carry a 0–20% creator cut. The off-chain fee code
(`src/stack/agentic/economy/fees.py`, `spectator.py`) mirrors the contract
tiers.

Earlier figures ("3% + 3%", "flat 7%") are obsolete. The canonical Arc testnet
addresses are in `CONTRACTS.md`: `BoardmanEscrow`
`0xD382f627fB565eb96D9EFFb66B9119DD4a555847` and `SpectatorPool`
`0xd45bE49456021B74D2712fcffD47f17f91D39664`. `0x3cD5…5A77` and `0xD898…66Fc`
are archived deployments.

---

## 5. Spectator betting

Spectators bet pari-mutuel on agent-vs-agent matches. The skill-game argument
does not cover this, because the bettor has no influence on the outcome.
Founder decision: keep the feature, behind a server-side kill switch that is
**off by default on mainnet** until counsel signs off. The exact spec
(`SPECTATOR_BETTING_ENABLED` plus a per-country allowlist) is in
[`docs/compliance/KYC_AML_PLAN.md`](docs/compliance/KYC_AML_PLAN.md) §6.
**Status: not implemented yet.** It is scheduled for the Ledger wave.

---

## 6. Logging and audit

- Geo-fence denials log the reason, country and path. Remote IPs are not
  logged by the middleware today.
- Geo decisions are not cached per user or session. Each request is evaluated.
- Custody events are written to `gaming.wallet_credit_audit` (deposits, keyed
  by `tx_hash`) and `gaming.wallet_debit_audit` (sends and withdrawals).
- There is no sanctions screening, KYC, or SAR process yet. See the KYC/AML
  plan.
