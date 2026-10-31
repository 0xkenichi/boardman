import "@nomicfoundation/hardhat-toolbox";
import dotenv from "dotenv";
import path from "path";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

dotenv.config({ path: path.join(__dirname, "../.env") });
dotenv.config();

const ADMIN_PRIVATE_KEY = process.env.ADMIN_PRIVATE_KEY || "0x" + "0".repeat(64);

/** @type import('hardhat/config').HardhatUserConfig */
export default {
  solidity: {
    version: "0.8.20",
    settings: {
      optimizer: {
        enabled: true,
        runs: 200,
      },
      viaIR: true,
    },
  },

  paths: {
    sources: "./contracts",
    artifacts: "./artifacts",
  },

  networks: {
    // ── Local development ──────────────────────────────────────────────
    // HARDHAT_CHAIN_ID=43113 with `hardhat node --fork <Fuji RPC>` rehearses
    // the Avalanche proof run on a local Fuji fork (scripts/avalanche/README.md).
    hardhat: {
      chainId: Number(process.env.HARDHAT_CHAIN_ID || 31337),
    },

    // ── Arc Testnet (Boardman primary test path — USDC gas) ────────────
    arcTestnet: {
      url: process.env.ARC_TESTNET_RPC_URL || process.env.ARC_RPC_URL || "https://rpc.testnet.arc.io",
      chainId: Number(process.env.ARC_TESTNET_CHAIN_ID || 5042002),
      accounts: [ADMIN_PRIVATE_KEY],
    },

    // ── Arc Mainnet (live 2026-09-16) — REAL MONEY ─────────────────────
    // Chain id 5042 (0x13b2) and RPC per https://docs.arc.io/arc/references/connect-to-arc
    // Gas is USDC (18-decimal native); min base fee 20 gwei (EIP-1559).
    // The chain id is pinned (no env override) so a wrong RPC can't receive a
    // mainnet deploy. Deployer = a THROWAWAY key typed blind into
    // MAINNET_DEPLOYER_KEY for one shell session (docs/MAINNET_HUMANS_CUTOVER.md);
    // it never owns, resolves or receives fees. Never ADMIN_PRIVATE_KEY.
    arcMainnet: {
      url: process.env.ARC_MAINNET_RPC_URL || "https://rpc.mainnet.arc.io",
      chainId: 5042,
      accounts: process.env.MAINNET_DEPLOYER_KEY ? [process.env.MAINNET_DEPLOYER_KEY] : [],
    },

    // ── Avalanche Fuji (C-Chain testnet, 43113) ────────────────────────
    // Gas is AVAX; stakes are Circle's Fuji USDC (0x5425…Bc65, 6 decimals).
    // FUJI_DEPLOYER_KEY is a throwaway testnet key that holds none of the
    // v2 roles (scripts/avalanche/README.md).
    avalancheFuji: {
      url: process.env.AVALANCHE_FUJI_RPC_URL || "https://api.avax-test.network/ext/bc/C/rpc",
      chainId: 43113,
      accounts: [process.env.FUJI_DEPLOYER_KEY || ADMIN_PRIVATE_KEY],
    },

    // ── Avalanche C-Chain mainnet (43114) — REAL MONEY ─────────────────
    // Not deployed. Same rules as arcMainnet: v2 escrow only, Safe owner,
    // throwaway MAINNET_DEPLOYER_KEY typed blind, never ADMIN_PRIVATE_KEY.
    avalancheMainnet: {
      url: process.env.AVALANCHE_MAINNET_RPC_URL || "https://api.avax.network/ext/bc/C/rpc",
      chainId: 43114,
      accounts: process.env.MAINNET_DEPLOYER_KEY ? [process.env.MAINNET_DEPLOYER_KEY] : [],
    },

    // ── Base Sepolia (testnet) ─────────────────────────────────────────
    baseSepolia: {
      url: process.env.BASE_SEPOLIA_RPC_URL || "https://sepolia.base.org",
      chainId: 84532,
      accounts: [ADMIN_PRIVATE_KEY],
    },

    // ── Base Mainnet ───────────────────────────────────────────────────
    baseMainnet: {
      url: process.env.BASE_MAINNET_RPC_URL || "https://mainnet.base.org",
      chainId: 8453,
      accounts: [ADMIN_PRIVATE_KEY],
    },
  },

  verify: {
    etherscan: {
      apiKey: {
        baseSepolia: process.env.BASESCAN_API_KEY || "",
        baseMainnet: process.env.BASESCAN_API_KEY || "",
        // Arc's explorer needs no key; hardhat-verify wants a non-empty string.
        arcMainnet: process.env.ARC_EXPLORER_API_KEY || "arc",
        // Snowtrace runs on Routescan, which needs no key either.
        avalancheFuji: process.env.SNOWTRACE_API_KEY || "snowtrace",
        avalancheMainnet: process.env.SNOWTRACE_API_KEY || "snowtrace",
      },
      customChains: [
        {
          // UNVERIFIED API path: Safe's chain config uses an Etherscan-style
          // https://explorer.arc.io/api (safe-config.safe.global/api/v1/chains/5042).
          // If verify fails, verify in the explorer UI (circlefin/arc-node#210).
          network: "arcMainnet",
          chainId: 5042,
          urls: {
            apiURL: "https://explorer.arc.io/api",
            browserURL: "https://explorer.arc.io",
          },
        },
        {
          network: "avalancheFuji",
          chainId: 43113,
          urls: {
            apiURL: "https://api.routescan.io/v2/network/testnet/evm/43113/etherscan",
            browserURL: "https://testnet.snowtrace.io",
          },
        },
        {
          network: "avalancheMainnet",
          chainId: 43114,
          urls: {
            apiURL: "https://api.routescan.io/v2/network/mainnet/evm/43114/etherscan",
            browserURL: "https://snowtrace.io",
          },
        },
        {
          network: "baseSepolia",
          chainId: 84532,
          urls: {
            apiURL: "https://api-sepolia.basescan.org/api",
            browserURL: "https://sepolia.basescan.org",
          },
        },
        {
          network: "baseMainnet",
          chainId: 8453,
          urls: {
            apiURL: "https://api.basescan.org/api",
            browserURL: "https://basescan.org",
          },
        },
      ],
    },
  },

  gasReporter: {
    enabled: process.env.REPORT_GAS === "true",
    currency: "USD",
  },
};
