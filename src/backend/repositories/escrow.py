"""
repositories/escrow.py — Bets, escrow entries, match reports, fund lock/unlock.
All moved from db_layer.py.
"""
import uuid
import logging
from backend.supabase_client import get_supabase

logger = logging.getLogger(__name__)


def _get_supabase():
    return get_supabase()


def _validate_uuid(value: str, field_name: str = "id"):
    """Raise ValueError if value is not a valid UUID string."""
    try:
        uuid.UUID(str(value))
    except (ValueError, AttributeError):
        raise ValueError(f"Invalid UUID for field '{field_name}': {value}")


def _validate_positive_amount(amount, field_name: str = "amount"):
    """Raise ValueError if amount is not a positive number."""
    try:
        val = float(amount)
    except (TypeError, ValueError):
        raise ValueError(f"Invalid amount for field '{field_name}': {amount}")
    if val <= 0:
        raise ValueError(f"Amount '{field_name}' must be positive, got: {val}")
    return val


# ─── Match Reports ────────────────────────────────────────────────────────────

def get_match_reports(bet_id: str = None):
    """Get match reports, optionally filtered by bet_id"""
    supabase = _get_supabase()
    if bet_id:
        _validate_uuid(bet_id, "bet_id")
        res = supabase.table("match_reports").select("""
            id, bet_id, reporter_id, score, proof_url, created_at
        """).eq("bet_id", bet_id).execute()
    else:
        res = supabase.table("match_reports").select("""
            id, bet_id, reporter_id, score, proof_url, created_at
        """).execute()
    return res.data if res.data else []


def create_report(bet_id: str, reporter_id: str, score: str, proof_url: str = None):
    """Create a match report."""
    import re
    supabase = _get_supabase()
    _validate_uuid(bet_id, "bet_id")
    _validate_uuid(reporter_id, "reporter_id")
    # Sanitise score: e.g. "2-1"
    if not re.match(r'^\d+[\-:]\d+$', str(score)):
        raise ValueError(f"Invalid score format: {score}")
    data = {
        "bet_id": bet_id,
        "reporter_id": reporter_id,
        "score": score,
        "proof_url": proof_url[:2048] if proof_url else None
    }
    res = supabase.table("match_reports").insert(data).execute()
    return res.data[0] if res.data else None


def get_reports_for_bet(bet_id: str):
    _validate_uuid(bet_id, "bet_id")
    supabase = _get_supabase()
    res = supabase.table("match_reports").select("*").eq("bet_id", bet_id).execute()
    return res.data


# ─── Escrow Entries ───────────────────────────────────────────────────────────

def create_escrow_entry(entry_data: dict) -> str:
    """
    Create an escrow entry for a locked bet.

    Args:
        entry_data: {
            "bet_id": str,
            "user_id": str,
            "amount_usdc": float,
            "wallet_address": str,
            "escrow_tx_id": str,
            "tx_hash": str (optional),
            "status": str,  # LOCKED, RELEASED, FAILED
            "created_at": str
        }

    Returns:
        Entry UUID on success, None on failure
    """
    supabase = _get_supabase()
    try:
        # Ensure bet_id and user_id are valid UUIDs
        _validate_uuid(entry_data.get("bet_id"), "bet_id")
        _validate_uuid(entry_data.get("user_id"), "user_id")

        res = supabase.table("escrow_entries").insert(entry_data).execute()
        return res.data[0]["id"] if res.data else None
    except Exception as e:
        logger.exception("Escrow entry creation failed: %s", e)
        return None


def get_escrow_entries_by_bet(bet_id: str) -> list:
    """Get all escrow entries for a bet."""
    supabase = _get_supabase()
    _validate_uuid(bet_id, "bet_id")
    try:
        res = supabase.table("escrow_entries").select("*").eq("bet_id", bet_id).execute()
        return res.data if res.data else []
    except Exception as e:
        logger.exception("Escrow entries lookup by bet failed: %s", e)
        return []


def get_escrow_entries_by_user(user_id: str) -> list:
    """Get all escrow entries for a user."""
    supabase = _get_supabase()
    _validate_uuid(user_id, "user_id")
    try:
        res = supabase.table("escrow_entries").select("*").eq("user_id", user_id).execute()
        return res.data if res.data else []
    except Exception as e:
        logger.exception("Escrow entries lookup by user failed: %s", e)
        return []


def update_escrow_entry_status(bet_id: str, new_status: str) -> bool:
    """Update status of escrow entries for a bet."""
    supabase = _get_supabase()
    _validate_uuid(bet_id, "bet_id")
    try:
        res = supabase.table("escrow_entries").update({"status": new_status}).eq("bet_id", bet_id).execute()
        return bool(res.data)
    except Exception as e:
        logger.exception("Escrow status update failed: %s", e)
        return False


def get_locked_escrow_amount_for_bet(bet_id: str) -> float:
    """Get total amount locked in escrow for a bet."""
    entries = get_escrow_entries_by_bet(bet_id)
    return sum(
        entry.get("amount_usdc", 0)
        for entry in entries
        if entry.get("status") == "LOCKED"
    )


# ─── Fund Lock / Unlock ───────────────────────────────────────────────────────

def lock_funds(profile_id: str, amount: float):
    """Lock funds: deduct from available balance."""
    supabase = _get_supabase()
    _validate_uuid(profile_id, "profile_id")
    amount = _validate_positive_amount(amount, "lock amount")
    res = supabase.table("profiles").select("balance").eq("id", profile_id).single().execute()
    if not res.data:
        raise ValueError("Profile not found")
    balance = float(res.data["balance"])
    if balance < amount:
        raise ValueError("Insufficient available funds")
    new_balance = balance - amount
    res2 = supabase.table("profiles").update({"balance": new_balance}).eq("id", profile_id).gte("balance", amount).execute()
    return res2.data[0] if res2.data else None


def unlock_funds(profile_id: str, amount: float):
    """Unlock funds: add to balance."""
    supabase = _get_supabase()
    _validate_uuid(profile_id, "profile_id")
    amount = _validate_positive_amount(amount, "unlock amount")
    res = supabase.table("profiles").select("balance").eq("id", profile_id).single().execute()
    if not res.data:
        raise ValueError("Profile not found")
    balance = float(res.data["balance"])
    new_balance = balance + amount
    res2 = supabase.table("profiles").update({"balance": new_balance}).eq("id", profile_id).execute()
    return res2.data[0] if res2.data else None