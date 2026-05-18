# Blockchain Security Audit Report
**sideQuest Telegram Bot & ClawEscrow Contract**
**Date:** April 19, 2026
**Status:** COMPREHENSIVE REVIEW COMPLETED

---

## Executive Summary

Your blockchain implementation is **well-structured with solid fundamentals**, but has **several critical and high-severity vulnerabilities** that must be fixed before mainnet deployment. The smart contract is secure, but the integration layer has gaps in:

1. **Access control** (no Telegram input validation)
2. **Private key exposure** (environment variable at runtime)
3. **Transaction race conditions** (idempotency issues)
4. **Deposit attribution** (unattributed funds handling)
5. **Admin action authorization** (no verification for critical operations)

---

## CRITICAL FINDINGS

### 🔴 C1: No Input Validation on Telegram Commands (CRITICAL)

**Location:** `telegram_handler.py` lines 66-104
**Risk:** Users can trigger blockchain operations with arbitrary inputs

```python
# Line 94-101: Challenge creation with unvalidated stake amount
amount = float(args[0])  # No range checks!
if amount <= 0: raise ValueError  # Only checks > 0

game = args[1]  # No game validation against allowed list
is_on_chain = len(args) > 2 and args[2].lower() == "onchain"  # No auth check
```

**Attack Vector:**
- User runs `/challenge 999999 FIFA` → attempts to create $999k match → insufficient balance but no UI feedback
- User runs `/challenge 10 INVALID_GAME` → crashes or creates invalid match
- User can toggle `onchain` flag arbitrarily without permission checks

**Impact:** DoS, invalid state, unpredictable behavior
**Severity:** CRITICAL

**Fix Required:**
```python
# Validate stake against max config + user balance
MAX_STAKE_USD = 10000  # Match ClawEscrow.MAX_STAKE
VALID_GAMES = {"FIFA", "EA FC", "NBA", "2K"}

async def challenge_command(...):
    try:
        amount = float(args[0])
        if amount <= 0 or amount > MAX_STAKE_USD:
            await update.message.reply_text(f"❌ Stake must be $0.01–${MAX_STAKE_USD}")
            return

        if args[1].upper() not in VALID_GAMES:
            await update.message.reply_text(f"❌ Game must be one of: {', '.join(VALID_GAMES)}")
            return

        # Check user balance FIRST
        balance = await wallet_service.get_balance(profile["id"])
        if balance["internal_balance_usdc"] < amount:
            await update.message.reply_text(f"❌ Insufficient balance. Need ${amount}, have ${balance['internal_balance_usdc']}")
            return
```

---

### 🔴 C2: Admin Private Key in Memory (CRITICAL)

**Location:** `blockchain_layer.py` lines 223–226

```python
private_key = os.getenv("ADMIN_PRIVATE_KEY", "")
if not private_key:
    raise ValueError("[Blockchain] ADMIN_PRIVATE_KEY not set")
self.account = Account.from_key(private_key)
```

**Risk:**
- Private key is read into memory at app startup
- If app logs are captured, memory is dumped, or server is compromised, **the admin wallet is fully exposed**
- All contract resolution calls (resolveMatch, cancelMatch) use this single key
- No key rotation mechanism

**Current Exposure:**
- Admin wallet signs ALL match resolutions
- Controls fee recipient address
- Can pause/unpause contract
- Anyone with shell access can read `.env` file

**Impact:** Total loss of admin wallet funds + ability to steal all escrowed USDC
**Severity:** CRITICAL

**Immediate Actions Required:**
1. **Use a signer service** instead of loading raw key:
   - AWS KMS / HashiCorp Vault for key storage
   - Google Cloud KMS
   - AWS Secrets Manager with rotation

2. **Never store raw private keys** in environment variables

3. **Temporary mitigation (if high-value mainnet):**
   - Use a cold wallet for admin operations
   - Implement multi-sig for critical operations (resolveMatch, setResolver)
   - Create a signer service that runs on a separate, hardened server

**Example Safe Pattern:**
```python
class SecureSignerService:
    """
    Signs transactions via external KMS (Google Cloud, AWS, etc.)
    Admin wallet private key never leaves the KMS.
    """
    def __init__(self):
        self.kms = GoogleCloudKMS(project_id=os.getenv("GCP_PROJECT"))
        self.key_name = os.getenv("SIGNER_KEY_NAME")

    async def sign_transaction(self, txn_dict):
        # KMS signs the transaction
        signature = await self.kms.sign(
            self.key_name,
            txn_dict.encode()
        )
        return signature
```

