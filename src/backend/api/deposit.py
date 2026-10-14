"""
gaming/src/backend/api/deposit.py

User-facing deposit endpoints for ClawStation.

``GET /api/deposit/address`` returns the authenticated user's Circle deposit
address. ``GET /api/deposit/history`` lists recent USDC credits from
``gaming.wallet_credit_audit``.

Auth:
    Server-to-server only. The master Stack key is required, and the user is
    the one the BFF vouches for in ``X-Boardman-Caller``; a ``user_id`` query
    param may only repeat it. Without a caller header the platform itself
    (master key) may name any ``user_id``. Builder keys have no users here.
"""
from __future__ import annotations

import logging
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query

from gaming.src.backend.rematch_auth import extract_api_key, resolve_api_key

from gaming.src.backend.services.clawstation_circle import (
    CircleWalletError,
    get_deposit_address,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["deposit"])


def require_deposit_user(
    user_id: str = Query(default="", description="Must match X-Boardman-Caller when that is sent"),
    x_rematch_key: Optional[str] = Header(default=None, alias="X-Rematch-Key"),
    x_boardman_key: Optional[str] = Header(default=None, alias="X-Boardman-Key"),
    x_stack_key: Optional[str] = Header(default=None, alias="X-Stack-Key"),
    authorization: Optional[str] = Header(default=None),
    x_boardman_caller: Optional[str] = Header(default=None, alias="X-Boardman-Caller"),
) -> str:
    """The user whose deposits are read: the BFF-vouched caller, never a
    free query param."""
    principal = resolve_api_key(
        extract_api_key(
            x_rematch_key=x_rematch_key,
            x_boardman_key=x_boardman_key,
            x_stack_key=x_stack_key,
            authorization=authorization,
        )
    )
    if principal is None:
        raise HTTPException(status_code=401, detail="invalid or missing Stack API key")
    if not principal.is_master:
        raise HTTPException(status_code=403, detail="deposit routes are platform only")
    caller = (x_boardman_caller or "").strip()
    claimed = (user_id or "").strip()
    if caller:
        if claimed and claimed != caller:
            raise HTTPException(status_code=403, detail="user_id must be the signed-in caller")
        return caller
    if not claimed:
        raise HTTPException(status_code=422, detail="user_id is required")
    return claimed


def _get_supabase():
    from backend.supabase_client import get_supabase

    return get_supabase()


@router.get("/deposit/address")
async def deposit_address(user_id: str = Depends(require_deposit_user)):
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
    user_id: str = Depends(require_deposit_user),
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
