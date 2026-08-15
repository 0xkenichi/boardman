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
    hardhat: {
      chainId: 31337,
    },

    // ── Arc Testnet (Boardman primary test path — USDC gas) ────────────
    arcTestnet: {
      url: process.env.ARC_TESTNET_RPC_URL || process.env.ARC_RPC_URL || "https://rpc.testnet.arc.network",
      chainId: Number(process.env.ARC_TESTNET_CHAIN_ID || 5042002),
      accounts: [ADMIN_PRIVATE_KEY],
    },

    // ── Arc Mainnet (Sept 16 launch) ───────────────────────────────────
    arcMainnet: {
      url: process.env.ARC_MAINNET_RPC_URL || "https://rpc.arc.network",
      chainId: Number(process.env.ARC_MAINNET_CHAIN_ID || 5042001),
      accounts: [ADMIN_PRIVATE_KEY],
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
      },
      customChains: [
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
