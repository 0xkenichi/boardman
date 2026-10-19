# Boardman v2 contracts audit, October 2026

Internal pre-mainnet review of BoardmanEscrow v2 and SpectatorPool v2, and of
the backend code that signs and sends calls to them. This is not a substitute
for the external audit; section 8 lists what that audit should focus on.

| | |
|---|---|
| Branch | `audit/contracts`, based on `70a7c64` (integration/wave1) |
| Date | 2026-10-20 |
| Compiler | solc 0.8.20 (viaIR, optimizer 200, evm paris), OpenZeppelin 5.6.1 |
| Target chain | Arc mainnet (chain id 5042), USDC at `0x3600…0000` |
| Result | 0 Critical, 1 High, 1 Medium, 7 Low, 8 Info. No contract code change was needed. The High and the Medium are in the backend and are fixed. |

## 1. Scope

**Contracts** (`contracts/contracts/core/`)
- `BoardmanEscrow.sol` (v2, 587 lines)
- `SpectatorPool.sol` (v2, 775 lines)
- Inherited OpenZeppelin code: `Ownable2Step`, `ReentrancyGuard`, `Pausable`, `SafeERC20` (`trySafeTransfer`), `ECDSA`

**Deployment:** `contracts/scripts/deploy_v2.js`, and the `hardhat.config.js` networks.

**Backend call sites**
- `src/stack/agentic/onchain.py`: the EIP-712 `sign_create_permit`, `dual_lock_onchain`, `resolve_onchain`, version probing and `load_resolver_key`
- `src/stack/agentic/spectator_onchain.py`: openBook, close, depositFor, resolve and cancel
- Callers of those modules: `matches.py` (freeze and settlement), `house.py` (abort), `fee_sweep.py`, and `rematch_web.py` (the spectator bet apply path)
- `src/backend/services/clawstation_escrow.py`. This is the v1 human path, which is being cut.
- `src/backend/services/self_custody/*`: the passkey `createMatch` / `joinMatch` intents and the confirm logic

Out of scope: ClawEscrow (V0), the v1 deployments, Circle wallet internals, and the frontend.

## 2. Methodology

- Read the code line by line. For each function, we listed attacks for each role: owner, resolver, player1, player2, a random attacker, a USDC-blacklisted recipient, a front-runner, a griefer, a compromised resolver and a compromised backend.
- Attack classes covered:
  - reentrancy, including cross-function and read-only
  - access control
  - signature replay across chains, contracts and matches, and after cancel
  - EIP-712 drift between the contract and the Python signer
  - signature malleability
  - front-running
  - griefing and dust
  - fee math (rounding, overflow, fee > pot, tier boundaries, snapshot vs live)
  - `==` timeout boundaries
  - double payout or refund
  - stuck funds
  - pull-payment accounting
  - sweep bounds
  - pause bypass
  - Ownable2Step misuse
  - Arc and USDC specifics
  - pool odds manipulation, late deposits, bypassing `closeAt`, resolving before close, and over-allocation from rounding
- Checked Arc's documented behaviour against the code (section 6).
- Wrote a PoC test for every finding, and for each attack class we refuted. Fixed findings have tests that fail before the fix and pass after it. We checked this for the backend tests by reverting the fix locally.
- Added model-based invariant runs. A seeded PRNG drives random sequences, and a model predicts every address's wallet + `owed` balance after each step. At the end both contracts are drained to exactly zero.

**Tests**

| Suite | Before | After |
|---|---|---|
| `npx hardhat test` | 120 passing | **145 passing** (+19 in `test/Audit.2026-10.js`, +6 in `test/DeployPreflight.js`) |
| `pytest tests` | — | **1122 passed**, 7 skipped (+15 in `tests/test_audit_contracts_backend.py`) |

## 3. Findings summary

