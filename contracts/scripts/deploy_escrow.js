const hre = require("hardhat");
const fs = require("fs");
const path = require("path");

// ─── USDC Addresses ──────────────────────────────────────────────────────────
const USDC = {
  baseSepolia: "0x036CbD53842c5426634e7929541eC2318f3dCF7e",
  baseMainnet: "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
  hardhat:     "0x036CbD53842c5426634e7929541eC2318f3dCF7e", // placeholder for local
};

async function main() {
  const network = hre.network.name;
  console.log(`\n🚀 Deploying ClawEscrow to ${network}...`);

  const [deployer] = await hre.ethers.getSigners();
  console.log(`   Deployer:  ${deployer.address}`);
  console.log(`   Balance:   ${hre.ethers.formatEther(await hre.ethers.provider.getBalance(deployer.address))} ETH\n`);

  // ── Resolve addresses ────────────────────────────────────────────────
  const usdcAddress     = USDC[network] || USDC.baseSepolia;
  const feeRecipient    = process.env.FEE_RECIPIENT_ADDRESS || deployer.address;
  const resolverAddress = process.env.RESOLVER_ADDRESS      || deployer.address;

  console.log(`   USDC:          ${usdcAddress}`);
  console.log(`   Fee Recipient: ${feeRecipient}`);
  console.log(`   Resolver:      ${resolverAddress}\n`);

  // ── Deploy ───────────────────────────────────────────────────────────
  const ClawEscrow = await hre.ethers.getContractFactory("ClawEscrow");
  const escrow = await ClawEscrow.deploy(usdcAddress, feeRecipient, resolverAddress);
  await escrow.waitForDeployment();

  const address = await escrow.getAddress();
  console.log(`✅ ClawEscrow deployed at: ${address}`);

  // ── Save deployment info ─────────────────────────────────────────────
  const deploymentInfo = {
    network,
    chainId: hre.network.config.chainId,
    contracts: {
      ClawEscrow: address,
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

  const outFile = path.join(outDir, `${network}.json`);
  fs.writeFileSync(outFile, JSON.stringify(deploymentInfo, null, 2));
  console.log(`\n📄 Deployment info saved to: deployments/${network}.json`);

  // ── Print env vars to paste ───────────────────────────────────────────
  console.log("\n─────────────────────────────────────────────────");
  console.log("Add these to your backend .env:");
  console.log(`CSC_ADDRESS=${address}`);
  console.log(`BASE_RPC_URL=${hre.network.config.url || "https://sepolia.base.org"}`);
  console.log(`CHAIN_ID=${hre.network.config.chainId}`);
  console.log(`USDC_CONTRACT_ADDRESS=${usdcAddress}`);
  console.log("─────────────────────────────────────────────────\n");

  // ── Verify on Basescan (skip for local) ──────────────────────────────
  if (network !== "hardhat" && network !== "localhost") {
    console.log("⏳ Waiting 15s before verification...");
    await new Promise((r) => setTimeout(r, 15000));
    try {
      await hre.run("verify:verify", {
        address,
        constructorArguments: [usdcAddress, feeRecipient, resolverAddress],
      });
      console.log("✅ Contract verified on Basescan");
    } catch (e) {
      console.warn("⚠️  Verification failed (you can retry manually):", e.message);
    }
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
