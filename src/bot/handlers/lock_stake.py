"""Lock a challenge stake on-chain via ClawEscrow.sol."""
from __future__ import annotations

import logging
from decimal import Decimal

from aiogram import Router, types
from aiogram.filters import Command

from backend.supabase_client import get_supabase
from gaming.src.backend.services.clawstation_circle import (
    CircleWalletError,
    ensure_user_wallet,
)
from gaming.src.backend.services.clawstation_escrow import (
    EscrowError,
    approve_and_create_match,
    approve_and_join_match,
)
from gaming.src.bot.keyboards import back_menu
from gaming.src.bot.utils.db import get_or_create_profile
from gaming.src.bot.utils.notify import notify_user

logger = logging.getLogger(__name__)

router = Router()

_BASE_EXPLORER = "https://sepolia.basescan.org/tx/"


def _parse_args(text: str) -> str | None:
    parts = text.split(maxsplit=1)
    if len(parts) < 2:
        return None
    return parts[1].strip()


@router.message(Command("lock_stake"))
async def cmd_lock_stake(message: types.Message) -> None:
    """Lock the user's stake for an accepted challenge."""
    user = message.from_user
    if user is None or not message.text:
        return

    challenge_id = _parse_args(message.text)
    if not challenge_id:
        await message.answer(
            "Usage: `/lock_stake <challenge_id>`\n\n"
            "Example: `/lock_stake 550e8400-e29b-41d4-a716-446655440000`",
            reply_markup=back_menu(),
        )
        return

    profile = await get_or_create_profile(user)

    sb = get_supabase()
    result = (
        sb.schema("gaming")
        .table("challenges")
        .select("*")
        .eq("id", challenge_id)
        .maybe_single()
        .execute()
    )
    challenge = result.data
    if not challenge:
        await message.answer("❌ Challenge not found.", reply_markup=back_menu())
        return

    status = challenge.get("status")
    if status in ("locked", "submitted", "disputed", "resolved", "cancelled", "expired"):
        await message.answer(
            f"❌ Challenge is already *{status}*. No further stake locking needed.",
            reply_markup=back_menu(),
        )
        return

    is_creator = profile["id"] == challenge["creator_id"]
    is_opponent = profile["id"] == challenge.get("opponent_id")
    if not is_creator and not is_opponent:
        await message.answer("❌ You are not part of this challenge.", reply_markup=back_menu())
        return

    if is_creator and challenge.get("creator_lock_tx_id"):
        await message.answer("✅ You already locked your stake.", reply_markup=back_menu())
        return

    if is_opponent and challenge.get("opponent_lock_tx_id"):
        await message.answer("✅ You already locked your stake.", reply_markup=back_menu())
        return

    if is_opponent and challenge["status"] != "creator_locked":
        await message.answer(
            "⏳ Wait for the challenger to lock their stake first.",
            reply_markup=back_menu(),
        )
        return

    amount = Decimal(str(challenge["amount_usdc"]))

    try:
        await ensure_user_wallet(profile["id"])
    except CircleWalletError as exc:
        await message.answer(f"❌ Wallet error: {exc}", reply_markup=back_menu())
        return

    await message.answer("⏳ Locking your stake on-chain...")

    try:
        if is_creator:
            result = await approve_and_create_match(profile["id"], challenge_id, amount)
            update = {
                "status": "creator_locked",
                "creator_lock_tx_id": result["create_tx_id"],
                "creator_lock_tx_hash": result.get("tx_hash"),
            }
            tx_hash = result.get("tx_hash", "")
            reply_text = (
                f"✅ *Stake locked* (challenger)\n\n"
                f"Amount: *${amount:,.2f} USDC*\n"
                f"Tx: [{tx_hash[:10]}...]({_BASE_EXPLORER}{tx_hash})\n\n"
                f"Waiting for opponent to lock their stake."
            )
        else:
            result = await approve_and_join_match(profile["id"], challenge_id, amount)
            update = {
                "status": "locked",
                "opponent_id": profile["id"],
                "opponent_lock_tx_id": result["join_tx_id"],
                "opponent_lock_tx_hash": result.get("tx_hash"),
            }
            tx_hash = result.get("tx_hash", "")
            reply_text = (
                f"✅ *Stake locked* (opponent)\n\n"
                f"Amount: *${amount:,.2f} USDC*\n"
                f"Tx: [{tx_hash[:10]}...]({_BASE_EXPLORER}{tx_hash})"
            )
    except EscrowError as exc:
        logger.exception("[LockStake] Escrow error for user %s challenge %s", profile["id"], challenge_id)
        await message.answer(f"❌ Escrow error: {exc}", reply_markup=back_menu())
        return
    except Exception:
        logger.exception("[LockStake] Unexpected error for user %s challenge %s", profile["id"], challenge_id)
        await message.answer("❌ Could not lock stake. Please try again later.", reply_markup=back_menu())
        return

    sb.schema("gaming").table("challenges").update(update).eq("id", challenge_id).execute()
    await message.answer(reply_text, reply_markup=back_menu(), disable_web_page_preview=True)

    if is_opponent:
        await notify_user(
            challenge["creator_id"],
            f"🎮 Both stakes are locked for challenge `{challenge_id}`.\n\n"
            f"Play your match, then submit your score with `/submit_score {challenge_id} <score>` "
            f"or upload a screenshot.",
        )
        await notify_user(
            profile["id"],
            f"🎮 Both stakes are locked for challenge `{challenge_id}`.\n\n"
            f"Play your match, then submit your score with `/submit_score {challenge_id} <score>` "
            f"or upload a screenshot.",
        )