| ID | Title | Severity | Component | Status | Fix commit |
|---|---|---|---|---|---|
| H-01 | On-chain spectator bets accepted after the result is known | High | backend (pool operator, settlement) | Fixed (residual risk noted) | `be65d19` |
| M-01 | Pulled spectator stake refunded even though the pool deposit landed or may still land | Medium | backend (`rematch_web.py`) | Fixed | `be65d19` |
| L-01 | createMatch permit does not bind the platform fee | Low | BoardmanEscrow | Acknowledged | — |
| L-02 | A transient RPC error during the version probe pins the v1 ABI | Low | backend (`onchain.py`, `spectator_onchain.py`, self-custody) | Fixed | `4cb583f`, `be65d19` |
| L-03 | `dual_lock_onchain` treats a RESOLVED or CANCELLED escrow as "already locked" | Low | backend (`onchain.py`) | Fixed | `4cb583f` |
| L-04 | `deploy_v2.js` has no preflight for chain id, token, Safe or resolver, and deploys the pool on mainnet | Low | deploy script | Fixed | `4e632d2` |
| L-05 | Passkey confirm does not check `MatchTerms.player2`, and several permits can be live for one matchId | Low | backend (self-custody) | Open (recommendation) | — |
| L-06 | The ply-N `close()` is fire-and-forget, and `deposit()` bypasses the off-chain kill switch and geo gates | Low | backend + pool design | Partly mitigated by H-01, recommendation | — |
| L-07 | No backend path for human players to `withdraw()` deferred escrow payouts | Low | backend | Open (recommendation) | — |
| I-01 | Stray or forced USDC is outside the accounting and cannot be recovered | Info | both contracts | Acknowledged | — |
| I-02 | Gas-limit griefing of push payouts is not feasible with USDC | Info | BoardmanEscrow | Refuted (PoC) | — |
| I-03 | Fee tiers are not monotonic at the flat→bps boundary | Info | both contracts | Acknowledged | — |
| I-04 | `load_resolver_key` falls back to `ADMIN_PRIVATE_KEY` / `OWNER_PRIVATE_KEY` and to `./.env` | Info | backend | Recommendation | — |
| I-05 | Arc chain specifics (decimals, blocklist, timestamps, base fee, chain id) | Info | all | Verified, see section 6 | — |
| I-06 | CONTRACTS.md said the ply-N close was not wired | Info | docs | Fixed | this commit |
| I-07 | The deployer stays owner until the Safe accepts ownership | Info | deploy | Recommendation | — |
| I-08 | ClawStation crash recovery does not check that `player1` is ours | Info | backend (being cut) | Fails closed on v2 | — |

## 4. Findings

### H-01: On-chain spectator bets accepted after the result is known (High, fixed)

**Description.** SpectatorPool's only defence against betting on a known result is `closeAt` plus `close()`. The backend opens a book with `closeAt = now + SPECTATOR_BOOK_WINDOW_SECONDS` (default 900 s), whatever stage the game is at. The off-chain book freezes at ply 24, but the matching on-chain `close()` is sent on a daemon thread with no retry. At settlement, `close()` was only sent inside `resolve_book`, which runs after the escrow resolve tx, stats, the creator fee, LP steps and opening stats. That left three paths to bet on a result that was already decided:

1. **Direct `deposit()`.** A game that ends before the freeze ply (resign, flag, short game), or a freeze whose `close()` failed, leaves the book Open. From the moment the game ends on the live stream until `close()` lands, anyone can call `deposit()` on the winning side.
2. **Late Telegram approval.** The House path re-checked only the kill switch at apply time, not the match or book state. A user could request bets on both sides during the game and approve only the winner after the game ended. Approvals live for 2 minutes. `deposit_for` checked only the on-chain status and `closeAt`.
3. **Lazy openBook.** If the book was never opened on-chain at lock time, the first House deposit opened it with a fresh 900 s window, even late in the game.

