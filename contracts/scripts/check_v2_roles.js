/**
 * Read-only check of a deployed BoardmanEscrow v2: owner, pendingOwner,
 * resolver, feeRecipient, stake cap, pause state. Sends nothing; needs no key.
 *
 *   ESCROW=0x… EXPECT_OWNER=0xSafe EXPECT_RESOLVER=0x… EXPECT_TREASURY=0x… \
 *   EXPECT_MAX_STAKE_USDC=25 npx hardhat run scripts/check_v2_roles.js --network arcMainnet
 *
 * Exits non-zero on any mismatch. Run it after deploy (pendingOwner = Safe)
 * and again after the Safe's acceptOwnership with EXPECT_ACCEPTED=1 (owner =
 * Safe, pendingOwner = 0). On a mainnet EXPECT_OWNER, EXPECT_RESOLVER and
 * EXPECT_TREASURY are required and usdc() must be the known USDC
 * (EXPECT_USDC overrides). A paused escrow fails unless EXPECT_PAUSED=1.
 */
import hre from "hardhat";
import { checkRoles } from "./lib/v2_roles.js";

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

  // Audit 2026-10 D-03: the checks live in lib/v2_roles.js (tested).
  const { problems, notes } = checkRoles(state, network.name);
  for (const n of notes) console.log(`NOTE: ${n}`);
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
