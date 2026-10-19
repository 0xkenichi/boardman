"""
Rematch web BFF helpers — profile lookup + wallet snapshot for playingsidequest.fun.

Auth: X-Rematch-Key (or legacy X-Stack-Key) == REMATCH_API_KEY
(legacy STACK_API_KEY still accepted). Never call from the browser with this key;
only the Next.js BFF may use it.
"""
from __future__ import annotations

import asyncio
import hmac
import uuid
import logging
import os
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Query

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
    if not hmac.compare_digest(got.encode("utf-8"), expected.encode("utf-8")):
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


def _house_pull_dest() -> str:
    """Public House/ops address. Dest only — never treat BOARDMAN_RESOLVER_KEY as a key."""
    for key in (
        "BOARDMAN_OPS_USDC_ADDRESS",
        "BOARDMAN_FEE_RECIPIENT",
        "FEE_RECIPIENT_ADDRESS",
        "RESOLVER_ADDRESS",
        "BOARDMAN_HOUSE_WALLET",
    ):
        val = (os.getenv(key) or "").strip()
        if val.startswith("0x") and len(val) == 42:
            return val
    try:
        from gaming.src.stack.agentic.disbursement import house_public_wallet

        val = (house_public_wallet() or "").strip()
        if val.startswith("0x") and len(val) == 42:
            return val
    except Exception:
        pass
    raise ValueError("no House USDC address configured (BOARDMAN_OPS_USDC_ADDRESS)")


async def _pull_play_usdc(profile_id: str, amount: float, *, held: Decimal = Decimal("0")) -> dict:
    """Move USDC from the user's Circle play wallet (what Telegram shows).

    ``held`` is a stake already reserved on the play overlay for this very
    pull (``_reserve_play_stake``); it counts back toward the pre-check.
    """
    import asyncio

    from backend.circle_wallet_service import CircleWalletService
    from gaming.src.backend.services.chains import (
        get_circle_blockchain,
        get_circle_usdc_token_id,
        get_rpc_url,
        get_usdc_address,
    )
    from gaming.src.backend.services.clawstation_circle import (
        ensure_user_wallet,
        get_usdc_balance,
    )

    spendable = await get_usdc_balance(profile_id) + held
    if spendable + Decimal("0.000001") < Decimal(str(amount)):
        raise ValueError(f"Play wallet has ${spendable}, need ${amount}")
    wallet = await ensure_user_wallet(profile_id)
    wallet_id = wallet.get("wallet_id")
    if not wallet_id:
        raise ValueError("No Circle play wallet on this profile")
    dest = _house_pull_dest()
    cid = wallet.get("chain_id") or "arc"
    circle = CircleWalletService(
        blockchain=get_circle_blockchain(cid),
        usdc_address=get_usdc_address(cid),
        usdc_token_id=get_circle_usdc_token_id(cid),
        rpc_url=get_rpc_url(cid),
    )
    result = await asyncio.to_thread(circle.transfer_usdc, wallet_id, dest, float(amount))
    if not result.get("success"):
        raise ValueError(result.get("error") or "play wallet transfer failed")
    return result


class _SpendRefused(Exception):
    """Nothing was booked and nothing was charged."""

    def __init__(self, error: str, message: str) -> None:
        super().__init__(message)
        self.error = error
        self.message = message


def _finite_amount(raw) -> float:
    """Body amount as a finite float (NaN/inf would pass every `<` check)."""
    import math

    try:
        amount = float(raw or 0)
    except (TypeError, ValueError):
        return 0.0
    return amount if math.isfinite(amount) else 0.0


async def _reserve_play_stake(profile_id: str, amount: Decimal, key: str) -> None:
    """Take ``amount`` off the play balance (chain + overlay) BEFORE anything
    is booked: one conditional overlay debit, checked against a fresh chain
    read under the play_adjust lock. Raises _SpendRefused when it does not fit.

    Call it only under ``_play_spend_lock`` so no other spend of this profile
    moves the chain or the overlay between the read and the debit.
    """
    from gaming.src.backend.services.clawstation_circle import get_usdc_balance_strict
    from gaming.src.backend.services.play_adjust import InsufficientPlayBalance, apply_once

    chain, err = await get_usdc_balance_strict(profile_id)
    if err or chain is None:
        raise _SpendRefused("balance_unavailable", "Could not read your Boardman wallet. Nothing was charged.")
    try:
        apply_once(profile_id, -amount, key=f"hold:{key}", chain_usdc=Decimal(str(chain)))
    except InsufficientPlayBalance as exc:
        raise _SpendRefused(
            "insufficient_balance",
            f"Not enough USDC on your Boardman wallet ({exc}). Nothing was charged.",
        ) from exc


