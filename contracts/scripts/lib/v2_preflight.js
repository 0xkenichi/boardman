/**
 * Pre-deploy checks for deploy_v2.js (audit 2026-10 L-04). Pure reads; throws
 * on anything that would make the deployment unsafe or unusable.
 *
 * - arcMainnet must really be chain 5042 (deploy_v2.js also checks every
 *   known network's chain id against the RPC).
 * - The USDC address must be a contract whose decimals() is 6: MIN_STAKE,
 *   MAX_STAKE, the stake cap and every fee cap assume 6 decimals.
 * - Off-local, the owner must already have code on this chain (a Safe address
 *   from another chain would never call acceptOwnership), unless the founder
 *   EOA fallback is declared with V2_OWNER_IS_EOA=1.
 * - The resolver must be an EOA: createMatch verifies the permit with plain
 *   ECDSA, so a contract resolver could never sign one.
 * - Mainnets never get a SpectatorPool (spectator betting stays on testnet;
 *   deposit() is permissionless once a book is open). No override.
 */
export const ARC_MAINNET_CHAIN_ID = 5042n;
export const MAINNETS = new Set(["arcMainnet", "baseMainnet"]);

const ERC20_DECIMALS = ["function decimals() view returns (uint8)"];

export async function preflight(
  ethers,
  { networkName, local, mainnet, usdc, multisig, treasury, resolver, env = process.env }
) {
  const warnings = [];
  const isMainnet = mainnet ?? MAINNETS.has(networkName);
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

  let ownerKind = "local test account";
  if (!local) {
    if ((await code(multisig)) !== "0x") {
      ownerKind = "contract (Safe)";
    } else if (env.V2_OWNER_IS_EOA === "1") {
      ownerKind = "EOA (founder-wallet fallback)";
      warnings.push(`owner ${multisig} is an EOA (V2_OWNER_IS_EOA=1); move ownership to a Safe as soon as one exists`);
    } else {
      throw new Error(
        `owner multisig ${multisig} has no code on chain ${chainId}; deploy the Safe here first, ` +
          "or set V2_OWNER_IS_EOA=1 to accept the founder-wallet fallback (see the runbook)"
      );
    }
    if ((await code(treasury)) === "0x") warnings.push(`treasury ${treasury} is an EOA; a Safe is recommended`);
  }

  const deployPool = !isMainnet;
  return { chainId, deployPool, ownerKind, warnings };
}
