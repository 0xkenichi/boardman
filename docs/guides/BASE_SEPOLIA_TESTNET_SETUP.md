# Base Sepolia Testnet Setup Guide

## Prerequisites
- Base Sepolia USDC testnet tokens (faucet below)
- Admin wallet with ETH for gas (~0.2 ETH)
- Private key for admin wallet

## Network Configuration
- **Network**: Base Sepolia Testnet
- **Chain ID**: 84532
- **RPC URL**: https://sepolia.base.org
- **USDC Address**: 0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913
- **Block Explorer**: https://sepolia.basescan.org/

## Step 1: Get Test USDC

### Option A: Official Faucets
1. **Base Sepolia Faucet**: https://www.basescan.org/faucet
2. **QuickNode Faucet**: https://faucet.quicknode.com/base/sepolia
3. **Get ETH first**: https://sepoliafaucet.com/

### Option B: Manual USDC Mint (if deployed locally)
```bash
# Using cast (if ClawEscrow is deployed)
cast send 0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913 \
  "approve(address,uint256)" \
  0x[YOUR_ESCROW] \
  1000000000000000000
```

## Step 2: Configure Environment

Verify `.env` has:
```env
RPC_URL=https://sepolia.base.org
CHAIN_ID=84532
ADMIN_PRIVATE_KEY=0x[your_key]
USDC_ADDRESS=0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913
CSC_ADDRESS=0x[deployed_escrow_address]
ADMIN_WALLET_ADDRESS=0x[your_address]
```

## Step 3: Deploy ClawEscrow (if not done)

```bash
cd /Users/mac/Agents\ /ClawStation/contracts

# Using Foundry
forge build
forge create src/ClawEscrow.sol:ClawEscrow \
  --rpc-url https://sepolia.base.org \
  --private-key $ADMIN_PRIVATE_KEY \
  --constructor-args 0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913

# or using Hardhat
npx hardhat run scripts/deploy.js --network base-sepolia
```

**After deployment**: Update `.env` with `CSC_ADDRESS`

## Step 4: Approve USDC Spending

Before running tests, approve the escrow contract to spend your USDC:

```bash
cast send 0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913 \
  "approve(address,uint256)" \
  0x[ESCROW_ADDRESS] \
  100000000000000000000 \
  --rpc-url https://sepolia.base.org \
  --private-key $ADMIN_PRIVATE_KEY
```

Or check approval:
```bash
cast call 0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913 \
  "allowance(address,address)" \
  0x[YOUR_ADDRESS] 0x[ESCROW_ADDRESS] \
  --rpc-url https://sepolia.base.org
```

## Step 5: Start Local Testing

### 1. **Start Backend**
```bash
cd /Users/mac/Agents\ /ClawStation/backend
python -m pytest tests/test_blockchain_base_sepolia.py -v
```

### 2. **Run Blockchain Agent**
```bash
python blockchain_whatsapp_agent.py
```

### 3. **Test WhatsApp Commands**
Use your WhatsApp bot number and test:
```
/blockchain_balance
/blockchain_pool_create 0 10.5
/blockchain_pool_join 1
/blockchain_history
/blockchain_status 0x[hash]
```

### 4. **Monitor Transactions**
- Check in real-time: https://sepolia.basescan.org/
- View your wallet: https://sepolia.basescan.org/address/0x[YOUR_ADDRESS]

## Useful Commands

### Check Balance
```bash
cast call 0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913 \
  "balanceOf(address)" 0x[YOUR_ADDRESS] \
  --rpc-url https://sepolia.base.org
```

### Get Gas Price
```bash
cast gas-price --rpc-url https://sepolia.base.org
```

### View Pool Details
```bash
cast call 0x[ESCROW_ADDRESS] \
  "getPoolPlayers(uint256)" 0 \
  --rpc-url https://sepolia.base.org
```

## Transaction Monitoring

All transactions are logged in Supabase `blockchain_transactions` table:
- `user_id`: WhatsApp ID
- `pool_id`: Escrow pool ID
- `tx_hash`: Transaction hash
- `status`: pending/confirmed/failed
- `amount`: USDC amount

Watch status updates:
```sql
SELECT * FROM blockchain_transactions
WHERE user_id = 'whatsapp_id'
ORDER BY created_at DESC;
```

## Troubleshooting

### "Insufficient funds for gas"
- Need ETH, not just USDC
- Get ETH from: https://sepoliafaucet.com/

### "USDC transfer failed / Allowance exceeded"
- Approve escrow contract first (Step 4)
- Check allowance didn't exceed USDC balance

### "Pool not found"
- Ensure pool was created and started
- Check pool ID in explorer

### WhatsApp Bot Not Responding
- Check Evolution API is running: `curl http://localhost:8080/health`
- Verify webhook URL in .env
- Check logs: `tail -f backend/logs/blockchain.log`

## Moving to Mainnet

Once tests pass locally:
1. Update RPC to: `https://mainnet.base.org`
2. Update USDC to mainnet address
3. Deploy new ClawEscrow on mainnet
4. Fund admin wallet with real ETH
5. Update .env with mainnet contract address
6. Run full test suite before going live

## Safety Checklist

- [ ] Test with small USDC amounts first (1-10 USDC)
- [ ] Verify transaction on BaseScan before each action
- [ ] Keep private key secure, never commit to git
- [ ] Set up spending limits for bot wallet
- [ ] Monitor transaction logs daily
- [ ] Have rollback plan ready
