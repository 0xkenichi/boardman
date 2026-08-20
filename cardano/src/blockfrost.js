/**
 * Blockfrost API helper — thin wrapper around fetch for Cardano Preview testnet.
 */
import { BLOCKFROST_PROJECT_ID, BLOCKFROST_BASE_URL } from "./config.js";

const headers = { project_id: BLOCKFROST_PROJECT_ID };

async function request(path, opts = {}) {
  const url = `${BLOCKFROST_BASE_URL}${path}`;
  const res = await fetch(url, { headers, ...opts });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`Blockfrost ${res.status}: ${body}`);
  }
  return res.json();
}

// ── Chain info ──────────────────────────────────────────────
export const getLatestBlock = () => request("/blocks/latest");
export const getNetworkInfo = () => request("/network");

// ── Addresses ───────────────────────────────────────────────
export const getAddressBalance = (addr) =>
  request(`/addresses/${addr}/balance`);
export const getAddressUtxos = (addr) =>
  request(`/addresses/${addr}/utxos`);
export const getAddressTransactions = (addr) =>
  request(`/addresses/${addr}/transactions`);

// ── Transactions ────────────────────────────────────────────
export const getTx = (txHash) => request(`/txs/${txHash}`);
export const getTxUtxos = (txHash) => request(`/txs/${txHash}/utxos`);
export const getTxMetadata = (txHash) => request(`/txs/${txHash}/metadata`);
export const submitTx = (cbor) =>
  request("/tx/submit", {
    method: "POST",
    headers: { ...headers, "Content-Type": "application/cbor" },
    body: Buffer.from(cbor, "hex"),
  });

// ── Assets ──────────────────────────────────────────────────
export const getAsset = (assetId) => request(`/assets/${assetId}`);
export const getAssetAddresses = (assetId) =>
  request(`/assets/${assetId}/addresses`);
export const getPolicyAssets = (policyId) =>
  request(`/policy/${policyId}/assets`);

// ── Scripts ─────────────────────────────────────────────────
export const getScript = (scriptHash) => request(`/scripts/${scriptHash}`);
export const getScriptUtxos = (scriptHash) =>
  request(`/scripts/${scriptHash}/utxos`);
export const submitTxCbor = (cborHex) =>
  request("/tx/submit", {
    method: "POST",
    headers: { ...headers, "Content-Type": "application/cbor" },
    body: Buffer.from(cborHex, "hex"),
  });

// ── Metadata ────────────────────────────────────────────────
export const getMetadataLabels = () => request("/metadata/labels");

export default {
  getLatestBlock,
  getNetworkInfo,
  getAddressBalance,
  getAddressUtxos,
  getAddressTransactions,
  getTx,
  getTxUtxos,
  getTxMetadata,
  submitTx: submitTxCbor,
  getAsset,
  getAssetAddresses,
  getPolicyAssets,
  getScript,
  getScriptUtxos,
};
