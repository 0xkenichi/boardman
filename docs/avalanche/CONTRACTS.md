# Boardman contracts on Avalanche

Two contracts, both v2 ("safety release"). Source is in
[`contracts/contracts/core/`](../../contracts/contracts/core). They are built
with solc 0.8.20 (viaIR, optimizer 200, EVM paris) on OpenZeppelin 5.6.

| Contract | Fuji (43113) | C-Chain (43114) |
|----------|--------------|-----------------|
| `BoardmanEscrow` v2 | [`0xa0626A1744D4817B8b6fE0414a04CB20F6696F09`](https://testnet.snowtrace.io/address/0xa0626A1744D4817B8b6fE0414a04CB20F6696F09), source verified on Snowtrace and [Sourcify](https://repo.sourcify.dev/43113/0xa0626A1744D4817B8b6fE0414a04CB20F6696F09) (exact match) | not deployed (gated on the external audit and counsel) |
| `SpectatorPool` v2 | [`0x8D4cEb4A63f3Df00358F9075D24ccA4aDd1EdF6F`](https://testnet.snowtrace.io/address/0x8D4cEb4A63f3Df00358F9075D24ccA4aDd1EdF6F), source verified on Snowtrace and [Sourcify](https://repo.sourcify.dev/43113/0x8D4cEb4A63f3Df00358F9075D24ccA4aDd1EdF6F) (exact match) | never: spectator betting is testnet-only |
| USDC (Circle) | `0x5425890298aed601595a70AB815c96711a31Bc65` | `0xB97EF9Ef8734C71904D8002F8b6Bc66Dd9c48a6E` |

The deployment record is
[`contracts/deployments/boardman_v2_avalancheFuji.json`](../../contracts/deployments/boardman_v2_avalancheFuji.json):
roles, timeouts and deploy tx hashes. A live settled match is in
[FUJI_PROOF.md](./FUJI_PROOF.md).

## BoardmanEscrow: how a match moves

`OPEN → LOCKED (or DISPUTED) → RESOLVED or CANCELLED`, and only forward.

1. `createMatch(matchId, player2, stake, deadline, resolverSig)`. Player 1
   locks the stake. The resolver signs an EIP-712 permit
   (`CreateMatch(bytes32 matchId,address player1,address player2,uint256 stake,uint256 deadline)`,
   domain `BoardmanEscrow` / `2` / chainId / contract). The permit binds the
   opponent, so nobody can squat a match id or take the second seat.
2. `joinMatch(matchId)`. Only the bound player 2 can join, with the same stake.
3. `resolveMatch(matchId, winner)` pays the winner `2 × stake − fee`.
   `cancelMatch` refunds both players.
4. `refundExpired(matchId)` can be called by anyone:
   - An OPEN match older than `openTimeout` (24 h) refunds player 1.
   - A LOCKED match older than `lockTimeout` (7 d) refunds both players.

## What protects the money

| Risk | Guard |
|------|-------|
| Fees raised on money already locked, or set to 100% | Fees are capped in the bytecode: ≤ 10% (1000 bps), flat fee ≤ $0.50 per player. The fee is frozen per match at `createMatch`. |
| Resolver key lost or offline | `refundExpired` can be called by anyone after the timeout. Timeouts are immutable constructor parameters with bounds. |
| A USDC-blacklisted winner blocks settlement | A failed payout becomes `owed[player]` (`PayoutDeferred`), paid out later with `withdraw()`. Fees accrue in the contract and `withdrawFees()` sends them to the treasury. |
| One key controls everything | Owner (Ownable2Step, renounce disabled), treasury and resolver are separate keys. The deploy script refuses to give two roles to one address. The owner cannot move escrowed funds. |
| Pause used to trap funds | Pause blocks only money coming in (`createMatch`, `joinMatch`). Resolve, cancel, refund, withdraw and fee withdrawal always work. |
| Deploying to the wrong chain | `deploy_v2.js` checks the RPC chain id against the network (43113 / 43114). It also checks that USDC has 6 decimals and that the resolver is an EOA. |

**Invariant:**
`usdc.balanceOf(escrow) ≥ totalLocked + accruedFees + totalOwed`, with equality
unless someone sends USDC to the contract directly. Every match settles
`payout + fee == 2 × stake` with `fee ≤ pot / 4`.

## SpectatorPool (Fuji only)

A parimutuel book per match, with deposits on side A, side B or draw:

- `openBook(..., potCap, closeAt)` sets a betting deadline of at most 7 days.
- Deposits revert from `closeAt` on.
- `resolve` needs the book closed or past `closeAt`.
- Anyone can call `refundExpired` after `closeAt + refundGrace` (7 d) if the
  resolver never settles.
- Unclaimed winnings can only be swept after `claimWindow` (180 d), one book
  at a time.

`deploy_v2.js` refuses to deploy a SpectatorPool to any mainnet, with no
override.

## Trust assumptions (said plainly)

- **The resolver decides results.** A compromised resolver could pick the
  wrong winner or cancel matches within the timeout windows. It cannot pay
  itself unless it is a player. Results are refereed off-chain by Boardman's
  game engine. Moves are logged, but outcomes are not proven on-chain.
- **The owner** can set fees within the caps (future matches only), rotate
  the resolver and treasury, pause new money, and sweep expired pool books.
- **The token** is standard 6-decimal USDC: no fee-on-transfer, no rebasing,
  no callbacks.

## Internal audit

An internal pre-mainnet review of both v2 contracts and the backend code that
signs for them was completed on 20 Oct 2026. It is not a substitute for the
external audit funded in milestone M2.

- **Result:** 0 Critical, 1 High, 1 Medium, 7 Low, 8 Info. The High and the
  Medium were in the backend, and both are fixed. No contract code change was
  needed.
- **Coverage:** every finding and every refuted attack class has a
  proof-of-concept test: `contracts/test/Audit.2026-10.js`,
  `contracts/test/Audit.2026-10.delta.js` and
  `tests/test_audit_contracts_backend.py`. Model-based random runs drain both
  contracts to exactly zero.
- **Tests:** the contracts have 153 Hardhat tests (`cd contracts && npx hardhat test`).

The report lists what the external audit (M2) should focus on:
- **Permit design:** bind the fee into the permit, and add a nonce or a way
  to revoke a permit that is still live.
- **Resolver blast radius:** what a compromised resolver can do with the pool's `depositFor` and `resolve`.
- **Late bets:** an on-chain cut-off for pool deposits once a result is known.
- **Formal checks:** run the invariants under Echidna, Medusa or Certora,
  especially the pool's accounting across draw, seed and refund books.
- **USDC behaviour:** measure how Circle USDC transfers fail for blocklisted
  addresses on the target chain, which is C-Chain for this build.
- **Stake cap:** reconcile the off-chain and on-chain caps, and decide whether
  raising the cap needs a timelock.

## Deploy and verify

```bash
node scripts/avalanche/new_testnet_wallets.mjs   # testnet-only role keys, git-ignored
scripts/avalanche/deploy_fuji.sh                 # BoardmanEscrow v2 + SpectatorPool v2 on Fuji
cd contracts && npx hardhat verify --network avalancheFuji <escrow> <usdc> <treasury> <resolver> 86400 604800
```

For C-Chain mainnet (after M2 and M3):

```bash
CONFIRM_V2_DEPLOY=1 npm run deploy:v2:avalanche-mainnet
```

The mainnet deploy uses escrow only, a Safe owner, a $25 stake cap, and a
throwaway deployer key that holds none of the roles.
