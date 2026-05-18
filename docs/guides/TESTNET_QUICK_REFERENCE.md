# Base Sepolia Testnet - Quick Reference

## 🚀 Start Testing (2 minutes)

```bash
cd /Users/mac/Agents\ /ClawStation/backend
python3 run_testnet_now.py
```

This validates everything and guides you through first test.

---

## ⚡ Essential Commands

### Get Testnets Tokens
```bash
# ETH Sepolia (for gas)
https://sepoliafaucet.com/

# USDC Base Sepolia
https://www.basescan.org/faucet
```

### Check USDC Balance
```bash
cast call 0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913 \
  "balanceOf(address)" 0x[YOUR_ADDRESS] \
  --rpc-url https://sepolia.base.org
```

### Approve USDC to Escrow
```bash
cast send 0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913 \
  "approve(address,uint256)" \
  0x[ESCROW_ADDRESS] \
  100000000000000000000 \
  --rpc-url https://sepolia.base.org \
  --private-key $ADMIN_PRIVATE_KEY
```

### Start Backend
```bash
cd /Users/mac/Agents\ /ClawStation/backend
python3 api.py
```

### Start WhatsApp Bot
```bash
cd /Users/mac/Agents\ /ClawStation/backend
python3 blockchain_whatsapp_agent.py
```

### Start Evolution API
```bash
docker-compose up evolution
```

---

## 📱 WhatsApp Bot Commands

| Command | Example | What it does |
|---------|---------|----------------|
| `/blockchain_balance` | `/blockchain_balance` | Show USDC + ETH balance |
| `/blockchain_pool_create` | `/blockchain_pool_create 0 10.50` | Create 1v1 pool with 10.50 USDC fee |
| `/blockchain_pool_join` | `/blockchain_pool_join 1` | Join pool ID 1 |
| `/blockchain_history` | `/blockchain_history` | Show all your transactions |
| `/blockchain_status` | `/blockchain_status 0x123...` | Check transaction status |

---

## 🔍 Monitoring

### View Wallet on BaseScan
```
https://sepolia.basescan.org/address/0x[YOUR_ADDRESS]
```

### View Contract
```
https://sepolia.basescan.org/address/0x[ESCROW_ADDRESS]
```

### Check Pool Status (cast)
```bash
cast call 0x[ESCROW_ADDRESS] \
  "getPoolPlayers(uint256)" 0 \
  --rpc-url https://sepolia.base.org
```

### Watch Contract Events
```bash
cast logs \
  --address 0x[ESCROW_ADDRESS] \
  --rpc-url https://sepolia.base.org \
  --watch
```

---

## 💻 Environment Variables

Must be in `/backend/.env`:

```env
# Network
RPC_URL=https://sepolia.base.org
CHAIN_ID=84532

# Tokens
USDC_ADDRESS=0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913
CSC_ADDRESS=0x[your_escrow_address]

# Wallet
ADMIN_PRIVATE_KEY=0x[your_private_key]
ADMIN_WALLET_ADDRESS=0x[your_address]

# WhatsApp
EVOLUTION_API_URL=http://localhost:8080
EVOLUTION_INSTANCE=ClawStation

# Database
SUPABASE_SERVICE_KEY=...
```

---

## 🧪 Test Scenarios

### Scenario 1: Create Pool
```
User: /blockchain_pool_create 0 5.0
Bot:  "Create 1v1 with 5 USDC? [APPROVE] [REJECT]"
User: Clicks APPROVE
Bot:  "⏳ Creating..." → "✅ Pool ID: 0"
```

### Scenario 2: Join Pool
```
User: /blockchain_pool_join 0
Bot:  "Join pool 0 with 5 USDC? [APPROVE] [REJECT]"
User: Clicks APPROVE
Bot:  "✅ Joined pool 0"
```

### Scenario 3: Check History
```
User: /blockchain_history
Bot:  "1. Create Pool (5 USDC) ✅ Confirmed
       2. Join Pool (5 USDC) ✅ Confirmed"
```

---

## ⚠️ Common Issues

| Problem | Solution |
|---------|----------|
| "Insufficient funds" | Need more ETH - get from https://sepoliafaucet.com/ |
| "Allowance exceeded" | Run `approve_usdc(1000)` in blockchain_layer.py |
| "RPC timeout" | Use different RPC: `https://base-sepolia.publicnode.com` |
| WhatsApp not responding | Check Evolution API: `curl http://localhost:8080/health` |
| Transaction stuck | Increase gas price in `blockchain_layer.py` |

---

## 📊 Transaction Costs

**Estimate on Base Sepolia** (actual varies):

- Create Pool: ~0.001 ETH (~$2.50)
- Join Pool: ~0.0008 ETH (~$2)
- Resolve Pool: ~0.002 ETH (~$5)

**Tip**: Always have 0.2+ ETH for gas

---

## 🔄 Moving to Mainnet

Once testing is done:

```bash
# 1. Update .env
RPC_URL=https://mainnet.base.org
CHAIN_ID=8453

# 2. Deploy new ClawEscrow on mainnet
# 3. Update CSC_ADDRESS in .env
# 4. Fund wallet with ~1 ETH
# 5. Run test suite again
# 6. Start with small amounts ($10-50)
```

---

## 📚 Full Guides

- **Setup**: `BASE_SEPOLIA_TESTNET_SETUP.md`
- **Testing**: `LOCAL_TESTING_GUIDE.md`
- **Integration**: `backend/BLOCKCHAIN_WHATSAPP_INTEGRATION.md`

---

## 🎯 Checklist Before Mainnet

- [ ] Created pools ✅
- [ ] Joined pools ✅
- [ ] Received transaction confirmations in <30s
- [ ] All transactions show on BaseScan
- [ ] WhatsApp history shows correct amounts
- [ ] No funds lost
- [ ] Gas estimates accurate
- [ ] Error handling works
- [ ] Tested with $50+ worth of USDC
