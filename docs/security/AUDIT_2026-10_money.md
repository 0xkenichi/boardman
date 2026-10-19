# Money backend security audit (October 2026)

| | |
|---|---|
| Date | 2026-10-20 |
| Branch | `audit/money`, based on `70a7c64` (integration/wave1 + wallets/setup-proof) |
| Scope | Agentic ledger, matches, house and recovery, disbursement, the economy (fees, odds, LP, spectator book, budget), the db layer, the wallet bridge, play balance and `play_adjust`, the web BFF money routes (`rematch_web.py`), withdrawals and withdraw links, Paycrest on- and off-ramp, CCTP bridge, self-custody intents, Circle wallet service, the ClawStation settlement/escrow/circle path, tournaments, Paystack/fiat top-up, Circle and Paycrest webhooks, and AFM betting, marketplace and season money |
| Method | For each money movement, state its conservation invariant, then attack it: concurrency (threads and spawned processes on SQLite), crashes between steps, webhook replay and ordering, idempotency keys, amount edge cases, realm leakage, and caps. Every confirmed finding has a PoC test that fails on `70a7c64` and passes after the fix. |
| Out of scope | Web/API authorization and chat channels: two other auditors cover those. Authz issues found along the way are listed in §6. |

## 1. Summary

**Fixed:** 15 findings, in 10 commits:
- 2 Critical
- 4 High
- 5 Medium
- 4 Low

**Open:** 18 items are documented in §5 with a recommended fix and an owner action. One of them (O-1, AFM result predictability) is High.

**Tests:**
- Baseline: 1103 passed.
- Added: 47 audit tests across 8 files. They include 3 that use spawned processes.
- Full suite after the fixes: 1150 passed, 7 skipped, 0 failed.

What the confirmed findings have in common: almost every exploitable bug is a **check-then-act on a balance or a listing** where the "act" talks to something slow: Circle, a chain, or Telegram. The fixes use two primitives:

1. **`leases.exclusive(key)`** (`src/stack/agentic/db/leases.py`). This is a lock with exactly one holder: across processes and across requests/threads of the same process. It is built on the existing `match_leases` row, so it works on SQLite and on Postgres. On top of it:
   - `play_adjust.spend_lock(profile)` gives one spend of a play balance at a time;
   - `afm-market:<agent>` gives one market action per manager at a time.
2. **Reserve before you act.** A stake, cash-out or withdrawal cap is first taken with one conditional write: `play_adjust.apply_once(..., chain_usdc=fresh)` or `safety.reserve_daily_withdraw`. Only then does money move. The reservation is released only when it is known that nothing was sent, or once the chain carries the debit.

## 2. Severity table

| ID | Sev | Title | Area | Fix commit | Status |
|---|---|---|---|---|---|
| M-03 | Critical | Two buyers, or a buy racing a delist, pay for one AFM manager | `agent_market.py` | `9816421` | Fixed |
| M-06 | Critical | Tournament entry refunded twice from the shared pot | `tournament.py`, `tournament_money.py` | `f89b358` | Fixed |
| M-01 | High | Web bets / LP deposits overdraw the play balance (bets on credit) | `rematch_web.py` | `db34d4b`, `ff6da3d` | Fixed |
| M-08 | High | Daily withdraw cap bypass (concurrency, restart, multi-worker) | `safety.py`, `withdrawals.py` | `e41cf68` | Fixed |
| M-10 | High (latent) | Naira cash-out not reserved before the burn: same USDC spendable twice | `paycrest/offramp.py` | `c138711` | Fixed |
| M-04 | High | A sub-micro AFM stake freezes a whole fixture pot | `betting.py` | `e95442b` | Fixed |
| M-02 | Medium (latent Critical) | LP withdraw sends real USDC on a *pending* approval, before booking | `rematch_web.py` | `db34d4b` | Fixed |
| M-05 | Medium | Book-entry money reaches mainnet (AFM bets, bridge withdraw) | `betting.py`, `wallet_bridge.py` | `e95442b` | Fixed |
| M-11 | Medium | Cash-out sends the out-wallet's whole balance, bypassing caps | `paycrest/offramp.py` | `c138711` | Fixed |
| M-12 | Medium | Paycrest webhook marked seen before it is applied: on-ramp stuck | `paycrest/events.py` | `e3385b9` | Fixed |
| M-13 | Medium | Testnet `SPECTATOR_CHAIN` masks a mainnet settlement chain | `spectator_policy.py` | `11e4dc9` | Fixed |
| M-07 | Low | Prize shares can sum past the distributable pot | `tournament.py` | `f89b358` | Fixed |
| M-09 | Low | Audit-row failure after a sent withdrawal reports "nothing sent" | `withdrawals.py` | `e41cf68` | Fixed |
| M-14 | Low | Ledger defence in depth: negative credit, zero stake, settle-after-void | `ledger.py`, `spectator.py` | `11e4dc9` | Fixed |
| M-15 | Low | Non-finite amounts (`"NaN"`) pass the web amount guards | `rematch_web.py`, `betting.py` | `db34d4b`, `e95442b` | Fixed |

