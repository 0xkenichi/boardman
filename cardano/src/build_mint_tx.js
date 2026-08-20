#!/usr/bin/env node
/**
 * Build unsigned CIP-0170 metadata transaction on Cardano Preview testnet.
 * Outputs CBOR hex that can be signed via Lace CIP-30.
 */
import * as CSL from "@emurgo/cardano-serialization-lib-nodejs";
import { getAddressUtxos, getLatestBlock } from "./blockfrost.js";
import { writeFileSync } from "fs";

const WALLET = "addr_test1qrl34z7w7h50x02uhv99874u65xh76c50wafmxsukpkdxx9xrsrcsuzu8kvd6mtr5uwqjwu4t2ud58tg390gzfvxks9qh5acvj";
const NAME = process.argv.includes("--agent") ? process.argv[process.argv.indexOf("--agent") + 1] : "raja";
const PNL = parseFloat(process.argv.includes("--pnl") ? process.argv[process.argv.indexOf("--pnl") + 1] : "0");
const MATCHES = parseInt(process.argv.includes("--matches") ? process.argv[process.argv.indexOf("--matches") + 1] : "0");

const AGENTS = {
  raja: { name: "Raja", arc: "0xDB131a4B88ACA79c29D5aDF3C3Df033954D36029", games: ["agentic.chess_standard"], desc: "Aggressive tactical chess agent" },
  nero: { name: "Nero", arc: "0xe430C73cF2beD38aBE83DF8309763191624373E1", games: ["agentic.chess_standard"], desc: "Patient positional chess agent" },
};

// Helpers
const t = (s) => CSL.TransactionMetadatum.new_text(String(s).slice(0, 64));
const n = (i) => CSL.TransactionMetadatum.new_int(CSL.Int.new(CSL.BigNum.from_str(String(i))));
const bn = (i) => CSL.BigNum.from_str(String(i));

function buildMeta(agent) {
  const now = new Date().toISOString();

  const perf = CSL.MetadataMap.new();
  perf.insert(t("pnl_usdc"), n(Math.round(PNL * 100)));
  perf.insert(t("matches_played"), n(MATCHES));
  perf.insert(t("last_updated"), t(now));

  const att = CSL.MetadataMap.new();
  att.insert(t("issuer"), t("boardman"));
  att.insert(t("timestamp"), t(now));
  att.insert(t("version"), t("1.0"));

  const games = CSL.MetadataList.new();
  for (const g of agent.games) games.add(t(g));

  const data = CSL.MetadataMap.new();
  data.insert(t("agent_name"), t(agent.name));
  data.insert(t("agent_type"), t("chess"));
  data.insert(t("platform"), t("boardman"));
  data.insert(t("arc_wallet"), t(agent.arc));
  data.insert(t("registered_games"), CSL.TransactionMetadatum.new_list(games));
  data.insert(t("description"), t(agent.desc));
  data.insert(t("performance"), CSL.TransactionMetadatum.new_map(perf));
  data.insert(t("attestation"), CSL.TransactionMetadatum.new_map(att));

  const outer = CSL.MetadataMap.new();
  outer.insert(t("674"), CSL.TransactionMetadatum.new_map(data));
  return CSL.TransactionMetadatum.new_map(outer);
}

async function main() {
  const agent = AGENTS[NAME];
  if (!agent) { console.error("Unknown agent"); process.exit(1); }

  console.log(`\n🏷️  Building CIP-0170 tx for ${agent.name}\n`);

  // 1. UTXOs
  const utxos = await getAddressUtxos(WALLET);
  const u = utxos[0];
  const lovelace = BigInt(u.amount.find(a => a.unit === "lovelace")?.quantity || "0");
  console.log(`UTXO: ${u.tx_hash.slice(0,16)}#${u.output_index} = ${(Number(lovelace)/1e6).toFixed(2)} ADA`);

  // 2. Block + protocol params
  const block = await getLatestBlock();
  const latestSlot = block.slot;

  const feeA = 44; const feeB = 155381;
  const linearFee = CSL.LinearFee.new(bn(feeA), bn(feeB));

  // 3. TransactionBuilder
  const builder = CSL.TransactionBuilder.new(
    linearFee,
    bn(1000000),  // min utxo deposit
    bn(500000000), // pool deposit
    bn(2000000),   // key deposit
    bn(16384),     // max tx size
    bn(10)         // collateral percent
  );

  // Add input
  const addr = CSL.Address.from_bech32(WALLET);
  builder.add_regular_input(addr, u.tx_hash, u.output_index, bn(lovelace));

  // Add output (send everything back to self minus fee)
  const feeEstimate = bn(300000);
  const change = bn(lovelace).checked_sub(feeEstimate);
  builder.add_output(CSL.TransactionOutput.new(addr, CSL.Value.new(change)));

  // Set TTL
  builder.set_ttl_bignum(bn(latestSlot + 7200));

  // Set metadata (label 674)
  const metadata = buildMeta(agent);
  const metaWrap = CSL.GeneralTransactionMetadata.new();
  metaWrap.insert(bn(674), metadata);
  builder.set_metadata(metaWrap);

  console.log(`Metadata: CIP-0170 label 674 ✓`);

  // Build
  const tx = builder.build_tx();
  const cbor = Buffer.from(tx.to_bytes()).toString("hex");

  console.log(`CBOR: ${cbor.length} chars`);
  writeFileSync("public/unsigned_tx_hex.txt", cbor);

  console.log(`\n✅ Saved: cardano/public/unsigned_tx_hex.txt`);
  console.log(`\n📋 To sign in Lace:`);
  console.log(`   1. Open Lace wallet browser extension`);
  console.log(`   2. Press F12 → Console tab`);
  console.log(`   3. Copy-paste this code (replace TX_HEX with the cbor):`);
  console.log(`\n   (async()=>{`);
  console.log(`     const w=await window.cardano.lace.enable();`);
  console.log(`     const hex="TX_HEX_HERE";`);
  console.log(`     const s=await w.signTx(hex);`);
  console.log(`     const h=await w.submitTx(s);`);
  console.log(`     console.log("DONE",h);`);
  console.log(`   })()\n`);
}

main().catch(console.error);
