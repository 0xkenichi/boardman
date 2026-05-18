# Blockchain + WhatsApp Integration Guide

## Overview

This is a production-ready integration that handles all blockchain operations through WhatsApp. Users can create pools, join matches, check balances, and approve transactions entirely through WhatsApp with real-time feedback and explorer links.

## Architecture

```
┌──────────────────┐
│   WhatsApp User  │
│  (via Evolution  │
│      API)        │
└────────┬─────────┘
         │
    Text + Buttons
         │
    ┌────▼─────────────────┐
    │  API.py              │
    │  (Webhook Handler)   │
    └────┬─────────────────┘
         │
    ┌────▼──────────────────────────┐
    │ BlockchainWhatsAppCommands    │
    │ (Route commands)              │
    └────┬───────────────────────────┘
         │
    ┌────▼──────────────────────────┐
    │ BlockchainWhatsAppAgent       │
    │ - Transaction execution       │
    │ - Gas estimation              │
    │ - WhatsApp notifications      │
    │ - Event listening             │
    └────┬───────────────────────────┘
         │
    ┌────▼──────────────────────────┐
    │ BlockchainLayer               │
    │ (Web3 interactions)           │
    └────┬───────────────────────────┘
         │
    ┌────▼──────────────────────────┐
    │ Base Mainnet (8453)           │
    │ - ClawEscrow contract         │
    │ - USDT transfers              │
    └───────────────────────────────┘

Database:
┌──────────────────────────────────┐
│ Supabase                         │
│ - Transaction history            │
│ - User balances                  │
│ - Approvals queue                │
└──────────────────────────────────┘
```

## Setup

### 1. Add to `requirements.txt`

```
web3>=6.8.0
eth-keys>=0.4.0
eth-typing>=3.0.0
```

### 2. Environment Variables (`.env`)

```bash
# Blockchain
RPC_URL=https://mainnet.base.org
CHAIN_ID=8453
ESCROW_CONTRACT_ADDRESS=0x...
ADMIN_PRIVATE_KEY=0x...
USDT_ADDRESS=0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48  # Actually USDC on Base

# Evolution API
EVOLUTION_WEBHOOK_SECRET=your_webhook_secret
EVOLUTION_API_KEY=your_api_key
EVOLUTION_API_URL=https://evolution....

# WhatsApp
EVOLUTION_INSTANCE_NAME=clawstation
```

### 3. Update `app_controller.py`

Add to imports:
```python
from blockchain_whatsapp_agent import BlockchainWhatsAppAgent
from blockchain_whatsapp_commands import BlockchainWhatsAppCommands
from transaction_manager import TransactionManager
```

Add to `ClawController.__init__()`:
```python
self.blockchain_agent = BlockchainWhatsAppAgent(self.db, self.blockchain, self.bridge)
self.blockchain_commands = BlockchainWhatsAppCommands(self.blockchain_agent, self.bridge)
self.tx_manager = TransactionManager(self.db, self.blockchain.w3)

# Start background services
self.blockchain_agent.start_event_listener()
self.tx_manager.start_polling()
```

### 4. Update `whatsapp_handler.py`

Add blockchain command router:
```python
async def handle_message(from_number, text):
    # ... existing code ...

    # Route to blockchain commands
    if await blockchain_commands.handle_command(from_number, text):
        return

    # ... rest of handlers ...
```

## User Commands

### Check Balance
```
/blockchain_balance
```
Response:
```
💰 Your Balance

Available: $150.25 USDT
Network: Base Mainnet
Chain ID: 8453
```

### View Transaction History
```
/blockchain_history
```
Response:
```
📜 Recent Transactions

1. ✅ Create Pool
   Amount: $50.00
   Status: confirmed
   Hash: 0x1234abcd...

2. ⏳ Join Pool
   Amount: $25.00
   Status: pending
   Hash: 0x5678efgh...
```

### Check Transaction Status
```
/blockchain_status 0x123456...
```
Response:
```
✅ Transaction Status

Hash: 0x123456...
Status: CONFIRMED

🔗 View: https://basescan.org/tx/0x123456...
```

### Create a Pool
```
/blockchain_pool_create <type> <fee>

Types:
  0 = 1v1
  1 = Tournament
  2 = Squad

Example: /blockchain_pool_create 0 10.50
```

Flow:
1. User sends command
2. Bot checks balance
3. Bot estimates gas fee
4. Bot sends approval buttons
5. User clicks ✅ Approve or ❌ Reject
6. If approved:
   - Transaction submitted
   - User gets tx hash
   - Bot polls for confirmation
   - User gets notified with explorer link

### Join a Pool
```
/blockchain_pool_join <pool_id>

Example: /blockchain_pool_join 5
```

Same flow as pool creation.

## Transaction Flow Diagram

```
User Command
    ↓
Balance Check ──❌→ "Insufficient funds"
    ↓
Gas Estimation
    ↓
Send Approval Buttons
(✅ Approve / ❌ Reject)
    ↓
Wait for User Response
    ↓
❌ Reject? ──→ "Transaction rejected"
✅ Approve? ──→ Build & Sign Tx
    ↓
Send to Mempool
    ↓
Send: "⏳ Pending" msg + Hash
    ↓
Poll Blockchain (5s intervals)
    ↓
Confirmed? ──→ "✅ Confirmed!" + Explorer
Failed?    ──→ "❌ Failed" + Reason
```

## Real-Time Event Listening

The agent automatically listens for ClawEscrow events:

### Pool Created
```python
event PoolCreated(uint256 indexed poolId, PoolType poolType, uint256 entryFee, bool isPublic)
```
→ Logged, can trigger notifications

### Player Joined
```python
event PlayerJoined(uint256 indexed poolId, address indexed player)
```
→ Update live leaderboard