## 3. Conservation invariants

These are the invariants the PoCs attack. Each is now asserted by at least one test.

1. **Ledger.** `SUM(ledger_balances)` changes only by explicit external credits (deposits, faucet). Every transfer is a debit and credit in one transaction. No balance is ever below 0 (`CHECK`, conditional `UPDATE`). Amounts are integer micro-USDC with no float.
2. **Escrow.** stake_a + stake_b = payout + fee for a win; the stakes go back for a draw or abort. Settlement happens exactly once per result, through the journal and lease.
3. **Play balance.**
   - `chain_usdc + play_adjust ≥ 0` for every profile, at every moment, including while an external transfer (Circle pull, CCTP burn, withdrawal) is in flight.
   - At most one spend per profile runs at a time.
4. **Spectator book.** Payouts ≤ stakes + funded seeds. A book is either settled or void, never both.
5. **AFM pot.** Stakes recorded in a book = the micro-USDC debited into its pot, so the settle debit always fits.
6. **AFM market.** One listing produces exactly one buyer debit, one seller/creator credit, and one ownership change.
7. **LP pool.** USDC sent to an LP ≤ that LP's claim, and the claim is reduced before the transfer.
8. **Tournament.** Refunds ≤ locked entries, one refund per entry. Prizes + fee ≤ pot, and the pot = the sum of locked entries.
9. **Withdraw caps.** Per profile per UTC day, withdrawals ≤ `CLAW_DAILY_WITHDRAW_CAP_USDC`, shared across processes and restarts.
10. **Naira out.**
    - USDC paid to Paycrest per order ≤ that order's amount.
    - The play balance is reserved from PIN until the burn lands.
    - A refund brings home at most what the order put on Base.
11. **Webhooks.** A delivery counts as seen only once it has been applied. A replay is a no-op, and a failed delivery can be retried.
12. **Realms.**
    - Testnet book-entry money never becomes mainnet play balance or reaches Paycrest.
    - Mainnet money never funds AFM/arena book-entry bets.
    - Any mainnet chain signal makes the process mainnet (fail closed).

## 4. Findings (fixed)

### M-03: Critical: one AFM manager sold twice

- **Description.** Several functions each did the same thing:
  - which functions: `purchase_manager_agent`, `accept_manager_offer`, `delist_manager_agent` and `list_manager_for_sale`;
  - what they did: `load_json("agents.json")`, then move money (`_execute_sale`: a ledger debit/credit, or seconds of Circle transfers on the on-chain rail), then `save_json` of the **whole file**.
  
  There was no lock and no compare-and-set on the listing.
- **Exploit.**
  - **Double buy.** Two buyers (or buy-now racing an accepted offer) both load the listing and are both charged. The seller is paid twice, and the last write decides who owns the manager.
  - **Buy racing a delist.** The delist saves a stale copy after the sale: the seller keeps both the money and the manager.
  - On mainnet this plays out with real USDC.
