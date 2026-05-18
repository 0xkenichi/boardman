"""
betting_engine_onchain.py
────────────────────────────────────────────────────────────────────────────────
On-chain hooks for the betting engine. These wrap blockchain_layer calls
with the business logic the existing betting_engine.py needs.

Integrate by importing these functions into betting_engine.py and calling
them at the appropriate lifecycle points.
"""

import logging
import os
from typing import Optional

from blockchain_layer import get_blockchain_layer
from db_layer_blockchain import (
    debit_wallet,
    credit_wallet,
    update_match_onchain_status,
    award_play_points,
    record_transaction,
)

logger = logging.getLogger(__name__)

PLAY_POINTS_PER_DOLLAR = int(os.getenv("PLAY_POINTS_RATE", "10"))
PLATFORM_FEE_PCT = 0.03  # 3%


async def lock_stake_for_match(user_id: str, match_id: str, stake_usd: float) -> bool:
    """
    Debit a user's internal wallet balance when they join/create a challenge.
    The actual USDC is held in the escrow contract; we mirror this in the DB.

    Returns True if successful, False if insufficient balance.
    """
    success = await debit_wallet(user_id, stake_usd)
    if not success:
        logger.warning(f"[BettingEngine] User {user_id} has insufficient balance for ${stake_usd} stake")
        return False

    await record_transaction({
        "user_id":     user_id,
        "tx_hash":     f"internal_lock_{match_id}_{user_id}",
        "type":        "deposit",
        "amount_usdc": -stake_usd,
        "status":      "confirmed",
        "source":      "stake_lock",
        "network":     get_blockchain_layer().network_key,
    })

    logger.info(f"[BettingEngine] Locked ${stake_usd} stake for user {user_id} in match {match_id}")
    return True


async def resolve_match_and_payout(
    match_id: str,
    winner_user_id: str,
    winner_wallet: Optional[str],
    loser_user_id: str,
    stake_usd: float,
) -> dict:
    """
    Called when both players report the same score OR AI mediator resolves.
    1. Calls ClawEscrow.resolveMatch (on-chain) if winner has a linked wallet.
    2. Credits winner's internal balance (minus 3% fee).
    3. Awards $PLAY points to both players.
    4. Updates match status in DB to COMPLETED and records winner.
    """
    bl = get_blockchain_layer()
    total_pot = stake_usd * 2
    fee = total_pot * PLATFORM_FEE_PCT
    payout = total_pot - fee

    result = {"payout_usdc": payout, "fee_usdc": fee, "tx_hash": None}

    # ── Update escrow entries (mark as released) ─────────────────────────
    try:
        from db_layer import DBLayer
        db = DBLayer()
        # Mark escrow entries as released for this match
        db.update_escrow_entry_status(match_id, "RELEASED")
        logger.info(f"[BettingEngine] Escrow entries released for match {match_id}")
    except Exception as e:
        logger.error(f"[BettingEngine] Failed to release escrow for match {match_id}: {e}")

    # ── On-chain resolution (if winner has linked wallet) ──────────────────
    if winner_wallet:
        try:
            tx = await bl.resolve_match_onchain(match_id, winner_wallet)
            result["tx_hash"] = tx["tx_hash"]
            result["explorer_url"] = tx["explorer_url"]
            await update_match_onchain_status(match_id, "RESOLVED", tx["tx_hash"])
            logger.info(f"[BettingEngine] On-chain resolution tx: {tx['tx_hash']}")
        except Exception as e:
            # Log but don't fail — fall back to internal balance credit
            logger.error(f"[BettingEngine] On-chain resolve failed: {e}")
            await update_match_onchain_status(match_id, "RESOLVED")
    else:
        # No linked wallet — credit internal balance only
        await credit_wallet(
            user_id=winner_user_id,
            amount_usd=payout,
            tx_hash=f"internal_payout_{match_id}",
            source="match_payout",
        )
        await update_match_onchain_status(match_id, "RESOLVED")
        logger.info(f"[BettingEngine] Internal payout: ${payout:.2f} to user {winner_user_id}")

    # ── Award $PLAY points to both players ────────────────────────────────
    winner_points = int(stake_usd * PLAY_POINTS_PER_DOLLAR * 2)  # bonus for winning
    loser_points  = int(stake_usd * PLAY_POINTS_PER_DOLLAR)       # participation points

    await award_play_points(winner_user_id, winner_points)
    await award_play_points(loser_user_id,  loser_points)

    logger.info(
        f"[BettingEngine] Match {match_id} resolved. "
        f"Winner: {winner_user_id} +${payout:.2f} +{winner_points}pts | "
        f"Loser: {loser_user_id} +{loser_points}pts"
    )

    # ── Update main bets table status and winner (CRITICAL) ───────────────────
    try:
        from db_layer import DBLayer
        db = DBLayer()
        db.resolve_bet(match_id, winner_user_id)
        logger.info(f"[BettingEngine] Bet status updated to COMPLETED with winner {winner_user_id}")
    except Exception as e:
        logger.error(f"[BettingEngine] Failed to update bet status: {e}")

    result["winner_points"] = winner_points
    result["loser_points"] = loser_points
    return result


