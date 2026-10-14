# Boardman Mainnet Go-Live Checklist

Bar to clear: **the stake → settle → payout flow must be correct 1,000,000 times out of 1,000,000** before real users touch mainnet. This checklist is the gate. Every item needs a ✅ with date + evidence before `arc_mainnet.enabled` flips to `true`.

## Status: 🔒 BLOCKED (config prepped, `enabled: false`)

Legal & compliance gate (§4): **open**, with no counsel sign-off yet. Engineering cannot clear it alone.

---

## 1. Fund-loss audit — verified safe (Sept 2026)

| Path | Verdict | Evidence |
|---|---|---|
| Escrow contract | ✅ | `BoardmanEscrow.sol`: `ReentrancyGuard` on all state-changing fns, `SafeERC20`, status machine (OPEN→LOCKED→RESOLVED/CANCELLED) set before transfers, self-join blocked, `MAX_STAKE` cap, resolver-only resolve/cancel. `resolveMatch`/`cancelMatch` intentionally lack `whenNotPaused` — funds always exit-able during pause. |
| Payout idempotency | ✅ | `clawstation_escrow.resolve_match`: `_find_existing_audit(challenge_id, "payout")` short-circuit + `resolve-{id}` idempotency key. `cancel_match` same via `refund` audit. |
| Deposit credit | ✅ | `api/webhooks.py`: fails closed without `CIRCLE_WEBHOOK_SECRET`, constant-time HMAC, `tx_hash` UNIQUE + `FOR UPDATE` row lock → duplicate webhooks cannot double-credit. |
| Mutual-cancel gating | ✅ | `rematch_cancel.py`: free cancel only without locks; locked matches require both players (propose→confirm); on-chain refund failure never marks DB cancelled. |
| Refund-on-failure discipline | ✅ | Challenge status only flips to `resolved`/`cancelled` AFTER confirmed tx. Timeout ≠ failure — EscrowError raised, status preserved. |
| Stale creator_locked matches | ✅ FIXED (Sept 2026) | Was a real gap: only `open` challenges auto-expired, so a creator who staked and got ghosted had funds stuck forever. Now `sweep_stale_creator_locks` (`src/bot/jobs/expiry.py`) auto-refunds via idempotent `cancel_match`, re-checks status before refunding, leaves status untouched if the on-chain refund fails. Tests: `tests/test_expiry_sweep.py` (5). |
| Settlement discipline | ✅ | `clawstation_settlement.py`: never settles one-sided reports, conflicts → dispute/AI gate, no-show settle requires proof + timeout. |

## 2. Known soft spots (not blockers, watch these)

- `resolveMatch` / `cancelMatch` are **admin-trust** operations — the resolver wallet is a single private key. Mainnet: use a dedicated resolver EOA, funded minimal, key in secrets manager (not `.env` on a laptop).
- `joinMatch` transfers before checking the escrow actually received p1's stake? — No: p1's stake is verified by the chain itself (createMatch reverted otherwise). But the **backend** `creator_locked` state can be set while p1's tx later reorgs/fails on a reorg-prone chain. Arc finality: confirm no-reorg assumption with Arc docs before go-live.
- `cancelMatch` refunds but does not charge gas from users — resolver pays gas. Keep a gas budget alert on the resolver wallet.
- Deposit webhook accepts `transfer | transactions.outbound | transactions.inbound` types — outbound payout events are filtered by USDC-symbol + confirmation, but re-verify Circle's real event taxonomy on mainnet (testnet payloads ≠ mainnet payloads sometimes).

## 3. Gate checklist (all required before flipping `enabled: true`)

### Contracts
- [ ] `BoardmanEscrow` deployed to Arc mainnet (chain 5042) from a **dedicated deployer key**
- [ ] Deployment tx verified on arcscan; `BOARDMAN_ESCROW_ADDRESS_ARC_MAINNET` set in backend env
- [ ] Contract source verified/published on the explorer
- [ ] `ownership` transferred to ops multisig or secured owner key (not the deployer hot wallet)
- [ ] `resolver` set to dedicated resolver EOA (≠ owner, ≠ deployer)
- [ ] `feeRecipient` set and confirmed (tiered platform fee goes here: $0.50/player < $5 · 7% $5–$500 · 10% above)
- [ ] Small-value smoke test on mainnet: create → join → resolve with real dust USDC, verify payout + fee split on-chain
- [ ] Cancel path smoke test: create → cancel, both refunds land