**Exploit scenario.** In PoC `H-01 (contract side)`, side A fans hold $10 and side B fans hold $50. The game ends and A wins. Mallory deposits $100 on A before `close()`. She claims $132.36: a risk-free $32.36 taken from the side-B fan.

**Fix (`be65d19`)**
- `MatchService._settle` closes the pool book first, as a journaled `spectator_close_onchain` step that runs before any money step. If it fails, the failure is logged. `resolve_book` still closes before it resolves, so a failure never blocks settlement.
- `spectator_onchain.deposit_for` calls the new `assert_offchain_betting_open`. It refuses when the match status is not in `BET_STATUSES`, or when the off-chain book is `closed`, `settled` or `void`. This covers late approvals and lazy opens after the freeze.

**Residual risk.** Between the final move and the first settlement step's `close()` landing, a direct `deposit()` is still possible. That window is about one tx on Arc, instead of several txs plus database steps. Eliminating it fully needs a contract change (for example, the resolver posting a `resultKnownAt` that voids later deposits) or a shorter `closeAt`. See section 8.

**PoC**
- `contracts/test/Audit.2026-10.js`: `H-01 (contract side) …`
- `tests/test_audit_contracts_backend.py`:
  - `test_h01_settlement_closes_the_pool_book_before_any_other_step`
  - `test_h01_deposit_for_refuses_a_finished_match[settling|settled|cancelled]`
  - `test_h01_deposit_for_refuses_after_the_offchain_freeze`
  - regression guards: `…still_works_while_betting_is_open` and `…failed_early_close_does_not_block_settlement`

### M-01: Pulled stake refunded even though the pool deposit landed or may still land (Medium, fixed)

**Description.** `_apply_approved_spectator_bet` and the inline bet route do three things: pull the user's USDC to the House float, call `depositFor`, then project the result to JSON. Their `except Exception` refunded the full stake from the float on *any* error after the pull. Two of those errors happen after the money is already in the pool:

- `nonces.TxPendingConfirmation` from `_send`. Its own docstring says callers "must not refund". A receipt timeout does not mean the tx failed: it may still mine.
- Any exception in the projection (`mark_onchain`, `project_deposit`, `svc._save`) after `depositFor` has confirmed.

In both cases the user got a refund *and* kept a claimable position in the pool. The House float paid twice.

**Fix (`be65d19`)**
- `_deposit_spectator_onchain` now catches projection errors once the deposit has landed, and returns the tx hash with `projection_error`.
- Both routes check `spectator_onchain.deposit_may_have_landed(exc)`, which is true for a `TxPendingConfirmation` labelled `depositFor`. In that case they return `spectator_deposit_pending` and do not refund. The approval route stores that result so the bet is not applied a second time. A genuinely failed deposit is still refunded.

**PoC:** `test_m01_pending_deposit_is_not_refunded`, `test_m01_projection_error_after_a_landed_deposit_is_not_refunded`, and the guard `test_m01_failed_deposit_is_still_refunded`.

**Follow-up.** Ops need a reconcile step that turns a confirmed pending `depositFor` into a projected ticket, or refunds it if it reverted.

### L-01: createMatch permit does not bind the platform fee (Low, acknowledged)

The fee is snapshotted at `createMatch` from whatever the tiers are at that moment. The resolver's permit covers `(matchId, player1, player2, stake, deadline)` but not the fee. Between the permit being issued and `createMatch`, the owner (a multisig) can retune tiers up to the caps: 10%, or $0.50 per player and at most 25% of the pot. Player1 then pays more than they were quoted.

- Mitigations already in place: the caps, the `MatchTerms` event, and `getMatch()`, which player2 can read before joining. The agents and the passkey UI join automatically, though.
- Fixing this needs an ABI change: add `maxFee` to the permit, or revert when the fee is above the quote.
- PoC: `L-01 the owner can raise the fee…`

### L-02: A transient RPC error pins the v1 ABI (Low, fixed)

