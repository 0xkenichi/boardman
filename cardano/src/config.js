import { readFileSync } from "fs";
import { resolve, dirname } from "path";
import { fileURLToPath } from "url";

const __dirname = dirname(fileURLToPath(import.meta.url));

// Load .env if present
try {
  const envPath = resolve(__dirname, "../.env");
  const env = readFileSync(envPath, "utf8");
  for (const line of env.split("\n")) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#")) continue;
    const eq = trimmed.indexOf("=");
    if (eq < 0) continue;
    const key = trimmed.slice(0, eq).trim();
    const val = trimmed.slice(eq + 1).trim();
    if (val && !process.env[key]) process.env[key] = val;
  }
} catch {
  // .env not found — use process.env
}

export const BLOCKFROST_PROJECT_ID = process.env.BLOCKFROST_PROJECT_ID;
export const BLOCKFROST_BASE_URL =
  process.env.BLOCKFROST_BASE_URL || "https://cardano-preview.blockfrost.io/api/v0";
export const WALLET_MNEMONIC = process.env.WALLET_MNEMONIC;
export const FEE_RECIPIENT_ADDRESS = process.env.FEE_RECIPIENT_ADDRESS;
export const NETWORK = process.env.CARDANO_NETWORK || "preview";

if (!BLOCKFROST_PROJECT_ID && process.argv[1]?.endsWith("test.js") === false) {
  console.error("❌ BLOCKFROST_PROJECT_ID not set. Copy .env.example → .env and add your key.");
  process.exit(1);
}