- **PoC.**
  - `tests/test_audit_money_afm.py::test_two_buyers_one_manager_one_payment`: seller balance was 60 for one manager.
  - `::test_buy_racing_delist_never_keeps_both`.
  - `tests/test_audit_money_processes.py::test_two_processes_buying_one_manager_charge_one_buyer`: two spawned processes, exit codes `[0, 0]` before the fix.
- **Fix (`9816421`).** Every market action runs under `leases.exclusive("afm-market:<agent>")`. A concurrent action gets `MarketBusy`, a `ValueError`. Only the agent's own record is written back, under the store's cross-process `update_json` flock.
- **Status.** Fixed. Residual: other writers of `agents.json` (the registry) still use whole-file `save_json`; see O-13.

### M-06: Critical: tournament entry refunded twice

- **Description.** `leave_tournament` reads the entries, awaits `refund_entry`, and only then deletes the entry. `refund_entry` sent from the pot wallet with a **random** Circle idempotency key. `cancel_tournament` refunds every entry the same way, and marked the cup cancelled even when some refunds failed (that money was stuck).
- **Exploit.** Any of these drain other players' entries from the shared pot: two `/tleave` handlers (aiogram runs them concurrently), bot plus web, a cancel racing a leave, or a cancel re-run after a crashed leave. Join again and repeat.
- **PoC.** `tests/test_audit_money_tournament.py`:
  - `test_double_leave_refunds_once`: pot sent `[5.0, 5.0]` before the fix;
  - `test_cancel_after_a_crashed_leave_does_not_refund_again`;
  - `test_cancel_with_a_failed_refund_stays_retryable`.
- **Fix (`f89b358`).**
  - The refund carries `refund_idempotency_key(cup, entry_id, profile, amount)`, a uuid5 of the entry, and goes through `_transfer_with_key`, which refuses clients without key support. Circle collapses every duplicate.
  - A cancel with any failed refund raises and stays open, so a re-run retries it safely.
- **Status.** Fixed. Residual: this relies on Circle retaining idempotency keys. A durable `tournament_refunds` claim row like `_claim_place` would be stronger (O-6).

### M-01: High: web bets and LP deposits overdraw the play balance

- **Description.**
  - The bet path: `POST /api/rematch/web/spectator/bet`, `_apply_approved_spectator_bet` and `_apply_approved_lp`.
  - These checked the balance at **request** time. The approved path applied later against that stale `summary`.
  - The stake was taken by pulling USDC from Circle. When the pull failed, the code fell back to an **unconditional** `add_adjust(-amount)`.
- **Exploit.**
  - Set up N Telegram approvals (or N concurrent "always" requests) while the wallet holds one stake. All N tickets are booked, and the play balance goes to −(N−1)×stake.
  - If the bets win, the payouts first clear the debt and the rest is profit. If they lose, the player walks away from the debt.
  - Free leverage on real money once spectator betting is on.
- **PoC.** `tests/test_audit_money_web_spend.py`:
  - `test_two_approved_bets_cannot_spend_one_balance_twice`;
  - `test_direct_bets_racing_never_overdraw`: 3 of 3 racing requests succeeded;
  - `test_approved_lp_deposit_cannot_overdraw`;
  - `test_bet_falls_back_to_the_play_overlay_only_when_it_covers_the_stake`.
- **Fix (`db34d4b`, plus `ff6da3d` for the wallet bridge).** `_book_profile_bet` and the LP path run under `play_adjust.spend_lock(profile)`:
  1. **Reserve** the stake with `apply_once(-amount, key=hold:…, chain_usdc=<fresh strict chain read>)`. This raises `InsufficientPlayBalance` if the stake doesn't fit.
  2. Book the ticket (or credit the LP pool).
  3. Pull the USDC.
  4. If the pull succeeded, release the reservation (the chain now carries the debit). If it failed, the reservation **is** the debit.
  5. If booking failed, release and refuse.
  
  The wallet-bridge deposit also takes the same lock around its chain read and overlay debit.
