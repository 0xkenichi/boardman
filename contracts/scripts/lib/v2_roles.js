/**
 * Role checks behind check_v2_roles.js (audit 2026-10 delta D-03).
 *
 * The first version printed "OK" when no EXPECT_* was set at all, and
 * accepted an un-accepted ownership (owner still the deployer) as OK, so the
 * post-accept run of the runbook could not fail. Here:
 * - on a mainnet, EXPECT_OWNER, EXPECT_RESOLVER and EXPECT_TREASURY are
 *   required, and the USDC address is checked against the known one;
 * - EXPECT_ACCEPTED=1 requires owner == EXPECT_OWNER and pendingOwner == 0;
 * - a paused escrow is reported unless EXPECT_PAUSED=1.
 */
export const MAINNETS = new Set(["arcMainnet", "baseMainnet"]);
export const KNOWN_USDC = {
  arcTestnet: "0x3600000000000000000000000000000000000000",
  arcMainnet: "0x3600000000000000000000000000000000000000",
  baseSepolia: "0x036CbD53842c5426634e7929541eC2318f3dCF7e",
  baseMainnet: "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
};
const ZERO = "0x0000000000000000000000000000000000000000";

const eq = (a, b) => String(a).toLowerCase() === String(b).toLowerCase();

/** Returns {problems, notes}; problems non-empty means the check failed. */
export function checkRoles(state, networkName, env = process.env) {
  const problems = [];
  const notes = [];
  const mainnet = MAINNETS.has(networkName);
  if (mainnet) {
    for (const k of ["EXPECT_OWNER", "EXPECT_RESOLVER", "EXPECT_TREASURY"]) {
      if (!env[k]) problems.push(`${k} is required on ${networkName}`);
    }
  }
  if (Number(state.version) !== 2) problems.push(`ESCROW_VERSION ${state.version} != 2`);

  const want = env.EXPECT_OWNER;
  if (want) {
    const ownerOk = eq(state.owner, want);
    const pendingOk = eq(state.pendingOwner, want);
    if (!ownerOk && !pendingOk) problems.push("neither owner nor pendingOwner is EXPECT_OWNER");
    if (env.EXPECT_ACCEPTED === "1") {
      if (!ownerOk) problems.push("owner is not EXPECT_OWNER: the Safe has not called acceptOwnership()");
      if (!eq(state.pendingOwner, ZERO)) problems.push(`pendingOwner ${state.pendingOwner} is still set`);
    } else if (!ownerOk) {
      notes.push("the Safe has not called acceptOwnership() yet (rerun with EXPECT_ACCEPTED=1 after it does)");
    }
  }
  if (env.EXPECT_RESOLVER && !eq(state.resolver, env.EXPECT_RESOLVER)) problems.push("resolver mismatch");
  if (env.EXPECT_TREASURY && !eq(state.feeRecipient, env.EXPECT_TREASURY)) problems.push("feeRecipient mismatch");
  const usdc = env.EXPECT_USDC || KNOWN_USDC[networkName];
  if (usdc && !eq(state.usdc, usdc)) problems.push(`usdc ${state.usdc} != ${usdc}`);
  if (env.EXPECT_MAX_STAKE_USDC && Number(state.maxStakeUsdc) !== Number(env.EXPECT_MAX_STAKE_USDC)) {
    problems.push(`maxStakePerPlayer ${state.maxStakeUsdc} != ${env.EXPECT_MAX_STAKE_USDC}`);
  }
  if (state.paused && env.EXPECT_PAUSED !== "1") problems.push("escrow is paused");
  return { problems, notes };
}
