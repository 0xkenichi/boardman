# KYC / AML Plan (proposal)

> **Not legal advice.** This is an engineering proposal. The thresholds are
> placeholders until counsel confirms them for each market. Where a number
> needs a legal decision it is marked `[COUNSEL]`. Context:
> [`../legal/COUNSEL_BRIEF.md`](../legal/COUNSEL_BRIEF.md) and
> [`../../COMPLIANCE.md`](../../COMPLIANCE.md).

**Status (2026-10-14):** none of this is implemented. There is no identity
verification, sanctions screening, transaction monitoring or SAR process
today. The only controls are the geo-fence and the operational caps in
`src/backend/services/safety.py`: stakes $2–$25 per player
(`CLAW_MAX_STAKE_USDC`), withdrawals $1–$50 each, a $100 daily withdrawal cap,
hourly rate limits, and a global pause (`CLAW_PAUSED`).

---

## 1. Why this is needed

Boardman controls user wallets (Circle developer-controlled, company-held
entity secret). It credits fiat and cross-chain top-ups itself, lets users send
USDC to each other, and pays out winnings. Those are the activities that
typically bring AML obligations, whatever the gaming classification turns out
to be. Spectator betting adds betting-operator AML expectations wherever it is
enabled.

## 2. Proposed tiers

Volume means the sum, over a rolling 30 days, of deposits credited, stakes
locked, spectator tickets bought, and marketplace purchases.

| Tier | Requirements | Limits (proposal) |
|------|--------------|-------------------|
| **T0: unverified** | Telegram or web account, age and jurisdiction attestation, passes the geo-fence, wallet-address sanctions screening on every deposit source and withdrawal destination | Volume ≤ **$500 / 30 days** (from LEGAL.md). Keep today's caps: stake ≤ $25, withdrawal ≤ $50, ≤ $100/day. No P2P sends to other users. No spectator betting on mainnet. |
| **T1: identity verified** | Government ID and selfie liveness, name screened against sanctions and PEP lists, country of residence matches the geo signal | Volume ≤ **$5,000 / 30 days** `[COUNSEL]`. Stakes up to the contract maximum only after a T2 review. |
| **T2: enhanced due diligence** | Source of funds or wealth, manual review, periodic refresh | Above T1, case by case |
| **Builder (KYB)** | Company or individual verification of whoever holds a Stack API key, beneficial owners screened | Required before a builder key may stake real USDC `[COUNSEL]` |

Triggers that move a user up a tier, whatever the volume:

- any spectator bet on mainnet (if enabled at all): T1 `[COUNSEL: may need to
  be from the first bet in licensed markets]`;
- funding through the Naira or USD bank rails above a single top-up of
  `[COUNSEL]`;
- a withdrawal to an address that screening scores as high-risk;
- a monitoring alert (§4).

## 3. Sanctions screening

- **Lists:** OFAC SDN, including its published digital-currency addresses; UN
  consolidated list; EU consolidated list; UK HMT/OFSI. Re-screen when a list
  updates.
- **What to screen:** the source address of every inbound deposit (the Circle
  webhook payload has it), every withdrawal or send destination, builder agent
  wallets, and every name collected at T1 and above.
- **On a hit:** block the transaction, freeze the account's money actions, do
  not tell the user why (tipping-off risk), and escalate to the compliance
  owner within 24 hours `[COUNSEL: reporting duty and to whom]`.
- Note that Circle can freeze USDC at the issuer level independently of us.

## 4. Monitoring rules (first set)

| Rule | Signal |
|------|--------|
| Pass-through | Deposit followed by a withdrawal with little or no play |
| Chip dumping | Repeated losses to the same counterparty, or uneven agent matches between related builders |
| Fan-in / fan-out | Many accounts withdrawing to one address, or one account funding many |
| Structuring | Repeated amounts just under a tier threshold or a withdrawal cap |
| P2P velocity | Frequent `/send` to other users |
| Pool manipulation | One party betting heavily on a match involving an agent they own or build |
| Geo mismatch | KYC country ≠ geo signal, or frequent country changes |

Alerts open a case. Cases close with a recorded decision. Keep records for at
least 5 years `[COUNSEL: retention period per market]`.

## 5. SAR / STR process (proposal)

1. **Detect:** a monitoring alert, sanctions hit, staff referral or partner
   (Circle, Paystack) request.
2. **Triage** within 2 business days by the compliance owner. Freeze money
   actions if the risk warrants it.
3. **Investigate:** gather the on-chain trail, ledger rows
   (`gaming.wallet_credit_audit`, `gaming.wallet_debit_audit`), KYC data and
   IP/geo logs.
4. **Decide and file:** file with the relevant FIU `[COUNSEL: which FIU(s), for
   example FinCEN or the Nigerian FIU, given the entity and markets]` within the
   statutory deadline. Record the decision whether or not a report is filed.
5. **No tipping off.** Support staff use neutral wording.
6. **Exit:** offboard, return funds to a verified address, or hold them, as
   counsel directs.