- **Status.** Fixed. Residual: a crash between a successful pull and the release over-holds the player (fail-safe). The keys `hold:<k>` and `hold-pulled:<k>` let ops reconcile it.

### M-08: High: daily withdraw cap bypass

- **Description.**
  - `safety.check_daily_withdraw` only peeked before the Circle transfer; `commit_daily_withdraw` added after it.
  - The total lived in a per-process dict.
- **Exploit.**
  - Two withdrawals in flight at once (web link plus Telegram, or two links) both pass.
  - Every restart, and every extra uvicorn worker, resets the cap.
- **PoC.**
  - `tests/test_audit_money_withdraw.py::test_concurrent_withdrawals_cannot_pass_the_daily_cap`: 120 sent against a cap of 100.
  - `::test_the_daily_cap_survives_a_restart`.
  - `tests/test_audit_money_processes.py::test_daily_cap_is_shared_by_every_process`: 4 spawned processes.
- **Fix (`e41cf68`).**
  - `reserve_daily_withdraw` checks and adds in one `update_json` write to `daily_withdrawals.json` (cross-process flock), **before** the transfer. `release_daily_withdraw` gives it back only when Circle definitely failed.
  - `perform_withdrawal` runs under the same `spend_lock`, so a withdrawal cannot interleave with a bet, LP deposit, bridge deposit or cash-out.
  - The legacy `commit_daily_withdraw` (bot `send.py`) now writes the shared store too.
- **Status.** Fixed. The store is per host; it is shared by every process on the VM.

### M-10: High (latent): cash-out USDC spendable twice before the burn

- **Description.** `offramp.perform` checked `chain + overlay`, then `cctp.start`, which only approves; the burn lands 15 to 30 s or more later. Nothing reserved the amount in between.
- **Exploit.** Confirm a 39.95 cash-out PIN on 40, then spend 39 through an overlay debit (a bet or the wallet bridge) before the burn. The bank is paid **and** an unbacked position is left behind; the house is short. This becomes exploitable once mainnet overlay debits are on.
- **PoC.** `tests/test_audit_money_paycrest.py::test_cashout_holds_the_balance_until_the_burn`.
- **Fix (`c138711`).**
  - `perform` runs under `spend_lock`.
  - It reserves the daily cap, then holds the amount on the overlay (`cashout-hold:<order>`, checked against the strict chain read minus gas).
  - It releases the hold:
    - when the burn confirms (new `cctp → events.bridge_burned → offramp.on_bridge_burned`);
    - or when the bridge reaches a terminal state;
    - or immediately if the bridge never started (the cap is given back too).
- **Status.** Fixed.

### M-04: High: a sub-micro AFM stake freezes the fixture

- **Description.** `place_bet` debits `to_micro(amount)`, rounded half-even, but booked the raw `Decimal`. `settle_matchday` debits the book total from the pot, so the debit falls short by a micro, raises `InsufficientFunds`, and the book goes to `settle_failed`.
- **Exploit.** Two bets of `1.0000005` cost 2.000000 but book 2.000001. Every honest stake on that fixture is frozen, and nothing ever retries `settle_failed`.
- **PoC.** `tests/test_audit_money_afm.py::test_sub_micro_stakes_cannot_freeze_a_fixture`. Before the fix the error was "have 52.000000, need 52.000001".
- **Fix (`e95442b`).**
  - The stake is booked as `from_micro(to_micro(amount))`, and non-finite amounts are refused.
  - Book writes go through `update_json` (cross-process flock) instead of load/save.
  - Books now record `deadline_at`, so the stale-book guard can refund them.
- **Status.** Fixed. `close_stale_books` still has no scheduler (O-12).

### M-02: Medium (latent Critical): LP withdraw sends before booking, on a pending approval

