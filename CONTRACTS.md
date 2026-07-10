# ClawStation Contracts

## Base Sepolia

| Contract | Address | Deployed At |
|----------|---------|-------------|
| ClawEscrow | `0xDb76714390ccE1729558DF3c9EC4f45A1690dE78` | 2026-07-07 |

## Configuration

- **Network:** Base Sepolia (`chainId: 84532`)
- **USDC:** `0x036CbD53842c5426634e7929541eC2318f3dCF7e`
- **Fee Recipient:** `0x39EcF94ed35451A67006dcCE4A467aecdfAB6940`
- **Resolver:** `0x118d994c999923de4665Ca1A31e73A7872beAd56`
- **Platform Fee:** 7% (`FEE_BPS = 700`)
- **Max Stake:** $10,000 USDC per match

## Notes

- Re-deployed with `FEE_BPS` bumped from 300 (3%) to 700 (7%) per the ClawStation Foundation plan.
- The contract is owned by the deployer; ownership can be transferred to a multi-sig or governance contract before mainnet launch.
- Verification on BaseScan was attempted but failed due to the deprecated Etherscan v1 API endpoint in the current Hardhat config. Retry verification manually or migrate the config to Etherscan v2.