def _unreserve_play_stake(profile_id: str, amount: Decimal, key: str, why: str) -> None:
    from gaming.src.backend.services.play_adjust import apply_once

    apply_once(profile_id, amount, key=f"hold-{why}:{key}")


class _play_spend_lock:
    """One spend at a time per profile, across requests, threads and replicas."""

    def __init__(self, profile_id: str) -> None:
        from gaming.src.stack.agentic.db import leases

        self._cm = leases.exclusive(f"play-spend:{profile_id}")
        self._busy = leases.LeaseBusy

    def __enter__(self) -> None:
        try:
            self._cm.__enter__()
        except self._busy as exc:
            raise _SpendRefused(
                "spend_in_progress",
                "Another payment from this wallet is still going through. Try again in a moment.",
            ) from exc

    def __exit__(self, *exc) -> bool:
        return bool(self._cm.__exit__(*exc))


async def _book_profile_bet(
    *, profile_id: str, match_id: str, side: str, amount: float, spend_key: str, summary: dict
) -> dict:
    """Book a play-balance spectator bet and take its stake, exactly once.

    Demo book: reserve the stake on the overlay, book the ticket, then pull
    the USDC to the House (on success the reservation is released, since the
    chain now carries the debit; on failure the reservation IS the debit).
    On-chain book: pull -> pool deposit (the chain itself cannot overdraw).
    Returns {book, chain_tx, pulled, pull_err}; raises _SpendRefused when
    nothing was booked or charged.
    """
    from gaming.src.stack.agentic.house import get_house
    from gaming.src.stack.agentic.spectator_onchain import spectator_onchain_enabled

    out: dict = {"book": None, "chain_tx": {}, "pulled": False, "pull_err": ""}
    amt = Decimal(str(amount))
    with _play_spend_lock(profile_id):
        if spectator_onchain_enabled():
            try:
                # Chain is the book: pull to the House float, deposit into the
                # SpectatorPool, then project the confirmed tx. No take_bet —
                # place_bet refuses demo book entries on on-chain books.
                await _pull_play_usdc(profile_id, amount)
                out["pulled"] = True
                out["chain_tx"] = await _deposit_spectator_onchain(
                    profile_id=profile_id,
                    match_id=match_id,
                    side=side,
                    amount=amount,
                    user_address=str(summary.get("address") or ""),
                )
                if out["chain_tx"].get("book"):
                    out["book"] = out["chain_tx"].get("book")
            except Exception as exc:
                logger.exception("[RematchWeb] spectator pull/deposit failed match=%s", match_id)
                out["pull_err"] = str(exc)
                if out["pulled"]:
                    # Money safety: the pull landed but the pool deposit didn't
                    # — push the USDC back to the user's wallet, never strand it.
                    refund_h = ""
                    try:
                        from gaming.src.stack.agentic.spectator_onchain import refund_float_to_user

                        refund = await asyncio.to_thread(
                            refund_float_to_user, str(summary.get("address") or ""), amt
                        )
                        refund_h = str(refund.get("tx_hash") or "")
                    except Exception:
                        logger.exception("[RematchWeb] refund of pulled bet failed")
                    out["pull_err"] = f"on-chain deposit failed — {exc}"
                    if refund_h:
                        out["pull_err"] += f" · ${amount} refunded to your wallet (tx {refund_h[:12]})"
            return out

        await _reserve_play_stake(profile_id, amt, spend_key)
        try:
            out["book"] = get_house().take_bet(
                match_id,
                bettor_id=profile_id,
                side=side,
                amount_usdc=amt,
                # Play-balance stake; paid back to the play balance.
                funding="profile",
            )
        except Exception as exc:
            logger.warning("[RematchWeb] take_bet refused match=%s: %s", match_id, exc)
            _unreserve_play_stake(profile_id, amt, spend_key, "unbooked")
            raise _SpendRefused("spectator_book_failed", f"{exc}. Nothing was charged.") from exc
        try:
            await _pull_play_usdc(profile_id, amount, held=amt)
        except Exception as exc:
            # The reservation stays: the stake is carried by the overlay.
            logger.warning("[RematchWeb] play pull failed, stake held on the overlay: %s", exc)
            out["pull_err"] = str(exc)
        else:
            out["pulled"] = True
            _unreserve_play_stake(profile_id, amt, spend_key, "pulled")
    return out