- **Description.** `POST /spectator/lp/withdraw` refused only `denied`, `expired` and `telegram_unreachable`. A **pending** approval (the normal "ask" result) fell through to `refund_float_to_user`, real USDC from the House float. The claim was only reduced by `pool.withdraw` **after** the send, so N concurrent requests all pass the cap and all send.
- **Why it is latent.** `lp_withdraw` is not in `tx_approval.VALID_ACTIONS`, so `start_approval` answers `denied` and the route fails closed by accident. Adding the action would have turned this into a House-float drain.
- **PoC.** `tests/test_audit_money_web_spend.py`:
  - `test_lp_withdraw_never_sends_on_a_pending_approval`;
  - `test_lp_withdraw_race_sends_at_most_the_position`;
  - `test_lp_withdraw_send_failure_restores_the_position`.
- **Fix (`db34d4b`).**
  - It sends only on `approved`.
  - It takes the claim first: `pool.withdraw` re-checks the cap under the row lock.
  - It gives the claim back only for a `SpectatorOnchainError` raised before broadcast. Any other error keeps the claim and logs CRITICAL for reconciliation, so a payment is never made twice.
- **Status.** Fixed. Product note: LP withdrawals currently cannot succeed at all; add `lp_withdraw` to the approval actions, with an apply path, when it is wanted.

### M-05: Medium: book-entry money crossing into mainnet

- **Description.**
  - AFM `place_bet` was gated only by the shared spectator switch, so turning chess betting on for mainnet also opened AFM book-entry bets.
  - `wallet_bridge.withdraw` (football wallet to play overlay) had no mainnet refusal, unlike `deposit`. Any `owner:` balance on mainnet (legacy or migrated) could become positive play overlay. That overlay counts toward bets, withdraw links and cash-out checks.
- **PoC.** `tests/test_audit_money_afm.py`:
  - `test_afm_bets_refused_on_mainnet_even_with_the_switch_on`;
  - `test_bridge_withdraw_refused_on_mainnet`.
- **Fix (`e95442b`).** Both now refuse when `ledger._money_chain_is_mainnet()`. AFM bets return the standard 403 `spectator_betting_disabled`.

### M-11: Medium: cash-out pays the whole out-wallet balance

- **Description.** `offramp.submit` ordered and sent `usdc_balance(out_wallet)`. `refund_home` bridged the whole balance home.
- **Exploit.** The out address is a public CCTP mint recipient, so anyone can send USDC to it.
  - **Cap bypass.** USDC sent there is paid to the player's bank above the 300 per-order / 500 per-day caps.
  - **Mixed orders.** A sibling order's refund gets paid out by another order, or swept home by it, which invites a manual double refund.
- **PoC.** `tests/test_audit_money_paycrest.py::test_cashout_sends_only_the_order_amount`: about 419.98 was ordered against a 20 cash-out before the fix.
- **Fix (`c138711`).**
  - `submit` uses `min(balance, order.amount_usdc)`.
  - `refund_home` bridges at most the order's `sent_usdc` (or its amount if nothing was sent).
- **Status.** Fixed. Residual: any leftover in the out wallet now just stays there, and nothing alerts on it (O-10).

### M-12: Medium: Paycrest webhook seen before applied

- **Description.**
  - `record_event` commits the dedupe row first.
  - `apply_status` wrote `paycrest_status` **before** the transition.
  - The poller skips any order whose echo already matches.
- **Exploit / impact.** One failed transition on `settled` (a DB blip) leaves the on-ramp stuck in `awaiting_deposit` forever:
  - the route returns 500;
  - Paycrest's retry is answered `duplicate`;
  - the poller sees equal statuses and skips;
  - the USDC sits unswept on Base, which invites a manual double credit.
- **PoC.** `tests/test_audit_money_paycrest.py::test_a_webhook_that_failed_to_apply_is_processed_on_retry`.
- **Fix (`e3385b9`).**
  - A delivery that raises is `forget_event`-ed (deleted only while its outcome is still `received`), so the retry runs.
  - The status echo is written after the transition.

