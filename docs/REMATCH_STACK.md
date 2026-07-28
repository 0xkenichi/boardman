# Rematch Stack

**The infrastructure that powers Rematch — exposed so other builders can ship new experiences on top.**

| | |
|--|--|
| **Product** | Rematch (Telegram 1v1 staked gaming) |
| **Platform** | Rematch Stack (wallets · escrow · match lifecycle · proof · reputation · multi-chain) |
| **Status** | Foundation (v0) — interfaces + façade over live ClawStation services |
| **Code** | `src/stack/` · HTTP surface `/api/stack/v0` |

---

## One-liner

**Rematch Stack** is the reusable layer for *staked skill matches*: custodial USDC wallets, dual-lock escrow, match state machine, outcome verification hooks, and reputation — independent of any single chat UI.

Rematch (the bot + web) is the **first app** on the Stack. Builders should be able to ship:

- Discord / WhatsApp / web UIs on the same money rails  
- New games and proof rules (photo, video, oracle, manual)  
- Tournaments, ladders, prediction-style UIs that still settle as **1v1 escrow matches** under the hood  
- Partner white-labels with fee splits (from platform fee only)  
- **Agentic economy** apps: AI agents that play finite-outcome games, dual-lock stakes, optional spectator prediction — see `AGENTIC_ECONOMY.md`

---

## What is Stack vs App

```
┌─────────────────────────────────────────────────────────┐
│  Experiences (apps)                                     │
│  Rematch Telegram · future: web mini-app · Discord …    │
└───────────────────────────┬─────────────────────────────┘
                            │  Stack API / Python SDK
┌───────────────────────────▼─────────────────────────────┐
│  Rematch Stack                                          │
│  Identity · Wallets · Escrow · Matches · Proof · PLAY   │
│  Safety rails · Multi-chain config · Webhooks           │
└───────────────────────────┬─────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────┐
│  Rails                                                  │
│  Circle W3S · ClawEscrow.sol · Supabase · RPCs          │
└─────────────────────────────────────────────────────────┘
```

| Layer | Owns | Does not own |
|-------|------|----------------|
| **App** | UX, copy, keyboards, branding | On-chain math |
| **Stack** | Match lifecycle, wallets, settle, caps | Fancy frontend |
| **Rails** | Keys, contracts, DB | Product rules |

**Hard rule (same as live Rematch):** every stake is still a **1v1 challenge**  
`open → accepted → lock → play → proof → settle`.  
Stack features are additive — not a second money path.

---

## Core modules (v0)

| Module | Responsibility | Live code today |
|--------|----------------|-----------------|
| **Chains** | Chain registry, USDC, escrow addresses | `services/chains.py`, `config/chains.yaml` |
| **Wallets** | Ensure deposit address, balances | `services/clawstation_circle.py`, `circle_wallet_service.py` |
| **Escrow** | Dual lock / cancel / resolve | `services/clawstation_escrow.py`, `ClawEscrow.sol` |
| **Matches** | Challenge CRUD, codes, cancel, rematch | `match_codes`, `rematch_*`, bot handlers |
| **Settlement** | Resolve when reports ready | `clawstation_settlement.py` |
| **Proof** | Score / screenshot verification (pluggable) | `score_verifier`, submit_score handlers |
| **Reputation** | PLAY points, tiers, leaderboard | `play_points.py`, `rematch_public.py` |
| **Safety** | Pause, stake/withdraw caps, rate limits | `safety.py` |

Package layout (new):

```
src/stack/
  __init__.py          # public exports
  types.py             # shared domain types
  protocols.py         # builder-facing interfaces
  facade.py            # RematchStack façade (wires live services)
  api.py               # FastAPI router /api/stack/v0
  README.md            # builder quickstart
```

---

## Builder surfaces (roadmap)

### v0 — now (foundation)
- Documented architecture + Python façade  
- Read-only / operator HTTP: health, chains, public board shape  
- Protocols so new apps depend on **interfaces**, not Telegram handlers  

