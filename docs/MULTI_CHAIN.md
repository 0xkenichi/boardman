# Multi-chain (Base / Arc / Avalanche)

## Same address, separate balances

Your Circle deposit **address is the same** across networks.
USDC on Base ≠ USDC on Arc ≠ USDC on Avalanche.

| Network | Gas | Escrow | Best for |
|---------|-----|--------|----------|
| **Arc Testnet** | **USDC** (native) | deployed | No test ETH |
| Base Sepolia | ETH | deployed | Legacy / ETH faucet |
| Avalanche Fuji | AVAX | deployed | AVAX faucet |

## Bot: Switch network

Main menu → **Switch network** → pick Arc / Base / Avalanche.

- Sets `gaming_preferred_chain`
- New challenges default to that network
- Wallet shows USDC **per chain** + which is active

## Testing on Arc

1. Switch network → **Arc Testnet**
2. Fund deposit address with Arc testnet USDC ([Circle faucet](https://faucet.circle.com/) → Arc Testnet)
3. New challenge → pick **Arc** (or leave as preferred)
4. Accept → Lock stake (gas paid in USDC)
5. Side → play → submit photo `5-3`

## Env

```
CLAW_ESCROW_ADDRESS_ARC=0xFC44a06295d4fC58420027932A6FcB3C13D83859
CLAW_ESCROW_ADDRESS_BASE_SEPOLIA=0xDb76714390ccE1729558DF3c9EC4f45A1690dE78
CLAW_ESCROW_ADDRESS_AVALANCHE=0xFC44a06295d4fC58420027932A6FcB3C13D83859
CLAW_DEFAULT_CHAIN=arc
```

## SQL

`052_preferred_chain.sql` — preferred chain + circle wallet map.

## Circle note

Contract calls need a Circle wallet id that can sign on that blockchain.
We create/store per-chain ids in `gaming_circle_wallets` when possible; fall back to primary EOA.
