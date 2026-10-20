# ClawStation Contracts

## v2 safety release (BoardmanEscrow v2 + SpectatorPool v2) — not deployed yet

Source: `contracts/contracts/core/BoardmanEscrow.sol`, `contracts/contracts/core/SpectatorPool.sol`.
The deployed v1 contracts were built from commit `555a348`; check out that
commit to verify them on an explorer. "v2" here is the interface version
(`ESCROW_VERSION() == 2`, `POOL_VERSION() == 2`). It is not the older
`boardman_v1_arcTestnet_v2.json` flat-fee redeploy.

### What changed and why

| # | v1 problem | v2 behaviour |
|---|------------|--------------|
| 1 | SpectatorPool took bets after the result was known: `deposit` only checked `Open`, `_resolve` didn't need `Closed`, and the backend never called `close()` | `openBook(..., potCap, uint64 closeAt)` fixes a deadline (`now < closeAt ≤ now + 7d`). `deposit` / `depositFor` / `seed` revert with `BettingClosed` from `closeAt` on. `resolve` reverts with `BookStillOpen` unless the book is `Closed` or past `closeAt`. The backend sends `close()` before resolving, and `close_book_onchain()` exists for the kickoff freeze |
| 2 | Owner could change fees on locked funds, up to 100% or an uncapped flat fee, which could also make `resolveMatch` underflow | Hard caps: bps ≤ `1000` on both contracts; escrow flat fee ≤ `MIN_STAKE/4` ($0.50/player); pool flat fee ≤ $1 and also ≤ 25% of the pot. Escrow stores the fee per match at `createMatch` (`Match.platformFee`). The pool adds an append-only `FeeSchedule` and each book records its `feeScheduleId` at `openBook`. Fees are clamped to the pot |
| 3 | No way to get funds out if the resolver disappears | Escrow: `refundExpired(matchId)` can be called by anyone. An OPEN match older than `openTimeout` refunds player1, and `joinMatch` is closed by then. A LOCKED or DISPUTED match older than `lockTimeout` refunds both players, and `resolveMatch` is closed by then. Pool: `refundExpired(matchId)` can be called by anyone after `closeAt + refundGrace`, turns the book into a full refund, and `resolve` is closed by then. All timeouts are immutable constructor params with bounds |
| 4 | Pool pushed fees and creator shares, so one USDC-blacklisted address made `resolve` revert | Platform fees accrue to `protocolFees`, and `withdrawFees()` (anyone can call it) sends them to the current `feeRecipient`. Creator shares accrue to `owed[creator]` and `withdraw()` pays them out. Escrow fees accrue the same way. Player payouts are still pushed, but a failed transfer becomes `owed[player]` (`PayoutDeferred`) instead of reverting |
| 5 | Rounding dust and unclaimed winnings were stuck forever | Each settled book tracks `remaining`. `claim` decrements it and reverts if a claim would exceed it. After `claimWindow`, `sweep(matchId)` (owner only) moves that one book's `remaining` to `protocolFees`, and claims on that book stop |
| 6 | Anyone could squat a backend `matchId` with `createMatch`, and anyone could take the player2 seat | `createMatch(matchId, player2, stake, deadline, resolverSig)`. The resolver signs EIP-712 `CreateMatch(bytes32 matchId,address player1,address player2,uint256 stake,uint256 deadline)` on domain `BoardmanEscrow` / `2` / chainId / contract. `player1` is `msg.sender`. Only the bound `player2` can join |
| 7 | One EOA was owner, resolver and treasury, using plain `Ownable` | `Ownable2Step`, and `renounceOwnership` is disabled. `onlyResolver` no longer lets the owner through. Every role change emits an event. The deploy script refuses to give two roles to one address. Pause only blocks money coming in (`createMatch` / `joinMatch` / `openBook` / `seed` / `deposit` / `depositFor`); resolve, cancel, refund, claim, withdraw and sweep all keep working |
| 8 | `spectator_escrow.py` awaited synchronous Circle calls | The Circle calls run in a worker thread, the code waits for the approve to confirm, and `draw` bets go to side 2 |