def _gate_new_spectator_money(*, path: str, profile_id: str, match_id: str = "") -> None:
    """Kill switch + country allowlist (KYC_AML_PLAN §6). Before any approval
    or debit: raises the 403/451 SpectatorBettingUnavailable error."""
    from gaming.src.backend.services.spectator_policy import assert_spectator_betting_allowed

    assert_spectator_betting_allowed(path=path, match_id=match_id, profile_id=profile_id)


def _approved_flow_refusal(payload: dict, *, path: str, profile_id: str, match_id: str = "") -> Optional[dict]:
    """Re-check the switch when an approved spend is applied (it may have
    flipped since the request). Uses the country captured at request time."""
    from gaming.src.backend.services.spectator_policy import (
        SpectatorBettingUnavailable,
        assert_spectator_betting_allowed,
    )

    try:
        assert_spectator_betting_allowed(
            path=path,
            match_id=match_id,
            profile_id=profile_id,
            country=str(payload.get("country") or "") or None,
        )
    except SpectatorBettingUnavailable as exc:
        return {"success": False, "pending": False, **exc.body, "message": str(exc)}
    return None


async def _apply_approved_spectator_bet(
    *,
    approval_id: str,
    profile_id: str,
    match_id: str,
    side: str,
    amount: float,
    summary: dict,
) -> dict:
    """Debit + book the bet once. Idempotent across background task and GET poll."""
    from gaming.src.backend.services.tx_approval import (
        claim_apply,
        get_approval_row,
        store_apply_result,
    )
    from gaming.src.backend.db_layer_blockchain import debit_wallet
    from gaming.src.stack.agentic.spectator_onchain import spectator_onchain_enabled

    row = get_approval_row(approval_id) or {}
    payload = dict(row.get("payload") or {})
    if row.get("status") == "applied" or payload.get("_applied"):
        return {"success": True, "pending": False, **(payload.get("_result") or {})}

    claimed = claim_apply(approval_id)
    if claimed is None:
        fresh = get_approval_row(approval_id) or {}
        prev = dict((fresh.get("payload") or {}).get("_result") or {})
        if fresh.get("status") == "applied" or prev:
            return {"success": True, "pending": False, **prev}
        return {"success": False, "pending": True, "error": "not_approved_yet"}

    refused = _approved_flow_refusal(
        payload, path="approved spectator bet", profile_id=profile_id, match_id=match_id
    )
    if refused is not None:
        store_apply_result(approval_id, refused)
        return refused

    try:
        spent = await _book_profile_bet(
            profile_id=profile_id,
            match_id=match_id,
            side=side,
            amount=amount,
            spend_key=f"approval:{approval_id}",
            summary=summary or {},
        )
    except _SpendRefused as exc:
        failed = {"success": False, "pending": False, "error": exc.error, "message": exc.message}
        store_apply_result(approval_id, failed)
        return failed
    except Exception as exc:
        logger.exception("[RematchWeb] spectator book/deposit failed")
        return {
            "success": False,
            "pending": False,
            "error": "spectator_book_failed",
            "message": str(exc),
        }
    book, chain_tx, pull_err = spent["book"], spent["chain_tx"], spent["pull_err"]
    booked = book is not None or bool(chain_tx.get("tx_hash"))
    try:
        ledger = float((summary or {}).get("ledger_usdc") or 0)
        if booked and ledger + 1e-9 >= amount:
            await debit_wallet(profile_id, amount)
    except Exception:
        logger.warning("[RematchWeb] ledger sync after book failed", exc_info=True)

    if spectator_onchain_enabled() and pull_err and not chain_tx.get("tx_hash"):
        # On-chain bet: no pool deposit tx means the bet did NOT land.
        # (If the pull landed first, the refund path already pushed it back.)
        return {
            "success": False,
            "pending": False,
            "error": "spectator_deposit_failed",
            "message": pull_err,
            "refunded": "refunded to your wallet" in pull_err,
        }

    from gaming.src.backend.services.clawstation_circle import get_usdc_balance

    new_bal = float(await get_usdc_balance(profile_id))
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

    result = {
        "success": True,
        "pending": False,
        "profile_id": profile_id,
        "amount": amount,
        "side": side,
        "match_id": (book or {}).get("match_id") or match_id,
        "balance": new_bal,
        "address": summary.get("address") or "",
        "wallet": summary.get("address") or "",
        "house_book": bool(book),
        "tx_hash": chain_tx.get("tx_hash") or "",
        "explorer": chain_tx.get("explorer") or "",
        "onchain": bool(chain_tx.get("tx_hash")),
        "pull_error": pull_err,
    }
    store_apply_result(approval_id, result)
    logger.info("[RematchWeb] spectator bet placed match=%s approval=%s", match_id, approval_id)
    return result


