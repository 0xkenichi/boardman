"""Challenge creation and accept/decline callbacks."""
from __future__ import annotations

import logging
import shlex
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

from aiogram import F, Router, types
from aiogram.filters import Command

from backend.supabase_client import get_supabase
from gaming.src.backend.services.clawstation_circle import get_usdc_balance
from gaming.src.bot.keyboards import challenge_confirm_menu
from gaming.src.bot.utils.db import get_or_create_profile, get_profile_by_tag
from gaming.src.bot.utils.notify import notify_user

logger = logging.getLogger(__name__)

router = Router()

_MIN_STAKE = Decimal("1")
_MAX_STAKE = Decimal("10000")


def _parse_challenge_args(text: str) -> tuple[Optional[str], Decimal, str, str, str | None]:
    """Parse ``/challenge @opponent <amount> <game> public|private``.

    Returns ``(opponent_tag, amount, game, visibility, error)``.
    """
    raw = text.split(maxsplit=1)[1] if len(text.split(maxsplit=1)) > 1 else ""
    if not raw.strip():
        return None, Decimal("0"), "", "", "Usage: `/challenge @opponent <amount> <game> public|private`"

    try:
        parts = shlex.split(raw)
    except ValueError as exc:
        return None, Decimal("0"), "", "", f"Invalid quoting: {exc}"

    if not parts:
        return None, Decimal("0"), "", "", "Usage: `/challenge @opponent <amount> <game> public|private`"

    visibility = parts[-1].lower()
    if visibility not in ("public", "private"):
        return None, Decimal("0"), "", "", "Visibility must be `public` or `private`."

    if parts[0].lower() in ("public", "private"):
        # /challenge public <amount> <game> public
        if len(parts) < 4:
            return None, Decimal("0"), "", "", "Missing amount or game."
        opponent_tag = None
        amount_str = parts[1]
        game = " ".join(parts[2:-1])
    else:
        if len(parts) < 4:
            return None, Decimal("0"), "", "", "Missing opponent, amount, or game."
        opponent_tag = parts[0].lstrip("@")
        amount_str = parts[1]
        game = " ".join(parts[2:-1])

    try:
        amount = Decimal(amount_str)
    except Exception:
        return None, Decimal("0"), "", "", f"Invalid amount: `{amount_str}`"

    if amount < _MIN_STAKE or amount > _MAX_STAKE:
        return None, Decimal("0"), "", "", f"Amount must be between ${_MIN_STAKE} and ${_MAX_STAKE}."

    return opponent_tag, amount, game or "EAFC", visibility, None


async def _create_challenge(
    creator_id: str,
    opponent_id: Optional[str],
    amount: Decimal,
    game: str,
    visibility: str,
) -> dict:
    challenge_id = str(uuid.uuid4())
    expires_at = datetime.now(timezone.utc) + timedelta(hours=24)
    record = {
        "id": challenge_id,
        "creator_id": creator_id,
        "opponent_id": opponent_id,
        "amount_usdc": float(amount),
        "game": game,
        "visibility": visibility,
        "status": "open",
        "expires_at": expires_at.isoformat(),
    }
    sb = get_supabase()
    result = sb.schema("gaming").table("challenges").insert(record).execute()
    if not result.data:
        raise RuntimeError("Challenge insert returned no data")
    return result.data[0]


async def _get_open_challenge(challenge_id: str) -> Optional[dict]:
    sb = get_supabase()
    result = (
        sb.schema("gaming")
        .table("challenges")
        .select("*")
        .eq("id", challenge_id)
        .maybe_single()
        .execute()
    )
    return result.data if result.data else None


async def _update_challenge_status(challenge_id: str, status: str) -> None:
    sb = get_supabase()
    sb.schema("gaming").table("challenges").update({"status": status}).eq("id", challenge_id).execute()


async def _create_bet(challenge: dict, opponent_id: str) -> dict:
    bet_id = str(uuid.uuid4())
    record = {
        "id": bet_id,
        "challenge_id": challenge["id"],
        "challenger_id": challenge["creator_id"],
        "opponent_id": opponent_id,
        "amount_usdc": challenge["amount_usdc"],
        "status": "open",
    }
    sb = get_supabase()
    result = sb.schema("gaming").table("bets").insert(record).execute()
    if not result.data:
        raise RuntimeError("Bet insert returned no data")
    return result.data[0]


