#!/usr/bin/env node
/**
 * Serve the unsigned transaction for Lace wallet signing.
 * Run: node serve.js
 * Open: http://localhost:3456
 */
import http from "http";
import { readFileSync } from "fs";

const PORT = 3456;

const HTML = `<!DOCTYPE html>
<html><head><title>Boardman CIP-0170 Mint</title>
<style>
body{font-family:sans-serif;background:#0a0a0f;color:#fff;padding:2rem;max-width:700px;margin:0 auto}
h1{background:linear-gradient(135deg,#8b5cf6,#06b6d4);-webkit-background-clip:text;-webkit-text-fill-color:transparent}
.card{background:#1a1a2e;border:1px solid #2a2a4a;border-radius:12px;padding:1.5rem;margin:1rem 0}
button{padding:1rem 2rem;border-radius:8px;border:none;font-size:1.1rem;font-weight:600;cursor:pointer;background:linear-gradient(135deg,#8b5cf6,#06b6d4);color:#fff}
button:disabled{opacity:0.5;cursor:not-allowed}
.status{padding:1rem;border-radius:8px;margin-top:1rem;font-family:monospace;white-space:pre-wrap;word-break:break-all}
.ok{background:#0a2a1a;border:1px solid #22c55e;color:#22c55e}
.err{background:#2a0a0a;border:1px solid #ef4444;color:#ef4444}
.info{background:#1a1a3e;border:1px solid #333}
pre{background:#0f0f1f;padding:1rem;border-radius:8px;overflow-x:auto;font-size:0.8rem;max-height:200px;overflow-y:auto}
</style></head><body>
<h1>Boardman — CIP-0170 Agent Identity Mint</h1>
<p>Sign this transaction in your Lace wallet to put the CIP-0170 attestation on Cardano Preview testnet.</p>

<div class="card">
<h2>1. Connect Lace</h2>
<button onclick="connect()" id="btn">Connect Lace Wallet</button>
<div id="s1"></div>
</div>

<div class="card" id="signCard" style="display:none">
<h2>2. Sign & Submit</h2>
<button onclick="signAndSubmit()" id="btn2">Sign in Lace & Submit</button>
<div id="s2"></div>
</div>

<script type="module">
let wallet;
const CBOR = await fetch('/tx').then(r=>r.text());

window.connect = async function() {
  if(!window.cardano?.lace){document.getElementById('s1').innerHTML='<div class="status err">Lace not found</div>';return}
  try{
    wallet=await window.cardano.lace.enable();
    const addrs=await wallet.getUsedAddresses();
    document.getElementById('s1').innerHTML='<div class="status ok">Connected: '+addrs[0].slice(0,20)+'...</div>';
    document.getElementById('signCard').style.display='block';
  }catch(e){document.getElementById('s1').innerHTML='<div class="status err">'+e.message+'</div>'}
}

window.signAndSubmit = async function() {
  const btn=document.getElementById('btn2');
  const s=document.getElementById('s2');
  btn.disabled=true; btn.textContent='Signing...';
  try{
    s.innerHTML='<div class="status info">Waiting for Lace approval...</div>';
    const signed=await wallet.signTx(CBOR.trim());
    s.innerHTML='<div class="status info">Submitting...</div>';
    const hash=await wallet.submitTx(signed);
    s.innerHTML='<div class="status ok">✅ SUCCESS!\\nTx: '+hash+'\\nExplorer: https://preview.cardanoscan.io/transaction/'+hash+'</div>';
  }catch(e){s.innerHTML='<div class="status err">'+e.message+'</div>'}
  btn.disabled=false; btn.textContent='Sign in Lace & Submit';
}
</script></body></html>`;

const server = http.createServer((req, res) => {
  if (req.url === "/tx") {
    try {
      const tx = readFileSync("public/unsigned_tx_hex.txt", "utf8").trim();
      res.writeHead(200, { "Content-Type": "text/plain" });
      res.end(tx);
    } catch (e) {
      res.writeHead(500);
      res.end("Error: " + e.message);
    }
  } else {
    res.writeHead(200, { "Content-Type": "text/html" });
    res.end(HTML);
  }
});

server.listen(PORT, () => {
  console.log(`\n🌐 Open http://localhost:${PORT} in your browser`);
  console.log(`   Click "Connect Lace" → then "Sign in Lace & Submit"\n`);
});
