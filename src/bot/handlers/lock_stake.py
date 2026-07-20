"""Lock a challenge stake on-chain via ClawEscrow.sol (multi-chain)."""
from __future__ import annotations

import logging
from decimal import Decimal

from aiogram import Router, types
from aiogram.enums import ParseMode
from aiogram.filters import Command

from backend.supabase_client import get_supabase
from gaming.src.backend.services.chains import (
    default_chain_id,
    get_explorer_tx,
    normalize_chain_id,
)
from gaming.src.backend.services.challenge_compat import normalize_challenge
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
from gaming.src.bot.utils.text import bold, code, h

logger = logging.getLogger(__name__)

router = Router()


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

    challenge_ref = _parse_args(message.text)
    if not challenge_ref:
        await message.answer(
            "Usage: /lock_stake MATCH_CODE\n\n"
            "Example: /lock_stake K7M2P9QX\n\n"
            "Creator locks first, then opponent. Use My match for buttons.",
            reply_markup=back_menu(),
            parse_mode=None,
        )
        return

    profile = await get_or_create_profile(user)

    from gaming.src.backend.services.safety import assert_money_ops_allowed
    from gaming.src.backend.services.match_codes import load_challenge_by_ref, display_code

    gate = assert_money_ops_allowed(profile["id"], action="lock", kind="lock")
    if gate:
        await message.answer(gate, parse_mode=ParseMode.HTML, reply_markup=back_menu())
        return

    challenge = load_challenge_by_ref(challenge_ref)
    if not challenge:
        await message.answer("❌ Challenge not found.", reply_markup=back_menu(), parse_mode=None)
        return
    challenge_id = challenge["id"]
    match_code = display_code(challenge)

    chain_id = normalize_chain_id(challenge.get("settlement_chain") or default_chain_id())
    status = challenge.get("status")
    if status in ("locked", "submitted", "disputed", "resolved", "cancelled", "expired", "playing"):
        if status == "locked" or status == "playing":
            await message.answer(
                f"✅ Stakes already locked ({bold(status)}).\n"
                f"Play, then submit proof:\n"
                f"{code(f'/submit_score {match_code} <your_goals>')}\n"
                f"or send a screenshot with that caption.",
                reply_markup=back_menu(),
                parse_mode=ParseMode.HTML,
            )
            return
        await message.answer(
            f"❌ Challenge is already {bold(status)}. No further stake locking needed.",
            reply_markup=back_menu(),
            parse_mode=ParseMode.HTML,
        )
        return

    if status not in ("accepted", "creator_locked", "open"):
        await message.answer(
            f"❌ Challenge status is {bold(status)}. Accept the challenge first.",
            reply_markup=back_menu(),
            parse_mode=ParseMode.HTML,
        )
        return

    is_creator = profile["id"] == challenge["creator_id"]
    is_opponent = profile["id"] == challenge.get("opponent_id")
    if not is_creator and not is_opponent:
        await message.answer("❌ You are not part of this challenge.", reply_markup=back_menu(), parse_mode=None)
        return

    if is_creator and challenge.get("creator_lock_tx_id"):
        await message.answer("✅ You already locked your stake.", reply_markup=back_menu(), parse_mode=None)
        return

    if is_opponent and challenge.get("opponent_lock_tx_id"):
        await message.answer("✅ You already locked your stake.", reply_markup=back_menu(), parse_mode=None)
        return

    if is_opponent and challenge["status"] != "creator_locked":
        await message.answer(
            "⏳ Wait for the challenger to lock their stake first.",
            reply_markup=back_menu(),
            parse_mode=None,
        )
        return

    if is_creator and challenge["status"] not in ("accepted", "creator_locked"):
        if challenge["status"] == "open" and challenge.get("opponent_id"):
            get_supabase().schema("gaming").table("challenges").update({"status": "accepted"}).eq(
                "id", challenge_id
            ).execute()
        else:
            await message.answer(
                "⏳ Challenge must be accepted before locking stake.",
                reply_markup=back_menu(),
                parse_mode=None,
            )
            return

    amount = Decimal(str(challenge["amount_usdc"]))

    try:
        await ensure_user_wallet(profile["id"], chain_id=chain_id)
    except CircleWalletError as exc:
        await message.answer(
            f"❌ Wallet error: {h(exc)}",
            reply_markup=back_menu(),
            parse_mode=ParseMode.HTML,
        )
        return

    await message.answer(
        f"⏳ Locking ${amount:,.2f} USDC on {chain_id} (can take ~30–90s)…",
        parse_mode=None,
    )

    try:
        if is_creator:
            result = await approve_and_create_match(profile["id"], challenge_id, amount)
            tx_hash = result.get("tx_hash", "") or ""
            explorer = result.get("explorer_url") or get_explorer_tx(chain_id, tx_hash)
            reply_text = (
                f"✅ {bold('Stake locked')} (challenger)\n\n"
                f"Amount: {bold(f'${amount:,.2f} USDC')}\n"
                f"Chain: {bold(chain_id)}\n"
                + (f"Tx: {code(tx_hash)}\n{explorer}\n\n" if tx_hash else "\n")
                + "Waiting for opponent to lock their stake."
            )
            if challenge.get("opponent_id"):
                await notify_user(
                    challenge["opponent_id"],
                    f"🔐 Challenger locked stake on {bold(chain_id)}.\n"
                    f"Your turn: {code(f'/lock_stake {match_code}')}",
                )
        else:
            result = await approve_and_join_match(profile["id"], challenge_id, amount)
            tx_hash = result.get("tx_hash", "") or ""
            explorer = result.get("explorer_url") or get_explorer_tx(chain_id, tx_hash)
            reply_text = (
                f"✅ {bold('Stake locked')} (opponent)\n\n"
                f"Amount: {bold(f'${amount:,.2f} USDC')}\n"
                f"Chain: {bold(chain_id)}\n"
                + (f"Tx: {code(tx_hash)}\n{explorer}" if tx_hash else "Both stakes locked.")
            )
    except EscrowError as exc:
        logger.exception("[LockStake] Escrow error for user %s challenge %s", profile["id"], challenge_id)
        await message.answer(
            f"❌ Escrow error: {h(exc)}",
            reply_markup=back_menu(),
            parse_mode=ParseMode.HTML,
        )
        return
    except Exception as exc:
        logger.exception("[LockStake] Unexpected error for user %s challenge %s", profile["id"], challenge_id)
        await message.answer(
            f"❌ Could not lock stake: {h(exc)}",
            reply_markup=back_menu(),
            parse_mode=ParseMode.HTML,
        )
        return

    await message.answer(
        reply_text,
        reply_markup=back_menu(),
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
    )

    if is_opponent:
        from gaming.src.bot.utils.flow import next_steps_after_lock

        play_msg = next_steps_after_lock(challenge_id)
        await notify_user(challenge["creator_id"], play_msg)
        await notify_user(profile["id"], play_msg)
