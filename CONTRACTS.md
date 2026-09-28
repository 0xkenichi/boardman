# ClawStation Contracts

## Arc Mainnet (chain ID `5042` — live Sept 16 2026)

- Native USDC ERC-20 facade predeploy: `0x3600000000000000000000000000000000000000` (same as testnet, 6 decimals)
- RPC: `https://rpc.mainnet.arc.io` · Explorer: `https://explorer.arc.io`
- Gas token: USDC (native gas accounting, sub-second finality)
- BoardmanEscrow: **not deployed yet** — `npm run deploy:boardman:arc-mainnet` (needs `ADMIN_PRIVATE_KEY` with mainnet USDC for gas)
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
