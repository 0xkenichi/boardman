"""
gaming/src/backend/services/clawstation_settlement.py
────────────────────────────────────────────────────
Backend settlement worker for ClawStation (custodial escrow mode).

Reads challenges that have both scores submitted, resolves the winner,
pays out from the sideQuest escrow wallet, and notifies both players.
Disputes are escalated to admin resolution.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

from backend.supabase_client import get_supabase
from gaming.src.backend.services.clawstation_escrow import (
    EscrowError,
    flag_dispute,
    resolve_match,
)

logger = logging.getLogger(__name__)

# Dispute window: time after both scores are in before auto-payout is allowed.
DEFAULT_DISPUTE_WINDOW_MINUTES = int(os.getenv("SETTLEMENT_DISPUTE_WINDOW_MINUTES", "15"))


class SettlementError(Exception):
    """Raised when a settlement operation fails."""


def _get_supabase():
    return get_supabase()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _load_challenge(challenge_id: str) -> Optional[dict]:
    sb = _get_supabase()
    result = (
        sb.schema("gaming")
        .table("challenges")
        .select("*")
        .eq("id", challenge_id)
        .maybe_single()
        .execute()
    )
    return result.data


def _load_submitted_challenges() -> list[dict]:
    """Return challenges in 'submitted' status."""
    sb = _get_supabase()
    result = (
        sb.schema("gaming")
        .table("challenges")
        .select("*")
        .eq("status", "submitted")
        .execute()
    )
    return result.data or []


def _load_profile_address(profile_id: str) -> Optional[str]:
    sb = _get_supabase()
    result = (
        sb.table("profiles")
        .select("gaming_deposit_address")
        .eq("id", profile_id)
        .maybe_single()
        .execute()
    )
    if result.data:
        return result.data.get("gaming_deposit_address")
    return None


def _determine_winner(challenge: dict) -> Optional[str]:
    """Return the winner profile ID based on submitted scores, or None for draw."""
    creator_score = challenge.get("creator_score")
    opponent_score = challenge.get("opponent_score")
    if creator_score is None or opponent_score is None:
        return None

    if creator_score > opponent_score:
        return challenge["creator_id"]
    if opponent_score > creator_score:
        return challenge["opponent_id"]
    return None  # draw


def _both_scores_present(challenge: dict) -> bool:
    return challenge.get("creator_score") is not None and challenge.get("opponent_score") is not None


def _dispute_window_elapsed(challenge: dict) -> bool:
    """Return True if enough time has passed since the second score submission."""
    # We don't know the exact timestamp of the second score, so we use updated_at
    # as a conservative proxy once both scores are present.
    updated_at = challenge.get("updated_at")
    if not updated_at:
        return False
    try:
        updated = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
    except Exception:
        return False
    elapsed = _utcnow() - updated
    return elapsed >= timedelta(minutes=DEFAULT_DISPUTE_WINDOW_MINUTES)


async def _verify_screenshot_scores(challenge: dict) -> Optional[str]:
    """
    Optional AI-mediated verification when numeric scores disagree.
    Returns the inferred winner profile ID, None for draw, or None if
    verification fails.
    """
    creator_screenshot = challenge.get("screenshot_creator_url")
    opponent_screenshot = challenge.get("screenshot_opponent_url")
    if not creator_screenshot or not opponent_screenshot:
        return None

    creator_score = challenge.get("creator_score")
    opponent_score = challenge.get("opponent_score")
    reported_p1 = f"{creator_score or 0}-{opponent_score or 0}"
    reported_p2 = f"{opponent_score or 0}-{creator_score or 0}"

    try:
        from gaming.src.backend.score_verifier import get_score_verifier

        verifier = get_score_verifier()
        result = await verifier.verify_dispute(
            screenshot_p1=creator_screenshot,
            screenshot_p2=opponent_screenshot,
            reported_p1=reported_p1,
            reported_p2=reported_p2,
        )
        winner_label = result.get("winner")
        if winner_label == "player1":
            return challenge["creator_id"]
        if winner_label == "player2":
            return challenge["opponent_id"]
        return None
    except Exception as exc:
        logger.warning("[Settlement] AI verification failed for %s: %s", challenge["id"], exc)
        return None


def _update_challenge(
    challenge_id: str,
    status: str,
    winner_id: Optional[str] = None,
    tx_hash: Optional[str] = None,
    ai_verified_at: bool = False,
) -> None:
    sb = _get_supabase()
    update: dict = {"status": status}
    if winner_id is not None:
        update["winner_id"] = winner_id
    if tx_hash is not None:
        update["resolved_tx_hash"] = tx_hash
    if ai_verified_at:
        update["ai_verified_at"] = "now()"
    sb.schema("gaming").table("challenges").update(update).eq("id", challenge_id).execute()


async def _notify_result(
    challenge: dict,
    winner_id: Optional[str],
    tx_hash: Optional[str],
) -> None:
    from gaming.src.bot.utils.notify import notify_user

    creator_id = challenge["creator_id"]
    opponent_id = challenge.get("opponent_id")
    amount = Decimal(str(challenge["amount_usdc"]))
    challenge_id = challenge["id"]

    tx_text = f"\nTx: `{tx_hash}`" if tx_hash else ""

    if winner_id is None:
        result_text = (
            f"🤝 Challenge `{challenge_id}` ended in a draw.\n"
            f"Both players are refunded.{tx_text}"
        )
    else:
        winner_name = "Creator" if winner_id == creator_id else "Opponent"
        result_text = (
            f"🏆 Challenge `{challenge_id}` resolved.\n"
            f"Winner: *{winner_name}*\n"
            f"Payout: *${amount:,.2f}* (minus 7% platform fee)\n"
            f"{tx_text}"
        )

    await notify_user(creator_id, result_text)
    if opponent_id:
        await notify_user(opponent_id, result_text)


async def _execute_payout(challenge: dict, winner_id: Optional[str]) -> str:
    """Resolve the challenge in the DB and trigger the escrow payout."""
    challenge_id = challenge["id"]

    if winner_id is None:
        # Draw: refund both players.
        from gaming.src.backend.services.clawstation_escrow import cancel_match

        result = await cancel_match(challenge_id)
        return result.get("tx_hash", "")

    winner_address = await _load_profile_address(winner_id)
    if not winner_address:
        raise SettlementError(f"Winner {winner_id} has no deposit address")

    # Pre-set winner in DB so resolve_match can validate.
    _update_challenge(challenge_id, "submitted", winner_id=winner_id)

    result = await resolve_match(challenge_id, winner_address)
    return result.get("tx_hash", "")


async def settle_challenge(challenge_id: str, admin_winner_id: Optional[str] = None) -> dict:
    """
    Resolve a single challenge.

    If admin_winner_id is provided, skip score verification and dispute window
    (admin override). Otherwise auto-resolve only when scores agree and the
    dispute window has elapsed.
    """
    challenge = _load_challenge(challenge_id)
    if not challenge:
        raise SettlementError(f"Challenge {challenge_id} not found")

    if challenge.get("status") == "resolved":
        return {"success": True, "action": "skipped", "reason": "already_resolved"}

    if challenge.get("status") not in ("submitted", "disputed"):
        return {"success": True, "action": "skipped", "reason": f"status={challenge.get('status')}"}

    if admin_winner_id:
        winner_id = admin_winner_id
        logger.info("[Settlement] Admin resolving %s to winner %s", challenge_id, winner_id)
    else:
        if not _both_scores_present(challenge):
            return {"success": True, "action": "skipped", "reason": "missing_scores"}

        winner_id = _determine_winner(challenge)

        # If scores disagree, try AI screenshot verification.
        if winner_id is None and challenge.get("creator_score") != challenge.get("opponent_score"):
            ai_winner = await _verify_screenshot_scores(challenge)
            if ai_winner:
                winner_id = ai_winner

        # Still unresolved → flag dispute and wait for admin.
        if winner_id is None and challenge.get("creator_score") != challenge.get("opponent_score"):
            logger.info("[Settlement] Scores disagree for %s; escalating to dispute", challenge_id)
            try:
                await flag_dispute(challenge_id)
            except EscrowError as exc:
                logger.warning("[Settlement] Could not flag dispute: %s", exc)
            _update_challenge(challenge_id, "disputed")
            return {"success": True, "action": "disputed", "challenge_id": challenge_id}

        # Draw: still needs dispute window to pass in case a player wants to contest.
        if winner_id is None:
            if not _dispute_window_elapsed(challenge):
                return {
                    "success": True,
                    "action": "waiting_dispute_window",
                    "challenge_id": challenge_id,
                }

        # Matching-score winner must also wait for dispute window.
        if winner_id is not None and not _dispute_window_elapsed(challenge):
            return {
                "success": True,
                "action": "waiting_dispute_window",
                "challenge_id": challenge_id,
            }

    try:
        tx_hash = await _execute_payout(challenge, winner_id)
    except EscrowError as exc:
        logger.exception("[Settlement] Payout failed for %s", challenge_id)
        raise SettlementError(f"payout failed: {exc}") from exc

    _update_challenge(challenge_id, "resolved", winner_id=winner_id, tx_hash=tx_hash, ai_verified_at=True)
    await _notify_result(challenge, winner_id, tx_hash)

    return {
        "success": True,
        "action": "resolved",
        "challenge_id": challenge_id,
        "winner_id": winner_id,
        "tx_hash": tx_hash,
    }


async def admin_resolve_challenge(
    challenge_id: str,
    admin_profile_id: str,
    winner_id: str,
    note: Optional[str] = None,
) -> dict:
    """Admin manually resolves a disputed challenge."""
    challenge = _load_challenge(challenge_id)
    if not challenge:
        raise SettlementError(f"Challenge {challenge_id} not found")

    if winner_id not in (challenge["creator_id"], challenge.get("opponent_id")):
        raise SettlementError("Winner must be one of the challenge participants")

    # Log admin decision in the challenge row.
    sb = _get_supabase()
    sb.schema("gaming").table("challenges").update(
        {
            "admin_resolved_by": admin_profile_id,
            "admin_resolution_note": note or "Manual admin resolution",
        }
    ).eq("id", challenge_id).execute()

    return await settle_challenge(challenge_id, admin_winner_id=winner_id)


async def settle_all_pending() -> list[dict]:
    """Poll and settle every submitted challenge that is ready."""
    challenges = _load_submitted_challenges()
    results = []
    for challenge in challenges:
        try:
            result = await settle_challenge(challenge["id"])
            results.append(result)
        except Exception as exc:
            logger.exception("[Settlement] Failed to settle %s", challenge["id"])
            results.append({"success": False, "challenge_id": challenge["id"], "error": str(exc)})
    return results
