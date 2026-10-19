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
 * MAINNET (arcMainnet, baseMainnet) — real money, humans realm only:
 *   - deploys BoardmanEscrow ONLY. Spectator betting stays on testnet, so a
 *     SpectatorPool is never deployed to a mainnet (refused, no override).
 *   - sets the launch stake cap (ESCROW_MAX_STAKE_USDC, default 25) before
 *     the ownership offer; the Safe raises it after an audit (setMaxStake).
 *   - V2_OWNER_MULTISIG must be a contract (a Safe). The founder-wallet
 *     fallback (an EOA owner) needs V2_OWNER_IS_EOA=1, said out loud.
 *   - checks the RPC's chain id and that USDC has 6 decimals before deploying.
 *   - the deployer key is MAINNET_DEPLOYER_KEY (hardhat.config.js), a
 *     throwaway that holds only gas and none of the three roles.
 *   Runbook: docs/MAINNET_HUMANS_CUTOVER.md.
 *
 *   CONFIRM_V2_DEPLOY=1 V2_OWNER_MULTISIG=0xSafe V2_TREASURY=0xTreasury \
 *   V2_RESOLVER=0xResolverFromKeystore \
 *     npx hardhat run scripts/deploy_v2.js --network arcMainnet
 *
 * Env
 *   V2_OWNER_MULTISIG   required off-local: Safe that will own both contracts
 *   V2_OWNER_IS_EOA=1   mainnet only: accept an EOA owner (no Safe on this chain)
 *   V2_TREASURY         required off-local: feeRecipient for both contracts
 *   V2_RESOLVER         required off-local: backend resolver address
 *   USDC_ADDRESS        optional override of the per-network USDC address
 *   ESCROW_MAX_STAKE_USDC  per-player stake cap set at deploy (mainnet default 25)
 *   ESCROW_OPEN_TIMEOUT / ESCROW_LOCK_TIMEOUT / POOL_REFUND_GRACE / POOL_CLAIM_WINDOW
 *   CONFIRM_V2_DEPLOY=1 required off-local, so this never runs by accident
 */
import hre from "hardhat";
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

const LOCAL = new Set(["hardhat", "localhost"]);
// Real-money networks: escrow only, stake cap, Safe owner checks.
const MAINNET = new Set(["arcMainnet", "baseMainnet"]);
// Expected chain ids (the RPC must agree before anything is sent).
const CHAIN_IDS = { arcTestnet: 5042002n, arcMainnet: 5042n, baseSepolia: 84532n, baseMainnet: 8453n };
const USDC = {
  arcTestnet: "0x3600000000000000000000000000000000000000",
  // https://docs.arc.io/arc/references/contract-addresses (ERC-20 facade, 6 decimals)
  arcMainnet: "0x3600000000000000000000000000000000000000",
  baseSepolia: "0x036CbD53842c5426634e7929541eC2318f3dCF7e",
  baseMainnet: "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
};

const DAY = 24 * 3600;
const num = (name, dflt) => BigInt(process.env[name] || dflt);

