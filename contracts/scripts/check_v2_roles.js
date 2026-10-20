/**
 * Read-only check of a deployed BoardmanEscrow v2: owner, pendingOwner,
 * resolver, feeRecipient, stake cap, pause state. Sends nothing; needs no key.
 *
 *   ESCROW=0x… EXPECT_OWNER=0xSafe EXPECT_RESOLVER=0x… EXPECT_TREASURY=0x… \
 *   EXPECT_MAX_STAKE_USDC=25 npx hardhat run scripts/check_v2_roles.js --network arcMainnet
 *
 * Exits non-zero on any mismatch. Run it after deploy (pendingOwner = Safe)
 * and again after the Safe's acceptOwnership (owner = Safe, pendingOwner = 0).
 */
import hre from "hardhat";

const ABI = [
  "function owner() view returns (address)",
  "function pendingOwner() view returns (address)",
  "function resolver() view returns (address)",
  "function feeRecipient() view returns (address)",
  "function maxStakePerPlayer() view returns (uint256)",
  "function paused() view returns (bool)",
  "function ESCROW_VERSION() view returns (uint8)",
  "function usdc() view returns (address)",
];

async function main() {
  const { ethers, network } = hre;
  const addr = process.env.ESCROW;
  if (!addr || !ethers.isAddress(addr)) throw new Error("set ESCROW=0x… (the BoardmanEscrow address)");
  const c = new ethers.Contract(addr, ABI, ethers.provider);
  const state = {
    network: network.name,
    chainId: (await ethers.provider.getNetwork()).chainId.toString(),
    escrow: addr,
    version: Number(await c.ESCROW_VERSION()),
    owner: await c.owner(),
    pendingOwner: await c.pendingOwner(),
    resolver: await c.resolver(),
    feeRecipient: await c.feeRecipient(),
    usdc: await c.usdc(),
    maxStakeUsdc: ethers.formatUnits(await c.maxStakePerPlayer(), 6),
    paused: await c.paused(),
  };
  console.log(JSON.stringify(state, null, 2));

  const problems = [];
  const eq = (a, b) => String(a).toLowerCase() === String(b).toLowerCase();
  if (state.version !== 2) problems.push(`ESCROW_VERSION ${state.version} != 2`);
  const ownerOk = process.env.EXPECT_OWNER && eq(state.owner, process.env.EXPECT_OWNER);
  const pendingOk = process.env.EXPECT_OWNER && eq(state.pendingOwner, process.env.EXPECT_OWNER);
  if (process.env.EXPECT_OWNER && !ownerOk && !pendingOk) problems.push("neither owner nor pendingOwner is EXPECT_OWNER");
  if (process.env.EXPECT_OWNER && !ownerOk) console.log("NOTE: the Safe has not called acceptOwnership() yet");
  if (process.env.EXPECT_RESOLVER && !eq(state.resolver, process.env.EXPECT_RESOLVER)) problems.push("resolver mismatch");
  if (process.env.EXPECT_TREASURY && !eq(state.feeRecipient, process.env.EXPECT_TREASURY)) problems.push("feeRecipient mismatch");
  if (process.env.EXPECT_MAX_STAKE_USDC && Number(state.maxStakeUsdc) !== Number(process.env.EXPECT_MAX_STAKE_USDC)) {
    problems.push(`maxStakePerPlayer ${state.maxStakeUsdc} != ${process.env.EXPECT_MAX_STAKE_USDC}`);
  }
  if (problems.length) {
    console.error("MISMATCH:\n - " + problems.join("\n - "));
    process.exit(1);
  }
  console.log("OK");
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
