/**
 * Deploy BoardmanEscrow (V1) — Boardman by sideQuest.
 * Legacy ClawEscrow remains V0 archive.
 *
 * Env:
 *   NEW_WALLET_PRIVATE_KEY or ADMIN_PRIVATE_KEY  — deployer (Boardman wallet)
 *   FEE_RECIPIENT_ADDRESS / BOARDMAN_FEE_RECIPIENT
 *   RESOLVER_ADDRESS / BOARDMAN_FEE_RECIPIENT
 */
import hre from "hardhat";
import fs from "fs";
import path from "path";

const USDC = {
  baseSepolia: "0x036CbD53842c5426634e7929541eC2318f3dCF7e",
  baseMainnet: "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
  arcTestnet: "0x3600000000000000000000000000000000000000",
  // Arc mainnet — update when confirmed on explorer
  arcMainnet: process.env.ARC_MAINNET_USDC || "0x3600000000000000000000000000000000000000",
  hardhat: "0x036CbD53842c5426634e7929541eC2318f3dCF7e",
};

const BOARDMAN_WALLET = "0xFA931C535C9d10A324Ea7417a63ed22dD9b0cb2E";

async function main() {
  const network = hre.network.name;
  console.log(`\n🚀 Deploying BoardmanEscrow (V1) to ${network}...`);

  const [deployer] = await hre.ethers.getSigners();
  const bal = await hre.ethers.provider.getBalance(deployer.address);
  console.log(`   Deployer:  ${deployer.address}`);
  console.log(`   Balance:   ${hre.ethers.formatEther(bal)}\n`);

  if (deployer.address.toLowerCase() !== BOARDMAN_WALLET.toLowerCase()) {
    console.warn(
      `⚠️  Deployer is not Boardman V1 wallet ${BOARDMAN_WALLET}\n` +
        `   Continuing with ${deployer.address} — set NEW_WALLET_PRIVATE_KEY to use Boardman wallet.\n`
    );
  }

  const usdcAddress = USDC[network] || USDC.arcTestnet;
  const feeRecipient =
    process.env.FEE_RECIPIENT_ADDRESS ||
    process.env.BOARDMAN_FEE_RECIPIENT ||
    BOARDMAN_WALLET;
  const resolverAddress =
    process.env.RESOLVER_ADDRESS ||
    process.env.BOARDMAN_FEE_RECIPIENT ||
    BOARDMAN_WALLET;

  console.log(`   USDC:          ${usdcAddress}`);
  console.log(`   Fee Recipient: ${feeRecipient}`);
  console.log(`   Resolver:      ${resolverAddress}\n`);

  const BoardmanEscrow = await hre.ethers.getContractFactory("BoardmanEscrow");
  const escrow = await BoardmanEscrow.deploy(usdcAddress, feeRecipient, resolverAddress);
  await escrow.waitForDeployment();

  const address = await escrow.getAddress();
  console.log(`✅ BoardmanEscrow deployed at: ${address}`);

  const deploymentInfo = {
    product: "Boardman by sideQuest",
    formerly: "Rematch by sideQuest",
    version: "v1",
    contractName: "BoardmanEscrow",
    network,
    chainId: hre.network.config.chainId,
    contracts: {
      BoardmanEscrow: address,
      ClawEscrow_V0_archive: "see contracts/deployments/* and CONTRACTS.md",
    },
    config: {
      usdc: usdcAddress,
      feeRecipient,
      resolver: resolverAddress,
    },
    deployedAt: new Date().toISOString(),
    deployer: deployer.address,
  };

  const outDir = path.join(__dirname, "../deployments");
  if (!fs.existsSync(outDir)) fs.mkdirSync(outDir, { recursive: true });

  const outFile = path.join(outDir, `boardman_v1_${network}.json`);
  fs.writeFileSync(outFile, JSON.stringify(deploymentInfo, null, 2));
  console.log(`\n📄 Saved: deployments/boardman_v1_${network}.json`);

  // Update aggregate boardman_v1_wallets.json if present
  const walletsFile = path.join(outDir, "boardman_v1_wallets.json");
  try {
    const w = JSON.parse(fs.readFileSync(walletsFile, "utf8"));
    w.escrowV1 = w.escrowV1 || {};
    w.escrowV1[network] = address;
    w.status = "escrow_deployed_partial";
    w.updatedAt = new Date().toISOString().slice(0, 10);
    fs.writeFileSync(walletsFile, JSON.stringify(w, null, 2) + "\n");
    console.log("📄 Updated boardman_v1_wallets.json");
  } catch (_) {
    /* optional */
  }

  console.log("\n─────────────────────────────────────────────────");
  console.log("Add to backend .env:");
  if (network === "arcTestnet" || network.includes("arc")) {
    console.log(`CLAW_ESCROW_ADDRESS_ARC=${address}`);
    console.log(`BOARDMAN_ESCROW_ADDRESS_ARC=${address}`);
  } else if (network === "baseSepolia") {
    console.log(`CLAW_ESCROW_ADDRESS_BASE_SEPOLIA=${address}`);
    console.log(`BOARDMAN_ESCROW_ADDRESS_BASE_SEPOLIA=${address}`);
  } else {
    console.log(`BOARDMAN_ESCROW_ADDRESS=${address}`);
  }
  console.log("─────────────────────────────────────────────────\n");
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