`escrow_version`, `pool_version` and the self-custody `ChainReader.escrow_version` treated *any* exception from the version probe as "v1".

- In `onchain.py` and `spectator_onchain.py` the result was also cached for the life of the process. One RPC timeout meant every later create, open or deposit used the v1 ABI against the v2 contract. Those calls fail closed (selector not found), but after an approve.
- In the passkey path, the player was handed v1 `createMatch(bytes32,uint256)` calldata to sign.

**Fix:** only `ContractLogicError` or `BadFunctionCallOutput` means v1 (`is_missing_function_error`). Other errors propagate. The passkey intent now refuses with "try again" instead.

PoC: `test_l02_version_probe_does_not_cache_a_transient_failure`, `test_l02_a_contract_without_the_probe_is_v1`.

**Mainnet recommendation:** set `BOARDMAN_ESCROW_VERSION=2` and `SPECTATOR_POOL_VERSION=2`.

### L-03: Settled escrow reported as "already locked" (Low, fixed)

`dual_lock_onchain` returned `already_locked: True` for any existing match with status ≥ 1, including RESOLVED (3) and CANCELLED (4). It also swallowed all exceptions around the probe. A retried lock could therefore run a match whose stakes had already been paid out or refunded, and `resolve_onchain` would then report `already_settled` success.

It now raises on a final status. PoC: `test_l03_dual_lock_refuses_a_settled_onchain_match[3|4]`.

Not changed: a retried lock that finds its own OPEN match still calls `createMatch` again, which reverts with `MatchAlreadyExists`. This is a liveness issue only. The resolver can cancel, or player1 gets a refund after `openTimeout`.

### L-04: deploy_v2 lacked a preflight (Low, fixed)

The `arcMainnet` RPC URL and chain id are both env-overridable, and so is the USDC address (`ARC_MAINNET_USDC`, `USDC_ADDRESS`). Nothing checked any of the following:

- the chain is really 5042
- the token has 6 decimals (every constant assumes this)
- the owner Safe exists on this chain (a Safe address from another chain would leave the throwaway deployer as owner forever)
- the resolver is an EOA (permits use plain ECDSA, so a Safe resolver could never authorise a match)

The script also deployed SpectatorPool on mainnet, where betting is off until counsel signs off and where `deposit()` is permissionless once a book is open.

**Fix:** `scripts/lib/v2_preflight.js` runs all of these checks. Mainnets skip the pool unless `V2_DEPLOY_POOL=1`. PoC: the 6 tests in `test/DeployPreflight.js`. The local deploy smoke run passes.

### L-05: Passkey confirm does not check `MatchTerms.player2` (Low, open)

- `prepare_lock` signs a new permit each time it is called, with the opponent's *current* address: their passkey account, or their Circle wallet.
- Until the TTL runs out, a creator can hold several valid permits for one matchId with different `player2` values.
- `confirm` matches only `MatchCreated(matchId, account, stake)`, so the confirmed intent's `detail.player2` may not be the `player2` actually bound on-chain.
- `join_allowed` then follows the wrong address. The opponent is refused off-chain, or told to join from a wallet the escrow will not accept.

Funds are safe, because refunds follow the on-chain `player2`, but the match stalls until a timeout. **Recommendation:** when confirming `lock_create`, decode `MatchTerms` from the same receipt and store its `player2`. Also invalidate or reuse the previous unexpired permit instead of minting a new one.

### L-06: Off-chain betting gates do not bind the pool (Low, partly mitigated)

The spectator kill switch, the country allowlist and the freeze are all enforced off-chain. `deposit()` is open to anyone while a book is Open and before `closeAt`. The ply-N `close()` runs on a daemon thread with no retry. The kill switch neither calls `close()` on open books nor `pause()` (which is owner-only) on the pool.

H-01 narrows the timing window, but compliance gating is advisory for wallets that call the contract directly.