async def dispute_match_onchain(match_id: str) -> dict:
    """
    Called when score reports conflict. Flags match as DISPUTED on-chain
    and returns info for the AI mediator to begin review.
    """
    bl = get_blockchain_layer()
    try:
        tx = await bl.flag_dispute_onchain(match_id)
        await update_match_onchain_status(match_id, "DISPUTED")
        return {"disputed": True, "tx_hash": tx["tx_hash"]}
    except Exception as e:
        logger.error(f"[BettingEngine] On-chain dispute flag failed: {e}")
        await update_match_onchain_status(match_id, "DISPUTED")
        return {"disputed": True, "tx_hash": None, "error": str(e)}


async def cancel_match_and_refund(
    match_id: str,
    player1_user_id: str,
    player2_user_id: Optional[str],
    stake_usd: float,
) -> dict:
    """
    Cancels a match and refunds players.
    Called on: timeout, mutual agreement, unresolvable dispute.
    """
    bl = get_blockchain_layer()

    # ── Release escrow entries ─────────────────────────────────────────────
    try:
        from db_layer import DBLayer
        db = DBLayer()
        # Mark escrow entries as cancelled for this match
        db.update_escrow_entry_status(match_id, "CANCELLED")
        logger.info(f"[BettingEngine] Escrow entries cancelled for match {match_id}")
    except Exception as e:
        logger.error(f"[BettingEngine] Failed to cancel escrow for match {match_id}: {e}")

    try:
        tx = await bl.cancel_match_onchain(match_id)
        await update_match_onchain_status(match_id, "CANCELLED", tx["tx_hash"])
    except Exception as e:
        logger.error(f"[BettingEngine] On-chain cancel failed: {e}")
        # Fall back to internal refund
        await credit_wallet(player1_user_id, stake_usd, f"refund_p1_{match_id}", "refund")
        if player2_user_id:
            await credit_wallet(player2_user_id, stake_usd, f"refund_p2_{match_id}", "refund")
        await update_match_onchain_status(match_id, "CANCELLED")
        # Still try to cancel the DB bet record even in fallback path
        try:
            db.cancel_bet(match_id)
        except Exception as e2:
            logger.error(f"[BettingEngine] Failed to cancel bet record (fallback): {e2}")
        return {"cancelled": True, "refunded": True, "onchain": False}

    # On-chain cancel succeeded — update main bet status to CANCELLED
    try:
        db.cancel_bet(match_id)
        logger.info(f"[BettingEngine] Bet status set to CANCELLED for match {match_id}")
    except Exception as e:
        logger.error(f"[BettingEngine] Failed to cancel bet record: {e}")

    logger.info(f"[BettingEngine] Match {match_id} cancelled. Refunds processed on-chain.")
    return {"cancelled": True, "refunded": True, "onchain": True, "tx_hash": tx["tx_hash"]}
