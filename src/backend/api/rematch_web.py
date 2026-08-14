"""
Rematch web BFF helpers — profile lookup + wallet snapshot for playingsidequest.fun.

Auth: X-Rematch-Key (or legacy X-Stack-Key) == REMATCH_API_KEY
(legacy STACK_API_KEY still accepted). Never call from the browser with this key;
only the Next.js BFF may use it.
"""
from __future__ import annotations

import logging
import os
from decimal import Decimal
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


def _resolve_live_match_id(match_id: str) -> str:
    """Map arena/live/empty onto the current House table. Never return 'arena'."""
    from gaming.src.stack.agentic.house import LIVE_STATUSES
    from gaming.src.stack.agentic.matches import get_match_service

    mid = (match_id or "").strip()
    if mid and mid.lower() not in {"arena", "live"}:
        return mid
    pair = {"agent_raja_kia_alekhine", "agent_nero_sicilian_french"}
    for m in get_match_service().list_matches(50):
        if m.get("status") in LIVE_STATUSES and {
            m.get("agent_a_id"),
            m.get("agent_b_id"),
        } == pair:
            found = str(m.get("match_id") or "")
            if found and found.lower() not in {"arena", "live"}:
                return found
    raise HTTPException(
        status_code=400,
        detail="no live match to bet on — start Auto play first",
    )


async def _deposit_spectator_onchain(
    *,
    profile_id: str,
    match_id: str,
    side: str,
    amount: float,
    user_address: str,
) -> dict:
    """House depositFor + JSON projection. Caller already debited the ledger."""
    from gaming.src.stack.agentic.economy.spectator import SpectatorBook
    from gaming.src.stack.agentic.house import resolve_side
    from gaming.src.stack.agentic.matches import get_match_service
    from gaming.src.stack.agentic.spectator_onchain import deposit_for

    svc = get_match_service()
    match = svc.get(match_id)
    if not match:
        raise ValueError(f"match not found: {match_id}")
    slot = resolve_side(match, side)
    if not user_address or not str(user_address).startswith("0x"):
        raise ValueError("on-chain spectator bet needs your Boardman wallet address")
    dep = deposit_for(
        match_id,
        user_address,
        Decimal(str(amount)),
        slot,
        match=match,
    )
    book = SpectatorBook()
    if not (book.get(match_id) or {}).get("onchain"):
        book.mark_onchain(
            match_id,
            pool=str(dep.get("pool") or ""),
            open_tx_hash=str(dep.get("open_tx_hash") or ""),
        )
    projected = book.project_deposit(
        match_id,
        bettor_id=profile_id,
        side=slot,
        amount_usdc=Decimal(str(amount)),
        tx_hash=str(dep.get("tx_hash") or ""),
        explorer=str(dep.get("explorer") or ""),
    )
    rec = svc.get(match_id) or match
    rec["spectator_book"] = {
        "match_id": match_id,
        "status": projected.get("status"),
        "totals": projected.get("totals"),
        "pot_cap_usdc": projected.get("pot_cap_usdc"),
        "onchain": True,
        "pool": projected.get("pool") or dep.get("pool"),
        "deposit_txs": [
            {"tx_hash": b.get("tx_hash"), "explorer": b.get("explorer")}
            for b in (projected.get("bets") or [])
            if b.get("tx_hash")
        ],
    }
    data = svc._load()
    data["matches"][match_id] = rec
    svc._save(data)
    return {
        "tx_hash": dep.get("tx_hash"),
        "explorer": dep.get("explorer"),
        "book": {"match_id": match_id, "side": slot, "book": projected},
    }


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
    match_id = str(body.get("match_id") or "").strip()[:64]

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

    from gaming.src.stack.agentic.spectator_onchain import spectator_onchain_enabled

    try:
        match_id = _resolve_live_match_id(match_id)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("[RematchWeb] live match lookup failed")
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if spectator_onchain_enabled() and match_id.lower() in {"arena", "live", ""}:
        raise HTTPException(
            status_code=400,
            detail="spectator on-chain requires a live match_id — start Auto play first",
        )

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

        # Telegram-mediated approval: ask the user to approve the spend (unless
        # they've pre-approved bets with 'always'). Declined/expired → no debit.
        try:
            from gaming.src.backend.services.tx_approval import request_approval

            decision = await request_approval(
                profile_id,
                "spectator_bet",
                {"amount": amount, "side": side, "match_id": match_id},
            )
        except Exception as exc:
            logger.exception("[RematchWeb] approval gate failed")
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        if decision.get("status") in ("denied", "expired", "telegram_unreachable"):
            msg = {
                "denied": "You didn't approve this spend in Telegram. Nothing was charged.",
                "expired": "The approval request expired (2 min). Nothing was charged — try again.",
                "telegram_unreachable": (
                    "Could not ping Telegram. Open @myboardmanOfficialBot, tap Start, then try again."
                ),
            }.get(decision.get("status") or "", "Approval failed. Nothing was charged.")
            return {
                "success": False,
                "error": f"approval_{decision['status']}",
                "approval_id": decision.get("approval_id"),
                "message": decision.get("message") or msg,
            }
        if decision.get("mode") == "always":
            logger.info("[RematchWeb] spectator bet auto-approved (always) profile=%s", profile_id)

        # Custodial debit first (Telegram play balance). On-chain path then
        # depositFor from House float so the bet gets an Arc hash.
        ok = await debit_wallet(profile_id, amount)
        if not ok:
            bal = await get_wallet_balance(profile_id)
            return {
                "success": False,
                "error": "insufficient_balance",
                "balance": float(bal),
                "address": summary.get("address") or "",
            }

        chain_tx: dict = {}
        book = None
        if spectator_onchain_enabled():
            try:
                chain_tx = await _deposit_spectator_onchain(
                    profile_id=profile_id,
                    match_id=match_id,
                    side=side,
                    amount=amount,
                    user_address=str(summary.get("address") or ""),
                )
                book = chain_tx.get("book")
            except Exception as exc:
                logger.exception("[RematchWeb] spectator on-chain deposit failed — refunding ledger")
                try:
                    from gaming.src.backend.db_layer_blockchain import credit_wallet

                    await credit_wallet(
                        profile_id,
                        amount,
                        tx_hash="spectator_refund",
                        source="spectator_onchain_failed",
                    )
                except Exception:
                    logger.exception("[RematchWeb] ledger refund after failed depositFor also failed")
                return {
                    "success": False,
                    "error": "spectator_onchain_failed",
                    "message": str(exc),
                    "match_id": match_id,
                    "address": summary.get("address") or "",
                }
        else:
            try:
                from gaming.src.stack.agentic.house import get_house

                book = get_house().take_bet(
                    match_id,
                    bettor_id=profile_id,
                    side=side,
                    amount_usdc=Decimal(str(amount)),
                )
            except Exception:
                logger.exception("[RematchWeb] house take_bet failed match=%s", match_id)

        new_bal = await get_wallet_balance(profile_id)
        try:
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
            "match_id": (book or {}).get("match_id") or match_id,
            "balance": float(new_bal),
            "address": summary.get("address") or "",
            "wallet": summary.get("address") or "",
            "house_book": bool(book),
            "tx_hash": chain_tx.get("tx_hash") or "",
            "explorer": chain_tx.get("explorer") or "",
            "onchain": bool(chain_tx.get("tx_hash")),
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