**Recommendations**
- The kill switch should `close()` every open book.
- Retry a failed freeze `close()`.
- Do not deploy the pool on mainnet until there is a decision on allowlisting (now the deploy default).

### L-07: No backend withdraw path for human players' deferred payouts (Low, open)

When a push fails (for example, a USDC-blacklisted winner), the escrow credits `owed[player]`. `fee_sweep.py` withdraws `owed` only for agent wallets whose keys the backend holds. We found no call site that runs `withdraw()` for a Circle-wallet or passkey player. Funds are not lost: any player who controls their address can call `withdraw()` directly. But Circle developer-controlled wallets depend on the backend to do it.

**Recommendation:** add a withdraw intent for escrow `owed` and pool `claim`, and show `owed` to players.

### I-01: Stray or forced USDC (Info)

Neither contract can recover USDC that is outside its accounting:

- USDC sent with a plain `transfer` (a player error, or a passkey wallet paying instead of approving)
- on Arc, native USDC forced in through a `SELFDESTRUCT` beneficiary. Native and ERC-20 USDC share one balance, and EIP-6780 still moves the balance.

Accounting never reads `balanceOf`, so this cannot break anything, but monitors must check `>=` and not `==`. The CONTRACTS.md note was updated.

An owner-only `skim()` bounded to `balance − (locked + fees + owed)` could be considered. It adds owner surface. PoC: `I-01 stray USDC…`

### I-02: Gas-limit griefing of push payouts (Info, refuted)

The known limitation was that a `refundExpired` caller could pick a gas limit that makes the push fail and the payout land in `owed`. Under EIP-150's 63/64 rule, that only works if the token transfer needs about 63 times the gas that the code after the call needs (about 45k for `owed` and the events), so about 2.8M gas. USDC needs about 30–60k.

PoC `I-02 no gas limit makes refundExpired succeed while deferring a payout` sweeps gas limits from 60k below the estimate up to the estimate. Every limit either reverts the whole tx or pushes successfully. A blacklisted recipient correctly falls back to `owed` (`I-02 a blacklisted player…`).

On Arc, a transfer that reverts on the blocklist still consumes gas. If the USDC system contract ever burned all the gas it was forwarded on failure, the caller would need a gas limit of at least 64 × 45k. `eth_estimateGas` finds that, so nothing gets stuck. We did not add a gas floor or stipend: an under-sized stipend would push *every* payout into `owed`.

### I-03: Non-monotonic fee tiers (Info)

| Contract | Smaller amount | Fee | Slightly larger amount | Fee |
|---|---|---|---|---|
| Escrow | stake $4.99 | $1.00 (flat) | stake $5.00 | $0.70 (7%) |
| Pool | pot just under $10 | min($1, 25% of pot) | pot of $10 | $0.70 |

This is a product choice. Make sure UI quotes come from `quotePlatformFee`. PoC: `I-03 tier boundaries…`

### I-04: Resolver key fallbacks (Info)

`load_resolver_key` falls back to `ADMIN_PRIVATE_KEY`, which is also the hardhat deployer key, and to `OWNER_PRIVATE_KEY`. It also reads `./.env` from the working directory. On mainnet, the owner is a Safe and the deployer is a throwaway, so a fallback key can only produce invalid permits or reverted resolves. But it means deployer keys can end up in the backend environment.

**Recommendation:** on mainnet, accept only `BOARDMAN_RESOLVER_KEY`. Check the derived address against `escrow.resolver()` before signing a permit; `_verify_resolver` already does this before a resolve.

### I-05: Arc specifics (Info, verified)

See section 6.

### I-06: Stale docs (Info, fixed)

CONTRACTS.md migration step 5 said `close_book_onchain()` was not wired into the ply-N freeze. It is wired, asynchronously. The step was rewritten to describe the H-01 behaviour.

### I-07: Ownership window (Info)

Until the Safe calls `acceptOwnership()`, the throwaway deployer is owner. It can rotate the resolver and treasury, set fees and pause. It cannot move escrowed funds.