---

### 🔴 C3: Unattributed Deposit Handling (CRITICAL)

**Location:** `transaction_manager.py` (no code shown), `db_layer_blockchain.py` line 55

```python
# Users can send USDC to admin wallet with no reference ID
# If deposit doesn't match a known user, it goes to unattributed_deposits table
async def record_unattributed_deposit(data: dict):
    sb.table("unattributed_deposits").insert(data).execute()
```

**Risk:**
- Users can send USDC to the deposit address without proper attribution
- You lose track of who sent what
- Attacker can pollute your deposit table with thousands of $0.01 transfers → spam + data bloat
- No recovery mechanism for unattributed deposits
- Deposits are NOT transferred back to user wallets— they just sit in the contract

**Current Flow:**
1. User is told: "Send USDC to `0x123...` (admin wallet)"
2. Admin wallet receives USDC
3. TransactionManager scans for Transfer events
4. If sender is known user → credit wallet
5. If sender is unknown → `unattributed_deposits` orphaned

**Impact:** Lost user funds, wallet reconciliation failures
**Severity:** CRITICAL (from user perspective)

**Fixes Needed:**

1. **Use unique deposit addresses per user:**
   ```python
   # Instead of sending users to admin wallet, use:
   # - Circle custodial wallets (already in code!)
   # - Unique deposit sub-addresses (hard with USDC)
   # - Invoice/reference number tracking

   async def get_crypto_deposit_address(user_id: str) -> dict:
       # Check if user has Circle wallet
       profile = await db.get_user_profile(user_id)
       if profile.get("circle_wallet_id"):
           circle_address = await circle_wallet_service.get_wallet_address(
               profile["circle_wallet_id"]
           )
           return {
               "address": circle_address,
               "type": "custodial",
               "note": "Your personal sideQuest wallet on Circle"
           }

       # Fall back to admin wallet with clear reference
       return {
           "address": admin_wallet,
           "type": "admin_pool",
           "reference": f"sidequest-{user_id}",
           "note": f"Include {user_id} in memo/reference field"
       }
   ```

2. **Add deposit reference tracking:**
   ```python
   # When giving user a deposit address, give them a reference code
   reference_code = f"SQ-{user_id}-{int(time.time())}"

   # User includes in transaction memo or on-chain message
   # TransactionManager matches reference code → auto-credits wallet
   ```

3. **Implement dispute resolution:**
   ```python
   async def handle_unattributed_deposit(tx_hash: str, amount: float, sender: str):
       """
       For deposits with no known user:
       1. Store in unattributed table
       2. Let user claim with reference number
       3. Auto-return to sender if unclaimed after 7 days
       """
       pass
   ```

---

## HIGH SEVERITY FINDINGS

### 🟠 H1: No Idempotency for Concurrent Match Operations

**Location:** `betting_engine_onchain.py` lines 30–53 (lock_stake_for_match)

```python
async def lock_stake_for_match(user_id: str, match_id: str, stake_usd: float) -> bool:
    # No check if stake already locked for this match!
    success = await debit_wallet(user_id, stake_usd)
    if not success:
        return False

    # If this function is called twice (retry, race condition):
    # User gets debited TWICE, but match only uses single amount
    await record_transaction({...})
    return True
```

**Attack Vector:**
- User presses "Join Match" button twice → balance debited twice
- Network retry on failing transaction → stake locked twice
- Two matches with same player + same match ID → race condition

**Impact:** Wallet depletion, incorrect match state
**Severity:** HIGH

**Fix:**
```python
async def lock_stake_for_match(user_id: str, match_id: str, stake_usd: float) -> bool:
    """Idempotent stake locking with unique constraint."""

    # Check if stake already locked for this match
    existing = await db.get_match_stake_lock(match_id, user_id)
    if existing:
        logger.info(f"Stake already locked for match {match_id}, user {user_id}")
        return True  # Idempotent success

    success = await debit_wallet(user_id, stake_usd)
    if not success:
        return False

    # Record with unique (match_id, user_id) constraint
    await record_transaction_with_idempotent_key({
        "idempotent_key": f"{match_id}_{user_id}_lock",
        "user_id": user_id,
        ...
    })
    return True
```

