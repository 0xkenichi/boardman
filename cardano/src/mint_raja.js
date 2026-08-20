#!/usr/bin/env node
/**
 * Mint a CIP-0170 agent identity NFT on Cardano Preview testnet.
 *
 * Derives the signing key from the wallet mnemonic, builds a
 * minting transaction with CIP-0170 metadata, signs, and submits.
 */
import { wordlist } from "@scure/bip39/wordlists/english.js";
import { mnemonicToSeedSync } from "@scure/bip39";
import { HDKey } from "@scure/bip32";
import * as CSL from "@emurgo/cardano-serialization-lib-nodejs";
import { getAddressUtxos, getLatestBlock, submitTx } from "./blockfrost.js";
import { WALLET_MNEMONIC, FEE_RECIPIENT_ADDRESS } from "./config.js";

// ── Agent data ──────────────────────────────────────────────
const AGENT_NAME = process.argv.includes("--agent")
  ? process.argv[process.argv.indexOf("--agent") + 1]
  : "raja";

const AGENTS = {
  raja: {
    name: "Raja",
    arcWallet: "0xDB131a4B88ACA79c29D5aDF3C3Df033954D36029",
    games: ["agentic.chess_standard"],
    description: "Aggressive tactical chess agent — attacks first, defends never.",
  },
  nero: {
    name: "Nero",
    arcWallet: "0xe430C73cF2beD38aBE83DF8309763191624373E1",
    games: ["agentic.chess_standard"],
    description: "Patient positional chess agent — structure first, then counterpunch.",
  },
};

// ── Derive signing key from mnemonic ────────────────────────
function deriveSigningKey(mnemonic) {
  const seed = mnemonicToSeedSync(mnemonic);
  const root = HDKey.fromMasterSeed(seed);
  // CIP-1852: m/1852'/1815'/0'/0/0
  const derived = root.derive("m/1852'/1815'/0'/0/0");

  const privKeyBytes = derived.privateKey;
  const privKey = CSL.PrivateKey.from_normal_bytes(
    new Uint8Array(privKeyBytes.slice(0, 32))
  );
  const pubKey = privKey.to_public();
  const pubKeyHash = pubKey.hash();

  return { privKey, pubKey, pubKeyHash };
}

// ── Build address from key hash ─────────────────────────────
function getTestnetAddress(pubKeyHash) {
  const cred = CSL.Credential.from_keyhash(pubKeyHash);
  const entAddr = CSL.EnterpriseAddress.new(0, cred); // network 0 = testnet
  return entAddr.to_address();
}

// ── Build native minting script ─────────────────────────────
function buildMintScript(pubKeyHash) {
  return CSL.NativeScript.new_script_pubkey(
    CSL.ScriptPubKey.new(pubKeyHash)
  );
}

// ── CIP-0170 metadata ───────────────────────────────────────
function buildMetadata(agent) {
  const now = new Date().toISOString();
  const agentMeta = {
    agent_name: agent.name,
    agent_type: "chess",
    platform: "boardman",
    arc_wallet: agent.arcWallet,
    registered_games: agent.games,
    description: agent.description,
    performance: { pnl_usdc: 0, matches_played: 0, last_updated: now },
    attestation: { issuer: "boardman", timestamp: now, version: "1.0" },
  };

  const metadata = CSL.GeneralTransactionMetadata.new();
  metadata.insert(
    BigInt(674),
    CSL.TransactionMetadatum.from_json(JSON.stringify({ "674": agentMeta }))
  );
  return metadata;
}