**Recommendation:** accept ownership immediately, and check `owner()` and `pendingOwner()` on both contracts before the backend switches over. Then discard the deployer key.

### I-08: ClawStation v1 path (Info)

`clawstation_escrow.py` still calls `createMatch(bytes32,uint256)`, which reverts on v2, so it fails closed. Its crash recovery treats an existing on-chain match as "ours" without comparing `player1`. That was exploitable on v1 by squatting a matchId. On v2 it is not, because the permit binds `player1`. Remove the path with the planned ClawStation cut.

## 5. Attacks considered and refuted (with PoCs)

| ID | Attack | Why it fails | Test |
|---|---|---|---|
| A-01 | Backend and contract EIP-712 drift (name, version, typehash, field order) | Shared vector: the ethers digest equals the contract digest, the Python `sign_create_permit` recovers the same digest, v ∈ {27, 28}, and s is low | `A-01…`, `test_a01_python_permit_signs_the_contract_digest` |
| A-02 | Cross-chain replay (testnet 5042002 → mainnet) | chainId is in the domain, and the separator is rebuilt on a fork | `A-02…` |
| A-03 | Cross-contract replay (old or new escrow) | verifyingContract is in the domain | `A-03…` |
| A-04 | Replay after cancel, refund or resolve | A matchId can be created only once, whatever its status | `A-04…` |
| A-05 | Malleability, field tampering, front-running createMatch | OZ ECDSA rejects high-s; player1 = msg.sender is signed; every field is signed | `A-05…`, plus the existing v2 tests |
| A-06/07 | Gap or overlap at `==` timeout boundaries | join and resolve stop at exactly the timestamp where the refund starts | `A-06…`, `A-07…` |
| A-08 | Compromised resolver, owner or treasury pays an outsider | `winner ∈ {player1, player2}`, and the owner cannot act as resolver | `A-08…`, `INV-E` |
| A-09 | Late deposit, resolve before close, resolve after grace | `_requireBetting`, `BookStillOpen`, `ResolveWindowElapsed`; edges checked to the second | `A-09…` |
| A-10 | Sweep stealing other books, or double sweep | Bounded by that book's `remaining`, the `swept` flag, and owner-only | `A-10…` |
| A-11 | Outsider or double claim | `claimable` is 0 for non-depositors, and `claimed` is set | `A-11…`, `INV-P` |
| — | Reentrancy (including cross-function and read-only) | USDC has no hooks; state is written before every external call; every transfer path is `nonReentrant`; views are never read mid-call | review |
| — | Overflow in fee math or casts | stake ≤ 1e10, so `uint96` and `uint40` casts are safe; 0.8 checked math; fee clamped to the pot | review, `I-03` |
| — | Pause bypass | Every money-in path has `whenNotPaused`; every money-out path ignores pause | existing v2 tests |
| — | Ownable2Step misuse or renounce | Two-step transfer, and `renounceOwnership` reverts | existing v2 tests |
| — | Rounding over-allocation in the pool | Floor division, Σ claims ≤ distributable, dust is swept | `INV-P` |

**Invariant runs**
- **INV-E** (90 random steps, blacklist toggles included): after every step, the model's wallet + `owed` for each of 7 addresses matches the chain exactly. `balance == locked + fees + owed`. A compromised resolver tries to pay an outsider on every settle and is always refused. No player loses more than their stake. After draining, the balance is 0 and owed is 0.
- **INV-P** (110 random steps, mixing direct deposits, `depositFor`, seeds, close, resolve on A/B/draw/refund, cancel, refundExpired and claims): solvency holds after every step. Refund claims are exact. No claim exceeds the book's `remaining`. After draining, the pool holds 0, the net across all accounts is 0, and the owner never gained.

## 6. Arc and USDC specifics

Checked against docs.arc.io (EVM differences, stablecoin-native model) and third-party network listings.

