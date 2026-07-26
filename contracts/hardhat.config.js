require("@nomicfoundation/hardhat-toolbox");
require("dotenv").config();

const ADMIN_PRIVATE_KEY = process.env.ADMIN_PRIVATE_KEY || "0x" + "0".repeat(64);

/** @type import('hardhat/config').HardhatUserConfig */
module.exports = {
  solidity: {
    version: "0.8.20",
    settings: {
      optimizer: {
        enabled: true,
        runs: 200,
      },
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

    // ── Base Sepolia (testnet) ─────────────────────────────────────────
    baseSepolia: {
      url: process.env.BASE_SEPOLIA_RPC_URL || "https://sepolia.base.org",
      chainId: 84532,
      accounts: [ADMIN_PRIVATE_KEY],
      gasPrice: "auto",
    },

    // ── Base Mainnet ───────────────────────────────────────────────────
    baseMainnet: {
      url: process.env.BASE_MAINNET_RPC_URL || "https://mainnet.base.org",
      chainId: 8453,
      accounts: [ADMIN_PRIVATE_KEY],
      gasPrice: "auto",
    },
  },

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

  gasReporter: {
    enabled: process.env.REPORT_GAS === "true",
    currency: "USD",
  },
};
