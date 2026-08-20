# Boardman — Cardano Integration

CIP-0170 identity + CIP-0113 programmable tokens + USDM deposit rail on Cardano Preview testnet.

## Quick Start

```bash
# 1. Install dependencies
npm install

# 2. Get Blockfrost API key (free)
#    → https://blockfrost.io (select "Cardano Preview Testnet")

# 3. Get testnet tADA
#    → https://testnets.cardano.org/en/testnet/faucet/

# 4. Configure
cp .env.example .env
# Edit .env with your Blockfrost key and wallet mnemonic

# 5. Check wallet
node src/setup_wallet.js

# 6. Mint agent identity (dry run)
node src/mint_agent_identity.js --agent raja --dry-run

# 7. Deploy CIP-0113 token (dry run)
node src/deploy_cip113.js --type agent-token --dry-run

# 8. Run tests
BLOCKFROST_PROJECT_ID=test node src/test.js
```

## What This Does

| File | Purpose |
|------|---------|
| `src/config.js` | Load env vars |
| `src/blockfrost.js` | Blockfrost API helper |
| `src/wallet.js` | Key generation |
| `src/setup_wallet.js` | Wallet setup + balance check |
| `src/mint_agent_identity.js` | CIP-0170 agent identity minting |
| `src/deploy_cip113.js` | CIP-0113 programmable token deployment |
| `src/bridge_usdm.js` | USDM deposit rail design |

## Agent Identity (CIP-0170)

Each agent gets a unique NFT on Cardano containing:
- Agent name + type
- Registered game IDs
- Arc wallet address
- Rolling PNL digest
- Issuer attestation

Token name: `boardman_agent_{name}` (e.g., `boardman_agent_raja`)

## CIP-0113 Programmable Tokens

Three token types for Boardman:

| Token | Purpose | Transferable |
|-------|---------|-------------|
| Agent Identity | KYC-gated agent verification | Yes (KYC required) |
| LP Pool Share | Liquidity provider position | Yes (with hold period) |
| Spectator Receipt | Bet participation proof | No (soulbound) |

## USDM Bridge

```
Cardano USDM → Bridge → Arc USDC → Boardman Play Balance
```

Same pattern as existing Stellar/Avalanche rails. CIP-0113 compliance layer enforces KYC/AML on both sides.

## Catalyst Proposal

This integration qualifies for two Catalyst Pilot areas:
- **CIP-0170 On-chain Identity** — agent identity attestations
- **CIP-0113 Programmable Tokens** — compliance-gated tokens
- **Stablecoins** — USDM deposit rail

TRL: Existing product is TRL 6 (live on Arc testnet). Cardano integration starts at TRL 3-4 (proven patterns, new chain).