- **USDC.** The ERC-20 interface at `0x3600…0000` has **6 decimals**. The native gas balance is the same USDC with **18 decimals**: one balance, two views. The contracts only use the ERC-20 view and keep no native balance (they have no payable or receive function). Sub-micro native dust is invisible to `balanceOf`. Forced native USDC is covered by I-01.
- **Blocklist.** A transfer to or from a blocklisted address reverts, and still consumes gas when included. `_pay` uses `trySafeTransfer` and falls back to `owed`; the pool pulls only. An escrow or pool address that is itself blocklisted would freeze everything. That is a Circle trust assumption.
- **Timestamps.** Non-decreasing at 1-second granularity, and several blocks may share one. All boundaries use `>=` and `<` consistently, and the windows are hours or days long, so validator skew does not matter.
- **PREVRANDAO** is always 0. It is not used.
- **Minimum base fee** is 20 gwei, and txs below it are silently dropped. The backend sets `maxFee = 2·base + 1 gwei`, which is fine.
- **Chain id.** 5042 per docs-derived sources and Alchemy. One provider page lists a different value, so the preflight now pins 5042 for `arcMainnet`.
- **Finality.** Final on inclusion, so receipts can be trusted after one confirmation.

## 7. Centralization and trust assumptions

- **Owner (Safe).**
  - Can: set fees within the caps (only for future matches and books), rotate the resolver and treasury, pause money in, and sweep books after `claimWindow`.
  - Cannot: move escrowed, owed or claimable funds, or settle anything.
- **Resolver (hot key).**
  - Decides every outcome.
  - Can cancel any live match or book at any time, sign permits for any pair, and open books with any agent wallets and closeAt (≤ 7 d).
  - In the pool, a compromised resolver can `depositFor` on a side with its own float and then resolve to that side. This takes the losers' money without breaking any invariant.
  - It cannot pay a non-player in the escrow, and it cannot take a book's money except by betting.
  - Keep it in an HSM or KMS, rate-limit it, and alert on unusual resolves.
- **Backend.** Holds every agent's spend key and the resolver key, so a compromised backend controls agent stakes and outcomes. Human stakes are protected only by the timeouts (`openTimeout`, `lockTimeout`, `refundGrace`).
- **Circle (USDC issuer).** Can blocklist players or the contracts themselves, and can upgrade the token's behaviour.
- **Arc validators.** Permissioned BFT. They control ordering, so they can front-run a `close()` like any searcher (H-01 residual), and they control timestamps within the protocol's bounds.

## 8. Recommendations for the external audit

1. **H-01 residual.** Evaluate an on-chain fix: a resolver-posted `resultKnownAt` that excludes later deposits, or deposits that must carry a backend-signed, short-lived quote. Also confirm the 900 s default against real game lengths.
2. **Arc USDC system contract.** Measure the real gas cost of `transfer` and how it fails for blocklisted addresses (revert or `false`, gas burned or not) on Arc mainnet. Local simulators cannot reproduce the blocklist. Re-check I-02 with those numbers.
3. **Permit design.** Bind the fee (L-01), and consider a nonce or a resolver-side revocation for permits that are still live (L-05).
4. **Resolver blast radius.** Review the pool's `depositFor` + `resolve` power. Consider capping `depositFor` per book, or requiring the House float to be a separate role from the resolver.
5. **Off-chain/on-chain gate parity.** Review L-06 against compliance: should `deposit()` be allowlisted on mainnet?
6. **Formal properties.** Run the invariants in section 5 under Echidna, Medusa or Certora with unbounded sequences, especially the pool's `remaining` accounting across draw, seed and refund books.
7. **Ops.** Reconcile pending `depositFor` txs (M-01 follow-up), add a withdraw/claim path for human players (L-07), alert on `owed` and on `balance != accounted`, and do the ownership acceptance checklist (I-07).