### v1 — builder API (next)
- API keys (`STACK_API_KEY` / per-app keys)  
- Create challenge · accept · lock status · settle hooks  
- Webhooks: `match.locked`, `match.settled`, `match.disputed`  
- Sandbox = current testnets (Arc / Base / Avalanche)

### v2 — multi-experience
- `app_id` / partner attribution (fee share from **platform fee only**)  
- Pluggable `OutcomeVerifier` (vision / oracle / manual)  
- Game catalog registry (EA FC first; more titles as config)

### v3 — open ecosystem
- Published OpenAPI + SDK (TS/Python)  
- Example apps: “minimal web 1v1”, “Discord bot stub”  
- Mainnet rails behind explicit flags  

---

## HTTP surface (v0)

Base: `/api/stack/v0`

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| GET | `/health` | none | Stack liveness + module flags |
| GET | `/chains` | none | Supported settlement chains |
| GET | `/catalog` | none | Capabilities (games, modules) |
| GET | `/public/board` | none | Leaderboard + open challenges (same data as Rematch public) |

v1 will add authenticated match/wallet routes; money-moving endpoints stay key-gated like `/api/settlement/*`.

---

## Design principles

1. **App-agnostic core** — Telegram is a client, not the source of truth.  
2. **One money path** — ClawEscrow dual-lock only.  
3. **Pluggable proof** — verifiers return structured outcomes; stack settles.  
4. **Conservative safety** — pause switch, caps, idempotency (reuse `safety.py`).  
5. **Testnet-first** — public builder sandbox before mainnet.  
6. **Secrets never in git** — Circle entity secret, service role, bot token local/host only.  

---

## What builders should not reinvent

- Circle wallet set + entity secret cryptography  
- ClawEscrow ABI / dual-lock sequencing  
- Report timeout / dispute settlement rules  
- PLAY scoring (unless they opt into a separate ledger)

---

## Success metrics

| Signal | Meaning |
|--------|---------|
| Second client | Any non-Telegram UI creates + settles a match via Stack |
| Time-to-first-lock | Builder docs → funded test lock in &lt; 1 day |
| Isolation | Rematch bot upgrades don’t break Stack contracts |

---

## Related docs

- Product: `REMATCH_PRODUCT_BRIEF.md`, `MVP_FLOW.md`  
- **Agentic economy (AI agents + spectator markets):** `AGENTIC_ECONOMY.md`  
- Safe feature phases: `PHASES_1_2_3_SAFE_DESIGN.md`  
- Contracts: `CONTRACTS.md`  
- Multi-chain: `MULTI_CHAIN.md`, `config/chains.yaml`  
- Builder package: `src/stack/README.md`  

---

## Network posture (product truth)

| | |
|--|--|
| **Network** | Testnet only (not mainnet) |
| **Live for users** | **Arc Testnet** only |
| **Next** | Avalanche Fuji — config ready, **not enabled** |
| **Legacy** | Base Sepolia — internal/ops, not in UI |

Override live set with env: `CLAW_ENABLED_CHAINS=arc` (default behaviour)  
or later `CLAW_ENABLED_CHAINS=arc,avalanche` when Avalanche is ready.

---

## Immediate build order

1. ✅ This doc + `src/stack` façade + `/api/stack/v0` health/chains/catalog  
2. ✅ Arc-only live chain gate (`enabled` in `chains.yaml` + `list_chains`)  
3. Authenticated match lifecycle API (thin wrappers over existing services)  
4. Webhook emitter for match state transitions  
5. Example: minimal HTTP client script that lists chains + public board  
6. Avalanche enablement checklist (gas tank, faucet UX, dual-lock E2E) — when Arc is solid  
7. OpenAPI export + grant-friendly one-pager  

---

*Rematch Stack is how Rematch becomes infrastructure — not just a bot.*
