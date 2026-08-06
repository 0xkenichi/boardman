# ClawStation Contracts

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

### Boardman V1 wallets (product)

| Role | Address |
|------|---------|
| Ops / fee / resolver | `0xFA931C535C9d10A324Ea7417a63ed22dD9b0cb2E` |
| Escrow contract | _pending deploy_ |

See `contracts/deployments/boardman_v1_wallets.json` and `docs/BOARDMAN_V1_WALLETS.md`.
- **Platform Fee:** 7% (`FEE_BPS = 700`)
- **Max Stake:** $10,000 USDC per match

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