**Database:**
```sql
CREATE UNIQUE INDEX idx_stake_lock_idempotent
ON stake_locks(match_id, user_id, idempotent_key)
WHERE status = 'LOCKED';
```

---

### 🟠 H2: No Authorization Checks for Admin Actions via Telegram

**Location:** `telegram_handler.py` lines 20–26

```python
ADMIN_NUMBERS = frozenset(["2348022202143", "2347073924753", "2349163497691"])

def _is_admin(user_id: str) -> bool:
    # This function ALWAYS returns True!
    return True  # ← ANYONE is admin!
```

**Current State:** The authorization function exists but is disabled. Any Telegram user can:
- Create/cancel matches as admin
- Resolve matches (award payouts to arbitrary winners)
- Link wallets without verification
- Approve/reject transactions

**Impact:** Fraud, theft, match manipulation
**Severity:** HIGH

**Fix:**
```python
def _is_admin(user_id: str) -> bool:
    """Check if user is admin based on Telegram user ID or phone number."""
    # Map Telegram user IDs to admin status
    ADMIN_TELEGRAM_IDS = frozenset([123456789, 987654321])  # Get from DB

    return str(user_id) in ADMIN_TELEGRAM_IDS

async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Decorator for admin-only commands."""
    user_id = str(update.effective_user.id)
    if not _is_admin(user_id):
        await update.message.reply_text("❌ You don't have permission to use this command.")
        return

    # ... proceed with admin action
```

---

### 🟠 H3: No Verification for Match Resolution Winners

**Location:** `blockchain_layer.py` line 314, `betting_engine_onchain.py` line 80

```python
async def resolve_match_onchain(self, match_id: str, winner_address: str) -> dict:
    mid = self.match_id_to_bytes32(match_id)
    winner = Web3.to_checksum_address(winner_address)
    fn = self.escrow.functions.resolveMatch(mid, winner)
    # NO CHECK: Is winner_address actually one of the players?
    # NO CHECK: Did both players agree?
    result = await asyncio.to_thread(self._build_and_send, fn)
```

**Risk:** Admin can award match to anyone (not even a player in the match)

**On-Chain Protection:** ClawEscrow.sol line 165–166 DOES check:
```solidity
if (winner != m.player1 && winner != m.player2)
    revert InvalidWinner(winner);
```

**But off-chain is unprotected.** Fix:

```python
async def resolve_match_onchain(self, match_id: str, winner_address: str) -> dict:
    mid = self.match_id_to_bytes32(match_id)

    # BEFORE sending tx: verify winner is a player
    match_data = await self.get_match_data(mid)
    if not match_data:
        raise ValueError(f"Match {match_id} not found on-chain")

    winner = Web3.to_checksum_address(winner_address)
    p1 = Web3.to_checksum_address(match_data["player1"])
    p2 = Web3.to_checksum_address(match_data["player2"])

    if winner not in (p1, p2):
        raise ValueError(f"Winner {winner} is not a player in this match")

    if match_data["status"] not in ("LOCKED", "DISPUTED"):
        raise ValueError(f"Match status {match_data['status']} cannot be resolved")

    fn = self.escrow.functions.resolveMatch(mid, winner)
    return await asyncio.to_thread(self._build_and_send, fn)
```

---

### 🟠 H4: No Rate Limiting on Blockchain API Endpoints

**Location:** `blockchain_api_endpoints.py` lines 51–80

```python
@router.post("/approve")
async def approve_transaction(request: ApproveTransactionRequest):
    # NO rate limiting, NO request signing, NO auth token check!
    success, message, tx_hash = blockchain_agent.approve_transaction(request.approval_token)
    return {...}
```

**Attack:** Attacker can spam:
- `/approve` with random tokens 1000x/sec
- `/blockchain/balance/anyone` to enumerate users
- Gas cost overruns processing spam requests

**Fix:**
```python
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

@router.post("/approve")
@limiter.limit("5/minute")  # 5 approvals per minute per IP
async def approve_transaction(request: ApproveTransactionRequest):
    # Also validate approval_token format
    if not is_valid_token_format(request.approval_token):
        raise HTTPException(status_code=400, detail="Invalid token format")

    success, message, tx_hash = blockchain_agent.approve_transaction(request.approval_token)
    return {...}
```