### M-13: Medium: a mainnet chain masked by a testnet `SPECTATOR_CHAIN`

- **Description.** In `spectator_policy.is_mainnet()`, `SPECTATOR_CHAIN` or `BOARDMAN_SETTLEMENT_RAIL` *replaced* `default_chain_id()`. So with a mainnet `chains.yaml` default, `CLAW_DEFAULT_CHAIN` unset and `SPECTATOR_CHAIN=arc`, the check returned False. That leaves spectator betting on by default and the demo faucet on.
- **PoC.** `tests/test_audit_money_ledger_guards.py::test_testnet_spectator_chain_cannot_mask_a_mainnet_settlement_chain`.
- **Fix (`11e4dc9`).** Every chain signal is checked, and any mainnet signal wins.

### M-07: Low: prize rounding overpays

- **Description.** Each place was quantized half-even, so a $1.09 pot at 10% fee paid 0.99 of a 0.98 distributable. This happens for 1,791 of the 19,900 pots between $1 and $199.
- **PoC.** `tests/test_audit_money_tournament.py`:
  - `test_prizes_never_exceed_the_distributable_pot`;
  - `test_every_pot_from_1_to_199_dollars_conserves`.
- **Fix (`f89b358`).**
  - Shares are rounded down, and the whole-cent dust goes to the top place.
  - Hardening: a real-money final pays from the sum of the locked entries, not the stored `pot_usdc` or `entry × preset`. This is not exploitable today because `start_tournament` recounts the pot; the test is a regression guard.

### M-09: Low: a sent withdrawal reported as not sent

- **Description.** `execute_transfer_sync` called `get_supabase()` after the Circle transfer and outside any `try`. When it raised, the link was marked failed and the player was told "Nothing was sent; try again", so a retry double-sends the player's own funds.
- **PoC.** `tests/test_audit_money_withdraw.py::test_audit_failure_after_the_transfer_still_reports_it_sent`.
- **Fix (`e41cf68`).** The audit write is fully best-effort after the transfer.

### M-14: Low: ledger defence in depth

- **Description and PoC.** `tests/test_audit_money_ledger_guards.py` covers three gaps:
  - `ledger.credit` accepted a negative amount: a silent debit booked as a credit row.
  - `open_escrow` accepted a zero stake. A negative stake was already blocked by the `CHECK (stake_micro >= 0)` column constraint, which the PoC hit.
  - `SpectatorBook.settle` accepted a `void` book, so it could pay refunds plus winnings. The match state machine blocks this today; the book-level guard covers it independently.
- **Fix (`11e4dc9`).** All three are refused.

### M-15: Low: non-finite amounts

- **Description.** `float("NaN")` passes every `amount < x` guard in the web BFF routes, and `"NaN"` is a valid string. It reached `add_adjust` and could corrupt the player's overlay to `NaN`, after which every balance read fails.
- **PoC.**
  - `tests/test_audit_money_web_spend.py::test_non_finite_amounts_are_refused` (`NaN`, `inf` on bet, LP and LP-withdraw);
  - `tests/test_audit_money_afm.py::test_non_finite_bets_are_refused`.
- **Fix.** `db34d4b` (`_finite_amount`) and `e95442b`.

## 5. Open items (not fixed on this branch)

