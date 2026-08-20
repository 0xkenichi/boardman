#!/usr/bin/env node
/**
 * Setup and verify Cardano testnet wallet.
 *
 * Usage:
 *   1. node src/setup_wallet.js           — show address + balance
 *   2. node src/setup_wallet.js --generate — generate new mnemonic
 *
 * Before running:
 *   - Copy .env.example → .env
 *   - Add your Blockfrost API key
 *   - If generating: add the mnemonic back to .env
 *   - Fund the address from https://testnets.cardano.org/en/testnet/faucet/
 */
import { WALLET_MNEMONIC, FEE_RECIPIENT_ADDRESS, NETWORK } from "./config.js";
import { getAddressBalance, getLatestBlock } from "./blockfrost.js";
import { generateMnemonic } from "./wallet.js";

const cmd = process.argv[2];

if (cmd === "--generate") {
  console.log("🔑 Generating new mnemonic...\n");
  const mnemonic = generateMnemonic();
  console.log("Mnemonic (save this securely!):");
  console.log(`\n  ${mnemonic}\n`);
  console.log("Add to .env:");
  console.log(`  WALLET_MNEMONIC=${mnemonic}`);
  process.exit(0);
}

async function main() {
  console.log(`\n🌐 Cardano ${NETWORK} testnet\n`);

  // Check chain health
  try {
    const latest = await getLatestBlock();
    console.log(`  Latest block: #${latest.block}`);
    console.log(`  Slot: ${latest.slot}`);
    console.log(`  Hash: ${latest.hash.slice(0, 16)}...`);
  } catch (e) {
    console.error(`  ❌ Cannot reach Blockfrost: ${e.message}`);
    console.error("  Check your BLOCKFROST_PROJECT_ID in .env");
    process.exit(1);
  }

  if (!WALLET_MNEMONIC) {
    console.log("\n⚠️  No WALLET_MNEMONIC set in .env");
    console.log("   Run: node src/setup_wallet.js --generate");
    console.log("   Or add an existing mnemonic to .env\n");
    return;
  }

  // Derive address from mnemonic
  // For now, we need the address to be set manually or derived properly
  // The Blockfrost API works with addresses, not mnemonics directly
  console.log("\n📋 Wallet status:");
  console.log(`  Mnemonic: ${WALLET_MNEMONIC.slice(0, 12)}...`);
  console.log(`  Network: ${NETWORK}`);

  if (FEE_RECIPIENT_ADDRESS) {
    try {
      const balance = await getAddressBalance(FEE_RECIPIENT_ADDRESS);
      console.log(`\n💰 Fee recipient balance:`);
      console.log(`  Address: ${FEE_RECIPIENT_ADDRESS}`);
      for (const utxo of balance) {
        console.log(`  ${utxo.unit}: ${(Number(utxo.quantity) / 1_000_000).toFixed(2)} ADA`);
      }
    } catch (e) {
      console.log(`  ⚠️  Could not fetch balance: ${e.message}`);
    }
  }

  console.log("\n✅ Wallet check complete\n");
}

main().catch(console.error);
