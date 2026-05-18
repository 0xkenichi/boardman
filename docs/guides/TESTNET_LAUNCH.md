# sideQuest — Testnet → Mainnet Launch Runbook
> Last updated: April 2026 | Network: Base Sepolia → Base Mainnet

---

## Prerequisites

- Node.js 20+
- Python 3.11+
- A funded admin wallet (see Step 1)
- Supabase project created
- Evolution API running + WhatsApp number ready

---

## PHASE 1 — Base Sepolia Testnet

### Step 1: Set Up Admin Wallet

Generate a fresh wallet for testnet (keep separate from any personal funds):

```bash
# Option A: cast (Foundry)
cast wallet new

# Option B: Python
python3 -c "from eth_account import Account; a = Account.create(); print(a.address, a.key.hex())"
```

**Fund with testnet ETH (for gas):**
→ https://www.coinbase.com/faucets/base-ethereum-goerli-faucet
→ https://faucet.quicknode.com/base/sepolia

**Get testnet USDC:**
→ https://faucet.circle.com (select Base Sepolia, request USDC)

---

### Step 2: Configure Environment

```bash
cd backend
cp .env.example .env
```

Fill in `.env`:
```
NETWORK=testnet
ADMIN_PRIVATE_KEY=0x<your_testnet_key>
ADMIN_WALLET_ADDRESS=0x<your_testnet_address>
FEE_RECIPIENT_ADDRESS=0x<your_testnet_address>
RESOLVER_ADDRESS=0x<your_testnet_address>
BASE_SEPOLIA_RPC_URL=https://sepolia.base.org
SUPABASE_URL=https://YOUR_PROJECT.supabase.co
SUPABASE_SERVICE_ROLE_KEY=<key>
```

---

### Step 3: Run DB Migration

In Supabase SQL editor, run:
```
backend/migrations/001_blockchain_schema.sql
```

---

### Step 4: Deploy ClawEscrow to Base Sepolia

```bash
cd contracts
npm install
cp ../backend/.env .env   # reuse the same env file

# Deploy
npm run deploy:testnet
```

You'll see output like:
```
✅ ClawEscrow deployed at: 0xABCD...1234
Add these to your backend .env:
CSC_ADDRESS=0xABCD...1234
CHAIN_ID=84532
```

Copy `CSC_ADDRESS` into `backend/.env`.

**Verify on Basescan (optional but recommended):**
```bash
BASESCAN_API_KEY=<your_key> npm run verify:testnet -- <CONTRACT_ADDRESS> <USDC_ADDRESS> <FEE_RECIPIENT> <RESOLVER>
```

View at: https://sepolia.basescan.org/address/<CONTRACT_ADDRESS>

---

### Step 5: Start the Backend

```bash
cd backend
pip install -r requirements.txt
python main.py
# or via Docker:
docker-compose up -d --build
```

**Check blockchain health:**
```bash
curl http://localhost:8000/health/blockchain
```

Expected:
```json
{
  "status": "ok",
  "network": "testnet",
  "name": "Base Sepolia",
  "connected": true,
  "eth_balance": 0.05,
  "escrow": "0xABCD...1234"
}
```

---

### Step 6: Authenticate WhatsApp

```bash
# Get QR code
curl http://localhost:8080/instance/connect/sidequest

# Or open in browser:
http://localhost:8080/instance/connect/sidequest
```

Scan the QR with your WhatsApp Business number.

Set global webhook in Evolution API admin panel:
- URL: `http://your-backend-host:8000/webhook/evolution`
- Events: `MESSAGES_UPSERT`

---

### Step 7: End-to-End Test

Run the simulation script:
```bash
cd ..
python simulate_full_flow.py
```

Or manually test on WhatsApp:

```
# Test user 1 (creator):
/start
/deposit        ← get deposit address (custodial wallet auto-created)
/balance        ← should show $0.00 initially

# User sends USDC to their deposit address (wait for confirmation)
/balance        ← should show deposited amount

/challenge 5 FIFA

# Test user 2 (opponent):
/bets           ← see open challenges
/match <MATCH_ID>
/balance        ← should show reduced balance

# After playing:
/report <MATCH_ID> 3-1
# (Both users report same score)
# Winner gets notified + $PLAY points
```

---

### Step 8: Testnet Checklist

Before opening to real users:

```
[ ] Contract deployed and verified on sepolia.basescan.org
[ ] /health/blockchain returns "ok"
[ ] WhatsApp instance authenticated
[ ] Evolution webhook configured
[ ] USDC deposit → balance credit working end-to-end
[ ] /challenge → /match → /report → payout working
[ ] /link_wallet command working
[ ] 1% fee deducted correctly (check feeRecipient balance)
[ ] $PLAY points awarded correctly
[ ] Cancellation + refund working
[ ] Dispute → AI mediator → admin resolve working
[ ] Admin wallet has sufficient ETH for ~1000 txs (0.05 ETH is fine for testnet)
```

---

## PHASE 2 — Base Mainnet

**Only proceed after testnet is stable with real users.**

### Pre-Mainnet Checklist

```
[ ] 2+ weeks of stable testnet operation
[ ] No critical bugs or fund loss incidents
[ ] Slither static analysis run: cd contracts && slither contracts/ClawEscrow.sol
[ ] Manual review of all resolve/cancel edge cases
[ ] Admin ETH funded on mainnet (0.1 ETH recommended for 500 deploys + ops)
[ ] Admin wallet private key moved to secrets manager (not .env file)
[ ] FEE_RECIPIENT_ADDRESS set to a secure multisig or separate cold wallet
```

### Mainnet Deploy

```bash
# Update .env
NETWORK=mainnet

# Deploy
cd contracts
npm run deploy:mainnet

# Update CSC_ADDRESS in backend .env to mainnet contract
# Update CHAIN_ID=8453
```

Mainnet USDC: `0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913`

### Mainnet Security Hardening

1. **Private key management** — move `ADMIN_PRIVATE_KEY` to:
   - AWS Secrets Manager / GCP Secret Manager / Doppler
   - Never store in `.env` on a server

2. **Pause circuit breaker** — if anything looks wrong:
   ```bash
   cast send <CSC_ADDRESS> "pause()" --private-key $ADMIN_PRIVATE_KEY --rpc-url https://mainnet.base.org
   ```

3. **Monitor admin ETH balance** — set up alerting if it drops below 0.02 ETH

4. **Monitor escrow balance** — `GET /admin/escrow-balance` should match sum of all locked matches in DB

5. **Max stake** — ClawEscrow enforces $10,000 USDC cap per match. Adjust if needed via contract upgrade.

---

## Useful Commands

```bash
# Check contract on-chain
cast call <CSC_ADDRESS> "contractBalance()(uint256)" --rpc-url https://sepolia.base.org

# Check admin ETH balance
cast balance $ADMIN_WALLET_ADDRESS --rpc-url https://sepolia.base.org

# Send manual resolve (emergency fallback)
cast send <CSC_ADDRESS> "resolveMatch(bytes32,address)" <MATCH_ID_BYTES32> <WINNER_ADDRESS> \
  --private-key $ADMIN_PRIVATE_KEY --rpc-url https://sepolia.base.org

# Pause contract (emergency)
cast send <CSC_ADDRESS> "pause()" --private-key $ADMIN_PRIVATE_KEY --rpc-url https://sepolia.base.org
```

---

## Architecture After Completion

```
User (WhatsApp)
      │
      ▼
Evolution API → backend/api.py
                    │
              ┌─────┴──────────────────┐
              │                        │
        betting_engine.py     transaction_manager.py
              │                        │
        betting_engine_onchain.py      │ polls every 15s
              │                        │
              └──────┬─────────────────┘
                     │
              blockchain_layer.py
                     │
              ClawEscrow.sol (Base Sepolia / Mainnet)
                     │
              USDC held trustlessly in escrow
```
