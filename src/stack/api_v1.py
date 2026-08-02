"""
Rematch Stack HTTP API v1 — match lifecycle for any client.

Auth: header ``X-Stack-Key: $STACK_API_KEY`` (or Authorization: Bearer …).
If STACK_API_KEY is unset, v1 routes return 503 (safe default).

Money rails: create/accept/report/settle use the same Supabase challenges +
settlement services as the Telegram bot. On-chain lock still goes through
existing escrow helpers (caller supplies profile UUIDs).
"""
from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Optional

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/stack/v1", tags=["rematch-stack-v1"])


def _require_stack_key(
    x_stack_key: Optional[str] = Header(default=None, alias="X-Stack-Key"),
    authorization: Optional[str] = Header(default=None),
) -> str:
    expected = (os.getenv("STACK_API_KEY") or "").strip()
    if not expected:
        raise HTTPException(
            status_code=503,
            detail="STACK_API_KEY not configured on server",
        )
    got = (x_stack_key or "").strip()
    if not got and authorization:
        auth = authorization.strip()
        if auth.lower().startswith("bearer "):
            got = auth[7:].strip()
    if not got or got != expected:
        raise HTTPException(status_code=401, detail="invalid or missing stack API key")
    return got


class CreateMatchBody(BaseModel):
    creator_id: str = Field(..., description="Profile UUID of challenger")
    opponent_id: Optional[str] = Field(None, description="Profile UUID; omit for public")
    amount_usdc: float = Field(..., gt=0, le=10_000)
    game_id: str = Field("imessage.8_ball", description="Catalog game_id")
    chain_id: str = "arc"
    visibility: str = "private"
    message: Optional[str] = None


class AcceptMatchBody(BaseModel):
    opponent_id: str


class LockMatchBody(BaseModel):
    profile_id: str


class ReportBody(BaseModel):
    profile_id: str
    """For scoreline games: home-away like 5-3. For binary: W or L (reporter perspective)."""
    score: str
    claim_win: Optional[bool] = None


def _sb():
    from backend.supabase_client import get_supabase

    return get_supabase()


def _load_challenge(match_id: str) -> Optional[dict]:
    from gaming.src.backend.services.match_codes import load_challenge_by_ref

    return load_challenge_by_ref(match_id)


@router.get("/health")
async def v1_health(_: str = Depends(_require_stack_key)):
    from gaming.src.stack.facade import get_stack

    return {"success": True, "api": "v1", **get_stack().health().to_dict()}


@router.get("/games")
async def v1_games(
    category: Optional[str] = None,
    _: str = Depends(_require_stack_key),
):
    from gaming.src.backend.services.game_catalog import list_categories, list_games

    return {
        "success": True,
        "categories": list_categories(enabled_only=True),
        "games": list_games(category=category, enabled_only=True),
    }


@router.get("/games/{game_id}")
async def v1_game(game_id: str, _: str = Depends(_require_stack_key)):
    from gaming.src.backend.services.game_catalog import get_game

    g = get_game(game_id)
    if not g:
        raise HTTPException(status_code=404, detail="game not found")
    return {"success": True, "game": g}


