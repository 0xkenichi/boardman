"""
repositories/wallet.py — Balance, withdrawals, Flutterwave, Paystack, Circle.
All moved from db_layer.py.
"""
import re
import uuid
import logging
from supabase_client import get_supabase

logger = logging.getLogger(__name__)


def _get_supabase():
    return get_supabase()


def _validate_uuid(value: str, field_name: str = "id"):
    """Raise ValueError if value is not a valid UUID string."""
    try:
        uuid.UUID(str(value))
    except (ValueError, AttributeError):
        raise ValueError(f"Invalid UUID for field '{field_name}': {value}")


# ─── Balance / Play Points ────────────────────────────────────────────────────

def update_balance(profile_id: str, amount: float):
    """
    Atomically adjust balance using a Postgres RPC that does a row-lock
    increment so concurrent calls cannot double-spend.
    """
    supabase = _get_supabase()
    _validate_uuid(profile_id, "profile_id")
    try:
        res = supabase.rpc("adjust_balance", {"p_id": profile_id, "delta": float(amount)}).execute()
        return res.data
    except Exception as e:
        logger.error("adjust_balance RPC failed — Postgres function may not be deployed: %s", e)
        raise RuntimeError(
            "adjust_balance RPC unavailable. Deploy supabase/migrations/000_initial_schema.sql. "
            "Non-atomic fallback is unsafe under concurrent requests."
        ) from e


def award_play_points(profile_id: str, amount: float):
    """Atomically increment play_points via RPC or safe fallback."""
    supabase = _get_supabase()
    _validate_uuid(profile_id, "profile_id")
    try:
        val = float(amount)
    except (TypeError, ValueError):
        raise ValueError(f"Invalid amount for field 'play_points': {amount}")
    if val <= 0:
        raise ValueError(f"Amount 'play_points' must be positive, got: {val}")
    try:
        res = supabase.rpc("adjust_play_points", {"p_id": profile_id, "delta": float(amount)}).execute()
        return res.data
    except Exception:
        res = supabase.table("profiles").select("play_points").eq("id", profile_id).single().execute()
        current = float(res.data.get("play_points", 0)) if res.data else 0
        new_points = current + amount
        res2 = supabase.table("profiles").update({"play_points": new_points}).eq("id", profile_id).execute()
        return res2.data[0] if res2.data else None


def get_available_balance(profile_id: str):
    """Get available balance from the user's wallet."""
    supabase = _get_supabase()
    _validate_uuid(profile_id, "profile_id")
    res = supabase.table("profiles").select("balance").eq("id", profile_id).single().execute()
    if not res.data:
        return 0
    return float(res.data.get("balance", 0))


def get_play_points(profile_id: str):
    _validate_uuid(profile_id, "profile_id")
    supabase = _get_supabase()
    res = supabase.table("profiles").select("play_points").eq("id", profile_id).single().execute()
    return float(res.data.get("play_points", 0)) if res.data else 0


# ─── Wallet Linking ───────────────────────────────────────────────────────────

def link_wallet(profile_id: str, wallet_address: str):
    _validate_uuid(profile_id, "profile_id")
    if not re.match(r'^0x[0-9a-fA-F]{40}$', wallet_address):
        raise ValueError(f"Invalid Ethereum wallet address: {wallet_address}")
    supabase = _get_supabase()
    res = supabase.table("profiles").update({"wallet_address": wallet_address}).eq("id", profile_id).execute()
    return res.data[0] if res.data else None


# ─── Withdrawals ──────────────────────────────────────────────────────────────

def _validate_positive_amount(amount, field_name: str = "amount"):
    """Raise ValueError if amount is not a positive number."""
    try:
        val = float(amount)
    except (TypeError, ValueError):
        raise ValueError(f"Invalid amount for field '{field_name}': {amount}")
    if val <= 0:
        raise ValueError(f"Amount '{field_name}' must be positive, got: {val}")
    return val


def create_withdrawal(profile_id: str, amount):
    _validate_uuid(profile_id, "profile_id")
    amount = _validate_positive_amount(amount, "withdrawal amount")
    supabase = _get_supabase()
    data = {"profile_id": profile_id, "amount": amount, "status": "PENDING"}
    res = supabase.table("withdrawals").insert(data).execute()
    return res.data[0] if res.data else None


