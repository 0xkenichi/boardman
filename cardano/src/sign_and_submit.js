#!/usr/bin/env node
/**
 * Sign and submit CIP-0170 metadata tx using our generated wallet.
 */
import * as CSL from "@emurgo/cardano-serialization-lib-nodejs";
import { getAddressUtxos, getLatestBlock, submitTx } from "./blockfrost.js";
import { readFileSync } from "fs";

const wallet = JSON.parse(readFileSync("public/wallet.key", "utf8"));
const addr = CSL.Address.from_bech32(wallet.address);
const privKey = CSL.PrivateKey.from_hex(wallet.privKey);
const pubKey = privKey.to_public();
const keyHash = pubKey.hash();

console.log("Address:", wallet.address);

const utxos = await getAddressUtxos(wallet.address);
const u = utxos[0];
const lovelace = BigInt(u.amount.find(a => a.unit === "lovelace").quantity);
console.log("UTXO:", u.tx_hash.slice(0,16)+"#"+u.output_index, (Number(lovelace)/1e6).toFixed(2), "ADA");

const cfg = CSL.TransactionBuilderConfigBuilder.new()
  .fee_algo(CSL.LinearFee.new(CSL.BigNum.from_str("44"), CSL.BigNum.from_str("155381")))
  .pool_deposit(CSL.BigNum.from_str("500000000"))
  .key_deposit(CSL.BigNum.from_str("2000000"))
  .coins_per_utxo_byte(CSL.BigNum.from_str("4310"))
  .max_value_size(5000)
  .max_tx_size(16384)
  .build();

const builder = CSL.TransactionBuilder.new(cfg);
builder.add_key_input(
  keyHash,
  CSL.TransactionInput.new(CSL.TransactionHash.from_hex(u.tx_hash), u.output_index),
  CSL.Value.new(CSL.BigNum.from_str(String(lovelace)))
);
builder.add_output(CSL.TransactionOutput.new(addr, CSL.Value.new(CSL.BigNum.from_str("2000000"))));

const block = await getLatestBlock();
builder.set_ttl_bignum(CSL.BigNum.from_str(String(block.slot + 7200)));
builder.add_required_signer(keyHash);

// CIP-0170 Metadata (label 674)
const t = (s) => CSL.TransactionMetadatum.new_text(String(s).slice(0, 64));
const n = (i) => CSL.TransactionMetadatum.new_int(CSL.Int.new(CSL.BigNum.from_str(String(i))));
const now = new Date().toISOString();

const perf = CSL.MetadataMap.new();
perf.insert(t("pnl_usdc"), n(0));
perf.insert(t("matches_played"), n(0));
perf.insert(t("last_updated"), t(now));

const att = CSL.MetadataMap.new();
att.insert(t("issuer"), t("boardman"));
att.insert(t("timestamp"), t(now));
att.insert(t("version"), t("1.0"));

const data = CSL.MetadataMap.new();
data.insert(t("agent_name"), t("Raja"));
data.insert(t("agent_type"), t("chess"));
data.insert(t("platform"), t("boardman"));
data.insert(t("arc_wallet"), t("0xDB131a4B88ACA79c29D5aDF3C3Df033954D36029"));
data.insert(t("description"), t("Aggressive tactical chess agent"));
data.insert(t("performance"), CSL.TransactionMetadatum.new_map(perf));
data.insert(t("attestation"), CSL.TransactionMetadatum.new_map(att));

const outer = CSL.MetadataMap.new();
outer.insert(t("674"), CSL.TransactionMetadatum.new_map(data));
const metaWrap = CSL.GeneralTransactionMetadata.new();
metaWrap.insert(CSL.BigNum.from_str("674"), CSL.TransactionMetadatum.new_map(outer));
builder.set_metadata(metaWrap);
builder.add_change_if_needed(addr);

const tx = builder.build_tx();
console.log("Fee:", tx.body().fee().to_str(), "lovelace");

// Sign: Blake2b-256 hash of the transaction body
const blake2b = (await import("blake2b")).default;
const bodyBytes = tx.body().to_bytes();
const txHashBuf = Buffer.from(blake2b(32).update(Buffer.from(bodyBytes)).digest());
const signature = privKey.sign(txHashBuf);

const witness = CSL.TransactionWitnessSet.new();
const vkw = CSL.Vkeywitnesses.new();
vkw.add(CSL.Vkeywitness.new(CSL.Vkey.new(pubKey), signature));
witness.set_vkeys(vkw);

const signedTx = CSL.Transaction.new(tx.body(), witness, tx.auxiliary_data());
const cbor = Buffer.from(signedTx.to_bytes()).toString("hex");

console.log("Submitting...");
try {
  const hash = await submitTx(cbor);
  console.log("\n✅ SUCCESS!");
  console.log("Tx Hash:", hash);
  console.log("Explorer: https://preview.cardanoscan.io/transaction/" + hash);
  console.log("Metadata: CIP-0170 label 674 (agent identity attestation)");
} catch (e) {
  console.error("\n❌ Submit failed:", e.message);
  console.error("Full error:", JSON.stringify(e));
}