ABI notes for integrators. `deposit(bytes32,uint256,uint8)` is unchanged.
`matches(bytes32)` on the escrow keeps the v1 six-field tuple.
`getBook` keeps positions 0..23 and appends `closeAt, settledAt,
feeScheduleId, swept, remaining`. All v1 events are unchanged, and new ones
were added. The breaking changes are `createMatch`, the `openBook` signature,
both constructors, and the owner losing resolver powers. The Python
operators (`src/stack/agentic/onchain.py`, `spectator_onchain.py`) detect v1
or v2 through `ESCROW_VERSION()` / `POOL_VERSION()`, which can be overridden
with `BOARDMAN_ESCROW_VERSION` / `SPECTATOR_POOL_VERSION`. The on-chain
betting window is `SPECTATOR_BOOK_WINDOW_SECONDS` (default 900).

### Deploy (human only)

`contracts/scripts/deploy_v2.js` documents every constructor param. It needs
`V2_OWNER_MULTISIG`, `V2_TREASURY`, `V2_RESOLVER` and `CONFIRM_V2_DEPLOY=1`,
and must run from a throwaway deployer key. Defaults: `openTimeout` 24h,
`lockTimeout` 7d, `refundGrace` 7d, `claimWindow` 180d. It writes
`deployments/boardman_v2_<network>.json` and offers ownership to the
multisig. The multisig must call `acceptOwnership()` on every contract deployed.

Before deploying, on every non-local network, `scripts/lib/v2_preflight.js`
checks four things:
- `arcMainnet` really is chain 5042
- the USDC address is a contract with `decimals() == 6`
- the owner Safe already has code on this chain (an EOA owner only with `V2_OWNER_IS_EOA=1`)
- the resolver is an EOA, because permits are plain ECDSA

Mainnets never get a SpectatorPool: spectator betting stays off there, and the
pool's `deposit()` is permissionless once a book is open. After the Safe
accepts ownership, run `scripts/check_v2_roles.js` with `EXPECT_ACCEPTED=1`.
Smoke-test locally with `npx hardhat run scripts/deploy_v2.js --network localhost`.

### Migration plan v1 → v2

1. Create a Safe for the owner and a separate treasury Safe, and generate a
   fresh resolver key (not `0xFA93…`). Deploy v2 and accept ownership from the Safe.
2. **Agentic path.** Set `BOARDMAN_ESCROW_ADDRESS_ARC` and `SPECTATOR_ESCROW_ADDRESS`
   to the v2 addresses and `BOARDMAN_RESOLVER_KEY` to the v2 resolver, then restart.
   New matches and books go to v2. Match ids are new per match, so no id lives on both contracts.
3. **Let v1 drain.** Keep the v1 resolver key so in-flight v1 matches and books
   can resolve or cancel. v1 `resolveMatch` / `cancelMatch` / `resolve` / `cancel`
   have the same signatures, and the backend picks the v1 ABI by probing.
   This needs a v1-address config entry, or a
   one-off script, because the backend reads a single address per contract.
   After every v1 book has settled and been claimed, pause v1 (owner) and stop using it.
   v1 has no sweep, so its dust stays.
4. **Human (Circle) path.** `src/backend/services/clawstation_escrow.py` and
   `blockchain_layer.py` / `escrow_service.py` still call
   `createMatch(bytes32,uint256)`. They must get a resolver permit (see
   `sign_create_permit` in `onchain.py`) and pass `player2`, so the opponent
   must be known at create. Keep that path on v1 until they are updated.
5. `close_book_onchain()` runs (async) at the ply-N book freeze
   (`matches.freeze_book`) and, since the October 2026 audit (H-01), as the
   first settlement step. `deposit_for` also refuses once the match or its
   off-chain book is frozen. A direct `deposit()` is still possible until
   `close()` lands or `closeAt` passes, so keep `SPECTATOR_BOOK_WINDOW_SECONDS` short.
6. Run an ops job that calls `withdrawFees()` on both contracts and `withdraw()` for
   agent creator wallets on the pool, then update `chains.yaml` and this file with the addresses.

### Audit readiness

