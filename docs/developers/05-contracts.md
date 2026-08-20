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
| BoardmanEscrow | `0xD8984396f12Cd0BD3C3e120858dd7eCdEeEF66Fc` |
| USDC | `0x3600000000000000000000000000000000000000` |
| Fee recipient | `0xFA931C535C9d10A324Ea7417a63ed22dD9b0cb2E` |
| Resolver | `0xFA931C535C9d10A324Ea7417a63ed22dD9b0cb2E` |
| Platform fee | **300 bps (3%)** of pot |
| Max stake | $10,000 USDC per side (contract constant) |

Canonical JSON: `contracts/deployments/boardman_v1_arcTestnet.json`

### Lifecycle (on-chain)

```
player1: approve USDC → createMatch(matchId, stake)
player2: approve USDC → joinMatch(matchId)
         status = LOCKED
…
resolver: resolveMatch(matchId, winner)   // or cancel / dispute paths
         winner receives pot − 3% fee
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
npm run deploy:boardman:arc
```

Scripts: `contracts/scripts/deploy_boardman_escrow.js`  
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
| 7% platform on skill pot | **On-chain** `FEE_BPS = 700` |
| Creator fee on win | **Off-chain / ledger** at settle (debited from winner gross) |
| Spectator pot take | **Off-chain book** (default 3% platform + 2% creators) |

Do not assume the smart contract knows about creator bps or spectator pots — those are Stack economy modules.

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
