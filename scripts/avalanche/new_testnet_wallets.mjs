#!/usr/bin/env node
/**
 * Make the throwaway Fuji wallets for the Avalanche proof run.
 *
 * TESTNET ONLY. Writes .fuji/wallets.json (git-ignored, mode 0600) with four
 * fresh random keys, one per role, plus the keystore secret the proof run
 * seals its agent keys with. Prints addresses only. Refuses to overwrite.
 *
 *   node scripts/avalanche/new_testnet_wallets.mjs [.fuji/wallets.json]
 *
 * Roles (deploy_v2.js refuses to give one key two of them):
 *   funder_deployer  deploys the contracts, holds faucet AVAX + USDC, tops up the rest
 *   owner            Ownable2Step owner (an EOA on testnet: V2_OWNER_IS_EOA=1)
 *   treasury         feeRecipient; never signs
 *   resolver         signs createMatch permits and resolveMatch
 */
import { createRequire } from "module";
import crypto from "crypto";
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";

const here = path.dirname(fileURLToPath(import.meta.url));
const require = createRequire(path.join(here, "../../contracts/package.json"));
const { Wallet } = require("ethers");

const out = path.resolve(process.argv[2] || ".fuji/wallets.json");
if (fs.existsSync(out)) {
  console.error(`${out} exists; not overwriting`);
  process.exit(1);
}
fs.mkdirSync(path.dirname(out), { recursive: true, mode: 0o700 });

const roles = ["funder_deployer", "owner", "treasury", "resolver"];
const doc = {
  note: "TESTNET ONLY (Avalanche Fuji 43113). Never send mainnet funds here.",
  created: new Date().toISOString(),
  keystore_secret: crypto.randomBytes(32).toString("hex"),
  wallets: {},
};
for (const r of roles) {
  const w = Wallet.createRandom();
  doc.wallets[r] = { address: w.address, private_key: w.privateKey };
}
fs.writeFileSync(out, JSON.stringify(doc, null, 2) + "\n", { mode: 0o600 });
for (const r of roles) console.log(`${r.padEnd(16)} ${doc.wallets[r].address}`);
console.log(`saved ${path.relative(process.cwd(), out)}`);