_AGENT_ID_ALIASES = {
    "raja": "agent_raja_kia_alekhine",
    "nero": "agent_nero_sicilian_french",
}


@router.post("/spectator/lp")
async def web_spectator_lp(
    body: dict,
    x_rematch_key: Optional[str] = Header(default=None, alias="X-Rematch-Key"),
    x_stack_key: Optional[str] = Header(default=None, alias="X-Stack-Key"),
    authorization: Optional[str] = Header(default=None),
):
    """
    Real LP deposit: debit the human's wallet, credit the agent's LP pool.
    Gate: Telegram-mediated approval (bets vs LP have separate always-approve).

    body: { profile_id, agent_id, amount, agent_name? }
    """
    _require_key(x_rematch_key, x_stack_key, authorization)
    profile_id = str(body.get("profile_id") or "").strip()
    try:
        amount = float(body.get("amount") or 0)
    except (TypeError, ValueError):
        amount = 0.0
    agent_id = str(body.get("agent_id") or "").strip().lower()
    agent_name = str(body.get("agent_name") or "").strip()
    agent_id = _AGENT_ID_ALIASES.get(agent_id, agent_id)

    if not profile_id:
        raise HTTPException(status_code=400, detail="profile_id required")
    if not agent_id:
        raise HTTPException(status_code=400, detail="agent_id required")
    if amount < 0.25:
        raise HTTPException(status_code=400, detail="amount must be >= 0.25")

    try:
        from decimal import Decimal

        from gaming.src.backend.services.safety import is_paused
        from gaming.src.backend.services.clawstation_circle import get_balance_summary
        from gaming.src.backend.db_layer_blockchain import debit_wallet, get_wallet_balance

        if is_paused():
            raise HTTPException(status_code=503, detail="platform_paused")

        summary = await get_balance_summary(profile_id)
        ledger = float(summary.get("ledger_usdc") or 0)
        spendable = float(summary.get("spendable_usdc") or 0)
        available = max(ledger, spendable)
        if available + 1e-9 < amount:
            return {
                "success": False,
                "error": "insufficient_balance",
                "balance": available,
                "address": summary.get("address") or "",
                "message": "Not enough USDC on your Boardman wallet.",
            }

        from gaming.src.backend.services.tx_approval import request_approval

        decision = await request_approval(
            profile_id,
            "lp_deposit",
            {"amount": amount, "agent_id": agent_id, "agent_name": agent_name},
        )
        if decision.get("status") in ("denied", "expired", "telegram_unreachable"):
            msg = {
                "denied": "You didn't approve this LP deposit in Telegram. Nothing was charged.",
                "expired": "The approval request expired (2 min). Nothing was charged — try again.",
                "telegram_unreachable": (
                    "Could not ping Telegram. Open @myboardmanOfficialBot, tap Start, then try again."
                ),
            }.get(decision.get("status") or "", "Approval failed. Nothing was charged.")
            return {
                "success": False,
                "error": f"approval_{decision['status']}",
                "approval_id": decision.get("approval_id"),
                "message": decision.get("message") or msg,
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

        from gaming.src.stack.agentic.economy.lp import AgentLPPool

        pool = AgentLPPool().deposit(
            agent_id,
            lp_id=profile_id,
            amount_usdc=Decimal(str(amount)),
        )

        new_bal = await get_wallet_balance(profile_id)
        try:
            from gaming.src.backend.services.wallet_activity import log_debit

            log_debit(
                profile_id,
                Decimal(str(amount)),
                str(summary.get("chain_id") or "arc"),
                status="spectator_lp",
                source=f"lp:{agent_id}",
            )
        except Exception:
            pass

        return {
            "success": True,
            "profile_id": profile_id,
            "amount": amount,
            "agent_id": agent_id,
            "balance": float(new_bal),
            "address": summary.get("address") or "",
            "lp_total_usdc": pool.get("total_lp_usdc"),
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("[RematchWeb] spectator LP failed")
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