@router.post("/matches")
async def v1_create_match(body: CreateMatchBody, _: str = Depends(_require_stack_key)):
    from gaming.src.backend.services.challenge_compat import denormalize_challenge
    from gaming.src.backend.services.game_catalog import get_game, display_name
    from gaming.src.backend.services.match_codes import new_challenge_public_code
    from gaming.src.backend.services.play_points import assert_can_start_or_accept
    from gaming.src.backend.services.safety import assert_money_ops_allowed, validate_stake

    if not get_game(body.game_id) and not body.game_id.startswith("imessage."):
        # allow known console ids without catalog row
        if body.game_id not in ("EAFC", "NBA2K", "Other"):
            raise HTTPException(status_code=400, detail=f"unknown game_id: {body.game_id}")

    amount = Decimal(str(body.amount_usdc))
    err = validate_stake(amount)
    if err:
        raise HTTPException(status_code=400, detail=err)

    gate = assert_money_ops_allowed(
        body.creator_id, action="challenge", amount=amount, kind="stake"
    )
    if gate:
        raise HTTPException(status_code=403, detail=gate)

    blocked = assert_can_start_or_accept(body.creator_id)
    if blocked:
        raise HTTPException(status_code=409, detail=blocked)

    if body.opponent_id:
        blocked2 = assert_can_start_or_accept(body.opponent_id)
        if blocked2:
            raise HTTPException(status_code=409, detail=f"opponent: {blocked2}")

    challenge_id = str(uuid.uuid4())
    public_code = new_challenge_public_code()
    expires = datetime.now(timezone.utc) + timedelta(hours=24)
    visibility = body.visibility if body.opponent_id else "public"
    record = denormalize_challenge(
        {
            "id": challenge_id,
            "public_code": public_code,
            "creator_id": body.creator_id,
            "opponent_id": body.opponent_id,
            "amount_usdc": float(amount),
            "game": body.game_id,
            "visibility": visibility,
            "status": "open",
            "expires_at": expires.isoformat(),
            "message": body.message or f"Stack: {display_name(body.game_id)}",
            "settlement_chain": body.chain_id or "arc",
        }
    )
    try:
        _sb().schema("gaming").table("challenges").insert(record).execute()
    except Exception as exc:
        logger.exception("[StackV1] create match failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return {
        "success": True,
        "match_id": challenge_id,
        "public_code": public_code,
        "game_id": body.game_id,
        "game_label": display_name(body.game_id),
        "status": "open",
        "amount_usdc": float(amount),
        "chain_id": body.chain_id or "arc",
    }


@router.get("/matches/{match_ref}")
async def v1_get_match(match_ref: str, _: str = Depends(_require_stack_key)):
    ch = _load_challenge(match_ref)
    if not ch:
        raise HTTPException(status_code=404, detail="match not found")
    from gaming.src.backend.services.game_catalog import display_name, proof_instructions
    from gaming.src.backend.services.match_codes import display_code

    return {
        "success": True,
        "match": {
            "id": ch.get("id"),
            "public_code": display_code(ch),
            "status": ch.get("status"),
            "game_id": ch.get("game"),
            "game_label": display_name(str(ch.get("game") or "")),
            "amount_usdc": ch.get("amount_usdc"),
            "creator_id": ch.get("creator_id"),
            "opponent_id": ch.get("opponent_id"),
            "settlement_chain": ch.get("settlement_chain") or "arc",
            "proof_hint": proof_instructions(str(ch.get("game") or "")),
        },
    }


@router.post("/matches/{match_ref}/accept")
async def v1_accept_match(
    match_ref: str, body: AcceptMatchBody, _: str = Depends(_require_stack_key)
):
    from gaming.src.backend.services.challenge_compat import denormalize_challenge
    from gaming.src.backend.services.play_points import assert_can_start_or_accept

    ch = _load_challenge(match_ref)
    if not ch:
        raise HTTPException(status_code=404, detail="match not found")
    if ch.get("status") not in ("open",):
        raise HTTPException(status_code=409, detail=f"cannot accept status={ch.get('status')}")

    if ch.get("opponent_id") and ch.get("opponent_id") != body.opponent_id:
        raise HTTPException(status_code=403, detail="not the invited opponent")

    blocked = assert_can_start_or_accept(body.opponent_id)
    if blocked:
        raise HTTPException(status_code=409, detail=blocked)

    update = denormalize_challenge(
        {
            "opponent_id": body.opponent_id,
            "status": "accepted",
        }
    )
    _sb().schema("gaming").table("challenges").update(update).eq("id", ch["id"]).execute()
    return {"success": True, "match_id": ch["id"], "status": "accepted"}


