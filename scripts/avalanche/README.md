# Avalanche Fuji: deploy and prove the loop

These scripts deploy Boardman's v2 contracts to Avalanche Fuji and run one real
agent match through Boardman's own code: lock, play, settle. Everything is
testnet-only. The result is [`docs/avalanche/FUJI_PROOF.md`](../../docs/avalanche/FUJI_PROOF.md).

## 1. Wallets (once)

```bash
node scripts/avalanche/new_testnet_wallets.mjs
```

This writes `.fuji/wallets.json` (git-ignored, mode 0600). It holds four fresh
keys (`funder_deployer`, `owner`, `treasury`, `resolver`) and the secret that
seals the agents' keystore. Only addresses are printed. The deploy script
refuses to give one key two roles.

## 2. Testnet funds for `funder_deployer`

- **USDC:** <https://faucet.circle.com>, network *Avalanche Fuji*, 20 USDC a request.
- **AVAX:** <https://build.avax.network/console/primary-network/faucet>.
  It needs a Builder Hub sign-in. Today's Fuji base fee is about 10 wei, so
  0.05 AVAX covers many runs.

## 3. Deploy

```bash
scripts/avalanche/deploy_fuji.sh
```

This deploys `BoardmanEscrow` v2 and `SpectatorPool` v2 on chain 43113 with
the 24 h open timeout and 7 d lock timeout. It offers ownership to the `owner`
wallet and writes `contracts/deployments/boardman_v2_avalancheFuji.json`,
which includes the tx hashes. Verify on Snowtrace (Routescan, no API key):

```bash
cd contracts && npx hardhat verify --network avalancheFuji <escrow> <usdc> <treasury> <resolver> 86400 604800
```

## 4. Prove the loop

```bash
.venv/bin/python scripts/avalanche/fuji_proof.py
```

The proof run does these steps in order:

1. The owner accepts ownership of both contracts.
2. Gas goes to the owner, the resolver and the two demo agents (Raja and Nero).
3. Boardman's ops faucet (`onchain.fund_agent_from_key`) gives each agent its
   bankroll.
4. `MatchService.demo_raja_vs_nero` runs the match:
   - approve → `createMatch` with the resolver's EIP-712 permit
   - approve → `joinMatch`
   - a full chess game in the Stack engine
   - `resolveMatch` from the resolver

Arena data and agent keys live in `.fuji/arena/`, never in `data/`. The run
writes `docs/avalanche/fuji_proof_run.json` and `FUJI_PROOF.md`.

## Local rehearsal (no faucet needed)

```bash
cd contracts && HARDHAT_CHAIN_ID=43113 npx hardhat node &   # a local chain that reports Fuji's id
```

Then:

1. Deploy `MockUSDC` and mint to `funder_deployer`.
2. Run `deploy_fuji.sh` with `AVALANCHE_FUJI_RPC_URL=http://127.0.0.1:8545 USDC_ADDRESS=<mock>`.
3. Run `fuji_proof.py --rpc http://127.0.0.1:8545 --deployment <file> --data /tmp/arena`
   with `AVALANCHE_FUJI_USDC_ADDRESS=<mock>`.

Forking real Fuji (`hardhat node --fork`) also works but is slow through the
public RPC.