### Circle / wallets
- [ ] Circle W3S wallet-set confirmed working against `ARC` (mainnet) blockchain label
- [ ] `CIRCLE_USDC_TOKEN_ID_ARC_MAINNET` captured from Circle API (do NOT reuse the testnet UUID)
- [ ] One test user wallet created on mainnet; deposit of real USDC credited exactly once (send same webhook twice, verify single credit)
- [ ] Withdrawal/payout from a user wallet verified on-chain

### Backend config
- [ ] `chains.yaml`: `arc_mainnet.enabled: true` + `status: live` (only after ALL of the above)
- [ ] `CLAW_DEFAULT_CHAIN` / `BOARDMAN_SETTLEMENT_RAIL` decision recorded (testnet users vs mainnet cutover plan — do NOT silently move existing testnet balances)
- [ ] `ADMIN_PRIVATE_KEY` (resolver) funded with mainnet USDC-gas budget + low-balance alert
- [ ] `DEPLOYER_KEY` removed from env after deploy
- [ ] Scheduler running with `clawstation_creator_lock_sweep` active (log line on startup)

### Ops / process
- [ ] Resolver wallet balance monitor + alert (< $20 gas equivalent)
- [ ] Escrow contract balance reconciliation job: sum(locked stakes in DB) == escrow balance, daily
- [ ] Incident runbook: pause procedure (`pause()` from owner key), manual-resolve procedure
- [ ] Tiered fees + `MAX_STAKE` ($10k) sanity-reviewed against product pricing (off-chain caps in `safety.py` are $25 stake / $50 withdrawal today)
- [ ] Beta cohort first: 10–20 invited users, small caps (e.g. $5 stakes), 2 weeks, zero fund incidents

### Load / chaos proof (the 1,000,000 bar)
- [x] Replay harness: `tests/test_escrow_replay.py` — full lifecycles through the **real** escrow code (A: create→join→resolve, B: create→join→cancel, C: ghosted→sweep auto-refund) over an in-memory ledger with contract-accurate fakes (OPEN/LOCKED/DISPUTED states, Circle-style revert dicts, web3-style raises). Invariants per run: conservation (lock == payout+fee+refund), exactly-one payout/refund per match, escrow drained, DB converged. Evidence run: `PYTHONPATH="$PWD/src:$PWD" BOARDMAN_REPLAY_CYCLES=1000 .venv/bin/python -m pytest tests/test_escrow_replay.py -q` → 1,000 cycles, 10/10 pass, ~6s.
- [x] Chaos/crash-convergence: covered in the same file — approve-fail leaves no state; crashes between chain-move and DB-write (create, payout, refund) converge on retry with zero double-pay (real escrow code now self-heals from on-chain status reads).
- [ ] Replay against testnet with mainnet config (fakes prove logic; this proves wiring/RPC/decimals)
- [ ] Kill-the-process test: crash the backend between lock and settle; restart; sweep/settlement must complete the flow without human help
- [ ] Duplicate-webhook test: 10x replay of every Circle webhook event; balance changes exactly once

### Reconciliation
- [x] Job built: `src/backend/services/escrow_reconciliation.py` — per-challenge DB-expected-held (from lock tx ids) vs on-chain match state, plus headline contract-balance check; read-only, fail-loud, alerts ops. Scheduled every 60min (`clawstation_escrow_reconciliation`, `ESCROW_RECONCILE_INTERVAL_MIN=0` to disable). Tested clean + drift in `test_escrow_replay.py`.

## 4. Legal & compliance gate (all required before flipping `enabled: true`)

Not legal advice. These items track the controls and the counsel decisions described in
[`COMPLIANCE.md`](../COMPLIANCE.md), [`legal/COUNSEL_BRIEF.md`](legal/COUNSEL_BRIEF.md) and
[`compliance/KYC_AML_PLAN.md`](compliance/KYC_AML_PLAN.md). Items marked
"branch" exist on `docs/compliance-truth` and are not ticked until merged and
deployed.