Internal audit, October 2026: `docs/security/AUDIT_2026-10_contracts.md`
(PoCs in `contracts/test/Audit.2026-10.js`, `contracts/test/DeployPreflight.js`
and `tests/test_audit_contracts_backend.py`).

**Invariants** (each has a test in `contracts/test/*v2.js`, and the random property runs cover them too). On-chain monitors should check `>=` instead of `==`: USDC sent straight to a contract, or native USDC forced in on Arc, is outside the accounting.
- Escrow: `usdc.balanceOf(escrow) == totalLocked + accruedFees + totalOwed`. A match only moves forward: OPEN → LOCKED/DISPUTED → RESOLVED/CANCELLED. A match id is created once. `payout + fee == 2*stake`, `fee ≤ pot/4`, and the fee is the value frozen at create.
- Pool: `usdc.balanceOf(pool) == protocolFees + totalOwed + Σ live pots + Σ settled.remaining`. Per book, Σ claims ≤ `distributable`, the dust left is less than the number of winners, and refund books repay exactly the pot. `remaining` never underflows. A sweep touches only one book.
- No deposit lands at or after `closeAt`, and no resolve happens while a book is Open before `closeAt`, or at or after `closeAt + refundGrace`.
- Nothing can block money out: no payout path depends on the treasury or a creator accepting a transfer, and pause never blocks money out.

**Trust assumptions:**
- Owner (multisig) can set fees within the caps (only for future matches and books), rotate the resolver and treasury, pause intake, and sweep books past `claimWindow`. It cannot move escrowed or claimable funds.
- The resolver decides outcomes and permits. A compromised resolver can still pick a wrong winner within the timeout windows, cancel anything, or permit matches. It cannot take funds to itself unless it is also a player.
- `depositFor` pulls from the resolver's own balance (House float).
- The token is a standard 6-decimal USDC: no fee-on-transfer, no rebasing, and no callbacks.

**Known limitations:**
- Off-chain dispute evidence. The fee schedule is on-chain, but outcomes are not proven.
- `refundExpired` and `withdrawFees` can be called by anyone. A caller who gives too little gas can force a payout into `owed` instead of a push. Nothing is lost, the player just has to call `withdraw()`.
- A blacklisted player or creator cannot withdraw until they are unblacklisted, by design: there is no redirect.
- The domain separator is cached and rebuilt on a chain fork.
- Seeds on a losing side are forfeited to the pot, which is v1 economics and unchanged.
- The escrow permit has no nonce. Replay is prevented by the single-use `matchId`, but an unused permit stays valid until `deadline`, and the backend uses 600 s.
- The contracts are built with solc 0.8.20 for the paris EVM. EIP-712 is inlined because OZ 5.6's `EIP712` needs 0.8.24 and MCOPY.

**NatSpec:** both contract headers list the changes from v1. These all carry `@notice`/`@dev`, and `@param` where they take inputs:
- every state-changing function, including the requirement lists and timeout bounds
- the constructors
- every new event
- the role and config storage

Gaps: trivial views (`contractBalance`, `getMatchStatus`, `fanDepositOf`, `seedOf`), `pause`/`unpause` on the escrow, and the v1 events, which were kept unchanged. Run `npx hardhat test` (all hardhat tests) and `REPORT_GAS=true npx hardhat test` for gas figures.

## Arc Mainnet (chain ID `5042` — live Sept 16 2026)

- Native USDC ERC-20 facade predeploy: `0x3600000000000000000000000000000000000000` (same as testnet, 6 decimals)
- RPC: `https://rpc.mainnet.arc.io` · Explorer: `https://explorer.arc.io`
- Gas token: USDC (native gas accounting, sub-second finality)
- BoardmanEscrow: **not deployed yet** — `CONFIRM_V2_DEPLOY=1 npm run deploy:v2:arc-mainnet` (v2 only; see the v2 deploy notes above for the Safe owner, treasury and fresh resolver)
- Backend env after deploy: `BOARDMAN_ESCROW_ADDRESS_ARC_MAINNET=0x…`
- Circle W3S mainnet blockchain label: `ARC`; set `CIRCLE_USDC_TOKEN_ID_ARC_MAINNET` once confirmed

## Deployed (testnets)