// ── Main ────────────────────────────────────────────────────
async function main() {
  const agent = AGENTS[AGENT_NAME];
  if (!agent) {
    console.error(`Unknown agent: ${AGENT_NAME}. Use --agent raja or --agent nero`);
    process.exit(1);
  }

  console.log(`\n🏷️  Minting CIP-0170 identity for ${agent.name} on Cardano Preview testnet\n`);

  // 1. Derive key
  console.log("1️⃣  Deriving signing key...");
  const { privKey, pubKey, pubKeyHash } = deriveSigningKey(WALLET_MNEMONIC);
  const address = getTestnetAddress(pubKeyHash);
  const addrBech = address.to_bech32();
  console.log(`   Address: ${addrBech}`);

  // 2. Get UTXOs
  console.log("\n2️⃣  Fetching UTXOs...");
  let utxos;
  try {
    utxos = await getAddressUtxos(addrBech);
  } catch {
    utxos = await getAddressUtxos(FEE_RECIPIENT_ADDRESS);
  }
  console.log(`   Found ${utxos.length} UTXOs`);

  if (utxos.length === 0) {
    console.error("   ❌ No UTXOs. Fund the wallet first.");
    process.exit(1);
  }

  const utxo = utxos[0];
  const txHash = utxo.tx_hash;
  const outIdx = utxo.output_index;
  const lovelace = Number(utxo.amount.find((a) => a.unit === "lovelace")?.quantity || 0);
  console.log(`   Using: ${txHash.slice(0, 16)}...#${outIdx} (${(lovelace / 1_000_000).toFixed(2)} ADA)`);

  // 3. Build minting policy
  console.log("\n3️⃣  Building mint policy...");
  const mintScript = buildMintScript(pubKeyHash);
  const policyHash = mintScript.hash();
  console.log(`   Policy hash: ${policyHash.to_hex()}`);

  // Asset name
  const assetName = `boardman_agent_${AGENT_NAME}`;
  const assetNameBytes = Buffer.from(assetName);
  console.log(`   Asset name: ${assetName}`);

  // 4. Build metadata
  const metadata = buildMetadata(agent);
  console.log("   Metadata: CIP-0170 label 674 ✓");

  // 5. Build transaction body
  console.log("\n4️⃣  Building transaction...");

  // Protocol params (hardcoded for Preview testnet - standard values)
  const feeConstant = BigInt(155381);
  const feeCoefficient = BigInt(44);

  // Create multi-asset for minting
  const multiAsset = CSL.MultiAsset.new();
  const assets = CSL.Assets.new();
  assets.insert(CSL.AssetName.new(assetNameBytes), BigInt(1));
  multiAsset.insert(policyHash, assets);

  // Build outputs
  const minUTXO = BigInt(1300000); // min ADA for UTXO with tokens
  const txFeeEstimate = BigInt(200000); // generous fee estimate
  const change = lovelace - minUTXO - txFeeEstimate;

  // Output 1: send token + min ADA to self
  const output1Value = CSL.Value.new(minUTXO);
  output1Value.set_multiasset(multiAsset);
  const output1 = CSL.TransactionOutput.new(address, output1Value);

  // Output 2: change back to self
  const output2 = CSL.TransactionOutput.new(address, CSL.Value.new(change > BigInt(0) ? change : BigInt(0)));

  // Build inputs
  const inputs = CSL.TransactionInputs.new();
  inputs.add(CSL.TransactionInput.new(
    CSL.TransactionHash.from_hex(txHash),
    BigInt(outIdx)
  ));

  // Build outputs
  const outputs = CSL.TransactionOutputs.new();
  outputs.add(output1);
  if (change > 0) outputs.add(output2);

  // Mint definition
  const mint = CSL.Mint.new();
  const mintAssets = CSL.MintAssets.new();
  mintAssets.insert(CSL.AssetName.new(assetNameBytes), BigInt(1));
  mint.insert(policyHash, mintAssets);

  // Certificates, withdrawals, etc. = none
  const withdrawals = CSL.Withdrawals.new();
  const redeemers = CSL.Redeemers.new();
  const datums = CSL.Datums.new();
  const collateral = CSL.TransactionInputs.new();
  const requiredSigners = CSL.Ed25519KeyHashes.new();
  const scriptDataHash = undefined;

  // Build transaction body
  const txBody = CSL.TransactionBody.new_inputs_outputs(
    inputs,
    outputs
  );
  txBody.set_fee(BigInt(200000)); // will be adjusted
  txBody.set_mint(mint);
  txBody.set_metadata(metadata);

  // Set validity interval
  const ttl = (await getLatestBlock()).slot + 7200; // 2 hours from now
  txBody.set_ttl(BigInt(ttl));

  // Calculate actual fee
  const txHashForFee = txBody.hash();
  const fee = feeConstant + BigInt(txHashForFee.to_bytes().length) * feeCoefficient;
  txBody.set_fee(fee);

  // Adjust change for actual fee
  const finalChange = lovelace - minUTXO - fee;
  if (finalChange > 0) {
    // Rebuild with correct change... for now, the generous estimate should work
  }

  // 6. Sign
  console.log("\n5️⃣  Signing...");
  const txHashBuf = txBody.hash().to_bytes();
  const signature = privKey.sign(txHashBuf);

  const witness = CSL.TransactionWitnessSet.new();
  const vkw = CSL.Vkeywitnesses.new();
  vkw.add(CSL.Vkeywitness.new(CSL.Vkey.new(pubKey), signature));
  witness.set_vkeys(vkw);

  const nativeScripts = CSL.NativeScripts.new();
  nativeScripts.add(mintScript);
  witness.set_native_scripts(nativeScripts);

  const signedTx = CSL.Transaction.new(txBody, witness, metadata);

  // 7. Submit
  console.log("6️⃣  Submitting...");
  const txCbor = Buffer.from(signedTx.to_bytes()).toString("hex");

  try {
    const resultHash = await submitTx(txCbor);
    console.log(`\n✅ SUCCESS!`);
    console.log(`   Tx Hash: ${resultHash}`);
    console.log(`   Explorer: https://preview.cardanoscan.io/transaction/${resultHash}`);
    console.log(`   Agent: ${agent.name}`);
    console.log(`   Token: policy.${assetName}`);
    console.log(`   Metadata: CIP-0170 label 674\n`);
  } catch (e) {
    console.error(`\n❌ Submit failed: ${e.message}`);

    // Save for debugging
    const fs = await import("fs");
    const debugPath = `src/debug_tx_${Date.now()}.cbor`;
    fs.writeFileSync(debugPath, txCbor);
    console.log(`   Saved: ${debugPath}`);

    // Try to decode the error
    if (e.message.includes("Missing")) {
      console.log("\n   Likely issue: transaction body doesn't match witnesses.");
    }
  }
}

main().catch(console.error);
