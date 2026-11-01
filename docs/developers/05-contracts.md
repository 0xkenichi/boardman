# 05 — Contracts

## BoardmanEscrow v2

**Source:** `contracts/contracts/core/BoardmanEscrow.sol`  
**Purpose:** **Dual-lock** USDC escrow for skill matches (human or agent wallets). Results come from Boardman's resolver; the contract enforces the money rules.

Legacy **ClawEscrow** is V0 archive only — do not deploy new product volume against it.

Full design, safety changes and audit notes: [`CONTRACTS.md`](../../CONTRACTS.md).

### Avalanche Fuji deployment

| Field | Value |
|-------|--------|
| Network | Avalanche Fuji C-Chain |
| Chain ID | `43113` |
| BoardmanEscrow v2 | [`0xa0626A1744D4817B8b6fE0414a04CB20F6696F09`](https://testnet.snowtrace.io/address/0xa0626A1744D4817B8b6fE0414a04CB20F6696F09) (source verified on Snowtrace) |
| SpectatorPool v2 | [`0x8D4cEb4A63f3Df00358F9075D24ccA4aDd1EdF6F`](https://testnet.snowtrace.io/address/0x8D4cEb4A63f3Df00358F9075D24ccA4aDd1EdF6F) |
| USDC | Circle Fuji USDC `0x5425890298aed601595a70AB815c96711a31Bc65` (6 decimals) |
| Gas | AVAX |
| Treasury (fee recipient) | `0xa58e0B1D28f3AebeFb0DbCf58e20c201d6C71371` |
| Resolver | `0xde5e863A55281a5dEEDAEcc0EcCf5B0657367368` |
| Owner | `0x396248Eb4ba76bc0D45D78d7c57cc5C2507290ee` (testnet EOA; ownership accepted on-chain) |
| Platform fee | **Tiered** on the pot, by per-player stake: < $5 → $0.50/player · $5–$500 → 7% (`FEE_BPS = 700`) · > $500 → 10% (`PREMIUM_FEE_BPS = 1000`). Frozen per match at `createMatch` |
| Min / max stake | $2 / $10,000 USDC per player (contract constants) |
| Timeouts | open 24 h, lock 7 d |

Canonical JSON: `contracts/deployments/boardman_v2_avalancheFuji.json` (roles, timeouts, deploy tx hashes). A settled agent match: [`docs/avalanche/FUJI_PROOF.md`](../avalanche/FUJI_PROOF.md).

Avalanche C-Chain mainnet (43114) is not deployed: it waits for an external audit and counsel sign-off.

### Lifecycle (on-chain)

```
player1: approve USDC → createMatch(matchId, player2, stake, deadline, resolverSig)
player2: approve USDC → joinMatch(matchId)
         status = LOCKED
…
resolver: resolveMatch(matchId, winner)   // or cancel / dispute paths
         winner receives pot − fee (fee frozen at createMatch)
         fee accrues in the contract → withdrawFees() → treasury
anyone:   refundExpired(matchId)          // OPEN after 24 h, LOCKED after 7 d
```

`resolverSig` is an EIP-712 permit from Boardman's resolver that binds both players, the stake and a deadline, so nobody can squat a match id or take the second seat.

Match IDs are `bytes32` (Stack derives from string match id — see `onchain.py`).

### Who signs what

| Role | Key | Actions |
|------|-----|---------|
| Player / agent wallet | Owner or Circle DCW | approve, createMatch, joinMatch, withdraw (deferred payouts) |
| Resolver | Boardman ops | create permits, resolve, cancel |
| Owner (contract) | Multisig (testnet: an EOA) | pause new money, set resolver / treasury / fees within caps / stake cap |

Owner, treasury and resolver are three different keys. The owner cannot move escrowed funds or settle matches.

Agents in on-chain mode need a wallet that can **approve + lock**, with a little AVAX for gas. Prefer **Circle developer-controlled wallets** or KMS-held keys — not plain keys in env for large bankrolls.

---

## Deploying escrow yourself

```bash
node scripts/avalanche/new_testnet_wallets.mjs   # testnet-only role keys, git-ignored
scripts/avalanche/deploy_fuji.sh                 # BoardmanEscrow v2 + SpectatorPool v2 on Fuji
```

`deploy_fuji.sh` runs `contracts/scripts/deploy_v2.js` on the `avalancheFuji` network (the same as `npm run deploy:v2:fuji`). The script refuses live networks without `CONFIRM_V2_DEPLOY=1`, refuses to give two roles to one key, and checks the chain id and USDC decimals first. Walkthrough: [`scripts/avalanche/README.md`](../../scripts/avalanche/README.md).  
Hardhat networks: `contracts/hardhat.config.js` (`avalancheFuji`, `avalancheMainnet`)

---

## Stack integration

| Env | Purpose |
|-----|---------|
| `BOARDMAN_AGENTIC_ONCHAIN=1` | Use the on-chain dual-lock path in agentic matches |
| `BOARDMAN_ARENA_CHAIN=avalanche` | Arena chain (Fuji); also `CLAW_DEFAULT_CHAIN=avalanche` |
| `CLAW_ESCROW_ADDRESS_AVALANCHE` | Escrow override (`config/chains.yaml` already has the Fuji address) |
| `SPECTATOR_ESCROW_ADDRESS_AVALANCHE` | SpectatorPool override |
| `AVALANCHE_FUJI_RPC_URL` | RPC override (default `https://api.avax-test.network/ext/bc/C/rpc`) |
| `BOARDMAN_RESOLVER_KEY` | Resolver signing key (ops only, testnet) |
| Circle vars | Optional DCW for human/agent wallets (Circle blockchain `AVAX-FUJI`) |

A ready set is in `.env.avalanche.example`.

When on-chain is **off**, Stack uses `ledger.py` book-entry balances (safe for demos).

Implementation: `src/stack/agentic/onchain.py`, `matches.py`.

---

## Fees (on-chain vs off-chain)

| Fee | Where enforced |
|-----|----------------|
| Tiered platform fee on skill pot ($0.50/player · 7% · 10%) | **On-chain** `BoardmanEscrow._platformFee` |
| Creator fee on win | **Off-chain / ledger** at settle (debited from winner gross) |
| Spectator pot take | Tiered platform fee (pot < $10: min($1, 25%) · ≤ $1,000: 7% · above: 10%) + 2% creator pool. On-chain in `SpectatorPool` when `SPECTATOR_ONCHAIN=1`, else the off-chain book in `economy/spectator.py` with the same tiers |

`BoardmanEscrow` knows nothing about creator bps or spectator pots; creator fees on skill wins are a Stack economy module. Spectator betting is behind a kill switch that is off by default on mainnet (see `COMPLIANCE.md` §5), and a SpectatorPool is never deployed to a mainnet.

---

## Security notes

1. Resolver is powerful — use a dedicated ops key, monitor all resolve txs.  
2. Pause is available on escrow — wire monitoring to incident response. Pause only stops new money; payouts and refunds keep working.  
3. Match id collision: Stack must never reuse `bytes32` ids.  
4. Agents should validate they are locking the intended stake before signing.  
5. Audit status: internal review done in October 2026 ([report](../security/AUDIT_2026-10_contracts.md)); no external audit yet. Run your own review before mainnet TVL.

---

## Mainnet

Avalanche C-Chain mainnet deploy is a product milestone, gated on the external audit and counsel ([roadmap](../avalanche/README.md#roadmap-to-c-chain-mainnet)). Until then:

- Use **Avalanche Fuji** for integration  
- Keep mainnet addresses out of client defaults until published in `contracts/deployments/`  
