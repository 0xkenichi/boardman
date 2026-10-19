/**
 * Pre-deploy checks for deploy_v2.js (audit 2026-10 L-04). Pure reads; throws
 * on anything that would make the deployment unsafe or unusable.
 *
 * - arcMainnet must really be chain 5042 (the RPC URL and chain id are both
 *   env-overridable in hardhat.config.js).
 * - The USDC address must be a contract whose decimals() is 6: MIN_STAKE,
 *   MAX_STAKE and every fee cap assume 6 decimals.
 * - Off-local, the owner multisig must already be deployed on this chain
 *   (a Safe address from another chain would never call acceptOwnership).
 * - The resolver must be an EOA: createMatch verifies the permit with plain
 *   ECDSA, so a contract resolver could never sign one.
 * - Mainnets skip SpectatorPool unless V2_DEPLOY_POOL=1: spectator betting is
 *   off on mainnet until counsel signs off, and deposit() is permissionless
 *   once any book is open.
 */
export const ARC_MAINNET_CHAIN_ID = 5042n;
export const MAINNETS = new Set(["arcMainnet", "baseMainnet"]);

const ERC20_DECIMALS = ["function decimals() view returns (uint8)"];

export async function preflight(ethers, { networkName, local, usdc, multisig, treasury, resolver, env = process.env }) {
  const warnings = [];
  const { chainId } = await ethers.provider.getNetwork();
  if (networkName === "arcMainnet" && chainId !== ARC_MAINNET_CHAIN_ID) {
    throw new Error(`arcMainnet RPC reports chain id ${chainId}, expected ${ARC_MAINNET_CHAIN_ID}`);
  }

  const code = async (a) => ethers.provider.getCode(a);
  if ((await code(usdc)) === "0x") throw new Error(`USDC ${usdc} has no code on chain ${chainId}`);
  let decimals;
  try {
    decimals = await new ethers.Contract(usdc, ERC20_DECIMALS, ethers.provider).decimals();
  } catch (e) {
    throw new Error(`USDC ${usdc} has no decimals(); not a USDC token`);
  }
  if (Number(decimals) !== 6) throw new Error(`USDC ${usdc} has ${decimals} decimals; v2 assumes 6`);

  if ((await code(resolver)) !== "0x") {
    throw new Error(`resolver ${resolver} is a contract; permits are plain ECDSA, so it must be an EOA`);
  }
  if (!local) {
    if ((await code(multisig)) === "0x") {
      throw new Error(`owner multisig ${multisig} has no code on chain ${chainId}; deploy the Safe here first`);
    }
    if ((await code(treasury)) === "0x") warnings.push(`treasury ${treasury} is an EOA; a Safe is recommended`);
  }

  const deployPool = !MAINNETS.has(networkName) || env.V2_DEPLOY_POOL === "1";
  if (!deployPool) warnings.push(`SpectatorPool skipped on ${networkName}; set V2_DEPLOY_POOL=1 to deploy it`);
  return { chainId, deployPool, warnings };
}