### Payout (User Won)
```python
event Payout(uint256 indexed poolId, address indexed winner, uint256 amount)
```
→ WhatsApp notification: "🎉 You won! $X.XX USDT"

### Disputed
```python
event Disputed(uint256 indexed poolId)
```
→ Notify admins of dispute

## Gas Estimation

Before any transaction, gas is estimated:

```python
gas_fee, gas_eth = agent.estimate_gas("create_pool")
# gas_fee = $0.15 (USD)
# gas_eth = "0.00005" ETH
```

Estimation logic:
- `create_pool`: 300,000 gas
- `join_pool`: 200,000 gas
- `resolve_pool`: 300,000 gas

Users see total cost in approval message:
```
Entry Fee: $50.00
Gas Fee: $0.15
Total: $50.15
```

## Error Handling

### Insufficient Balance
```
❌ Insufficient balance

Required: $50.50
Available: $45.00
```

### Transaction Failed
```
❌ Transaction Failed

Type: Create Pool
Error: Execution reverted

Please try again or contact support.
```

### Gas Too Low
```
❌ Insufficient funds for gas

Entry Fee: $50.00
Gas Fee: $0.20
Total: $50.20
Available: $50.10
```

## Database Schema (Supabase)

Add to `supabase_schema.sql`:

```sql
-- Transaction history
CREATE TABLE IF NOT EXISTS transactions (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  tx_hash VARCHAR(66) UNIQUE NOT NULL,
  user_id UUID NOT NULL REFERENCES profiles(id),
  type VARCHAR(50) NOT NULL,
  amount DECIMAL(16, 6) NOT NULL,
  gas_fee DECIMAL(16, 6),
  status VARCHAR(20) NOT NULL DEFAULT 'pending',
  pool_id INTEGER,
  created_at TIMESTAMP DEFAULT NOW(),
  confirmed_at TIMESTAMP,
  failed_reason TEXT,
  metadata JSONB,
  updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_tx_user ON transactions(user_id);
CREATE INDEX idx_tx_status ON transactions(status);
CREATE INDEX idx_tx_hash ON transactions(tx_hash);
```

## Security Considerations

1. **Private Key Management**
   - Store admin private key securely (environment variable)
   - Consider using multi-sig for production

2. **Signature Verification**
   - All Evolution webhooks verified with HMAC-SHA256
   - All blockchain transactions signed server-side

3. **Fund Protection**
   - User funds locked in Supabase until transaction confirmed
   - Dynamic platform fee (3% for early adopters, 7% for standard users)
   - Minimum fee floor of $0.50 per match
   - Escrow contract has reentrancy guard

4. **Rate Limiting**
   - Implement per-user rate limits on transaction creation
   - Max pending transactions per user (e.g., 3)

5. **Audit Trail**
   - All transactions logged with:
     - User ID
     - Transaction hash
     - Type
     - Amount
     - Status
     - Timestamp

## Monitoring

Key metrics to track:

```python
# In a monitoring dashboard:
- Total transactions (today/week/month)
- Transaction success rate
- Average gas fees
- Failed transactions by reason
- User balances distribution
- Contract TVL (total value locked)
```

## Testing

### 1. Local Testing with Anvil

```bash
# Start Anvil (Base fork)
anvil --fork-url https://mainnet.base.org

# In .env
RPC_URL=http://127.0.0.1:8545
CHAIN_ID=31337
```

### 2. Unit Tests

```python
# test_blockchain_whatsapp.py
def test_gas_estimation():
    agent = BlockchainWhatsAppAgent(db, blockchain, bridge)
    gas_fee, gas_eth = agent.estimate_gas("create_pool")
    assert gas_fee > 0
    assert float(gas_eth) > 0

def test_check_balance():
    balance = agent.get_user_balance("2348022202143")
    assert isinstance(balance, float)

def test_transaction_approval():
    token = agent.create_pool_request("2348022202143", 0, 10.0)
    success, msg, hash = agent.approve_transaction(token)
    assert success
    assert hash is not None
```

### 3. Staging Testing

```bash
# Test with Base Sepolia (testnet)
RPC_URL=https://sepolia.base.org
CHAIN_ID=84532
ESCROW_CONTRACT_ADDRESS=0x...  # Sepolia contract
```

Get faucet tokens: https://www.base.org/faucet

## Production Checklist

- [ ] Contract deployed on Base mainnet
- [ ] Admin wallet funded with ETH for gas
- [ ] All environment variables set
- [ ] Database tables created
- [ ] Event listeners implemented
- [ ] WhatsApp approval flow tested
- [ ] Gas estimation verified
- [ ] Error handling tested
- [ ] Monitoring dashboard set up
- [ ] Admin notifications configured
- [ ] Rate limiting enabled
- [ ] Audit logging verified

## Troubleshooting

### "Insufficient balance" always appears

Check:
1. User balance in database
2. Gas price on Base (may be high)
3. Entry fee configuration

### Transactions stuck pending

1. Check mempool: `eth_getTransactionByHash`
2. Check gas price (may be too low)
3. Consider resend with higher gas

### WhatsApp buttons not appearing

1. Verify Evolution API version
2. Check button format (max 3 buttons)
3. Check message length (max 4096 chars)

### Event listener not working

1. Check contract address
2. Verify ABI is correct
3. Check RPC endpoint connectivity

## Next Steps

1. Deploy contracts to Base mainnet
2. Fund admin wallet with ETH (~0.1 ETH for 1000+ transactions)
3. Create testnet version on Base Sepolia
4. Add transaction history to dashboard
5. Implement withdrawal flows
6. Add leaderboard updates
7. Create admin notifications for disputes