@router.post("/matches/{match_ref}/lock")
async def v1_lock_match(
    match_ref: str, body: LockMatchBody, _: str = Depends(_require_stack_key)
):
    """On-chain dual lock via existing escrow helpers."""
    from gaming.src.backend.services.clawstation_circle import (
        CircleWalletError,
        ensure_user_wallet,
        get_usdc_balance,
    )
    from gaming.src.backend.services.clawstation_escrow import (
        EscrowError,
        approve_and_create_match,
        approve_and_join_match,
    )
    from gaming.src.backend.services.safety import assert_money_ops_allowed

    ch = _load_challenge(match_ref)
    if not ch:
        raise HTTPException(status_code=404, detail="match not found")

    pid = body.profile_id
    is_creator = pid == ch.get("creator_id")
    is_opp = pid == ch.get("opponent_id")
    if not is_creator and not is_opp:
        raise HTTPException(status_code=403, detail="not a match participant")

    amount = Decimal(str(ch["amount_usdc"]))
    chain = ch.get("settlement_chain") or "arc"
    gate = assert_money_ops_allowed(pid, action="lock", amount=amount, kind="lock")
    if gate:
        raise HTTPException(status_code=403, detail=gate)

    try:
        await ensure_user_wallet(pid, chain_id=chain)
        bal = await get_usdc_balance(pid, chain_id=chain)
        if bal < amount:
            raise HTTPException(
                status_code=402,
                detail=f"insufficient balance: have {bal}, need {amount}",
            )
        if is_creator:
            if ch.get("status") == "open" and ch.get("opponent_id"):
                _sb().schema("gaming").table("challenges").update(
                    {"status": "accepted"}
                ).eq("id", ch["id"]).execute()
            result = await approve_and_create_match(pid, ch["id"], amount)
        else:
            if ch.get("status") != "creator_locked":
                raise HTTPException(
                    status_code=409, detail="wait for creator to lock first"
                )
            result = await approve_and_join_match(pid, ch["id"], amount)
    except HTTPException:
        raise
    except (EscrowError, CircleWalletError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("[StackV1] lock failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    ch2 = _load_challenge(ch["id"]) or ch
    return {
        "success": True,
        "match_id": ch["id"],
        "status": ch2.get("status"),
        "lock": result if isinstance(result, dict) else {"ok": True},
    }


@router.post("/matches/{match_ref}/report")
async def v1_report_score(
    match_ref: str, body: ReportBody, _: str = Depends(_require_stack_key)
):
    """Text score report (screenshot via /proof). Uses same DB fields as bot."""
    from gaming.src.backend.services.challenge_compat import denormalize_challenge
    from gaming.src.backend.services.game_catalog import outcome_type

    ch = _load_challenge(match_ref)
    if not ch:
        raise HTTPException(status_code=404, detail="match not found")

    pid = body.profile_id
    is_creator = pid == ch.get("creator_id")
    is_opp = pid == ch.get("opponent_id")
    if not is_creator and not is_opp:
        raise HTTPException(status_code=403, detail="not a participant")

    raw = (body.score or "").strip().upper()
    game = str(ch.get("game") or "")
    otype = outcome_type(game)

    home = away = None
    single = None
    if otype == "binary_winner" or raw in ("W", "L", "WIN", "LOSE", "LOSS"):
        # Reporter claim: W => they won => map via claim_win or W/L
        won = body.claim_win
        if won is None:
            won = raw in ("W", "WIN", "1")
        # Store as reporter's perspective scoreline 1-0 or 0-1
        if is_creator:
            home, away = (1, 0) if won else (0, 1)
        else:
            # opponent report: invert so home=creator side convention when possible
            home, away = (0, 1) if won else (1, 0)
    else:
        import re

        m = re.search(r"(\d+)\s*[-:]\s*(\d+)", raw)
        if not m:
            raise HTTPException(
                status_code=400,
                detail="score must be H-A (e.g. 5-3) or W/L for binary games",
            )
        home, away = int(m.group(1)), int(m.group(2))

    update: dict[str, Any] = {}
    if is_creator:
        update["creator_reported_home"] = home
        update["creator_reported_away"] = away
        if single is not None:
            update["creator_score"] = single
    else:
        update["opponent_reported_home"] = home
        update["opponent_reported_away"] = away
        if single is not None:
            update["opponent_score"] = single

    try:
        _sb().schema("gaming").table("challenges").update(
            denormalize_challenge(update)
        ).eq("id", ch["id"]).execute()
    except Exception as exc:
        # fallback column names
        try:
            _sb().schema("gaming").table("challenges").update(update).eq(
                "id", ch["id"]
            ).execute()
        except Exception as exc2:
            raise HTTPException(status_code=500, detail=str(exc2)) from exc

    # Attempt settle if ready
    settle_result = None
    try:
        from gaming.src.backend.services.clawstation_settlement import settle_challenge

        settle_result = await settle_challenge(ch["id"])
    except Exception as exc:
        logger.info("[StackV1] settle after report skipped: %s", exc)

    ch2 = _load_challenge(ch["id"]) or ch
    return {
        "success": True,
        "match_id": ch["id"],
        "status": ch2.get("status"),
        "reported": {"home": home, "away": away},
        "settle": settle_result,
    }


@router.post("/matches/{match_ref}/proof")
async def v1_submit_proof(
    match_ref: str,
    profile_id: str = Form(...),
    score: str = Form(""),
    file: UploadFile = File(...),
    _: str = Depends(_require_stack_key),
):
    """Upload final screenshot (+ optional score caption). Runs AI when possible."""
    import base64

    ch = _load_challenge(match_ref)
    if not ch:
        raise HTTPException(status_code=404, detail="match not found")

    pid = profile_id
    is_creator = pid == ch.get("creator_id")
    is_opp = pid == ch.get("opponent_id")
    if not is_creator and not is_opp:
        raise HTTPException(status_code=403, detail="not a participant")

    data = await file.read()
    if not data or len(data) > 8_000_000:
        raise HTTPException(status_code=400, detail="invalid image size")
    image_b64 = base64.b64encode(data).decode("ascii")

    ai: dict[str, Any] = {}
    try:
        from gaming.src.bot.handlers.submit_score import _run_ai_on_screenshot

        ai = await _run_ai_on_screenshot(image_b64, ch)
    except Exception as exc:
        logger.warning("[StackV1] AI proof failed: %s", exc)
        ai = {"ok": False, "error": str(exc)}

    # Store a marker that proof was submitted (URL storage optional)
    from gaming.src.backend.services.challenge_compat import denormalize_challenge

    update: dict[str, Any] = {}
    marker = f"stack_proof:{uuid.uuid4().hex[:12]}"
    if is_creator:
        update["screenshot_creator_url"] = marker
    else:
        update["screenshot_opponent_url"] = marker

    # If AI got scores, write them
    if ai.get("ok") and ai.get("player1_score") is not None:
        try:
            from gaming.src.bot.handlers.submit_score import _map_ai_to_home_away

            home, away = _map_ai_to_home_away(ai, ch)
            if home is not None and away is not None:
                if is_creator:
                    update["creator_reported_home"] = home
                    update["creator_reported_away"] = away
                else:
                    update["opponent_reported_home"] = home
                    update["opponent_reported_away"] = away
        except Exception:
            pass
    elif score.strip():
        # text fallback via report endpoint logic
        pass

    try:
        _sb().schema("gaming").table("challenges").update(
            denormalize_challenge(update)
        ).eq("id", ch["id"]).execute()
    except Exception as exc:
        logger.warning("[StackV1] proof column update: %s", exc)

    if score.strip() and not ai.get("ok"):
        # apply text score
        await v1_report_score(
            match_ref,
            ReportBody(profile_id=pid, score=score),
            _,
        )

    settle_result = None
    try:
        from gaming.src.backend.services.clawstation_settlement import settle_challenge

        settle_result = await settle_challenge(ch["id"])
    except Exception as exc:
        logger.info("[StackV1] settle after proof: %s", exc)

    return {
        "success": True,
        "match_id": ch["id"],
        "ai": {
            "ok": ai.get("ok"),
            "confidence": ai.get("confidence"),
            "score_string": ai.get("score_string"),
            "error": ai.get("error"),
        },
        "settle": settle_result,
    }


@router.post("/matches/{match_ref}/settle")
async def v1_settle(match_ref: str, _: str = Depends(_require_stack_key)):
    ch = _load_challenge(match_ref)
    if not ch:
        raise HTTPException(status_code=404, detail="match not found")
    try:
        from gaming.src.backend.services.clawstation_settlement import settle_challenge

        result = await settle_challenge(ch["id"])
        return {"success": True, "match_id": ch["id"], "result": result}
    except Exception as exc:
        logger.exception("[StackV1] settle failed")
        raise HTTPException(status_code=400, detail=str(exc)) from exc