async def _apply_approved_lp(
    *,
    approval_id: str,
    profile_id: str,
    agent_id: str,
    agent_name: str,
    amount: float,
    summary: dict,
) -> dict:
    """Debit + credit LP pool once. Idempotent across bot Yes and website poll."""
    from gaming.src.backend.services.tx_approval import (
        claim_apply,
        get_approval_row,
        store_apply_result,
    )
    from gaming.src.backend.db_layer_blockchain import debit_wallet

    row = get_approval_row(approval_id) or {} if approval_id else {}
    payload = dict(row.get("payload") or {})
    if row.get("status") == "applied" or payload.get("_applied"):
        return {"success": True, "pending": False, **(payload.get("_result") or {})}

    if approval_id:
        claimed = claim_apply(approval_id)
        if claimed is None:
            fresh = get_approval_row(approval_id) or {}
            prev = dict((fresh.get("payload") or {}).get("_result") or {})
            if fresh.get("status") == "applied" or prev:
                return {"success": True, "pending": False, **prev}
            return {"success": False, "pending": True, "error": "not_approved_yet"}

    agent_id = str(agent_id or payload.get("agent_id") or "").strip()
    agent_id = _AGENT_ID_ALIASES.get(agent_id.lower(), agent_id)
    refused = _approved_flow_refusal(payload, path="approved LP deposit", profile_id=profile_id)
    if refused is not None:
        if approval_id:
            store_apply_result(approval_id, refused)
        return refused
    try:
        from gaming.src.stack.agentic.economy.lp import AgentLPPool

        amt = Decimal(str(amount))
        spend_key = f"lp:{approval_id or uuid.uuid4().hex}"
        # Same discipline as a bet: reserve on the play balance (checked
        # against a fresh chain read, one spend per profile at a time), credit
        # the pool, then pull; the reservation is released once the chain
        # carries the debit. The stale request-time summary decides nothing.
        with _play_spend_lock(profile_id):
            await _reserve_play_stake(profile_id, amt, spend_key)
            try:
                pool = AgentLPPool().deposit(agent_id, lp_id=profile_id, amount_usdc=amt)
            except Exception:
                _unreserve_play_stake(profile_id, amt, spend_key, "unbooked")
                raise
            try:
                pull_res = await _pull_play_usdc(profile_id, amount, held=amt)
            except Exception as exc:
                logger.warning("[RematchWeb] LP Circle pull failed; stake held on the overlay: %s", exc)
            else:
                _unreserve_play_stake(profile_id, amt, spend_key, "pulled")
                logger.info(
                    "[RematchWeb] LP pull tx=%s", pull_res.get("tx_hash") or pull_res.get("transaction_id") or ""
                )
        ledger = float((summary or {}).get("ledger_usdc") or 0)
        if ledger + 1e-9 >= amount:
            await debit_wallet(profile_id, amount)
    except _SpendRefused as exc:
        failed = {"success": False, "pending": False, "error": exc.error, "message": exc.message}
        if approval_id:
            store_apply_result(approval_id, failed)
        return failed
    except Exception as exc:
        logger.exception("[RematchWeb] LP apply failed")
        return {
            "success": False,
            "pending": False,
            "error": "lp_apply_failed",
            "message": str(exc),
        }

    from gaming.src.backend.services.clawstation_circle import get_usdc_balance

    new_bal = float(await get_usdc_balance(profile_id))
    result = {
        "success": True,
        "pending": False,
        "profile_id": profile_id,
        "amount": amount,
        "agent_id": agent_id,
        "agent_name": agent_name or payload.get("agent_name") or "",
        "balance": new_bal,
        "address": (summary or {}).get("address") or "",
        "lp_total_usdc": pool.get("total_lp_usdc"),
        "kind": "lp",
    }
    if approval_id:
        store_apply_result(approval_id, result)
    logger.info("[RematchWeb] LP applied agent=%s approval=%s", agent_id, approval_id)
    return result