| ID | Sev | Item | Recommendation |
|---|---|---|---|
| O-1 | High | **AFM results are computable before betting closes** (partly confirmed). The engine seed is `sha256(match_id)` and `match_id` is public. Line-ups and plans are published at matchday open; betting stays open until the deadline. A club owner can simulate every lineup they might pick and back the result from a second account. | Seed with a server secret using commit-reveal (`sha256(secret_md ‖ match_id)`) and publish the commitment at open. Keep AFM betting off on mainnet (now enforced) until this is done. |
| O-2 | Medium | **CCTP legs use a fresh Circle key per attempt** (`cctp.py`: `{key}\|burn\|{n}`). A timeout that Circle actually accepted becomes `ChainOpsError`, the retry uses a new key, and the row can end `failed` after money moved. A third-party relay of the mint (`destinationCaller=0`) also ends `failed` even though the USDC was minted. Alerts then say the USDC "sits in the Base wallet", which invites a manual double credit. | Keep each leg's key stable across `ChainOpsError` retries; change it only after an on-chain failure. Before marking a mint failed, check `usedNonces` / Iris. |
| O-3 | Medium | **Paycrest `send()` treats a Circle timeout as not sent** (`transfer_usdc` returns `success:False` on a 30 s request timeout). The order goes back to `on_base` without `paycrest_id`. The funded Paycrest order is never polled, and the order ends `needs_review`, where an admin refund pays twice. | Persist `paycrest_id` and a fixed transfer key in a `funding` state before sending, retry with the same key, and never create a new Paycrest order while an earlier one may have been funded. |
| O-4 | Medium | **Self-custody `UNIQUE(tx_hash)`** (`self_custody/store.py`) assumes one intent per transaction. Bundled ERC-4337 UserOps lock several stakes in one transaction, and only the first confirms. Anyone can also submit a victim's pending hash on their own intent to block them. This is liveness only: the escrow holds the money. | Key on `(tx_hash, log_index)` or `user_op_hash`, and record a hash only after its receipt matches. |
| O-5 | Medium | **Passkey confirm is not crash-safe** (`intents.py`). The intent is set `confirmed` before `_apply`, so a crash leaves the stake locked and the match stuck. | Add `applied_at_ms`, and have the sweep re-run the (idempotent) `_apply` for confirmed-but-unapplied intents. |
| O-6 | Low | **Random Circle keys on player transfers** (withdraw links, tournament `lock_entry`). A timeout reported as failure lets a retry double-send the player's own funds. Tournament refunds now use entry keys (M-06), but there is no durable claim row. | Derive keys from the link hash or entry id, treat exceptions as "unknown", and add a `tournament_refunds` claim like `_claim_place`. |
| O-7 | Medium (unconfirmed) | **Season tick and wages across processes** (`season.py`). There is only a `threading.RLock`, plus whole-file `save_json`. If the keeper and the API both tick, wages are debited twice. | Use a DB lease around tick, and key wage debits by `s{n}_md{m}:{agent}`. |
| O-8 | Low | **Circle webhook** (`api/webhooks.py`). The Supabase path checks then inserts with no unique `tx_hash`. It accepts `transactions.outbound` as a credit, and the legacy `wallet_balance_usdc` credit double-counts a deposit already on-chain. Each case needs a validly signed body, and the parser does not match real Circle payloads. | Add a unique index with `INSERT … ON CONFLICT DO NOTHING RETURNING`, drop `outbound`, and retire the legacy credit. |
| O-9 | Low | **`/credit_topup` (bot) and `fiat_topups.json`.** Check-then-update guarded only by a `threading.Lock`, so two admins or processes can both send. | Use a store flock or a DB claim per reference. |
| O-10 | Low | **Paycrest out/in wallets.** No alert on leftover balances. The sweep races (two passes bridge the same balance). An expired on-ramp that is paid late is stranded. Cap sums are not transactional; off-ramp is now serialized per profile, on-ramp is not. | Add a per-profile lock around sweep, a leftover alert, and a grace poll for expired orders. |
| O-11 | Low | **Legacy `debit_wallet` "ledger sync"** in `rematch_web` also debits `profiles.wallet_balance_usdc` when it covers the stake: the player pays twice from two stores. | Decide whether the legacy balance is still money; if not, remove the sync. |
| O-12 | Low | **AFM.** `close_stale_books` has no caller, `settle_failed` books have no refund path, and `MAX_BET_USDC` is per call only. | Schedule the guard, add an ops refund for `settle_failed` books, and cap per better per fixture. |
| O-13 | Low | **`agents.json` has other whole-file writers** (registry). The market now writes per record under flock, but a registry save racing a sale could still drop the new owner. | Move listings and ownership to a DB row, or route all writers through `update_json`. |
| O-14 | Low | `Decimal("Infinity")` raises `OverflowError` (HTTP 500) in `self_custody/intents.submit` and `withdraw_links.confirm`. No state changes. | Catch `OverflowError` with `InvalidOperation`. |
| O-15 | Low | Passkey confirmations read the default chain, not the intent's chain, and there is no confirmation depth. This matters only if `SELF_CUSTODY_CHAIN` changes or a reorging chain is added. | Store and use the intent's chain, and add a depth. |
| O-16 | Low | `wallet_bridge.transfer_key = f"{party}\|{key}"` can collide when an id contains `\|`. `_same()` catches it, so the worst case is a 409 (denial of service). | Use a tuple key or a forbidden separator. |
| O-17 | Policy | `clawstation_settlement.py` no-show payouts can rest on the reporter's claim when the AI's confidence is low. | Confirm with product and counsel that this is intended. |
| O-18 | Info | `play_adjust` and `daily_withdrawals.json` are JSON files with a host-local flock: correct on the single VM, but not across hosts. `leases.exclusive` is not renewed (90 s TTL): a spend that stalls past the TTL frees the lock. The reservations still protect bets, LP and cash-outs; plain withdrawals then rely on the chain. | Move `play_adjust` into the agentic DB before running more than one host. |