---

### 🟠 H5: Transaction Monitoring Doesn't Handle Reorgs

**Location:** `transaction_manager.py` lines 84–94

```python
async def _process_new_blocks(self):
    current_block = self.bl.w3.eth.block_number
    safe_block = current_block - CONFIRMATIONS_REQUIRED  # 2 blocks

    if safe_block <= self._last_block:
        return  # No new confirmed blocks

    deposits = await self.bl.scan_incoming_usdc(
        from_block=self._last_block + 1,
        to_block=safe_block,
    )
```

**Issue:** On Base, 2-block confirmation is **very weak**. Block reorgs can still happen:
- Base has ~10-second block time
- 2 blocks = ~20 seconds of safety
- A reorg can happen up to 10+ blocks deep

**If a reorg happens:**
1. Block N contains Transfer event → TransactionManager credits user
2. Block N is reorg'd out
3. User's deposit is now invalid but wallet shows balance
4. User withdraws USDC that doesn't exist on-chain

**Impact:** Funds loss, wallet insolvency
**Severity:** HIGH

**Fix:**
```python
# Increase confirmation requirement for Base
CONFIRMATIONS_REQUIRED = int(os.getenv("TX_CONFIRMATIONS", "12"))  # ~2 minutes

# Better: Listen for L2 finality root on Ethereum L1
# Or: Only process deposits after L2 operator batch is finalized
# Or: Use Circle Attestation API for deposit confirmation
```

---

## MEDIUM SEVERITY FINDINGS

### 🟡 M1: Missing CSRF Protection on Telegram Commands

**Risk:** No verification that commands come from legitimate users

```python
# telegram_handler.py doesn't verify:
# - User is who they claim to be
# - Telegram token is valid
# - Message signature is authentic (optional but good practice)
```

**Mitigation:** Aiogram handles this via Telegram Bot API, but add per-user nonce:

```python
async def fund_command(...):
    profile = await identify_user(update)

    # Ask for confirmation code
    code = generate_otp()
    await db.save_pending_operation(user_id, "fund", code)

    await update.message.reply_text(
        f"Type `/confirm {code}` to confirm funding request"
    )
```

---

### 🟡 M2: No Signature Verification for Deposit Attribution

**Current:** Deposits are attributed solely by wallet address

```python
# No way to prove user A intended to send to contract
# User could claim "I didn't send that USDC"
```

**Better:** For Circle custodial wallets, add on-chain metadata:

```python
# When user initiates deposit, sign it with their key:
message = web3.keccak(text=f"deposit-{user_id}-{timestamp}")
signature = user_wallet.sign_message(message)

# Include signature in on-chain memo or side-channel
# On-chain contract can verify signature matches sender
```

---

### 🟡 M3: Insufficient Logging for Audit Trail

**Risk:** Cannot track who approved/resolved matches

```python
# betting_engine_onchain.py logs:
logger.info(f"[BettingEngine] Match {match_id} resolved → winner: {winner_address}")

# But doesn't log:
# - WHO called resolve (admin wallet? which IP?)
# - When (exact timestamp)
# - What parameters were used
# - Resolution method (on-chain vs internal)
```

**Fix:**
```python
async def resolve_match_and_payout(...):
    admin_wallet = bl.account.address
    timestamp = datetime.utcnow().isoformat()

    # Log to immutable audit table
    await db.audit_log({
        "action": "resolve_match",
        "match_id": match_id,
        "executed_by": admin_wallet,
        "timestamp": timestamp,
        "winner": winner_user_id,
        "was_onchain": bool(winner_wallet),
        "payout_amount": payout,
        "status": "success"
    })
```

---

### 🟡 M4: No Circuit Breaker for Contract Interactions

```python
# If ClawEscrow contract is hacked or paused,
# all match operations fail with no fallback

# Add monitoring:
async def check_contract_health():
    if escrow.functions.paused().call():
        logger.critical("CL

awEscrow is PAUSED!")
        await alert_admins()

    # Check contract has sufficient USDC balance
    balance = escrow.functions.contractBalance().call()
    if balance < expected_min:
        logger.error(f"Contract USDC low: {balance}")
```

---

