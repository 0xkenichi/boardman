/**
 * Deploy SpectatorPool — match-keyed spectator pot (not BoardmanEscrow).
 *
 * Env:
 *   NEW_WALLET_PRIVATE_KEY or ADMIN_PRIVATE_KEY  — deployer
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
  arcMainnet: process.env.ARC_MAINNET_USDC || "0x3600000000000000000000000000000000000000",
  hardhat: "0x036CbD53842c5426634e7929541eC2318f3dCF7e",
};

const BOARDMAN_WALLET = "0xFA931C535C9d10A324Ea7417a63ed22dD9b0cb2E";

async function main() {
  const network = hre.network.name;
  console.log(`\n🚀 Deploying SpectatorPool to ${network}...`);

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

  const SpectatorPool = await hre.ethers.getContractFactory("SpectatorPool");
  const pool = await SpectatorPool.deploy(usdcAddress, feeRecipient, resolverAddress);
  await pool.waitForDeployment();

  const address = await pool.getAddress();
  console.log(`✅ SpectatorPool deployed at: ${address}`);

  const deploymentInfo = {
    product: "Boardman by sideQuest",
    version: "v1",
    contractName: "SpectatorPool",
    network,
    chainId: hre.network.config.chainId,
    contracts: {
      SpectatorPool: address,
    },
    config: {
      usdc: usdcAddress,
      feeRecipient,
      resolver: resolverAddress,
      platformFeeBps: 300,
      creatorBps: 200,
    },
    deployedAt: new Date().toISOString(),
    deployer: deployer.address,
  };

  const outDir = path.join(__dirname, "../deployments");
  if (!fs.existsSync(outDir)) fs.mkdirSync(outDir, { recursive: true });

  const outFile = path.join(outDir, `spectator_pool_${network}.json`);
  fs.writeFileSync(outFile, JSON.stringify(deploymentInfo, null, 2));
  console.log(`\n📄 Saved: deployments/spectator_pool_${network}.json`);

  console.log("\n─────────────────────────────────────────────────");
  console.log("Add to backend .env:");
  console.log(`SPECTATOR_ESCROW_ADDRESS=${address}`);
  console.log("SPECTATOR_CHAIN=arc");
  console.log("SPECTATOR_ONCHAIN=1");
  console.log("─────────────────────────────────────────────────\n");
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