## 6. Authorization notes for the web/API auditor

- **LP withdraw sends on a pending approval** (M-02). This is an approval-gate bypass; it is fixed here.
- **`ui_paystack_check` does not check that the reference belongs to the caller.** It leaks amounts only. Not fixed.
- **The BFF money routes trust `profile_id` from the body** under the master key. This is by design for the Next BFF. It is worth confirming that the BFF binds `profile_id` to the session on every money route (`/spectator/bet`, `/spectator/lp`, `/spectator/lp/withdraw`).

## 7. Tests

- **Baseline (`70a7c64`):** 1103 passed, 0 failed.
- **Added:** 47 tests in these files:
  - `tests/test_audit_money_web_spend.py`
  - `tests/test_audit_money_afm.py`
  - `tests/test_audit_money_tournament.py`
  - `tests/test_audit_money_withdraw.py`
  - `tests/test_audit_money_paycrest.py`
  - `tests/test_audit_money_ledger_guards.py`
  - `tests/test_audit_money_bridge_lock.py`
  - `tests/test_audit_money_processes.py` (spawned processes)
  - helper: `tests/_audit_proc_helpers.py`
- **Changed:** `tests/channels_fixtures.py` now also fakes `get_usdc_balance_strict`, because the money paths read the strict chain balance before reserving.
- **Every PoC was run against the unfixed code and failed**, except the hardening tests marked as such in their docstrings.
- **Postgres:** not run. There is no local Postgres on the audit host, and `BOARDMAN_TEST_DATABASE_URL` was unset. The new lock is built on `match_leases` (`INSERT … ON CONFLICT` plus `FOR UPDATE`), which earlier waves exercised on Postgres. Re-run `tests/test_audit_money_processes.py` with `BOARDMAN_TEST_DATABASE_URL` before mainnet.
- **Full suite after the fixes:** 1150 passed, 7 skipped, 0 failed (1103 baseline + 47 new). Same command as the baseline, at `ff6da3d`.

## 8. Residual risks and go-live gates

1. **Don't turn on mainnet spectator, LP or AFM betting until O-1 is fixed.** M-05 and M-13 make the gates fail closed.
2. **Settle O-2 and O-3 before naira volume grows.** Both turn a provider timeout into an "it failed" that a human then refunds by hand. Until they are fixed, give `needs_review` cash-outs and bridges a runbook step that checks the chain before any manual refund.
3. **Reconcile reservations.** Ops should alert on `hold:*` and `cashout-hold:*` keys in `play_adjust.json` that have no release after 1 h.
4. **Keep a single host** for the API, bot and house until `play_adjust` and the daily-cap store move into the shared database (O-18).
