#!/usr/bin/env bash
# Deploy BoardmanEscrow v2 + SpectatorPool v2 to Avalanche Fuji with the
# testnet-only role wallets in .fuji/wallets.json (scripts/avalanche/new_testnet_wallets.mjs).
#
#   scripts/avalanche/deploy_fuji.sh                 # Fuji
#   AVALANCHE_FUJI_RPC_URL=http://127.0.0.1:8545 USDC_ADDRESS=0xMock scripts/avalanche/deploy_fuji.sh   # local rehearsal
#
# The funder_deployer wallet needs a little Fuji AVAX (Builder Hub faucet).
# Writes contracts/deployments/boardman_v2_avalancheFuji.json. Keys are passed
# to hardhat through the environment and never printed.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
W="${FUJI_WALLETS:-$ROOT/.fuji/wallets.json}"
[ -f "$W" ] || { echo "no $W: run node scripts/avalanche/new_testnet_wallets.mjs first" >&2; exit 1; }
field() { python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['wallets'][sys.argv[2]][sys.argv[3]])" "$W" "$1" "$2"; }

cd "$ROOT/contracts"
FUJI_DEPLOYER_KEY="$(field funder_deployer private_key)" \
CONFIRM_V2_DEPLOY=1 \
V2_OWNER_IS_EOA=1 \
V2_OWNER_MULTISIG="$(field owner address)" \
V2_TREASURY="$(field treasury address)" \
V2_RESOLVER="$(field resolver address)" \
  npx hardhat run scripts/deploy_v2.js --network avalancheFuji
