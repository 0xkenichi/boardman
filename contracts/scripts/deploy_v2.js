/**
 * Deploy the v2 safety release: BoardmanEscrow v2 + SpectatorPool v2.
 *
 * NOT run by CI or by agents. A human runs this once per network after the
 * multisig exists. On hardhat/localhost it deploys a MockUSDC and is safe to
 * run for smoke tests.
 *
 *   npx hardhat run scripts/deploy_v2.js --network localhost
 *   CONFIRM_V2_DEPLOY=1 npx hardhat run scripts/deploy_v2.js --network arcTestnet
 *
 * Constructor parameters
 * ──────────────────────
 * BoardmanEscrow(usdc, feeRecipient, resolver, openTimeout, lockTimeout)
 *   usdc          USDC token (Arc: 0x3600…0000 native facade, 6 decimals)
 *   feeRecipient  treasury; receives withdrawFees(). Use a treasury Safe.
 *   resolver      backend hot key; signs createMatch permits (EIP-712
 *                 "BoardmanEscrow" v"2") and resolves / cancels matches.
 *   openTimeout   seconds an OPEN match waits for player2 before player1 can
 *                 be refunded by anyone. Bounds 1h..7d. Default 24h.
 *   lockTimeout   seconds a LOCKED/DISPUTED match waits for the resolver
 *                 before anyone can refund both players (and resolve stops).
 *                 Bounds 1d..30d. Default 7d.
 *
 * SpectatorPool(usdc, feeRecipient, resolver, refundGrace, claimWindow)
 *   refundGrace   seconds after a book's closeAt before an unresolved book
 *                 becomes refundable by anyone. Bounds 1h..30d. Default 7d.
 *   claimWindow   seconds after settlement before the owner may sweep a
 *                 book's unclaimed remainder. Bounds 30d..730d. Default 180d.
 *
 * Both contracts are deployed owned by the deployer, then ownership is
 * offered to V2_OWNER_MULTISIG (Ownable2Step). The multisig MUST call
 * acceptOwnership() on both contracts; until then the deployer is owner.
 *
 * Env
 *   V2_OWNER_MULTISIG   required off-local: Safe that will own both contracts
 *   V2_TREASURY         required off-local: feeRecipient for both contracts
 *   V2_RESOLVER         required off-local: backend resolver address
 *   USDC_ADDRESS        optional override of the per-network USDC address
 *   ESCROW_OPEN_TIMEOUT / ESCROW_LOCK_TIMEOUT / POOL_REFUND_GRACE / POOL_CLAIM_WINDOW
 *   CONFIRM_V2_DEPLOY=1 required off-local, so this never runs by accident
 */
import hre from "hardhat";
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

const LOCAL = new Set(["hardhat", "localhost"]);
const USDC = {
  arcTestnet: "0x3600000000000000000000000000000000000000",
  arcMainnet: process.env.ARC_MAINNET_USDC || "0x3600000000000000000000000000000000000000",
  baseSepolia: "0x036CbD53842c5426634e7929541eC2318f3dCF7e",
  baseMainnet: "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
};

const DAY = 24 * 3600;
const num = (name, dflt) => BigInt(process.env[name] || dflt);