async def _finish_after_approval(approval_id: str) -> None:
    """Laptop-side waiter: Yes → apply even if the browser tab is gone."""
    from gaming.src.backend.services.tx_approval import apply_approved_spend, poll_approval

    decision = await poll_approval(approval_id, 120)
    if decision.get("status") != "approved":
        logger.info(
            "[RematchWeb] background approval %s id=%s",
            decision.get("status"),
            approval_id,
        )
        return
    await apply_approved_spend(approval_id)


@router.get("/profile")
def web_profile_by_telegram(
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
def web_profile_by_tag(
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
    background_tasks: BackgroundTasks,
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
    amount = _finite_amount(body.get("amount"))
    side = str(body.get("side") or "").strip().lower()
    match_id = str(body.get("match_id") or "").strip()[:64]

    if not profile_id:
        raise HTTPException(status_code=400, detail="profile_id required")
    if amount < 0.25:
        raise HTTPException(status_code=400, detail="amount must be >= 0.25")
    if side not in ("a", "b", "raja", "nero", "white", "black", "draw", "d", "tie"):
        raise HTTPException(status_code=400, detail="side must be a|b|raja|nero|draw")
    if side in ("raja", "white"):
        side = "a"
    if side in ("nero", "black"):
        side = "b"
    if side in ("d", "tie"):
        side = "draw"

    # Kill switch / allowlist: refuse before the approval, before any debit.
    _gate_new_spectator_money(path="POST /spectator/bet", profile_id=profile_id, match_id=match_id)

    from gaming.src.stack.agentic.spectator_onchain import spectator_onchain_enabled

    try:
        match_id = _resolve_live_match_id(match_id)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("[RematchWeb] live match lookup failed")
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # Reject dead tables BEFORE the Telegram approval — never make the user
    # approve a spend that cannot be booked onto a finished game.
    try:
        from gaming.src.stack.agentic.house import BET_STATUSES
        from gaming.src.stack.agentic.matches import get_match_service

        rec = get_match_service().get(match_id)
        if not rec:
            return {
                "success": False,
                "error": "match_not_found",
                "match_id": match_id,
                "message": "That table no longer exists — bet on the live game.",
            }
        if rec.get("status") not in BET_STATUSES:
            return {
                "success": False,
                "error": "match_not_open",
                "match_id": match_id,
                "message": (
                    f"That table is {rec.get('status')} — betting is closed. "
                    "Bet on the live game."
                ),
            }
    except HTTPException:
        raise
    except Exception:
        logger.warning("[RematchWeb] dead-table pre-check failed", exc_info=True)

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
        # Same number the bot shows: on-chain USDC on the play address.
        spendable = float(summary.get("spendable_usdc") or 0)
        if spendable + 1e-9 < amount:
            return {
                "success": False,
                "error": "insufficient_balance",
                "balance": spendable,
                "address": summary.get("address") or "",
                "message": "Not enough USDC on your Boardman wallet. Fund via Telegram bot → Get money.",
            }

        # Telegram-mediated approval: ask the user to approve the spend (unless
        # they've pre-approved bets with 'always'). Declined/expired → no debit.
        try:
            from gaming.src.backend.services.tx_approval import start_approval

            from gaming.src.backend.services.spectator_policy import request_country

            decision = await start_approval(
                profile_id,
                "spectator_bet",
                {"amount": amount, "side": side, "match_id": match_id, "country": request_country()},
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
        if decision.get("status") == "pending":
            background_tasks.add_task(
                _finish_after_approval,
                str(decision.get("approval_id") or ""),
            )
            return {
                "success": True,
                "pending": True,
                "approval_id": decision.get("approval_id"),
                "match_id": match_id,
                "profile_id": profile_id,
                "amount": amount,
                "side": side,
                "message": "Check Telegram to approve. The pot updates here after you tap Yes.",
            }
        if decision.get("mode") == "always":
            logger.info("[RematchWeb] spectator bet auto-approved (always) profile=%s", profile_id)

        # Reserve the stake, book the ticket, then pull (see _book_profile_bet).
        try:
            spent = await _book_profile_bet(
                profile_id=profile_id,
                match_id=match_id,
                side=side,
                amount=amount,
                spend_key=f"direct:{uuid.uuid4().hex}",
                summary=summary,
            )
        except _SpendRefused as exc:
            return {
                "success": False,
                "error": exc.error,
                "message": exc.message,
                "match_id": match_id,
                "address": summary.get("address") or "",
            }
        except Exception:
            logger.exception("[RematchWeb] house take_bet failed match=%s", match_id)
            return {
                "success": False,
                "error": "spectator_book_failed",
                "message": "Could not book the bet",
                "match_id": match_id,
                "address": summary.get("address") or "",
            }
        book, chain_tx, pull_err = spent["book"], spent["chain_tx"], spent["pull_err"]
        booked = book is not None or bool(chain_tx.get("tx_hash"))
        try:
            ledger = float(summary.get("ledger_usdc") or 0)
            if not booked:
                ledger = -1.0  # on-chain deposit failed: no ledger debit either
            if ledger + 1e-9 >= amount:
                await debit_wallet(profile_id, amount)
        except Exception:
            logger.warning("[RematchWeb] ledger sync after book failed", exc_info=True)

        if spectator_onchain_enabled() and pull_err and not chain_tx.get("tx_hash"):
            return {
                "success": False,
                "error": "spectator_deposit_failed",
                "message": pull_err,
                "refunded": "refunded to your wallet" in pull_err,
                "match_id": match_id,
                "address": summary.get("address") or "",
            }

        from gaming.src.backend.services.clawstation_circle import get_usdc_balance

        new_bal = float(await get_usdc_balance(profile_id))
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
            "pull_error": pull_err,
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("[RematchWeb] spectator bet failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/spectator/bet")
async def web_spectator_bet_status(
    approval_id: str = Query(default=""),
    profile_id: str = Query(default=""),
    x_rematch_key: Optional[str] = Header(default=None, alias="X-Rematch-Key"),
    x_stack_key: Optional[str] = Header(default=None, alias="X-Stack-Key"),
    authorization: Optional[str] = Header(default=None),
    x_boardman_caller: Optional[str] = Header(default=None, alias="X-Boardman-Caller"),
):
    """Poll Telegram Yes and apply the spend if the background task missed it.

    The approval must belong to the caller (X-Boardman-Caller, or the
    ``profile_id`` param) — a session can never poll someone else's."""
    _require_key(x_rematch_key, x_stack_key, authorization)
    aid = (approval_id or "").strip()
    if not aid:
        raise HTTPException(status_code=400, detail="approval_id required")
    owner = (x_boardman_caller or "").strip() or (profile_id or "").strip()
    if not owner:
        raise HTTPException(status_code=400, detail="profile_id required")
    from gaming.src.backend.services.tx_approval import apply_approved_spend, get_approval_row

    row = get_approval_row(aid) or {}
    if str(row.get("profile_id") or "") != owner:
        # same answer for unknown and foreign ids — no probing
        raise HTTPException(status_code=404, detail="approval_not_found")
    return await apply_approved_spend(aid)


@router.get("/spectator/lp")
@router.get("/spectator/approval")
async def web_spectator_approval_status(
    approval_id: str = Query(default=""),
    profile_id: str = Query(default=""),
    x_rematch_key: Optional[str] = Header(default=None, alias="X-Rematch-Key"),
    x_stack_key: Optional[str] = Header(default=None, alias="X-Stack-Key"),
    authorization: Optional[str] = Header(default=None),
    x_boardman_caller: Optional[str] = Header(default=None, alias="X-Boardman-Caller"),
):
    return await web_spectator_bet_status(
        approval_id=approval_id,
        profile_id=profile_id,
        x_rematch_key=x_rematch_key,
        x_stack_key=x_stack_key,
        authorization=authorization,
        x_boardman_caller=x_boardman_caller,
    )


# No /spectator/payout: crediting a client-chosen amount let any session mint
# balance. Spectator winnings and refunds are paid only by server-side
# settlement of the book.


_AGENT_ID_ALIASES = {
    "raja": "agent_raja_kia_alekhine",
    "nero": "agent_nero_sicilian_french",
}


@router.post("/spectator/lp")
async def web_spectator_lp(
    body: dict,
    background_tasks: BackgroundTasks,
    x_rematch_key: Optional[str] = Header(default=None, alias="X-Rematch-Key"),
    x_stack_key: Optional[str] = Header(default=None, alias="X-Stack-Key"),
    authorization: Optional[str] = Header(default=None),
):
    """
    Real LP deposit: debit the human's wallet, credit the agent's LP pool.
    Gate: Telegram Yes. Returns immediately; poll GET /spectator/lp?approval_id=.
    """
    _require_key(x_rematch_key, x_stack_key, authorization)
    profile_id = str(body.get("profile_id") or "").strip()
    amount = _finite_amount(body.get("amount"))
    agent_id = str(body.get("agent_id") or "").strip().lower()
    agent_name = str(body.get("agent_name") or "").strip()
    agent_id = _AGENT_ID_ALIASES.get(agent_id, agent_id)

    if not profile_id:
        raise HTTPException(status_code=400, detail="profile_id required")
    if not agent_id:
        raise HTTPException(status_code=400, detail="agent_id required")
    if amount < 0.25:
        raise HTTPException(status_code=400, detail="amount must be >= 0.25")

    # New LP money is gated with spectator betting (withdrawals never are).
    _gate_new_spectator_money(path="POST /spectator/lp", profile_id=profile_id)

    try:
        from gaming.src.backend.services.safety import is_paused
        from gaming.src.backend.services.clawstation_circle import get_balance_summary
        from gaming.src.backend.services.tx_approval import start_approval

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

        from gaming.src.backend.services.spectator_policy import request_country

        decision = await start_approval(
            profile_id,
            "lp_deposit",
            {"amount": amount, "agent_id": agent_id, "agent_name": agent_name, "country": request_country()},
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
        if decision.get("status") == "pending":
            background_tasks.add_task(
                _finish_after_approval,
                str(decision.get("approval_id") or ""),
            )
            return {
                "success": True,
                "pending": True,
                "approval_id": decision.get("approval_id"),
                "profile_id": profile_id,
                "amount": amount,
                "agent_id": agent_id,
                "agent_name": agent_name,
                "message": "Check Telegram to approve. This page updates after you tap Yes.",
            }

        return await _apply_approved_lp(
            approval_id=str(decision.get("approval_id") or ""),
            profile_id=profile_id,
            agent_id=agent_id,
            agent_name=agent_name,
            amount=amount,
            summary=summary,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("[RematchWeb] spectator LP failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/spectator/lp/withdraw")
async def web_spectator_lp_withdraw(
    body: dict,
    x_rematch_key: Optional[str] = Header(default=None, alias="X-Rematch-Key"),
    x_stack_key: Optional[str] = Header(default=None, alias="X-Stack-Key"),
    authorization: Optional[str] = Header(default=None),
):
    """
    LP withdraw: send REAL USDC from the House float to the LP's play wallet.
    Only free capital above reserve + open escrow locks is withdrawable.
    Requires a Telegram Yes (same approval rail as deposits).
    """
    _require_key(x_rematch_key, x_stack_key, authorization)
    profile_id = str(body.get("profile_id") or "").strip()
    amount = _finite_amount(body.get("amount"))
    agent_id = str(body.get("agent_id") or "").strip().lower()
    agent_id = _AGENT_ID_ALIASES.get(agent_id, agent_id)

    if not profile_id:
        raise HTTPException(status_code=400, detail="profile_id required")
    if not agent_id:
        raise HTTPException(status_code=400, detail="agent_id required")
    if amount <= 0:
        raise HTTPException(status_code=400, detail="amount must be positive")

    import asyncio

    from gaming.src.backend.services.safety import is_paused
    from gaming.src.backend.services.tx_approval import start_approval

    if is_paused():
        raise HTTPException(status_code=503, detail="platform_paused")

    from gaming.src.backend.services.clawstation_circle import get_balance_summary
    from gaming.src.stack.agentic import ledger
    from gaming.src.stack.agentic.economy.lp import AgentLPPool
    from gaming.src.stack.agentic.registry import AgentRegistry

    summary = await get_balance_summary(profile_id)
    agent = AgentRegistry().get_agent(agent_id) or {}
    agent_wallet = str(agent.get("wallet_address") or "").strip()
    if not agent_wallet:
        raise HTTPException(status_code=400, detail="agent not found or no wallet")
    eco = agent.get("economy") or {}
    try:
        reserve_bps = int(eco.get("reserve_bps") or 2000)
    except (TypeError, ValueError):
        reserve_bps = 2000

    bankroll = ledger.balance(agent_wallet)
    escrows = ledger._load().get("escrows") or {}
    locked_usdc = Decimal("0")
    aw = agent_wallet.lower()
    for esc in escrows.values():
        if esc.get("settled_at") is None and esc.get("status") in {"open", "partial_lock", "locked"}:
            if str(esc.get("agent_a_wallet") or "").lower() == aw or str(
                esc.get("agent_b_wallet") or ""
            ).lower() == aw:
                locked_usdc += Decimal(str(esc.get("stake_usdc") or "0"))

    pool = AgentLPPool()
    max_w = pool.withdrawable(
        agent_id,
        lp_id=profile_id,
        agent_bankroll=bankroll,
        reserve_bps=reserve_bps,
        locked_usdc=locked_usdc,
    )
    if Decimal(str(amount)) > max_w + Decimal("0.000001"):
        return {
            "success": False,
            "error": "withdrawable_cap",
            "max": str(max_w),
            "message": f"Only ${max_w} is withdrawable right now (reserve + escrow locks).",
        }

    decision = await start_approval(
        profile_id,
        "lp_withdraw",
        {"amount": amount, "agent_id": agent_id},
    )
    if decision.get("status") != "approved":
        # Only an explicit Yes (or 'always') sends money. A pending prompt is
        # NOT a Yes: nothing leaves the House float until the LP approves.
        st = str(decision.get("status") or "unknown")
        return {
            "success": False,
            "pending": st == "pending",
            "approval_id": decision.get("approval_id"),
            "error": f"approval_{st}",
            "message": decision.get("message") or "Approval failed. Nothing was sent.",
        }

    from gaming.src.stack.agentic.spectator_onchain import SpectatorOnchainError, refund_float_to_user

    user_wallet = str(summary.get("address") or "").strip()
    if not user_wallet.startswith("0x") or len(user_wallet) != 42:
        raise HTTPException(status_code=400, detail="no on-chain wallet on this profile")
    amt = Decimal(str(amount))
    # Book first, send second: the pool row lock re-checks the cap and takes
    # the claim, so two concurrent withdrawals can never both send.
    try:
        pool.withdraw(
            agent_id,
            lp_id=profile_id,
            amount_usdc=amt,
            agent_bankroll=bankroll,
            reserve_bps=reserve_bps,
            locked_usdc=locked_usdc,
        )
    except ValueError as exc:
        return {"success": False, "error": "withdrawable_cap", "message": str(exc)}
    try:
        tx = await asyncio.to_thread(refund_float_to_user, user_wallet, amt)
    except SpectatorOnchainError as exc:
        # Refused before any transfer was broadcast: give the claim back.
        AgentLPPool().deposit(agent_id, lp_id=profile_id, amount_usdc=amt)
        logger.warning("[RematchWeb] LP withdraw not sent, claim restored: %s", exc)
        raise HTTPException(status_code=502, detail=f"withdraw not sent: {exc}") from exc
    except Exception as exc:
        # The transfer may have been broadcast: keep the claim debited (never
        # risk paying twice) and leave it to ops to reconcile against chain.
        logger.critical(
            "[RematchWeb] LP withdraw %s for %s on %s in an unknown state — reconcile: %s",
            amt, profile_id, agent_id, exc,
        )
        raise HTTPException(status_code=500, detail="withdraw state unknown — support will reconcile") from exc

    return {
        "success": True,
        "profile_id": profile_id,
        "agent_id": agent_id,
        "amount": amount,
        "tx_hash": tx.get("tx_hash"),
        "explorer": tx.get("explorer"),
        "address": user_wallet,
        "message": f"${amount} sent to your play wallet.",
    }


@router.get("/matches")
def web_match_history(
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
