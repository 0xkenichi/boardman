# Circle + Escrow Quick Start

3-step integration of Circle custodial wallets with your WhatsApp betting app.

---

## Step 1: Database Setup (5 minutes)

Go to **Supabase Dashboard** → **SQL Editor** and run:

```sql
-- Create escrow tracking table
CREATE TABLE escrow_entries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    bet_id UUID NOT NULL REFERENCES bets(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    amount_usdc DECIMAL(18, 6) NOT NULL,
    wallet_address TEXT NOT NULL,
    escrow_tx_id TEXT NOT NULL UNIQUE,
    tx_hash TEXT,
    status TEXT NOT NULL DEFAULT 'LOCKED',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    CONSTRAINT valid_status CHECK (status IN ('LOCKED', 'RELEASED', 'FAILED'))
);

-- Add indexes
CREATE INDEX idx_escrow_bet_id ON escrow_entries(bet_id);
CREATE INDEX idx_escrow_user_id ON escrow_entries(user_id);
CREATE INDEX idx_escrow_status ON escrow_entries(status);

-- Add Circle wallet fields to profiles
ALTER TABLE profiles ADD COLUMN IF NOT EXISTS circle_wallet_id TEXT;
ALTER TABLE profiles ADD COLUMN IF NOT EXISTS circle_wallet_created_at TIMESTAMP;
```

✅ Done!

---

## Step 2: Initialize Escrow Wallet (2 minutes)

Run:

```bash
cd /Users/mac/Agents\ /ClawStation/backend
python3 setup_circle_escrow.py
```

Output:
```
✅ Escrow wallet created!
   ID: xxxx
   Address: 0x...

📋 ADD THESE TO YOUR .env FILE:
ESCROW_WALLET_ID=xxxx
ESCROW_WALLET_ADDRESS=0x...
```

Copy those two lines into your `.env` file. ✅ Done!

---

## Step 3: Fund for Testing (5 minutes)

Get testnet ETH for escrow:

1. Go to **https://sepoliafaucet.com/**
2. Paste your `ESCROW_WALLET_ADDRESS`
3. Request 0.05 ETH

For users to test, they need USDC:

1. Go to **https://www.basescan.org/faucet** (or bridge your own)
2. Create a test wallet
3. Get ~100 USDC

✅ Done!

---

## What You Now Have

| File | Purpose |
|------|---------|
| `circle_wallet_service.py` | Create user wallets, USDC transfers |
| `escrow_manager.py` | Lock stakes, release to winners |
| `db_layer.py` (updated) | Escrow database methods |
| `wallet_service.py` (updated) | Uses Circle API instead of mocks |
| `test_circle_wallet.py` | Test wallet creation & transfers |

---

## Architecture

```
New WhatsApp User
    ↓
create_custodial_wallet(profile_id)
    ↓
Circle API → User gets isolated EOA wallet on Base Sepolia
    ↓
Wallet shows in profile.wallet_address & profile.circle_wallet_id
```

**Bet Lock Flow:**
```
User places 50 USDC bet
    ↓
escrow_mgr.lock_user_stake(user_id, bet_id, 50)
    ↓
1. Approve escrow to spend USDC
2. Transfer 50 USDC to escrow wallet
3. Record in escrow_entries table
    ↓
Status: LOCKED
```

**Bet Release Flow:**
```
Bet resolves, user wins
    ↓
escrow_mgr.release_to_winner(bet_id, winner_id, 100)
    ↓
1. Transfer 100 USDC from escrow to winner's wallet
2. Update escrow_entries status to RELEASED
    ↓
Winner receives USDC! ✅
```

---

## Test It (10 minutes)

```bash
# 1. Test wallet creation
python3 test_circle_wallet.py

# 2. Expected output:
# ✅ Wallet created!
# ✅ Escrow wallet ready!
# ⚠️  Cannot check balance (wallet not funded yet)
```

Once wallets are funded with USDC/ETH, it'll show balances.

---

## Integrate with Betting

In your `betting_engine.py` or bet handler:

```python
from escrow_manager import EscrowManager

escrow_mgr = EscrowManager(db)

# When user places bet:
lock_result = escrow_mgr.lock_user_stake(
    profile_id=user_id,
    bet_id=bet_id,
    stake_amount=50.0
)

if not lock_result["success"]:
    print(f"Failed to lock stake: {lock_result['error']}")
    return

# When bet resolves:
payout_result = escrow_mgr.release_to_winner(
    bet_id=bet_id,
    winner_profile_id=winner_id,
    payout_amount=100.0
)

if payout_result["success"]:
    print(f"Winner paid! TX: {payout_result['tx_hash']}")
```

---

## Verify It Works (via WhatsApp)

Create a test bet flow:

```
User: /start
Bot: Creates profile + Circle wallet ✅

User: /fund 100
Bot: Guides user to get USDC ✅

User: /pool_create 1v1 50
Bot:
1. Locks 50 USDC in escrow ✅
2. Creates match on Base Sepolia ✅
3. Sends explorer link ✅

User: Wins!
Bot:
1. Releases 100 USDC from escrow ✅
2. Sends winner confirmation ✅
```

---

## Common Issues

| Issue | Fix |
|-------|-----|
| "Wallet creation failed" | Check Circle API keys in .env |
| "Insufficient balance" | Fund test wallet (escrow wallet needs ETH for gas) |
| "Transaction timeout" | Base Sepolia is slow, retry in 2 min |
| "ESCROW_WALLET_ID not set" | Run `setup_circle_escrow.py` and add to .env |

---

## Next: Move to Mainnet

When ready:

1. Update Circle API keys to production
2. Change RPC_URL to `https://mainnet.base.org`
3. Change blockchain from `BASE-SEPOLIA` to `BASE`
4. Run `setup_circle_escrow.py` again for mainnet escrow
5. Fund escrow with real ETH (~0.5 ETH)

---

**Status**: ✅ Ready for Base Sepolia testing
