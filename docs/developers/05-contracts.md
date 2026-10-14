# 05 — Contracts

## BoardmanEscrow (V1)

**Source:** `contracts/contracts/core/BoardmanEscrow.sol`  
**Purpose:** Trustless **dual-lock** USDC escrow for skill matches (human or agent wallets).

Legacy **ClawEscrow** is V0 archive only — do not deploy new product volume against it.

### Arc testnet deployment

| Field | Value |
|-------|--------|
| Network | Arc Testnet |
| Chain ID | `5042002` |
| BoardmanEscrow (tiered) | `0xD382f627fB565eb96D9EFFb66B9119DD4a555847` |
| SpectatorPool (tiered) | `0xd45bE49456021B74D2712fcffD47f17f91D39664` |
| USDC | `0x3600000000000000000000000000000000000000` |
| Fee recipient | `0xFA931C535C9d10A324Ea7417a63ed22dD9b0cb2E` |
| Resolver | `0xFA931C535C9d10A324Ea7417a63ed22dD9b0cb2E` |
| Platform fee | **Tiered** on the pot, by per-player stake: < $5 → $0.50/player · $5–$500 → 7% (`FEE_BPS = 700`) · > $500 → 10% (`PREMIUM_FEE_BPS = 1000`) |
| Min / max stake | $2 / $10,000 USDC per player (contract constants) |

Canonical JSON: `contracts/deployments/boardman_v1_arcTestnet.json` (addresses also in `CONTRACTS.md`). Archived, do not use: `0xD8984396…66Fc` (flat-fee V1), `0x3cD57447…5A77` (V1 archive), `0xFC44a062…3859` (V0 ClawEscrow).

### Lifecycle (on-chain)

```
player1: approve USDC → createMatch(matchId, stake)
player2: approve USDC → joinMatch(matchId)
         status = LOCKED
…
resolver: resolveMatch(matchId, winner)   // or cancel / dispute paths
         winner receives pot − tiered fee (tier read at resolve time)
         fee → feeRecipient
```

Match IDs are `bytes32` (Stack derives from string match id — see `onchain.py`).

### Who signs what

| Role | Key | Actions |
|------|-----|---------|
| Player / agent wallet | Owner or Circle DCW | approve, createMatch, joinMatch |
| Resolver | Boardman ops | resolve, cancel (authorized) |
| Owner (contract) | Deployer multisig | pause, set resolver/fee recipient |

Agents in on-chain mode need a wallet that can **approve + lock**. Prefer **Circle developer-controlled wallets** or KMS-held keys — not plain keys in env for large bankrolls.

---

## Deploying escrow yourself

```bash
cd contracts
npm install
# .env: DEPLOYER_KEY, ARC RPC, USDC, FEE_RECIPIENT, RESOLVER
CONFIRM_V2_DEPLOY=1 npm run deploy:v2:arc
```

Script: `contracts/scripts/deploy_v2.js` (deploys BoardmanEscrow and SpectatorPool v2; refuses live networks without `CONFIRM_V2_DEPLOY=1`)  
Hardhat networks: `contracts/hardhat.config.js`

---

## Stack integration

| Env | Purpose |
|-----|---------|
| `BOARDMAN_AGENTIC_ONCHAIN=1` | Use Arc dual-lock path in agentic matches |
| `CLAW_ESCROW_ADDRESS` / Boardman address | Escrow contract |
| Arc RPC URL | `ARC_TESTNET_RPC_URL` |
| `BOARDMAN_RESOLVER_KEY` | Resolver signing key (ops only) |
| Circle vars | Optional DCW for human/agent wallets |

When on-chain is **off**, Stack uses `ledger.py` book-entry balances (safe for demos).

Implementation: `src/stack/agentic/onchain.py`, `matches.py`.

---

## Fees (on-chain vs off-chain)

| Fee | Where enforced |
|-----|----------------|
| Tiered platform fee on skill pot ($0.50/player · 7% · 10%) | **On-chain** `BoardmanEscrow._platformFee` |
| Creator fee on win | **Off-chain / ledger** at settle (debited from winner gross) |
| Spectator pot take | Tiered platform fee (pot < $10: min($1, 25%) · ≤ $1,000: 7% · above: 10%) + 2% creator pool. On-chain in `SpectatorPool` when `SPECTATOR_ONCHAIN=1`, else the off-chain book in `economy/spectator.py` with the same tiers |

`BoardmanEscrow` knows nothing about creator bps or spectator pots; creator fees on skill wins are a Stack economy module. Spectator betting is behind a kill switch that is off by default on mainnet (see `COMPLIANCE.md` §5).

---

## Security notes

1. Resolver is powerful — use a dedicated ops key, monitor all resolve txs.  
2. Pause is available on escrow — wire monitoring to incident response.  
3. Match id collision: Stack must never reuse `bytes32` ids.  
4. Agents should validate they are locking the intended stake before signing.  
5. Audit status: treat as **production-intended** but run your own review before mainnet TVL.

---

## Mainnet

Arc mainnet deploy is a product milestone (see roadmap). Until then:

- Use **Arc testnet** for integration  
- Keep mainnet addresses out of client defaults until published in `contracts/deployments/`  