@router.message(Command("challenge"))
async def cmd_challenge(message: types.Message) -> None:
    """Create a public or private gaming challenge."""
    user = message.from_user
    if user is None or not message.text:
        return

    opponent_tag, amount, game, visibility, error = _parse_challenge_args(message.text)
    if error:
        await message.answer(f"❌ {error}")
        return

    profile = await get_or_create_profile(user)
    try:
        balance = await get_usdc_balance(profile["id"])
    except Exception as exc:
        logger.exception("[Challenge] Failed to fetch balance for %s", profile["id"])
        await message.answer(f"❌ Could not verify balance: {exc}")
        return

    if balance < amount:
        await message.answer(
            f"❌ Insufficient balance. You have *${balance:,.2f}* but need *${amount:,.2f}*."
        )
        return

    opponent: Optional[dict] = None
    if visibility == "private":
        if not opponent_tag:
            await message.answer("❌ Private challenges need an opponent: `@tag`.")
            return
        opponent = await get_profile_by_tag(opponent_tag)
        if not opponent:
            await message.answer(f"❌ Player `@{opponent_tag}` not found.")
            return

    challenge = await _create_challenge(
        creator_id=profile["id"],
        opponent_id=opponent["id"] if opponent else None,
        amount=amount,
        game=game,
        visibility=visibility,
    )

    challenge_text = (
        f"⚔️ *Challenge Created*\n\n"
        f"Game: *{game}*\n"
        f"Stake: *${amount:,.2f} USDC*\n"
        f"Visibility: *{visibility.title()}*\n"
        f"ID: `{challenge['id']}`"
    )

    if visibility == "private" and opponent:
        await notify_user(
            opponent["id"],
            f"{challenge_text}\n\nTap below to accept or decline.",
            buttons=challenge_confirm_menu(challenge["id"]),
        )
        await message.answer(f"✅ Private challenge sent to `@{opponent_tag}`.")
    else:
        await message.answer(challenge_text)


@router.callback_query(F.data.startswith("challenge:accept:"))
async def cb_accept(callback: types.CallbackQuery) -> None:
    """Accept a challenge."""
    await callback.answer()
    challenge_id = callback.data.split(":", 2)[2]
    challenge = await _get_open_challenge(challenge_id)
    if not challenge or challenge.get("status") != "open":
        await callback.message.answer("❌ Challenge is no longer available.")
        return

    accepter = await get_or_create_profile(callback.from_user)
    if challenge["creator_id"] == accepter["id"]:
        await callback.message.answer("❌ You cannot accept your own challenge.")
        return

    if challenge.get("visibility") == "private" and challenge.get("opponent_id") != accepter["id"]:
        await callback.message.answer("❌ This challenge is not for you.")
        return

    await _update_challenge_status(challenge_id, "accepted")
    await _create_bet(challenge, accepter["id"])

    await callback.message.answer(
        f"✅ Challenge accepted. Lock your stake with `/lock_stake {challenge_id}`"
    )
    await notify_user(
        challenge["creator_id"],
        f"🎮 Your challenge was accepted. Lock your stake with `/lock_stake {challenge_id}`",
    )


@router.callback_query(F.data.startswith("challenge:decline:"))
async def cb_decline(callback: types.CallbackQuery) -> None:
    """Decline a challenge."""
    await callback.answer()
    challenge_id = callback.data.split(":", 2)[2]
    challenge = await _get_open_challenge(challenge_id)
    if not challenge or challenge.get("status") != "open":
        await callback.message.answer("❌ Challenge is no longer available.")
        return

    decliner = await get_or_create_profile(callback.from_user)
    if challenge.get("visibility") == "private" and challenge.get("opponent_id") != decliner["id"]:
        await callback.message.answer("❌ This challenge is not for you.")
        return

    await _update_challenge_status(challenge_id, "declined")
    await callback.message.answer("❌ Challenge declined.")
    await notify_user(
        challenge["creator_id"],
        f"🚫 `{decliner.get('gaming_tag') or 'opponent'}` declined your challenge `{challenge_id}`.",
    )