| Chain | Network | ClawEscrow | USDC | Explorer |
|-------|---------|------------|------|----------|
| **base** | Base Sepolia (`84532`) | `0xDb76714390ccE1729558DF3c9EC4f45A1690dE78` | `0x036CbD53842c5426634e7929541eC2318f3dCF7e` | [Basescan](https://sepolia.basescan.org/address/0xDb76714390ccE1729558DF3c9EC4f45A1690dE78) |
| **arc** | Arc Testnet (`5042002`) | `0xFC44a06295d4fC58420027932A6FcB3C13D83859` | `0x3600000000000000000000000000000000000000` | [Arcscan](https://testnet.arcscan.app/address/0xFC44a06295d4fC58420027932A6FcB3C13D83859#code) |
| **avalanche** | Avalanche Fuji (`43113`) | `0xFC44a06295d4fC58420027932A6FcB3C13D83859` | `0x5425890298aed601595a70AB815c96711a31Bc65` | [Snowtrace](https://testnet.snowtrace.io/address/0xFC44a06295d4fC58420027932A6FcB3C13D83859) |

> Arc + Avalanche share the same CREATE address (same deployer nonce on both chains). Base used an earlier deploy.

## Shared config (Arc / Avalanche deploys)

### V0 archive (legacy Rematch testnet — do not use for Boardman mainnet)

- **Deployer:** `0xB2CCcac46cE93C2ac27fDBF7248938CC57F29424`
- **Fee Recipient:** `0x39EcF94ed35451A67006dcCE4A467aecdfAB6940`
- **Resolver:** `0x39EcF94ed35451A67006dcCE4A467aecdfAB6940`

### Boardman V1 (product) — **BoardmanEscrow**

| Role | Address |
|------|---------|
| Ops / fee / resolver | `0xFA931C535C9d10A324Ea7417a63ed22dD9b0cb2E` |
| **BoardmanEscrow (Arc Testnet, tiered)** | `0xD382f627fB565eb96D9EFFb66B9119DD4a555847` |
| SpectatorPool (Arc Testnet, tiered) | `0xd45bE49456021B74D2712fcffD47f17f91D39664` |
| BoardmanEscrow Arc Mainnet | _pending Sept 16_ |

Deploy artifacts: `contracts/deployments/boardman_v1_arcTestnet.json`  
Contract source: `contracts/contracts/core/BoardmanEscrow.sol`  
Legacy name **ClawEscrow** = V0 archive only.
- **Platform Fees (tiered, on-chain):** per-player stake < $5 → flat $0.50/player · $5–$500 → 7% (`FEE_BPS = 700`) · > $500 → 10% (`PREMIUM_FEE_BPS = 1000`). Owner-tunable via `setFeeTiers`; quote with `quotePlatformFee(stakePerPlayer)`.
- **Min Stake:** $2 USDC per player (`MIN_STAKE = 2e6`) · **Max Stake:** $10,000 per match
- **SpectatorPool fees (pot-level tiers):** pot < $10 → min($1.00, 25% of pot) · ≤ $1000 → 7% · above → 10%. Owner-tunable via `setSpectatorFeeTiers`.
- Testnet redeploy required for the tiered contracts (fresh address → update `chains.yaml` + env); mainnet has not been deployed yet, so it inherits tiers from day one.

## Env

```
CLAW_ESCROW_ADDRESS_BASE_SEPOLIA=0xDb76714390ccE1729558DF3c9EC4f45A1690dE78
CLAW_ESCROW_ADDRESS_ARC=0xFC44a06295d4fC58420027932A6FcB3C13D83859
CLAW_ESCROW_ADDRESS_AVALANCHE=0xFC44a06295d4fC58420027932A6FcB3C13D83859
CSC_ADDRESS=0xDb76714390ccE1729558DF3c9EC4f45A1690dE78
```

Also mirrored in `gaming/config/chains.yaml` and `contracts/deployments/*.json`.

## Redeploy

```bash
cd contracts
npx hardhat run scripts/deploy_escrow.js --network arcTestnet
npx hardhat run scripts/deploy_escrow.js --network avalancheFuji
npx hardhat run scripts/deploy_escrow.js --network baseSepolia
```
