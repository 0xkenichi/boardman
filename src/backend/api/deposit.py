"""
gaming/src/backend/api/deposit.py

User-facing deposit endpoints for ClawStation.

``GET /api/deposit/address`` returns the authenticated user's Circle deposit
address. ``GET /api/deposit/history`` lists recent USDC credits from
``gaming.wallet_credit_audit``.

Auth note:
    For this chunk the endpoints accept ``user_id`` as a query parameter.
    Production should replace this with JWT/session-based authentication.
"""
from __future__ import annotations

import logging
from decimal import Decimal
from fastapi import APIRouter, HTTPException, Query

from gaming.src.backend.services.clawstation_circle import (
    CircleWalletError,
    get_deposit_address,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["deposit"])


def _get_supabase():
    from backend.supabase_client import get_supabase

    return get_supabase()


@router.get("/deposit/address")
async def deposit_address(user_id: str = Query(..., description="User UUID (replace with JWT in production)")):
    """Return the user's Circle USDC deposit address on Base Sepolia."""
    try:
        address = await get_deposit_address(user_id)
    except CircleWalletError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("[DepositAPI] Failed to resolve deposit address for %s", user_id)
        raise HTTPException(status_code=500, detail="Failed to resolve deposit address") from exc

    return {
        "address": address,
        "currency": "USDC",
        "network": "BASE",
    }


@router.get("/deposit/history")
async def deposit_history(
    user_id: str = Query(..., description="User UUID (replace with JWT in production)"),
    limit: int = Query(50, ge=1, le=200),
):
    """Return recent USDC credits from ``gaming.wallet_credit_audit``."""
    sb = _get_supabase()
    try:
        result = (
            sb.table("wallet_credit_audit")
            .select("tx_hash, amount_usdc, status, created_at")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
    except Exception as exc:
        logger.exception("[DepositAPI] Failed to load deposit history for %s", user_id)
        raise HTTPException(status_code=500, detail="Failed to load deposit history") from exc

    rows = result.data or []
    for row in rows:
        amount = row.get("amount_usdc")
        if amount is not None:
            row["amount_usdc"] = str(Decimal(str(amount)))
    return {"items": rows, "count": len(rows)}
