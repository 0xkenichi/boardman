# Circle + Escrow Setup Guide for Base Sepolia

This document walks you through setting up custodial wallets via Circle and escrow management for your WhatsApp betting app.

---

## 1. Database Setup

### Create the `escrow_entries` table in Supabase

Go to your Supabase dashboard and run this SQL:

```sql
-- Create escrow_entries table
CREATE TABLE escrow_entries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    bet_id UUID NOT NULL REFERENCES bets(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    amount_usdc DECIMAL(18, 6) NOT NULL,
    wallet_address TEXT NOT NULL,
    escrow_tx_id TEXT NOT NULL UNIQUE,  -- Circle transaction ID
    tx_hash TEXT,                       -- Blockchain tx hash
    status TEXT NOT NULL DEFAULT 'LOCKED',  -- LOCKED, RELEASED, FAILED
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),

    CONSTRAINT valid_status CHECK (status IN ('LOCKED', 'RELEASED', 'FAILED'))
);

-- Add indexes for queries
CREATE INDEX idx_escrow_bet_id ON escrow_entries(bet_id);
CREATE INDEX idx_escrow_user_id ON escrow_entries(user_id);
CREATE INDEX idx_escrow_status ON escrow_entries(status);

-- Add Circle wallet fields to profiles table (if not exists)
ALTER TABLE profiles ADD COLUMN IF NOT EXISTS circle_wallet_id TEXT;
ALTER TABLE profiles ADD COLUMN IF NOT EXISTS circle_wallet_created_at TIMESTAMP;
```

---

## 2. Environment Variables

Add these to your `.env` file:

```bash
# Circle API
CIRCLE_API_KEY=TEST_API_KEY:c6ae7278b2b8a011af7c6f9e1d8ffe76:f02988c714436c4d51cb58f45ff0509b
CIRCLE_CLIENT_KEY=TEST_CLIENT_KEY:84dee858c064baf8b9e27d22b87f92d4:d9a54d28c340932af0e5120e0697d916

# After running setup, these will be populated:
ESCROW_WALLET_ID=xxx  # Set after creating escrow wallet
ESCROW_WALLET_ADDRESS=0x...  # Set after creating escrow wallet
```

---

## 3. Initialize Escrow Wallet

Run this Python script to create your escrow wallet (do this once):

```python
# setup_escrow.py
import os
from dotenv import load_dotenv
from backend.circle_wallet_service import CircleWalletService

load_dotenv()

circle = CircleWalletService()

# Create escrow wallet
print("Creating escrow wallet...")
escrow = circle.get_or_create_escrow_wallet()

if escrow["success"]:
    print(f"✅ Escrow wallet created!")
    print(f"Wallet ID: {escrow['wallet_id']}")
    print(f"Address: {escrow['wallet_address']}")
    print(f"Blockchain: {escrow.get('blockchain', 'BASE-SEPOLIA')}")
    print()
    print("Add these to your .env:")
    print(f"ESCROW_WALLET_ID={escrow['wallet_id']}")
    print(f"ESCROW_WALLET_ADDRESS={escrow['wallet_address']}")
else:
    print(f"❌ Error: {escrow['error']}")
```

Run it:
```bash
cd /Users/mac/Agents\ /ClawStation
python3 setup_escrow.py
```

Copy the output into your `.env` file.

---

## 4. Fund the Test Escrow Wallet

You need ETH for gas. Get testnet ETH from faucet:

1. Go to https://sepoliafaucet.com/
2. Enter your escrow wallet address (from step 3)
3. Request ~0.05 ETH (for gas)

You don't need to fund it with USDC—users will deposit USDC into their own wallets.

---

## 5. Test USDC Funding for Users

### Get Base Sepolia USDC

Users need USDC to place bets. Get testnet USDC:

```bash
# Option A: Faucet (if available)
# https://www.basescan.org/faucet

# Option B: Bridge from Sepolia Ethereum
# Use: https://bridge.base.org/
# Send ETH from Sepolia → Base Sepolia, swap for USDC
```

---

## 6. Verify Wallet Creation Flow

When a new WhatsApp user texts, here's what happens:

### Current Flow (FYI):

```
User texts WhatsApp (+234...)
  ↓
whatsapp_handler extracts phone number
  ↓
controller.get_user("whatsapp_id", phone_number)
  ↓
db.get_or_create_profile() creates profile with whatsapp_id
  ↓
Bot responds with /help
```

### Updated Flow with Circle (Add to whatsapp_handler.py):

```
[Same as above until profile created]
  ↓
wallet_service.create_custodial_wallet(profile_id)
  ↓
circle_wallet_service.create_custodial_wallet_for_user()
  ↓
✅ User now has isolated Circle-managed wallet on Base Sepolia
  ↓
Bot: "✅ Your wallet is ready. Send /blockchain_balance to check"
```

---

## 7. Integration with WhatsApp Commands

### Update `whatsapp_handler.py` to Create Wallet on First Message