def confirm_withdrawal(withdrawal_id: str):
    """Mark a pending withdrawal as COMPLETED (idempotent guard on status)."""
    _validate_uuid(withdrawal_id, "withdrawal_id")
    supabase = _get_supabase()
    res = supabase.table("withdrawals").update({
        "status": "COMPLETED"
    }).eq("id", withdrawal_id).eq("status", "PENDING").execute()
    return res.data[0] if res.data else None


def get_withdrawals_by_user(user_id: str):
    """Get all withdrawals for a specific user"""
    _validate_uuid(user_id, "user_id")
    supabase = _get_supabase()
    res = supabase.table("withdrawals").select("*").eq("profile_id", user_id).execute()
    return res.data if res.data else []


# ─── Virtual Accounts (Flutterwave) ──────────────────────────────────────────

def get_virtual_account(profile_id: str):
    """Returns virtual account details or None."""
    _validate_uuid(profile_id, "profile_id")
    supabase = _get_supabase()
    try:
        res = supabase.table("virtual_accounts").select("*").eq("profile_id", profile_id).maybe_single().execute()
        return res.data
    except Exception as e:
        logger.exception("Virtual account lookup failed: %s", e)
        return None


def save_virtual_account(profile_id: str, account_number: str, bank_name: str, account_name: str, flw_ref: str):
    """Save virtual account details."""
    _validate_uuid(profile_id, "profile_id")
    supabase = _get_supabase()
    data = {
        "profile_id": profile_id,
        "account_number": account_number,
        "bank_name": bank_name,
        "account_name": account_name,
        "flw_ref": flw_ref,
    }
    try:
        res = supabase.table("virtual_accounts").upsert(data).execute()
        return res.data[0] if res.data else None
    except Exception as e:
        logger.exception("Virtual account save failed: %s", e)
        return None


# ─── Flutterwave Transaction Tracking ────────────────────────────────────────

def has_flw_tx_been_processed(flw_tx_id: str) -> bool:
    """Idempotency check for Flutterwave transactions."""
    supabase = _get_supabase()
    try:
        res = supabase.table("flw_transactions").select("id").eq("flw_tx_id", flw_tx_id).maybe_single().execute()
        return res.data is not None
    except Exception as e:
        logger.exception("FLW transaction check failed: %s", e)
        return False


def mark_flw_tx_processed(flw_tx_id: str, profile_id: str, amount_usd: float):
    """Mark Flutterwave transaction as processed."""
    supabase = _get_supabase()
    try:
        data = {
            "flw_tx_id": flw_tx_id,
            "profile_id": profile_id,
            "amount_usd": amount_usd,
        }
        res = supabase.table("flw_transactions").insert(data).execute()
        return res.data[0] if res.data else None
    except Exception as e:
        logger.exception("FLW transaction mark failed: %s", e)
        return None


# ─── Crypto Transaction Tracking ─────────────────────────────────────────────

def has_crypto_tx_been_processed(tx_hash: str) -> bool:
    supabase = _get_supabase()
    try:
        res = supabase.table("crypto_transactions").select("id").eq("tx_hash", tx_hash).maybe_single().execute()
        return res.data is not None
    except Exception as e:
        logger.exception("Crypto TX check failed: %s", e)
        return False


def mark_crypto_tx_processed(tx_hash: str, profile_id: str, amount_usd: float):
    supabase = _get_supabase()
    try:
        data = {
            "tx_hash": tx_hash,
            "profile_id": profile_id,
            "amount_usd": amount_usd,
        }
        res = supabase.table("crypto_transactions").insert(data).execute()
        return res.data[0] if res.data else None
    except Exception as e:
        logger.exception("Crypto TX mark failed: %s", e)
        return None


# ─── On-chain Bet Updates ─────────────────────────────────────────────────────

def update_bet_on_chain_tx(bet_id: str, tx_hash: str):
    _validate_uuid(bet_id, "bet_id")
    if not re.match(r'^0x[0-9a-fA-F]{64}$', tx_hash):
        raise ValueError(f"Invalid tx hash: {tx_hash}")
    supabase = _get_supabase()
    res = supabase.table("bets").update({"on_chain_tx": tx_hash}).eq("id", bet_id).execute()
    return res.data[0] if res.data else None


def set_bet_on_chain_pool_id(bet_id: str, pool_id: int):
    _validate_uuid(bet_id, "bet_id")
    if pool_id is None or pool_id < 0:
        raise ValueError("Invalid pool id")
    supabase = _get_supabase()
    res = supabase.table("bets").update({"on_chain_pool_id": pool_id}).eq("id", bet_id).execute()
    return res.data[0] if res.data else None