async function main() {
  const { ethers, network } = hre;
  const local = LOCAL.has(network.name);
  const mainnet = MAINNET.has(network.name) || process.env.V2_TREAT_AS_MAINNET === "1";
  if (!local && process.env.CONFIRM_V2_DEPLOY !== "1") {
    throw new Error(`Refusing to deploy to ${network.name} without CONFIRM_V2_DEPLOY=1`);
  }
  const signers = await ethers.getSigners();
  if (!signers.length) {
    throw new Error(`No deployer key for ${network.name} (set MAINNET_DEPLOYER_KEY blind; see the runbook)`);
  }
  const deployer = signers[0];

  const want = CHAIN_IDS[network.name];
  const got = (await ethers.provider.getNetwork()).chainId;
  if (want !== undefined && got !== want) {
    throw new Error(`RPC chain id ${got} != expected ${want} for ${network.name}; refusing`);
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

  // Real-money checks before anything is sent.
  let maxStake = null;
  let ownerKind = "unchecked";
  if (mainnet) {
    if (process.env.DEPLOY_SPECTATOR_POOL === "1") {
      throw new Error("SpectatorPool is never deployed to a mainnet: spectator betting stays on testnet");
    }
    const code = await ethers.provider.getCode(multisig);
    if (code && code !== "0x") {
      ownerKind = "contract (Safe)";
    } else if (process.env.V2_OWNER_IS_EOA === "1") {
      ownerKind = "EOA (founder-wallet fallback)";
    } else {
      throw new Error(
        `V2_OWNER_MULTISIG ${multisig} has no code on ${network.name}. Deploy the Safe first, or set ` +
          "V2_OWNER_IS_EOA=1 to accept the founder-wallet fallback (see the runbook)"
      );
    }
    const erc20 = new ethers.Contract(usdc, ["function decimals() view returns (uint8)"], ethers.provider);
    const decimals = Number(await erc20.decimals());
    if (decimals !== 6) throw new Error(`USDC at ${usdc} reports ${decimals} decimals, expected 6`);
    maxStake = ethers.parseUnits(process.env.ESCROW_MAX_STAKE_USDC || "25", 6);
  } else if (process.env.ESCROW_MAX_STAKE_USDC) {
    maxStake = ethers.parseUnits(process.env.ESCROW_MAX_STAKE_USDC, 6);
  }
  const withPool = !mainnet;

  console.log(`Deploying v2 to ${network.name} (chainId ${got})${mainnet ? " — REAL MONEY, escrow only" : ""}`);
  console.log({ deployer: deployer.address, usdc, treasury, resolver, multisig, ownerKind });
  console.log({ openTimeout, lockTimeout, refundGrace, claimWindow, maxStake: maxStake?.toString() ?? "MAX_STAKE" });

  const escrow = await (await ethers.getContractFactory("BoardmanEscrow")).deploy(
    usdc, treasury, resolver, openTimeout, lockTimeout
  );
  await escrow.waitForDeployment();
  const escrowAddr = await escrow.getAddress();
  if (maxStake !== null) {
    await (await escrow.setMaxStake(maxStake)).wait();
  }
  let pool = null;
  let poolAddr = "";
  if (withPool) {
    pool = await (await ethers.getContractFactory("SpectatorPool")).deploy(
      usdc, treasury, resolver, refundGrace, claimWindow
    );
    await pool.waitForDeployment();
    poolAddr = await pool.getAddress();
  }

  // Offer ownership to the multisig; it must acceptOwnership() on each.
  await (await escrow.transferOwnership(multisig)).wait();
  if (pool) await (await pool.transferOwnership(multisig)).wait();
  if ((await escrow.pendingOwner()).toLowerCase() !== multisig.toLowerCase()) {
    throw new Error("pendingOwner is not the multisig — stop and investigate");
  }

  const info = {
    product: "Boardman by sideQuest",
    version: "v2-safety",
    network: network.name,
    chainId: Number(got),
    realm: mainnet ? "humans (real money)" : "arena / practice",
    contracts: pool ? { BoardmanEscrow: escrowAddr, SpectatorPool: poolAddr } : { BoardmanEscrow: escrowAddr },
    config: {
      usdc,
      feeRecipient: treasury,
      resolver,
      pendingOwner: multisig,
      ownerKind,
      escrow: {
        openTimeout: openTimeout.toString(),
        lockTimeout: lockTimeout.toString(),
        maxStakePerPlayer: (await escrow.maxStakePerPlayer()).toString(),
        eip712: { name: "BoardmanEscrow", version: "2" },
      },
      ...(pool
        ? { spectatorPool: { refundGrace: refundGrace.toString(), claimWindow: claimWindow.toString(), maxBettingWindow: String(7 * DAY) } }
        : {}),
    },
    deployedAt: new Date().toISOString(),
    deployer: deployer.address,
    todo: pool
      ? "multisig must call acceptOwnership() on both contracts"
      : "the owner (Safe) must call acceptOwnership() on BoardmanEscrow",
  };
  console.log(JSON.stringify(info, null, 2));

  if (!local || process.env.WRITE_LOCAL_DEPLOYMENT === "1") {
    const out = path.join(__dirname, "../deployments", `boardman_v2_${network.name}.json`);
    fs.writeFileSync(out, JSON.stringify(info, null, 2) + "\n");
    console.log(`Saved ${path.relative(process.cwd(), out)}`);
  }

  if (mainnet) {
    console.log("\nBackend env for the humans realm (set ONLY after the Safe's acceptOwnership):");
    console.log(`BOARDMAN_ESCROW_ADDRESS_ARC_MAINNET=${escrowAddr}`);
    console.log("BOARDMAN_RESOLVER_KEY_MAINNET=<keystore entry name, e.g. resolver_arc_mainnet — never a key>");
    console.log(`(the keystore entry's address must equal V2_RESOLVER ${resolver})`);
    return;
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
