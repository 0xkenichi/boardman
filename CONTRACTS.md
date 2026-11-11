# Boardman contracts

Boardman settles on Avalanche C-Chain. Two contracts do the money work, both
at interface version 2 (the "v2 safety release"):

- `BoardmanEscrow` locks both players' USDC stakes and pays the winner.
- `SpectatorPool` runs a parimutuel book per match. It is testnet-only.

Source: `contracts/contracts/core/BoardmanEscrow.sol` and
`contracts/contracts/core/SpectatorPool.sol`. They are built with solc 0.8.20
(viaIR, optimizer 200, EVM paris) on OpenZeppelin 5.6. "v2" is the interface
version (`ESCROW_VERSION() == 2`, `POOL_VERSION() == 2`).

A shorter summary for reviewers is in
[docs/avalanche/CONTRACTS.md](docs/avalanche/CONTRACTS.md).

## Avalanche Fuji (chain ID `43113`): live

| Contract | Address |
|----------|---------|
| `BoardmanEscrow` v2 | [`0xa0626A1744D4817B8b6fE0414a04CB20F6696F09`](https://testnet.snowtrace.io/address/0xa0626A1744D4817B8b6fE0414a04CB20F6696F09) (source verified on Snowtrace and [Sourcify](https://repo.sourcify.dev/43113/0xa0626A1744D4817B8b6fE0414a04CB20F6696F09), exact match) |
| `SpectatorPool` v2 | [`0x8D4cEb4A63f3Df00358F9075D24ccA4aDd1EdF6F`](https://testnet.snowtrace.io/address/0x8D4cEb4A63f3Df00358F9075D24ccA4aDd1EdF6F) (source verified on Snowtrace and [Sourcify](https://repo.sourcify.dev/43113/0x8D4cEb4A63f3Df00358F9075D24ccA4aDd1EdF6F), exact match) |
| USDC (Circle, Fuji) | `0x5425890298aed601595a70AB815c96711a31Bc65` (6 decimals) |

- **Gas** is paid in AVAX. Stakes are Circle USDC. The platform gas tank
  (`src/backend/services/gas_tank.py`) tops up custodial play wallets with
  AVAX when they run low (`config/chains.yaml`: below 0.01 AVAX, top up 0.05).
- **Record:** [`contracts/deployments/boardman_v2_avalancheFuji.json`](contracts/deployments/boardman_v2_avalancheFuji.json)
  has the roles, the timeouts (open 24 h, lock 7 d, refundGrace 7 d,
  claimWindow 180 d) and the deploy tx hashes. The per-player stake cap on
  Fuji is the contract maximum, $10,000.
- **Roles:** four separate testnet-only keys: a throwaway deployer, the owner
  (an EOA, deployed with `V2_OWNER_IS_EOA=1`), the treasury and the resolver.
  The owner accepted ownership of both contracts on-chain.
- **Live proof:** a real agent match locked, played and settled on Fuji:
  [docs/avalanche/FUJI_PROOF.md](docs/avalanche/FUJI_PROOF.md).
- **Config:** the `avalanche` row of `config/chains.yaml` (Circle W3S
  blockchain `AVAX-FUJI`, CCTP domain 1, explorer
  `https://testnet.snowtrace.io`).

Deploy and verify (testnet keys only):

```bash
node scripts/avalanche/new_testnet_wallets.mjs   # role keys in .fuji/wallets.json, git-ignored
scripts/avalanche/deploy_fuji.sh                 # runs deploy_v2.js on avalancheFuji
cd contracts && npx hardhat verify --network avalancheFuji <escrow> <usdc> <treasury> <resolver> 86400 604800
```

`deploy_fuji.sh` runs the same command as `npm run deploy:v2:fuji`
(`hardhat run scripts/deploy_v2.js --network avalancheFuji`), with the role
addresses from `.fuji/wallets.json`. Verification goes through Routescan, the Snowtrace API,
and needs no API key. Both contracts are also verified on Sourcify (exact
match: creation and runtime bytecode, including the metadata hash). Step by step: [scripts/avalanche/README.md](scripts/avalanche/README.md).

Backend env (`.env.avalanche.example`):

```
BOARDMAN_ARENA_CHAIN=avalanche
CLAW_DEFAULT_CHAIN=avalanche
CLAW_ENABLED_CHAINS=avalanche
# chains.yaml already has the addresses; set these only to override:
# CLAW_ESCROW_ADDRESS_AVALANCHE=0x...
# SPECTATOR_ESCROW_ADDRESS_AVALANCHE=0x...
# AVALANCHE_FUJI_RPC_URL=https://api.avax-test.network/ext/bc/C/rpc
```

## Avalanche C-Chain mainnet (chain ID `43114`): not deployed

Real-money play waits for two gates: an external audit of `BoardmanEscrow` v2
and a legal opinion from Nigerian counsel. Nothing is deployed on C-Chain
mainnet.

- USDC: Circle `0xB97EF9Ef8734C71904D8002F8b6Bc66Dd9c48a6E`. RPC
  `https://api.avax.network/ext/bc/C/rpc`. Explorer `https://snowtrace.io`.
  Circle W3S blockchain `AVAX`. CCTP domain 1. Gas in AVAX.
- Config row `avalanche_mainnet` (`status: prep`, `network: mainnet`). It is
  the humans realm's chain (`BOARDMAN_HUMANS_CHAIN`). Real money also needs
  `REAL_MONEY_ENABLED=1`.
- The plan: `BoardmanEscrow` v2 only (never a `SpectatorPool`), a Safe as
  owner, a $25 per-player stake cap, and a throwaway `MAINNET_DEPLOYER_KEY`
  that holds none of the roles.

```bash
cd contracts
CONFIRM_V2_DEPLOY=1 V2_OWNER_MULTISIG=<Safe> V2_TREASURY=<treasury> V2_RESOLVER=<resolver> \
  npm run deploy:v2:avalanche-mainnet
```

Then, after the Safe calls `acceptOwnership()`, set
`BOARDMAN_ESCROW_ADDRESS_AVALANCHE_MAINNET`. The full runbook is
[docs/MAINNET_HUMANS_CUTOVER.md](docs/MAINNET_HUMANS_CUTOVER.md).

## v2 safety design

### What changed from v1, and why

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

### Fees and limits

- **Escrow platform fee** (tiered by per-player stake, frozen per match at
  `createMatch`): under $5 a flat $0.50 per player; $5 to $500 7%
  (`FEE_BPS = 700`); above $500 10% (`PREMIUM_FEE_BPS = 1000`). The owner can
  retune the tiers with `setFeeTiers`, inside the caps above. Quote with
  `quotePlatformFee(stakePerPlayer)`.
- **Stakes:** $2 minimum per player (`MIN_STAKE`), $10,000 maximum
  (`MAX_STAKE`). The owner can set a per-player cap between the two with
  `setMaxStake` (`maxStakePerPlayer`); a mainnet deploy sets it to $25.
- **SpectatorPool fee** (by pot): under $10, min($1, 25% of the pot); up to
  $1,000, 7%; above, 10%. Owner-tunable via `setSpectatorFeeTiers`, inside
  the caps.

### ABI notes for integrators

`deposit(bytes32,uint256,uint8)` is unchanged. `matches(bytes32)` on the
escrow keeps the v1 six-field tuple. `getBook` keeps positions 0..23 and
appends `closeAt, settledAt, feeScheduleId, swept, remaining`. All v1 events
are unchanged, and new ones were added. The breaking changes are
`createMatch`, the `openBook` signature, both constructors, and the owner
losing resolver powers.

The Python operators (`src/stack/agentic/onchain.py`, `spectator_onchain.py`)
detect v1 or v2 through `ESCROW_VERSION()` / `POOL_VERSION()`, which can be
overridden with `BOARDMAN_ESCROW_VERSION` / `SPECTATOR_POOL_VERSION`. The
human (Circle) path in `src/backend/services/clawstation_escrow.py` uses the
v2 `createMatch` with a resolver permit whenever the chain's `escrow_version`
in `chains.yaml` is 2, as it is for `avalanche` and `avalanche_mainnet`. The
on-chain betting window is `SPECTATOR_BOOK_WINDOW_SECONDS` (default 900).

### Deploy (human only)

`contracts/scripts/deploy_v2.js` documents every constructor param. It needs
`V2_OWNER_MULTISIG`, `V2_TREASURY`, `V2_RESOLVER` and `CONFIRM_V2_DEPLOY=1`,
and must run from a throwaway deployer key. Defaults: `openTimeout` 24h,
`lockTimeout` 7d, `refundGrace` 7d, `claimWindow` 180d. It writes
`deployments/boardman_v2_<network>.json` and offers ownership to the
multisig. The multisig must call `acceptOwnership()` on every contract deployed.

Before deploying, on every non-local network, the script checks:
- the RPC's chain id matches the network (43113 for `avalancheFuji`, 43114
  for `avalancheMainnet`)
- the USDC address is a contract with `decimals() == 6`
  (`scripts/lib/v2_preflight.js`)
- the owner Safe already has code on this chain (an EOA owner only with `V2_OWNER_IS_EOA=1`)
- the resolver is an EOA, because permits are plain ECDSA

Mainnets never get a SpectatorPool: spectator betting stays on testnet, and
the pool's `deposit()` is permissionless once a book is open. There is no
override. After the owner accepts ownership, run `scripts/check_v2_roles.js`
with `EXPECT_ACCEPTED=1`. On `avalancheMainnet`, pass `EXPECT_OWNER`,
`EXPECT_RESOLVER`, `EXPECT_TREASURY` and `EXPECT_USDC` yourself: the
role-check library (`scripts/lib/v2_roles.js`) only makes them mandatory, and
only knows the USDC address, for `arcMainnet` and `baseMainnet`.

Smoke-test locally with `npx hardhat run scripts/deploy_v2.js --network localhost`.

### Operating notes

1. Fuji was deployed straight to v2, so there is nothing to migrate there.
2. `close_book_onchain()` runs (async) at the ply-N book freeze
   (`matches.freeze_book`) and, since the October 2026 audit (H-01), as the
   first settlement step. `deposit_for` also refuses once the match or its
   off-chain book is frozen. A direct `deposit()` is still possible until
   `close()` lands or `closeAt` passes, so keep `SPECTATOR_BOOK_WINDOW_SECONDS` short.
3. `src/stack/agentic/fee_sweep.py` calls `withdrawFees()` on both contracts
   and `withdraw()` for agent creator wallets on the pool.
4. After any redeploy, update `config/chains.yaml`, this file and
   `docs/avalanche/` with the new addresses.

### Audit readiness

Internal audit, October 2026: [docs/security/AUDIT_2026-10_contracts.md](docs/security/AUDIT_2026-10_contracts.md)
(PoCs in `contracts/test/Audit.2026-10.js`, `contracts/test/Audit.2026-10.delta.js`,
`contracts/test/DeployPreflight.js` and `tests/test_audit_contracts_backend.py`).
That review targeted the same v2 source. The only contract change since was
a NatSpec move (finding D-05).

**Invariants** (each has a test in `contracts/test/*v2.js`, and the random property runs cover them too). On-chain monitors should check `>=` instead of `==`: USDC sent straight to a contract is outside the accounting.
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

Gaps: trivial views (`contractBalance`, `getMatchStatus`, `fanDepositOf`, `seedOf`), `unpause` on the escrow, and the v1 events, which were kept unchanged. Run `npx hardhat test` (all hardhat tests) and `REPORT_GAS=true npx hardhat test` for gas figures.

## Appendix: Other networks (configured, not offered in this build)

These rows stay in `config/chains.yaml` with `enabled: false` so the same
code can settle elsewhere. None is offered to players in this build.

| Network | Contract | Address | Notes |
|---------|----------|---------|-------|
| Arc Testnet (`5042002`) | BoardmanEscrow v1, tiered | `0xD382f627fB565eb96D9EFFb66B9119DD4a555847` | `contracts/deployments/boardman_v1_arcTestnet.json`. Earlier flat-fee v1: `0xD8984396f12Cd0BD3C3e120858dd7eCdEeEF66Fc`; v1 archive: `0x3cD57447490c81598Bd8CaCBe3843b24E5735A77` |
| Arc Testnet (`5042002`) | SpectatorPool v1, tiered | `0xd45bE49456021B74D2712fcffD47f17f91D39664` | `contracts/deployments/spectator_pool_arcTestnet.json`. Earlier flat-fee pool: `0x7Dcd347fA916bF93Ad8BF3c1c8e9D17111B5313e` |
| Arc Testnet (`5042002`) | ClawEscrow (V0 archive) | `0xFC44a06295d4fC58420027932A6FcB3C13D83859` | USDC `0x3600000000000000000000000000000000000000` |
| Arc Mainnet (`5042`) | BoardmanEscrow v2 | not deployed | `npm run deploy:v2:arc-mainnet`; env `BOARDMAN_ESCROW_ADDRESS_ARC_MAINNET` |
| Avalanche Fuji (`43113`) | ClawEscrow (V0 archive) | `0xFC44a06295d4fC58420027932A6FcB3C13D83859` | Superseded by v2 above; keys not held. Same address as on Arc Testnet (same deployer nonce) |
| Base Sepolia (`84532`) | ClawEscrow (V0) | `0xDb76714390ccE1729558DF3c9EC4f45A1690dE78` | USDC `0x036CbD53842c5426634e7929541eC2318f3dCF7e`. Legacy, internal only |

- The Arc Testnet v1 contracts use one key, `0xFA931C535C9d10A324Ea7417a63ed22dD9b0cb2E`,
  as deployer, fee recipient and resolver. v2 exists to end that.
- V0 (legacy Rematch testnet) roles: deployer `0xB2CCcac46cE93C2ac27fDBF7248938CC57F29424`;
  fee recipient and resolver `0x39EcF94ed35451A67006dcCE4A467aecdfAB6940`.
- Env overrides: `CLAW_ESCROW_ADDRESS_ARC`, `CLAW_ESCROW_ADDRESS_BASE_SEPOLIA`
  (or `CSC_ADDRESS`). V0 contracts came from `contracts/scripts/deploy_escrow.js`.
