"""
Rematch web BFF helpers — profile lookup + wallet snapshot for playingsidequest.fun.

Auth: X-Rematch-Key (or legacy X-Stack-Key) == REMATCH_API_KEY
(legacy STACK_API_KEY still accepted). Never call from the browser with this key;
only the Next.js BFF may use it.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Query

from gaming.src.backend.rematch_auth import extract_api_key, rematch_api_key

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/rematch/web", tags=["rematch-web"])


def _require_key(
    x_rematch_key: Optional[str] = None,
    x_stack_key: Optional[str] = None,
    authorization: Optional[str] = None,
) -> str:
    expected = rematch_api_key()
    if not expected:
        raise HTTPException(
            status_code=503,
            detail="REMATCH_API_KEY not configured (legacy: STACK_API_KEY)",
        )
    got = extract_api_key(
        x_rematch_key=x_rematch_key,
        x_stack_key=x_stack_key,
        authorization=authorization,
    )
    if got != expected:
        raise HTTPException(status_code=401, detail="invalid rematch api key")
    return got


def _sb():
    from backend.supabase_client import get_supabase

    return get_supabase()


@router.get("/profile")
async def web_profile_by_telegram(
    telegram_id: int = Query(..., description="Telegram user id"),
    x_rematch_key: Optional[str] = Header(default=None, alias="X-Rematch-Key"),
    x_stack_key: Optional[str] = Header(default=None, alias="X-Stack-Key"),
    authorization: Optional[str] = Header(default=None),
):
    """Resolve telegram_id → Rematch profile (for web login)."""
    _require_key(x_rematch_key, x_stack_key, authorization)
    try:
        from gaming.src.bot.utils.db import _fetch_by_telegram_id

        row = _fetch_by_telegram_id(int(telegram_id))
    except Exception as exc:
        logger.exception("[RematchWeb] profile lookup failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    if not row:
        return {
            "success": True,
            "found": False,
            "telegram_id": telegram_id,
            "message": "No profile yet — open the Telegram bot once (/start)",
        }

    return {
        "success": True,
        "found": True,
        "profile_id": row["id"],
        "id": row["id"],
        "gaming_tag": row.get("gaming_tag"),
        "display_name": row.get("display_name"),
        "telegram_id": row.get("telegram_id"),
        "play_points": row.get("play_points") or 0,
    }


@router.get("/profile/by-tag")
async def web_profile_by_tag(
    tag: str = Query(...),
    x_rematch_key: Optional[str] = Header(default=None, alias="X-Rematch-Key"),
    x_stack_key: Optional[str] = Header(default=None, alias="X-Stack-Key"),
    authorization: Optional[str] = Header(default=None),
):
    _require_key(x_rematch_key, x_stack_key, authorization)
    clean = tag.strip().lstrip("@").lower()
    if not clean:
        raise HTTPException(status_code=400, detail="tag required")
    try:
        r = (
            _sb()
            .table("profiles")
            .select("id, gaming_tag, display_name, telegram_id")
            .ilike("gaming_tag", clean)
            .limit(1)
            .execute()
        )
        row = (r.data or [None])[0]
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    if not row:
        return {"success": True, "found": False, "tag": clean}
    return {
        "success": True,
        "found": True,
        "profile_id": row["id"],
        "gaming_tag": row.get("gaming_tag"),
        "display_name": row.get("display_name"),
    }


@router.get("/wallet")
async def web_wallet_snapshot(
    profile_id: str = Query(...),
    x_rematch_key: Optional[str] = Header(default=None, alias="X-Rematch-Key"),
    x_stack_key: Optional[str] = Header(default=None, alias="X-Stack-Key"),
    authorization: Optional[str] = Header(default=None),
):
    """Play-wallet balance summary (spendable + other addresses)."""
    _require_key(x_rematch_key, x_stack_key, authorization)
    try:
        from gaming.src.backend.services.clawstation_circle import get_balance_summary
        from gaming.src.backend.services.safety import is_paused

        summary = await get_balance_summary(profile_id)
        play_points = 0
        tag = name = None
        try:
            r = (
                _sb()
                .table("profiles")
                .select("play_points, gaming_tag, display_name")
                .eq("id", profile_id)
                .limit(1)
                .execute()
            )
            row = (r.data or [None])[0] or {}
            play_points = int(row.get("play_points") or 0)
            tag = row.get("gaming_tag")
            name = row.get("display_name")
        except Exception:
            pass

        spendable = float(summary.get("spendable_usdc") or 0)
        other = float(summary.get("other_usdc") or 0)
        return {
            "success": True,
            "profile_id": profile_id,
            "gaming_tag": tag,
            "display_name": name,
            "balance": spendable,
            "total_balance": spendable + other,
            "other_balance": other,
            "other_address": summary.get("other_address") or "",
            "address": summary.get("address") or "",
            "chain_id": summary.get("chain_id") or "arc",
            "ledger_usdc": float(summary.get("ledger_usdc") or 0),
            "play_points": play_points,
            "paused": bool(is_paused()),
            "balance_error": summary.get("balance_error"),
        }
    except Exception as exc:
        logger.exception("[RematchWeb] wallet snapshot failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/matches")
async def web_match_history(
    profile_id: str = Query(...),
    limit: int = Query(30, ge=1, le=100),
    x_rematch_key: Optional[str] = Header(default=None, alias="X-Rematch-Key"),
    x_stack_key: Optional[str] = Header(default=None, alias="X-Stack-Key"),
    authorization: Optional[str] = Header(default=None),
):
    """Recent matches for a profile — same history as Telegram bot."""
    _require_key(x_rematch_key, x_stack_key, authorization)
    try:
        from gaming.src.backend.services.rematch_public import get_match_history

        matches = get_match_history(profile_id, limit, include_open=True)
        return {
            "success": True,
            "profile_id": profile_id,
            "matches": matches,
            "count": len(matches),
        }
    except Exception as exc:
        logger.exception("[RematchWeb] match history failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
