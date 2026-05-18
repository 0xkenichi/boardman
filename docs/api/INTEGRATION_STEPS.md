# Integration Steps: Blockchain + WhatsApp Agent

Follow these steps to integrate the blockchain + WhatsApp agent into your existing ClawStation backend.

## Step 1: Add to `api.py` (Main FastAPI App)

At the top of `backend/api.py`, add:

```python
from blockchain_whatsapp_agent import BlockchainWhatsAppAgent
from blockchain_whatsapp_commands import BlockchainWhatsAppCommands
from blockchain_api_endpoints import router as blockchain_router, init_blockchain_routes
from transaction_manager import TransactionManager
```

In the app initialization section (after creating `app = FastAPI()`), add:

```python
# Initialize blockchain agent
from blockchain_layer import BlockchainLayer
from evolution_bridge import EvolutionBridge
from db_layer import DBLayer

# These should already exist in your app
controller = ClawController()  # Your existing controller
db = DBLayer()  # Your existing DB layer
blockchain = BlockchainLayer(
    os.getenv("RPC_URL"),
    os.getenv("ADMIN_PRIVATE_KEY"),
    os.getenv("ESCROW_CONTRACT_ADDRESS")
)
bridge = EvolutionBridge()  # Your existing bridge

# Create agent instances
blockchain_agent = BlockchainWhatsAppAgent(db, blockchain, bridge)
blockchain_commands = BlockchainWhatsAppCommands(blockchain_agent, bridge)
tx_manager = TransactionManager(db, blockchain.w3)

# Initialize routes
init_blockchain_routes(blockchain_agent, blockchain_commands, tx_manager)

# Start background services
blockchain_agent.start_event_listener()
tx_manager.start_polling()

# Include blockchain routes
app.include_router(blockchain_router)
```

## Step 2: Update WhatsApp Message Handler

In `backend/api.py`, find the webhook handler for Evolution messages and add blockchain command routing:

```python
@app.post("/webhook/evolution")
async def evolution_webhook(request: Request):
    raw_body = await request.body()
    signature = request.headers.get("x-evolution-signature", "")

    # ... existing signature verification ...

    data = await request.json()

    # Extract WhatsApp message
    from_number = _normalise_number(data.get("sender", ""))  # Use your normalizer
    message_text = data.get("message", {}).get("text", "").strip()

    # Route to blockchain commands FIRST
    if await blockchain_commands.handle_command(from_number, message_text):
        return {"status": "ok", "handled": "blockchain"}

    # Then route to existing handlers
    if await handle_regular_whatsapp_command(from_number, message_text):
        return {"status": "ok", "handled": "command"}

    return {"status": "ok"}
```

## Step 3: Update Environment Variables

Add to `.env`:

```bash
# Blockchain
RPC_URL=https://mainnet.base.org
CHAIN_ID=8453
ESCROW_CONTRACT_ADDRESS=0x...  # Deploy ClawEscrow.sol first
ADMIN_PRIVATE_KEY=0x...  # Private key of admin wallet
USDT_ADDRESS=0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48

# Admin API
ADMIN_API_KEY=your_admin_api_key_here
```

## Step 4: Database Migration

Run this SQL in Supabase to create transaction tracking tables:

```sql
-- Transaction tracking
CREATE TABLE IF NOT EXISTS blockchain_transactions (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  tx_hash VARCHAR(66) UNIQUE NOT NULL,
  user_id UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  tx_type VARCHAR(50) NOT NULL,
  amount DECIMAL(16, 6) NOT NULL,
  gas_fee DECIMAL(16, 6),
  status VARCHAR(20) NOT NULL DEFAULT 'pending',
  pool_id INTEGER,
  created_at TIMESTAMP DEFAULT NOW(),
  confirmed_at TIMESTAMP,
  failed_reason TEXT,
  metadata JSONB DEFAULT '{}',
  updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_tx_user ON blockchain_transactions(user_id);
CREATE INDEX idx_tx_status ON blockchain_transactions(status);
CREATE INDEX idx_tx_hash ON blockchain_transactions(tx_hash);

-- Approval queue (temporary)
CREATE TABLE IF NOT EXISTS approval_queue (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  token VARCHAR(128) UNIQUE NOT NULL,
  user_id UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  action VARCHAR(50) NOT NULL,
  pool_id INTEGER,
  entry_fee DECIMAL(16, 6),
  gas_fee DECIMAL(16, 6),
  created_at TIMESTAMP DEFAULT NOW(),
  expires_at TIMESTAMP DEFAULT NOW() + INTERVAL '15 minutes',
  CONSTRAINT ap_expires CHECK (expires_at > created_at)
);

CREATE INDEX idx_ap_token ON approval_queue(token);
CREATE INDEX idx_ap_expires ON approval_queue(expires_at);
```

