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
    """Resolve telegram_id → Rematch profile (for web login).

    Looks up Supabase ``profiles`` by ``telegram_id`` (same row the bot creates on /start).
    """
    _require_key(x_rematch_key, x_stack_key, authorization)
    try:
        from gaming.src.bot.utils.db import _fetch_by_telegram_id

        tid = int(telegram_id)
        row = _fetch_by_telegram_id(tid)
        # Some older rows stored telegram_id as text — retry string match
        if not row:
            try:
                sb = _sb()
                r = (
                    sb.table("profiles")
                    .select(
                        "id, display_name, gaming_tag, gaming_tier, gaming_reputation_score, "
                        "telegram_id, circle_wallet_id, gaming_deposit_address, play_points"
                    )
                    .eq("telegram_id", str(tid))
                    .limit(1)
                    .execute()
                )
                data = r.data or []
                row = data[0] if data else None
            except Exception:
                logger.warning(
                    "[RematchWeb] string telegram_id fallback failed for %s", tid, exc_info=True
                )
    except Exception as exc:
        logger.exception("[RematchWeb] profile lookup failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    if not row:
        logger.info("[RematchWeb] no profile for telegram_id=%s", telegram_id)
        return {
            "success": True,
            "found": False,
            "telegram_id": telegram_id,
            "message": "No profile yet — open the Telegram bot once (/start)",
        }
    logger.info(
        "[RematchWeb] found profile id=%s tag=%s for telegram_id=%s",
        row.get("id"),
        row.get("gaming_tag"),
        telegram_id,
    )

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


@router.post("/spectator/bet")
async def web_spectator_bet(
    body: dict,
    x_rematch_key: Optional[str] = Header(default=None, alias="X-Rematch-Key"),
    x_stack_key: Optional[str] = Header(default=None, alias="X-Stack-Key"),
    authorization: Optional[str] = Header(default=None),
):
    """
    Debit a human play balance for an agent-arena spectator stake.
    Same profile / wallet identity as Telegram bot.

    body: { profile_id, amount, side, match_id? }
    """
    _require_key(x_rematch_key, x_stack_key, authorization)
    profile_id = str(body.get("profile_id") or "").strip()
    try:
        amount = float(body.get("amount") or 0)
    except (TypeError, ValueError):
        amount = 0.0
    side = str(body.get("side") or "").strip().lower()
    match_id = str(body.get("match_id") or "arena")[:64]

    if not profile_id:
        raise HTTPException(status_code=400, detail="profile_id required")
    if amount < 0.25:
        raise HTTPException(status_code=400, detail="amount must be >= 0.25")
    if side not in ("a", "b", "raja", "nero", "white", "black"):
        raise HTTPException(status_code=400, detail="side must be a|b|raja|nero")
    if side in ("raja", "white"):
        side = "a"
    if side in ("nero", "black"):
        side = "b"

    try:
        from gaming.src.backend.services.safety import is_paused
        from gaming.src.backend.services.clawstation_circle import get_balance_summary
        from gaming.src.backend.db_layer_blockchain import debit_wallet, get_wallet_balance

        if is_paused():
            raise HTTPException(status_code=503, detail="platform_paused")

        summary = await get_balance_summary(profile_id)
        # Prefer internal ledger (bot play balance); fall back to spendable view
        ledger = float(summary.get("ledger_usdc") or 0)
        spendable = float(summary.get("spendable_usdc") or 0)
        available = max(ledger, spendable)
        if available + 1e-9 < amount:
            return {
                "success": False,
                "error": "insufficient_balance",
                "balance": available,
                "address": summary.get("address") or "",
                "message": "Not enough USDC on your Boardman wallet. Fund via Telegram bot → Get money.",
            }

        ok = await debit_wallet(profile_id, amount)
        if not ok:
            bal = await get_wallet_balance(profile_id)
            return {
                "success": False,
                "error": "insufficient_balance",
                "balance": float(bal),
                "address": summary.get("address") or "",
            }

        new_bal = await get_wallet_balance(profile_id)
        try:
            from decimal import Decimal

            from gaming.src.backend.services.wallet_activity import log_debit

            log_debit(
                profile_id,
                Decimal(str(amount)),
                str(summary.get("chain_id") or "arc"),
                status="spectator_bet",
                source=f"arena:{match_id}:{side}",
            )
        except Exception:
            pass

        return {
            "success": True,
            "profile_id": profile_id,
            "amount": amount,
            "side": side,
            "match_id": match_id,
            "balance": float(new_bal),
            "address": summary.get("address") or "",
            "wallet": summary.get("address") or "",
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("[RematchWeb] spectator bet failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/spectator/payout")
async def web_spectator_payout(
    body: dict,
    x_rematch_key: Optional[str] = Header(default=None, alias="X-Rematch-Key"),
    x_stack_key: Optional[str] = Header(default=None, alias="X-Stack-Key"),
    authorization: Optional[str] = Header(default=None),
):
    """
    Credit winnings (or refund) back to the same Telegram-linked profile wallet.
    body: { profile_id, amount, reason? }
    """
    _require_key(x_rematch_key, x_stack_key, authorization)
    profile_id = str(body.get("profile_id") or "").strip()
    try:
        amount = float(body.get("amount") or 0)
    except (TypeError, ValueError):
        amount = 0.0
    reason = str(body.get("reason") or "spectator_payout")[:80]
    if not profile_id:
        raise HTTPException(status_code=400, detail="profile_id required")
    if amount <= 0:
        raise HTTPException(status_code=400, detail="amount must be positive")
    try:
        from gaming.src.backend.db_layer_blockchain import credit_wallet, get_wallet_balance

        await credit_wallet(profile_id, amount, tx_hash=f"spectator:{reason}", source=reason)
        bal = await get_wallet_balance(profile_id)
        return {"success": True, "profile_id": profile_id, "amount": amount, "balance": float(bal)}
    except Exception as exc:
        logger.exception("[RematchWeb] spectator payout failed")
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