```python
# In the message handler (around line 187):

profile = controller.get_user("whatsapp_id", from_number)

# NEW: Create wallet if user doesn't have one
if profile and not profile.get("wallet_address"):
    wallet_result = wallet_service.create_custodial_wallet(profile["id"])
    if wallet_result["success"]:
        print(f"✅ Created wallet for {from_number}: {wallet_result['wallet_address']}")
        # Optionally notify user
        response_text = "✅ Your wallet is ready! Use /blockchain_balance to check it.\n\n" + response_text
    else:
        print(f"❌ Failed to create wallet: {wallet_result['message']}")
```

---

## 8. Bet Flow with Escrow

### Create Bet (Lock User Stake)

```python
# In betting_engine.py or bet handler:

from escrow_manager import EscrowManager

escrow_mgr = EscrowManager(db)

# User creates bet with 50 USDC stake
result = escrow_mgr.lock_user_stake(
    profile_id=user_id,
    bet_id=bet_id,
    stake_amount=50.0
)

if result["success"]:
    print(f"✅ Locked {result['amount_locked']} USDC in escrow")
    print(f"TX: {result['tx_hash']}")
else:
    print(f"❌ Failed to lock stake: {result['error']}")
```

### Resolve Bet (Release to Winner)

```python
# When bet resolves:

result = escrow_mgr.release_to_winner(
    bet_id=bet_id,
    winner_profile_id=winner_id,
    payout_amount=100.0  # e.g., 50 + 50 prize
)

if result["success"]:
    print(f"✅ Released {result['amount_released']} USDC to winner")
    print(f"TX: {result['tx_hash']}")
else:
    print(f"❌ Failed to payout: {result['error']}")
```

---

## 9. Check Escrow Balance

```python
result = escrow_mgr.get_escrow_balance()

if result["success"]:
    print(f"Escrow balance: {result['balance_usdc']} USDC")
    print(f"TX chain: {result.get('balance_wei')} wei")
```

---

## 10. Testing Locally

### Test Wallet Creation

```python
# test_circle_integration.py

from db_layer import DBLayer
from wallet_service import WalletService

db = DBLayer()
wallet_svc = WalletService(db)

# Simulate a new user
test_profile = db.get_or_create_profile("whatsapp_id", "234801234567")
print(f"Created profile: {test_profile['id']}")

# Create wallet
result = wallet_svc.create_custodial_wallet(test_profile["id"])
print(f"Wallet result: {result}")

if result["success"]:
    # Check balance
    balance = wallet_svc.get_custodial_wallet_balance(result["wallet_address"])
    print(f"Balance: {balance}")
```

### Test Escrow Lock (Requires funds)

```python
from escrow_manager import EscrowManager

escrow_mgr = EscrowManager(db)

# First, fund the test user wallet with some USDC (via faucet)
# Then:

lock_result = escrow_mgr.lock_user_stake(
    profile_id=test_profile["id"],
    bet_id="fake-bet-uuid",
    stake_amount=10.0  # Small for testing
)

print(f"Lock result: {lock_result}")
```

---

## 11. Monitoring & Debugging

### Check Transaction Status

```python
from circle_wallet_service import CircleWalletService

circle = CircleWalletService()

# Check a transaction
result = circle.wait_for_transaction(
    transaction_id="tx-id-from-result",
    max_wait_seconds=120
)

print(f"Status: {result['status']}")
print(f"Hash: {result.get('tx_hash')}")
```

### View Escrow Entries in DB

```python
# In Supabase dashboard:
SELECT * FROM escrow_entries
WHERE status = 'LOCKED'
ORDER BY created_at DESC;
```

---

## 12. Common Issues & Fixes

### "Wallet creation failed"

- Check `CIRCLE_API_KEY` and `CIRCLE_CLIENT_KEY` are correct
- Verify you're on Base Sepolia test credentials (not mainnet)

### "Insufficient balance for transfer"

- User's wallet has no USDC yet
- Get testnet USDC from faucet or bridge

### "Transaction timeout"

- Base Sepolia can be slow, retry after 2-3 minutes
- Check explorer: `https://sepolia.basescan.org/tx/{tx_hash}`

### "Escrow wallet address not set"

- Run `setup_escrow.py` to create escrow wallet
- Add `ESCROW_WALLET_ID` and `ESCROW_WALLET_ADDRESS` to `.env`

---

## 13. Moving to Mainnet

When you're ready (after testing works perfectly):

1. **Update Circle credentials** to production API keys
2. **Change blockchain** from `BASE-SEPOLIA` to `BASE`
3. **Change RPC_URL** to `https://mainnet.base.org`
4. **Fund escrow wallet** with real ETH (~0.1-0.5 ETH for gas)
5. **Re-run setup_escrow.py** to create mainnet escrow wallet
6. **Update database escrow entries table** (same schema works for both)

---

## Summary

| Component | Purpose |
|-----------|---------|
| **CircleWalletService** | Create user wallets, approve/transfer USDC |
| **EscrowManager** | Lock stakes during bets, release to winners |
| **PDL** | Stores escrow entries & transaction tracking |
| **whatsapp_handler** | Auto-create wallet on user first message |
| **betting_engine** | Call escrow_mgr when bets are placed/resolved |

Everything is custodial—sideQuest controls all wallets. Users don't manage private keys.

---

**Status**: ✅ Ready for local Base Sepolia testing