## SMART CONTRACT AUDIT (Solidity)

### ✅ ClawEscrow.sol — Strengths

**Correctly Uses:**
- ✅ `nonReentrant` guard on all transfers
- ✅ SafeERC20 for safe token transfers (no return value issues)
- ✅ Proper status enum with state transitions
- ✅ Access control via `onlyResolver` and `onlyOwner` modifiers
- ✅ Constants for fee basis points
- ✅ Zero-address checks in constructor
- ✅ Pausable mechanism for emergencies

### ⚠️ Minor Issues

**1. Match Status Validation Gap**

```solidity
function resolveMatch(bytes32 matchId, address winner)
    external onlyResolver {
    // Allows resolving from LOCKED OR DISPUTED
    // But no time limit check — matches could resolve years later
}
```

**Recommendation:**
```solidity
uint256 public constant RESOLUTION_TIMEOUT = 30 days;

function resolveMatch(bytes32 matchId, address winner)
    external onlyResolver matchExists(matchId) {
    Match storage m = matches[matchId];

    // Add timeout check
    if (block.timestamp > m.lockedAt + RESOLUTION_TIMEOUT) {
        revert MatchResolutionTimeout();
    }

    // ... rest of function
}
```

**2. Missing Event for Fee Changes**

```solidity
function setFeeRecipient(address _feeRecipient) external onlyOwner {
    emit FeeRecipientUpdated(feeRecipient, _feeRecipient);
    feeRecipient = _feeRecipient;
}
// ✅ This IS correct, FeeRecipientUpdated event is emitted
```

**3. No Slippage Protection for Fee Calculations**

```solidity
uint256 totalPot = m.stakePerPlayer * 2;
uint256 fee = (totalPot * FEE_BPS) / BPS_DENOM;  // 100 / 10000 = 1%
uint256 payout = totalPot - fee;

// If FEE_BPS changes (it doesn't, it's constant, so this is FINE)
```

✅ **No issues here** — fee is immutable.

---

## SECURE PATTERNS IN USE

✅ **Good:**
- Proper use of Web3 checksummed addresses
- USDC decimal handling (6 decimals) is correct
- Match ID generation via hashing string → bytes32 is secure
- Transaction building with proper nonce + gas limits
- Async/await patterns prevent blocking
- Database transactions for wallet operations

---

## RECOMMENDATIONS BY PRIORITY

### Immediate (Before Any Mainnet/Real Funds)

1. **Implement admin key management** — move away from environment variable to KMS
2. **Add missing deposit attribution** — unique addresses or reference codes
3. **Fix Telegram command validation** — stake limits, game type checks
4. **Enable authorization checks** — `_is_admin()` should actually check
5. **Add idempotency tokens** — for match operations

### Before Production Launch

6. Add rate limiting to API endpoints
7. Increase block confirmations to 12+ (from 2)
8. Implement audit logging for all admin actions
9. Add signature verification for deposits (if possible)
10. Create circuit breaker for contract health monitoring
11. Add per-user deposit addresses (via Circle)

### For Hardening

12. Implement multi-sig for critical operations (resolveMatch)
13. Add dispute resolution for unattributed deposits
14. Create withdrawal review queue (hold funds 24h before release)
15. Implement gas price monitoring (prevent overpaying on layer 2)

---

## Testing Checklist

- [ ] Test concurrent `/challenge` commands → verify idempotent behavior
- [ ] Test invalid stake amounts → all inputs rejected
- [ ] Test unattributed deposits → funds tracked and recoverable
- [ ] Test admin auth → non-admins cannot resolve matches
- [ ] Test reorg scenario → deposits still valid after 12-block reorg
- [ ] Test rate limits → API rejects spam after threshold
- [ ] Test circle wallet creation → on-chain address matches DB
- [ ] Test match cancellation → both players refunded correctly

---

## Conclusion

**Risk Level:** 🔴 **HIGH** (for production mainnet)

Your implementation is **architecturally sound**, but **authentication, authorization, and fund attribution gaps** make it unsafe for real user funds right now.

**Timeline:**
- **72 hours:** Fix C1, C2, C3 (validation, keys, deposits)
- **1 week:** Complete all CRITICAL and HIGH items
- **Testnet only until:** All fixes deployed and tested

Start with the private key migration (C2) — that's your single point of catastrophic failure.