Owner: a named compliance officer `[HUMAN: appoint]`. Engineering provides the
tooling, not the decisions.

## 6. Spectator-betting kill switch: implementation spec

Implementer: Ledger engineer (later wave). This spec is normative.

### 6.1 Configuration

| Env var | Values | Default |
|---------|--------|---------|
| `SPECTATOR_BETTING_ENABLED` | `1/true/yes/on` = on; `0/false/no/off` = off | **off when the chain is mainnet**, on otherwise |
| `SPECTATOR_BETTING_COUNTRIES` | comma-separated ISO-3166 alpha-2 codes, for example `KE,GH` (case-insensitive, whitespace ignored) | empty |

- Any other value of `SPECTATOR_BETTING_ENABLED` (a typo, for example) counts
  as **off** and logs an error once at startup.
- **"Chain is mainnet"** is true if `geo_fence.is_production()` is true, or if
  the spectator chain resolves to Arc mainnet: `SPECTATOR_CHAIN`, else
  `BOARDMAN_SETTLEMENT_RAIL`, else `default_chain_id()`, equal to `arc_mainnet`,
  or the resolved `chains.yaml` entry has `chain_id: 5042`. If chain resolution
  raises, treat it as mainnet.
- Values are read per call from the environment. No in-process caching, so a
  restart is not needed for tests, and ops can flip the switch with an env
  change and restart.

### 6.2 Decision function

Add one function. Every gated path must call it, and nothing else should
re-implement the logic:

```python
# src/backend/services/spectator_policy.py (new)
def spectator_betting_decision(country: str | None) -> tuple[bool, str]:
    """Return (allowed, reason). reason ∈
    {"ok", "disabled", "country_unknown", "country_not_allowed", "country_blocked"}."""
```

Rules, in order:

1. Global pause (`safety.is_paused()`): return `(False, "disabled")`.
2. Switch off (explicitly, or by mainnet default): return `(False, "disabled")`.
3. `country` is on the geo-fence blocked list: return `(False, "country_blocked")`.
4. On mainnet: the allowlist is **required**. If `country` is `None`, return
   `(False, "country_unknown")`. If `country` is not in
   `SPECTATOR_BETTING_COUNTRIES`, return `(False, "country_not_allowed")`. An
   empty allowlist therefore allows nobody.
5. Off mainnet: if `SPECTATOR_BETTING_COUNTRIES` is non-empty, apply rule 4.
   Otherwise allow.
6. Return `(True, "ok")`.

The `country` input comes from the geo-fence: the `GeoDecision.country` from
`evaluate_request` for HTTP (the trusted `x-boardman-client-country` for BFF
calls). For Telegram there is currently no signal, so the value is `None`,
which means bot spectator betting is refused on mainnet. Builder-key calls use
the builder's edge or IP country until counsel rules on builder end users.

### 6.3 What is gated

Gated (refuse new money in):

- `POST /api/rematch/web/spectator/bet` (`src/backend/api/rematch_web.py`, around line 626)
- `POST /api/rematch/web/spectator/lp` (around line 941): new LP deposits
- `POST /api/stack/agentic/matches/{id}/spectator/bet` (`src/stack/agentic/api.py`, around line 1038)
- `POST /api/stack/agentic/house/matches/{id}/bets` (around line 219) and `HouseRuntime.take_bet` (`src/stack/agentic/house.py`, around line 453)
- Service layer, as defence in depth: `SpectatorBook.place_bet` (`src/stack/agentic/economy/spectator.py`, around line 137), `spectator_escrow.deposit_to_pool` (`src/backend/services/spectator_escrow.py`, around line 52), `spectator_onchain.deposit_for` (`src/stack/agentic/spectator_onchain.py`, around line 315)
- Opening a new pool or seeding one from agent stakes (`spectator_seed_bps`): when the switch is off, don't open or seed a book

Never gated (users must always be able to exit):

- claims and payouts of existing tickets (`POST /spectator/payout`, `SpectatorPool.claim`)
- refunds of cancelled pools
- `POST /spectator/lp/withdraw`
- read-only odds and book views (these should return `spectator_betting: {enabled, reason}` so the UI can hide the bet controls)

### 6.4 Responses

| Reason | HTTP | Body |
|--------|------|------|
| `disabled` | 403 | `{"error": "spectator_betting_disabled"}` |
| `country_blocked`, `country_not_allowed`, `country_unknown` | 451 | `{"error": "spectator_betting_unavailable_in_region", "reason": "<reason>"}` |

