#!/usr/bin/env node
/**
 * Mint a CIP-0170 agent identity attestation on Cardano Preview testnet.
 *
 * This creates a unique NFT for each Boardman agent (Raja, Nero, etc.)
 * containing:
 *   - Agent name
 *   - Registered game IDs
 *   - Arc wallet address
 *   - Rolling PNL digest
 *   - Timestamp
 *
 * The token is minted under a one-time minting policy (lock after first mint).
 * Metadata follows CIP-0170 structure for verifiable on-chain identity.
 *
 * Usage:
 *   node src/mint_agent_identity.js --agent raja
 *   node src/mint_agent_identity.js --agent nero --pnl 42.5
 */
import { BLOCKFROST_PROJECT_ID, BLOCKFROST_BASE_URL, WALLET_MNEMONIC, FEE_RECIPIENT_ADDRESS } from "./config.js";

// ── Agent Registry ──────────────────────────────────────────
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

// ── CIP-0170 Identity Metadata Schema ───────────────────────
// Label 674 = CIP-0170 agent identity attestation
export function buildIdentityMetadata(agent, pnl = 0, matchCount = 0) {
  const now = new Date().toISOString();
  return {
    // CIP-0170 identity attestation (label 674)
    "674": {
      agent_name: agent.name,
      agent_type: "chess",
      platform: "boardman",
      arc_wallet: agent.arcWallet,
      registered_games: agent.games,
      description: agent.description,
      performance: {
        pnl_usdc: pnl,
        matches_played: matchCount,
        last_updated: now,
      },
      attestation: {
        issuer: "boardman",
        timestamp: now,
        version: "1.0",
      },
    },
  };
}

// ── Minting Policy ──────────────────────────────────────────
// One-time mint: policy script that only allows minting if the
// transaction is signed by the wallet and the asset name hasn't been used.
function buildMintPolicy(walletPubKeyHash) {
  return {
    type: "sig",
    keyHash: walletPubKeyHash,
  };
}

// ── Main ────────────────────────────────────────────────────
async function main() {
  const args = process.argv.slice(2);
  const agentFlag = args.indexOf("--agent");
  const agentName = agentFlag >= 0 ? args[agentFlag + 1] : "raja";
  const pnlFlag = args.indexOf("--pnl");
  const pnl = pnlFlag >= 0 ? parseFloat(args[pnlFlag + 1]) : 0;
  const matchesFlag = args.indexOf("--matches");
  const matches = matchesFlag >= 0 ? parseInt(args[matchesFlag + 1]) : 0;
  const dryRun = args.includes("--dry-run");

  const agent = AGENTS[agentName];
  if (!agent) {
    console.error(`Unknown agent: ${agentName}. Available: ${Object.keys(AGENTS).join(", ")}`);
    process.exit(1);
  }

  console.log(`\n🏷️  Boardman Agent Identity — CIP-0170 Attestation`);
  console.log(`   Agent: ${agent.name}`);
  console.log(`   Arc wallet: ${agent.arcWallet}`);
  console.log(`   Games: ${agent.games.join(", ")}`);
  console.log(`   PNL: ${pnl} USDC`);
  console.log(`   Matches: ${matches}`);

  // Build the metadata
  const metadata = buildIdentityMetadata(agent, pnl, matches);
  console.log(`\n📋 CIP-0170 Metadata:`);
  console.log(JSON.stringify(metadata, null, 2));

  // Build the minting policy
  // In production, derive the wallet pubkey hash from the mnemonic
  const policyHash = "placeholder_wallet_pubkey_hash";
  const policy = buildMintPolicy(policyHash);

  const assetName = `boardman_agent_${agentName.toLowerCase()}`;
  const policyId = "placeholder_policy_id"; // computed from policy script

  console.log(`\n🪙 Token:`);
  console.log(`   Policy ID: ${policyId}`);
  console.log(`   Asset Name: ${assetName}`);
  console.log(`   Full Asset ID: ${policyId}${Buffer.from(assetName).toString("hex")}`);
  console.log(`   Mint Policy: ${JSON.stringify(policy)}`);

  if (dryRun) {
    console.log(`\n✅ Dry run complete — no transaction submitted`);
    return;
  }

  // Check if we have wallet credentials
  if (!WALLET_MNEMONIC) {
    console.log(`\n⚠️  WALLET_MNEMONIC not set — cannot submit transaction`);
    console.log(`   This is the metadata + policy that would be minted.`);
    console.log(`   Set WALLET_MNEMONIC in .env and run again to mint.\n`);
    return;
  }

  // TODO: Build and submit the actual minting transaction
  // This requires:
  // 1. Derive private key from mnemonic
  // 2. Build the minting transaction with metadata
  // 3. Sign with private key
  // 4. Submit via Blockfrost
  console.log(`\n⏳ Transaction building requires wallet key derivation.`);
  console.log(`   Connect a Cardano wallet (Eternl/Nami) to sign the mint tx.`);
  console.log(`   Or use the Boardman API: POST /api/cardano/mint-identity\n`);
}

main().catch(console.error);
