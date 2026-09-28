# Boardman Mainnet Go-Live Checklist

Bar to clear: **the stake → settle → payout flow must be correct 1,000,000 times out of 1,000,000** before real users touch mainnet. This checklist is the gate. Every item needs a ✅ with date + evidence before `arc_mainnet.enabled` flips to `true`.

## Status: 🔒 BLOCKED (config prepped, `enabled: false`)

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
- [ ] `feeRecipient` set and confirmed (7% fee goes here)
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
- [ ] 7% fee + `MAX_STAKE` ($10k) sanity-reviewed against product pricing
- [ ] Beta cohort first: 10–20 invited users, small caps (e.g. $5 stakes), 2 weeks, zero fund incidents

### Load / chaos proof (the 1,000,000 bar)
- [x] Replay harness: `tests/test_escrow_replay.py` — full lifecycles through the **real** escrow code (A: create→join→resolve, B: create→join→cancel, C: ghosted→sweep auto-refund) over an in-memory ledger with contract-accurate fakes (OPEN/LOCKED/DISPUTED states, Circle-style revert dicts, web3-style raises). Invariants per run: conservation (lock == payout+fee+refund), exactly-one payout/refund per match, escrow drained, DB converged. Evidence run: `PYTHONPATH="$PWD/src:$PWD" BOARDMAN_REPLAY_CYCLES=1000 .venv/bin/python -m pytest tests/test_escrow_replay.py -q` → 1,000 cycles, 10/10 pass, ~6s.
- [x] Chaos/crash-convergence: covered in the same file — approve-fail leaves no state; crashes between chain-move and DB-write (create, payout, refund) converge on retry with zero double-pay (real escrow code now self-heals from on-chain status reads).
- [ ] Replay against testnet with mainnet config (fakes prove logic; this proves wiring/RPC/decimals)
- [ ] Kill-the-process test: crash the backend between lock and settle; restart; sweep/settlement must complete the flow without human help
- [ ] Duplicate-webhook test: 10x replay of every Circle webhook event; balance changes exactly once

### Reconciliation
- [x] Job built: `src/backend/services/escrow_reconciliation.py` — per-challenge DB-expected-held (from lock tx ids) vs on-chain match state, plus headline contract-balance check; read-only, fail-loud, alerts ops. Scheduled every 60min (`clawstation_escrow_reconciliation`, `ESCROW_RECONCILE_INTERVAL_MIN=0` to disable). Tested clean + drift in `test_escrow_replay.py`.

## 4. Rollback plan

- Flip `arc_mainnet.enabled: false` (config reload — `reload_chains_config()` clears the cache; restart API workers to be safe)
- `pause()` the escrow from the owner key if a contract-level stop is needed — resolve/cancel still work while paused, new stakes don't
- User comms template: funds are in escrow, not lost; refunds are on-chain and verifiable on arcscan
