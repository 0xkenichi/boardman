"""
db_layer_blockchain.py
────────────────────────────────────────────────────────────────────────────────
Blockchain-specific DB operations. These methods should be mixed into or
imported by the main db_layer.py.

Add this to your existing db_layer.py / DBLayer class, or import and call
from transaction_manager.py.
"""

import logging
from typing import Optional
from supabase_client import get_supabase
import os

logger = logging.getLogger(__name__)


# ─── System Config ────────────────────────────────────────────────────────────

async def get_system_config(key: str) -> Optional[dict]:
    sb = get_supabase()
    result = sb.table("system_config").select("*").eq("key", key).single().execute()
    return result.data if result.data else None


async def set_system_config(key: str, value: str):
    sb = get_supabase()
    sb.table("system_config").upsert(
        {"key": key, "value": value, "updated_at": "now()"},
        on_conflict="key"
    ).execute()


# ─── Transactions ─────────────────────────────────────────────────────────────

async def get_transaction_by_hash(tx_hash: str) -> Optional[dict]:
    sb = get_supabase()
    result = sb.table("transactions").select("*").eq("tx_hash", tx_hash).single().execute()
    return result.data if result.data else None


async def record_transaction(data: dict):
    sb = get_supabase()
    sb.table("transactions").insert(data).execute()


async def record_unattributed_deposit(data: dict):
    sb = get_supabase()
    sb.table("unattributed_deposits").insert(data).execute()


async def get_recent_transactions(limit: int = 100) -> list:
    """Get recent confirmed transactions ordered by block descending."""
    sb = get_supabase()
    res = sb.table("transactions").select("*").order("block", desc=True).limit(limit).execute()
    return res.data if res.data else []


async def flag_transaction_reorg(tx_hash: str):
    """Mark a transaction as reorged for manual review."""
    sb = get_supabase()
    sb.table("transactions").update({"status": "reorged"}).eq("tx_hash", tx_hash).execute()


# ─── Wallet ───────────────────────────────────────────────────────────────────

async def get_user_by_wallet(wallet_address: str) -> Optional[dict]:
    """Find a user by their linked crypto wallet address."""
    sb = get_supabase()
    result = (
        sb.table("profiles")
        .select("*")
        .ilike("linked_wallet", wallet_address)
        .single()
        .execute()
    )
    return result.data if result.data else None


async def credit_wallet(user_id: str, amount_usd: float, tx_hash: str, source: str = "crypto_deposit"):
    """Add USDC to user's internal balance and log the transaction."""
    sb = get_supabase()
    try:
        res = sb.rpc("credit_wallet", {"p_user_id": user_id, "p_amount": amount_usd}).execute()
        # Verify: read back balance
        bal_res = sb.table("profiles").select("wallet_balance_usdc").eq("id", user_id).single().execute()
        new_bal = bal_res.data.get("wallet_balance_usdc") if bal_res.data else None
        logger.info(f"[DB] Credited ${amount_usd:.2f} to user={user_id} tx={tx_hash[:10]}... new_bal=${new_bal}")
    except Exception as e:
        logger.error(f"[DB] CREDIT FAILED user={user_id} amount=${amount_usd} tx={tx_hash}: {e}")
        raise


async def debit_wallet(user_id: str, amount_usd: float) -> bool:
    """Deduct USDC from user's internal balance. Returns False if insufficient."""
    sb = get_supabase()
    try:
        sb.rpc("debit_wallet", {"p_user_id": user_id, "p_amount": amount_usd}).execute()
        return True
    except Exception as e:
        if "Insufficient balance" in str(e):
            return False
        raise


async def get_wallet_balance(user_id: str) -> float:
    sb = get_supabase()
    result = sb.table("profiles").select("wallet_balance_usdc").eq("id", user_id).single().execute()
    return float(result.data["wallet_balance_usdc"]) if result.data else 0.0


async def link_wallet_address(user_id: str, wallet_address: str):
    sb = get_supabase()
    sb.table("profiles").update({"linked_wallet": wallet_address.lower()}).eq("id", user_id).execute()


async def link_circle_wallet(user_id: str, wallet_id: str, wallet_address: str, wallet_set_id: str):
    """Associate a Circle custodial wallet (deposit address) with a user profile."""
    sb = get_supabase()

    # Validate uniqueness: ensure wallet_id and wallet_address aren't already assigned to another user
    existing_wallet = sb.table("profiles").select("id").or_(
        f"circle_wallet_id.eq.{wallet_id},wallet_address.eq.{wallet_address.lower()}"
    ).neq("id", user_id).execute()

    if existing_wallet.data:
        raise ValueError(f"Wallet {wallet_id} or address {wallet_address} already assigned to another user")

    sb.table("profiles").update({
        "circle_wallet_id":     wallet_id,
        "wallet_address":       wallet_address.lower(),   # custodial deposit address
        "circle_wallet_set_id": wallet_set_id,
        # leave linked_wallet alone — it's the external withdrawal address
    }).eq("id", user_id).execute()


# ─── Match On-Chain Tracking ──────────────────────────────────────────────────

async def update_match_onchain_id(match_id: str, onchain_match_id: str):
    sb = get_supabase()
    sb.table("bets").update({"onchain_match_id": onchain_match_id}).eq("id", match_id).execute()


async def update_match_onchain_status(match_id: str, status: str, tx_hash: Optional[str] = None):
    sb = get_supabase()
    update = {"onchain_status": status}
    if tx_hash:
        update["resolve_tx_hash"] = tx_hash
    sb.table("bets").update(update).eq("id", match_id).execute()


async def award_play_points(user_id: str, points: int):
    """Award $PLAY token points (10 per $1 staked)."""
    sb = get_supabase()
    sb.rpc("increment_play_points", {"p_user_id": user_id, "p_points": points}).execute()
