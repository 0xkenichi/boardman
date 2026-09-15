# Boardman — Cross-Chain Identity Layer

Agent identity attestations and programmable tokens for the Boardman platform.

## Current Status

**Design phase.** This directory contains exploratory code for cross-chain identity and compliance layers. Nothing here is production-ready.

## Architecture

```
Agent Identity NFT → On-chain attestation → Verifiable by any chain
Compliance Token    → Transfer rules       → KYC/AML enforcement
Stablecoin Bridge   → Deposit rail         → Cross-chain play balance
```

## What's Here

| File | Purpose | Status |
|------|---------|--------|
| `src/config.js` | Environment variable loader | Working |
| `src/blockfrost.js` | Blockfrost API helper | Working |
| `src/wallet.js` | Key derivation (CIP-1852) | Working |
| `src/setup_wallet.js` | Wallet setup + balance check | Working |
| `src/mint_agent_identity.js` | Agent identity minting | Prototype |
| `src/deploy_cip113.js` | Programmable token deployment | Design |
| `src/bridge_usdm.js` | Stablecoin bridge design | Design only |

## Quick Start

```bash
npm install
cp .env.example .env
# Add your Blockfrost API key and wallet mnemonic to .env
node src/setup_wallet.js
```

## What Needs Doing

- [ ] Implement actual CIP-0170 compliant metadata (currently uses label 674, needs label 170)
- [ ] Build working CIP-0113 validator with lifecycle rules
- [ ] Design and implement stablecoin bridge contract
- [ ] KERI/AID identity lifecycle integration
- [ ] Integration with Boardman's core engine (currently Solidity/Arc)

## Note

This is exploratory work. The core Boardman platform runs on Avalanche Arc testnet. This directory explores how identity and compliance could extend to other chains.
