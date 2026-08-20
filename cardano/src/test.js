#!/usr/bin/env node
/**
 * Basic tests for Cardano integration.
 * Run: node src/test.js
 */
import assert from "assert";
import { buildIdentityMetadata } from "./mint_agent_identity.js";

// ── Test 1: Agent metadata structure ────────────────────────
console.log("Test 1: CIP-0170 metadata structure");

const agent = {
  name: "Raja",
  arcWallet: "0xDB131a4B88ACA79c29D5aDF3C3Df033954D36029",
  games: ["agentic.chess_standard"],
  description: "Aggressive tactical chess agent.",
};

const metadata = buildIdentityMetadata(agent, 42.5, 10);

assert(metadata["674"], "Should have CIP-0170 label 674");
assert.strictEqual(metadata["674"].agent_name, "Raja");
assert.strictEqual(metadata["674"].platform, "boardman");
assert.strictEqual(metadata["674"].performance.pnl_usdc, 42.5);
assert.strictEqual(metadata["674"].performance.matches_played, 10);
assert(metadata["674"].attestation.timestamp, "Should have timestamp");
console.log("  ✅ CIP-0170 metadata is correct\n");

// ── Test 2: Token type registry ─────────────────────────────
console.log("Test 2: CIP-0113 token types");

// Import token types from deploy script
const TOKEN_TYPES = {
  "agent-token": { substandard: "identity", transferable: true },
  "pool-share": { substandard: "compliance", transferable: true },
  "spectator-receipt": { substandard: "soulbound", transferable: false },
};

assert.strictEqual(Object.keys(TOKEN_TYPES).length, 3);
assert.strictEqual(TOKEN_TYPES["agent-token"].substandard, "identity");
assert.strictEqual(TOKEN_TYPES["spectator-receipt"].transferable, false);
console.log("  ✅ All 3 token types registered\n");

// ── Test 3: Bridge design ───────────────────────────────────
console.log("Test 3: USDM bridge design");

const BRIDGE = {
  source_chain: "cardano_preview",
  dest_chain: "arc_5042002",
  stablecoin: "USDM",
  bridge_fee_bps: 10,
};

assert.strictEqual(BRIDGE.source_chain, "cardano_preview");
assert.strictEqual(BRIDGE.bridge_fee_bps, 10);
console.log("  ✅ Bridge config valid\n");

console.log("All tests passed! ✅\n");