### Counsel
- [ ] Counsel engaged (gaming + fintech); brief sent. The brief exists (branch) but has not been sent.
- [ ] Written view on custody / money transmission / VASP for launch markets (brief Q1)
- [ ] Written view on spectator pools (brief Q2). Until then, spectator betting stays off on mainnet.
- [ ] Blocked list confirmed per product line (brief Q5); `config/blocked_regions.json` updated and version bumped
- [ ] Launch market(s) cleared in writing, including Nigeria specifically (brief Q4)
- [ ] Circle developer-controlled wallet terms and Paystack / bank-account terms reviewed for this use

### Geo-fence
- [ ] Blocked list loads from the tracked `config/blocked_regions.json` with no env var (branch: fixed and tested)
- [ ] Strict fail-closed money routes + `config/compliance/geo_fence.json` merged (branch: `tests/test_geo_fence_strict.py`)
- [ ] `src/backend/main.py` calls `evaluate_request`. The strict-xfail tripwire in `test_geo_fence_strict.py` is removed.
- [ ] BFF (`frontend/lib/stackServer.ts`) forwards `x-vercel-ip-country` as `x-boardman-client-country` on money calls
- [ ] Mainnet env sets `GEO_FENCE_STRICT=1` (or a production signal). Smoke test: unknown country → 451, allowed country → 200, `/api/healthz` → 200.
- [ ] API ingress limited to Cloudflare/Vercel, or `edge_country_headers: []` with the MaxMind DB shipped (header-spoofing gap)
- [ ] Telegram money flows: decide between KYC-residence gating and disabling bot money actions on mainnet (Telegram gives no geo signal)

### Book-entry ledger
- [ ] `BOARDMAN_DEMO_FAUCET` unset on the mainnet deploy (the code refuses it there anyway; a CRITICAL "REFUSED" log line means someone set it)
- [ ] House agents' and AI clubs' ledger wallets funded for real before the first house match / season (the faucet is off on mainnet)
- [ ] Marketplace parties bind Circle wallets: the book-entry sale rail is refused on mainnet
- [ ] Chess spectator ledger books debit the bettor before a bet counts (today `SpectatorBook.place_bet` records the bet without a ledger debit, yet payouts credit the bettor's ledger wallet)

### Spectator betting
- [ ] Kill switch built to spec (KYC/AML plan §6): `SPECTATOR_BETTING_ENABLED` off by default on mainnet, `SPECTATOR_BETTING_COUNTRIES` allowlist, tests
- [ ] Mainnet launches with spectator betting **off** and the allowlist empty unless counsel has cleared a market in writing
- [ ] Claim, refund and LP withdraw verified to work while the switch is off

### Custody, KYC/AML
- [ ] Docs stop claiming "non-custodial" (branch: all tracked docs corrected 2026-10-14)
- [ ] Compliance officer named; SAR process adopted (KYC/AML plan §5)
- [ ] Wallet sanctions screening on every deposit source and withdrawal destination; vendor confirmed to support Arc
- [ ] KYC tiers enforced at the hooks in KYC/AML plan §7; T0 volume limit ($500 / 30 days, pending counsel)
- [ ] Builder KYB decision (brief Q3/Q7) before builder keys stake real USDC
- [ ] Fiat and cross-chain funding rails (Paystack, bank, Avalanche/Stellar ops credit) cleared by counsel or disabled on mainnet
- [ ] P2P `/send` to other users: keep, limit, or disable (brief Q1)

### Terms and disclosures
- [ ] `docs/TERMS_OF_SERVICE.md`: every `[COUNSEL: …]` marker resolved; published; acceptance recorded
- [ ] Privacy Policy drafted and reviewed
- [ ] Fee-after-lock question resolved (contract fixes the fee at lock, or counsel approves disclosure) (brief Q6)
- [ ] Pre-stake / pre-bet confirmations shown (LEGAL.md "Required user-facing disclaimers")
- [ ] Untracked `docs/AGENTIC_ECONOMY_V2.md` in the main checkout corrected (it cites archived escrow `0x3cD5…5A77` and a 300 bps fee) before it is committed or published

## 5. Rollback plan

- Spectator pools only: set `SPECTATOR_BETTING_ENABLED=0` and restart (once the switch exists). Existing tickets still settle.

- Flip `arc_mainnet.enabled: false` (config reload — `reload_chains_config()` clears the cache; restart API workers to be safe)
- `pause()` the escrow from the owner key if a contract-level stop is needed — resolve/cancel still work while paused, new stakes don't
- User comms template: funds are in escrow, not lost; refunds are on-chain and verifiable on arcscan