## Step 5: Test the Integration

### 5a. Test Balance Endpoint
```bash
curl http://localhost:8000/blockchain/balance/2348022202143
```

Expected response:
```json
{
  "whatsapp_id": "2348022202143",
  "balance_usd": 150.25,
  "estimated_gas_fee": 0.15,
  "gas_eth": "0.00005",
  "network": "Base Mainnet",
  "chain_id": 8453
}
```

### 5b. Test WhatsApp Command
Send message to your bot:
```
/blockchain_balance
```

Expected WhatsApp response:
```
💰 Your Balance

Available: $150.25 USDT
Network: Base Mainnet
Chain ID: 8453
```

### 5c. Test Pool Creation
Send:
```
/blockchain_pool_create 0 10.50
```

Expected:
1. Bot asks for approval with buttons ✅ Approve / ❌ Reject
2. Click ✅ Approve
3. Bot responds with transaction hash
4. Bot shows pending status
5. Bot sends confirmation when block included

## Step 6: Deploy Contract (if not already done)

Use your `deploy_contract.py`:

```bash
python deploy_contract.py contracts/ClawEscrow.sol
```

Save the contract address and update `.env`:
```bash
ESCROW_CONTRACT_ADDRESS=0x...
```

## Step 7: Test Event Listening

Start the listener:
```bash
curl -X POST http://localhost:8000/blockchain/events/start \
  -H "x-admin-key: your_admin_api_key"
```

Monitor events:
```bash
curl http://localhost:8000/blockchain/events/status
```

## Step 8: Monitor Transactions

### Get pending transactions
```bash
curl http://localhost:8000/blockchain/admin/stats \
  -H "x-admin-key: your_admin_api_key"
```

### Get transaction history
```bash
curl http://localhost:8000/blockchain/history/2348022202143
```

### Check transaction status
```bash
curl http://localhost:8000/blockchain/status/0x1234...
```

## Step 9: Production Checklist

Before going live:

- [ ] Contract deployed to Base mainnet
- [ ] Admin wallet has sufficient ETH (~0.5 ETH for 1000+ transactions)
- [ ] Environment variables set in production
- [ ] Database tables created
- [ ] Event listener tested
- [ ] Error handling verified
- [ ] WhatsApp approvals tested
- [ ] Transaction history working
- [ ] Admin endpoints secured
- [ ] Monitoring dashboard updated
- [ ] Rate limiting configured
- [ ] Audit logging enabled

## Troubleshooting

### Import errors

If you get `ImportError: cannot import name 'BlockchainWhatsAppAgent'`:
1. Make sure files are in `/backend/` directory
2. Check file names match exactly
3. Try running: `python -c "from blockchain_whatsapp_agent import BlockchainWhatsAppAgent"`

### Blockchain connection errors

If errors like `Connection refused`:
1. Check RPC_URL is correct
2. Verify network connectivity
3. Try: `curl https://mainnet.base.org` in terminal

### WhatsApp buttons not showing

If approval buttons don't appear:
1. Check Evolution API version supports interactive messages
2. Verify button count ≤ 3
3. Check message is under 4096 characters

### Transactions stuck pending

If transactions stay pending:
1. Check gas price: `curl -X GET http://localhost:8000/blockchain/admin/stats`
2. Manually bump gas with higher nonce
3. Check transaction on BaseScan

### Missing user balance

If balance shows 0:
1. Verify profile exists in database
2. Check balance field is populated
3. Run: `SELECT balance FROM profiles WHERE whatsapp_id = '234...'`

## Next: Advanced Features

Once basic integration works, add:

1. **Batch operations**
   - User can create multiple pools in sequence
   - Parallel transaction processing

2. **Withdrawal flows**
   - Users withdraw to bank account
   - Settlement on Base → Naira conversion

3. **Dashboard**
   - Real-time balance updates
   - Transaction history UI
   - Leaderboard

4. **Advanced approvals**
   - Biometric confirmation
   - Rate limiting
   - Daily limits

5. **Analytics**
   - Transaction volume metrics
   - User acquisition funnel
   - Fee collection tracking

## Support

For issues, check:
1. Console logs: `tail -f logs/backend.log`
2. Database: Supabase dashboard
3. Blockchain: BaseScan.org
4. Evolution API: Dashboard