The bot replies with a neutral message ("Spectator pools aren't available
here."). It never names the allowlist.

Also expose the public policy on `GET /api/stack/agentic/economy/policy`
(`spectator_betting.enabled`, without the country list) so the frontend can
hide controls. The server stays authoritative.

### 6.5 Turning off while pools are open

Existing pools keep settling or refunding normally. No new tickets are taken.
Ops may cancel open books (`SpectatorPool.cancel`, a resolver call) to refund
immediately. Document that in the runbook (SRE).

### 6.6 Logging and tests

- Log every refusal at INFO with reason, country, match id and path, plus a
  counter metric. Do not log user identifiers beyond the internal profile id.
- Required tests: default off for mainnet via each mainnet signal; default on
  for testnet; typo value counts as off; empty allowlist on mainnet refuses
  everyone; allowlisted country passes; blocked country is refused even when
  allowlisted; unknown country is refused on mainnet; every gated route
  returns the right status; claim, payout, refund and LP withdraw work while
  the switch is off.

## 7. Where the KYC/AML hooks go in code

Put one compliance gate in front of each money movement, preferably by
extending the existing central gate
`safety.assert_money_ops_allowed(user_id, action, amount, kind)`
(`src/backend/services/safety.py:188`), which the bot and Stack v1 already
call. Add `kind` values `"deposit"`, `"bet"`, `"buy"`, `"send"` and `"payout"`,
and call a new `compliance.check(user_id, kind, amount, counterparty_address)`
from it. That call returns a refusal or `None` and records the check.

| Flow | Hook location | Checks |
|------|---------------|--------|
| **Deposit address issued** | `GET /api/deposit/address` (`src/backend/api/deposit.py:36`); `clawstation_circle.ensure_user_wallet` (`src/backend/services/clawstation_circle.py:171`) | geo-fence (already a money route), age and jurisdiction attestation recorded |
| **Deposit credited** | Circle webhook `_apply_credit` (`src/backend/api/webhooks.py:278`) | sanctions-screen the source address; add to 30-day volume; if over the tier limit, credit but freeze money actions and prompt for KYC (crediting keeps the ledger true) |
| **Fiat / cross-chain top-up** | `/credit_topup` admin command (`src/bot/handlers/fiat_topup.py:877`); Paystack webhook (`frontend/app/api/rematch/paystack/webhook/route.ts`); Stellar watcher (`src/backend/services/stellar_watcher.py`) | payer-name vs KYC-name match above `[COUNSEL]`; volume; T1 required above `[COUNSEL]` |
| **Stake lock** | `assert_money_ops_allowed(kind="lock")` callers: bot `cmd_lock_stake` (`src/bot/handlers/lock_stake.py:67`), Stack v1 lock (`src/stack/api_v1.py:367`) and create (`:178`); the on-chain step `CircleWalletService.lock_stake_in_escrow` (`src/backend/circle_wallet_service.py:772`); agent path `src/stack/agentic/onchain.py` | tier volume limit; self-exclusion; geo |
| **Spectator bet / LP** | §6.3 routes | kill switch (§6), T1 on mainnet, volume |
| **Marketplace buy** | `purchase_manager_agent` via `POST /football/agents/purchase` and `offer/accept` (`src/stack/agentic/api.py`) | volume; sanctions-screen the seller payout address |
| **Withdraw / P2P send** | `_execute_transfer` (`src/bot/handlers/send.py:53`, gated at `:338`); lowest common point `CircleWalletService.transfer_usdc` (`src/backend/circle_wallet_service.py:490`) | sanctions-screen the destination; T0 sends only to own verified addresses; pass-through rule; daily cap (exists) |
| **Payout** | `clawstation_escrow.resolve_match` (`src/backend/services/clawstation_escrow.py:574`); `clawstation_settlement.settle_challenge` (`src/backend/services/clawstation_settlement.py:544`); spectator payout routes | winner not frozen or sanctioned (else hold payout in escrow and escalate); chip-dumping rule on the pair |

Because `transfer_usdc` is the single place where user wallets send funds out,
a screening check there catches every outbound path, including ones added
later. Keep the per-flow checks too, because they hold the context (which user,
and why).

## 8. Vendor categories (no pricing claims; verify Arc support)

| Need | Category | Well-known vendors |
|------|----------|--------------------|
| Wallet / transaction screening | Blockchain analytics (KYT) | Chainalysis (KYT; also a free sanctions-screening API and oracle), TRM Labs, Elliptic, Merkle Science. Also check whether Circle's own compliance tooling for programmable wallets covers Arc. |
| Identity verification | Document and liveness IDV | Sumsub, Onfido, Persona, Veriff, Jumio, Smile ID (strong African document coverage) |
| Sanctions / PEP name screening | Watchlist screening | ComplyAdvantage, LSEG World-Check, Dow Jones Risk & Compliance (many IDV vendors bundle one) |
| Gaming-grade geolocation | Location compliance | GeoComply; MaxMind GeoIP2 with its anonymous-IP (VPN/proxy) database |
| Case management / monitoring | Transaction monitoring | Unit21, Hummingbird, Sardine |

Selection questions for every vendor: does it support **Arc** (a new chain)
and USDC on it; does it cover target-market ID documents; where is data
stored; how does it fit Circle developer-controlled wallets.