async function main() {
  const { ethers, network } = hre;
  const local = LOCAL.has(network.name);
  const signers = await ethers.getSigners();
  const deployer = signers[0];

  if (!local && process.env.CONFIRM_V2_DEPLOY !== "1") {
    throw new Error(`Refusing to deploy to ${network.name} without CONFIRM_V2_DEPLOY=1`);
  }

  // Local runs fill roles from the default test accounts.
  const multisig = process.env.V2_OWNER_MULTISIG || (local ? signers[3].address : "");
  const treasury = process.env.V2_TREASURY || (local ? signers[2].address : "");
  const resolver = process.env.V2_RESOLVER || (local ? signers[1].address : "");
  for (const [k, v] of Object.entries({ V2_OWNER_MULTISIG: multisig, V2_TREASURY: treasury, V2_RESOLVER: resolver })) {
    if (!v || !ethers.isAddress(v)) throw new Error(`${k} must be set to an address`);
  }
  // Role separation (finding 7): one key must not hold two roles.
  const roles = [multisig, treasury, resolver].map((a) => a.toLowerCase());
  if (new Set(roles).size !== 3) throw new Error("owner multisig, treasury and resolver must be distinct");
  if (!local && roles.includes(deployer.address.toLowerCase())) {
    throw new Error("deployer must be a throwaway key, not one of the v2 roles");
  }

  const openTimeout = num("ESCROW_OPEN_TIMEOUT", DAY);
  const lockTimeout = num("ESCROW_LOCK_TIMEOUT", 7 * DAY);
  const refundGrace = num("POOL_REFUND_GRACE", 7 * DAY);
  const claimWindow = num("POOL_CLAIM_WINDOW", 180 * DAY);

  let usdc = process.env.USDC_ADDRESS || USDC[network.name];
  if (!usdc && local) {
    const mock = await (await ethers.getContractFactory("MockUSDC")).deploy();
    await mock.waitForDeployment();
    usdc = await mock.getAddress();
  }
  if (!usdc) throw new Error(`no USDC address for ${network.name}; set USDC_ADDRESS`);

  console.log(`Deploying v2 to ${network.name} (chainId ${network.config.chainId})`);
  console.log({ deployer: deployer.address, usdc, treasury, resolver, multisig });
  console.log({ openTimeout, lockTimeout, refundGrace, claimWindow });

  const escrow = await (await ethers.getContractFactory("BoardmanEscrow")).deploy(
    usdc, treasury, resolver, openTimeout, lockTimeout
  );
  await escrow.waitForDeployment();
  const pool = await (await ethers.getContractFactory("SpectatorPool")).deploy(
    usdc, treasury, resolver, refundGrace, claimWindow
  );
  await pool.waitForDeployment();
  const escrowAddr = await escrow.getAddress();
  const poolAddr = await pool.getAddress();

  // Offer ownership to the multisig; it must acceptOwnership() on both.
  await (await escrow.transferOwnership(multisig)).wait();
  await (await pool.transferOwnership(multisig)).wait();

  const info = {
    product: "Boardman by sideQuest",
    version: "v2-safety",
    network: network.name,
    chainId: network.config.chainId,
    contracts: { BoardmanEscrow: escrowAddr, SpectatorPool: poolAddr },
    config: {
      usdc,
      feeRecipient: treasury,
      resolver,
      pendingOwner: multisig,
      escrow: { openTimeout: openTimeout.toString(), lockTimeout: lockTimeout.toString(), eip712: { name: "BoardmanEscrow", version: "2" } },
      spectatorPool: { refundGrace: refundGrace.toString(), claimWindow: claimWindow.toString(), maxBettingWindow: String(7 * DAY) },
    },
    deployedAt: new Date().toISOString(),
    deployer: deployer.address,
    todo: "multisig must call acceptOwnership() on both contracts",
  };
  console.log(JSON.stringify(info, null, 2));

  if (!local || process.env.WRITE_LOCAL_DEPLOYMENT === "1") {
    const out = path.join(__dirname, "../deployments", `boardman_v2_${network.name}.json`);
    fs.writeFileSync(out, JSON.stringify(info, null, 2) + "\n");
    console.log(`Saved ${path.relative(process.cwd(), out)}`);
  }

  console.log("\nBackend env (switch only after acceptOwnership on both):");
  console.log(`BOARDMAN_ESCROW_ADDRESS_ARC=${escrowAddr}`);
  console.log(`SPECTATOR_ESCROW_ADDRESS=${poolAddr}`);
  console.log("BOARDMAN_RESOLVER_KEY=<private key of the resolver above>");
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
