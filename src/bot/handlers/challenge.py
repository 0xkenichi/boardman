"""Challenge creation and accept/decline callbacks (multi-chain MVP)."""
from __future__ import annotations

import logging
import shlex
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

from aiogram import F, Router, types
from aiogram.enums import ParseMode
from aiogram.filters import Command

from backend.supabase_client import get_supabase
from gaming.src.backend.services.chains import (
    chain_has_escrow,
    default_chain_id,
    format_chain_help,
    get_chain,
    normalize_chain_id,
)
from gaming.src.backend.services.challenge_compat import denormalize_challenge, normalize_challenge
from gaming.src.backend.services.clawstation_circle import get_usdc_balance
from gaming.src.bot.keyboards import challenge_confirm_menu
from gaming.src.bot.utils.db import get_or_create_profile, get_profile_by_tag
from gaming.src.bot.utils.notify import notify_user
from gaming.src.bot.utils.text import bold, code, h

logger = logging.getLogger(__name__)

router = Router()

from gaming.src.backend.services.safety import MAX_STAKE_USDC, MIN_STAKE_USDC

_MIN_STAKE = MIN_STAKE_USDC
_MAX_STAKE = MAX_STAKE_USDC
_USAGE = (
    "Usage: /challenge @opponent amount game public|private [chain]\n\n"
    "Examples:\n"
    "• /challenge @stillkenichi 5 EAFC private\n"
    "• /challenge @rival 10 \"NBA 2K\" private base\n"
    "• /challenge public 5 EAFC public arc\n\n"
    "Chains: base (live), arc, avalanche\n"
    "Default chain uses the live escrow (usually base)."
)


def _parse_challenge_args(
    text: str,
) -> tuple[Optional[str], Decimal, str, str, str, str | None]:
    """Parse challenge args.

    Returns (opponent_tag, amount, game, visibility, chain_id, error).
    """
    raw = text.split(maxsplit=1)[1] if len(text.split(maxsplit=1)) > 1 else ""
    if not raw.strip():
        return None, Decimal("0"), "", "", default_chain_id(), _USAGE

    try:
        parts = shlex.split(raw)
    except ValueError as exc:
        return None, Decimal("0"), "", "", default_chain_id(), f"Invalid quoting: {exc}"

    if not parts:
        return None, Decimal("0"), "", "", default_chain_id(), _USAGE

    # Optional trailing chain: arc | base | avalanche
    chain_id = default_chain_id()
    known_chains = {"arc", "base", "avalanche", "avax", "fuji", "base_sepolia"}
    if parts[-1].lower() in known_chains:
        try:
            chain_id = normalize_chain_id(parts[-1])
        except Exception:
            chain_id = default_chain_id()
        parts = parts[:-1]

    if len(parts) < 1:
        return None, Decimal("0"), "", "", chain_id, _USAGE

    visibility = parts[-1].lower() if parts else ""
    if visibility not in ("public", "private"):
        return (
            None,
            Decimal("0"),
            "",
            "",
            chain_id,
            "Visibility must be public or private.\n\n" + _USAGE,
        )

    if parts[0].lower() in ("public", "private"):
        if len(parts) < 4:
            return None, Decimal("0"), "", "", chain_id, "Missing amount or game.\n\n" + _USAGE
        opponent_tag = None
        amount_str = parts[1]
        game = " ".join(parts[2:-1])
    else:
        if len(parts) < 4:
            return (
                None,
                Decimal("0"),
                "",
                "",
                chain_id,
                "Missing opponent, amount, or game.\n\n" + _USAGE,
            )
        opponent_tag = parts[0].lstrip("@")
        amount_str = parts[1]
        game = " ".join(parts[2:-1])

    try:
        amount = Decimal(amount_str)
    except Exception:
        return None, Decimal("0"), "", "", chain_id, f"Invalid amount: {amount_str}"

    if amount < _MIN_STAKE or amount > _MAX_STAKE:
        return (
            None,
            Decimal("0"),
            "",
            "",
            chain_id,
            f"Amount must be between ${_MIN_STAKE} and ${_MAX_STAKE}.",
        )

    return opponent_tag, amount, game or "EAFC", visibility, chain_id, None


async def _create_challenge(
    creator_id: str,
    opponent_id: Optional[str],
    amount: Decimal,
    game: str,
    visibility: str,
    settlement_chain: str,
) -> dict:
    from gaming.src.backend.services.match_codes import display_code

    challenge_id = str(uuid.uuid4())
    expires_at = datetime.now(timezone.utc) + timedelta(hours=24)
    # Never insert public_code — live gaming.challenges has no such column (PGRST204)
    record = denormalize_challenge(
        {
            "id": challenge_id,
            "creator_id": creator_id,
            "opponent_id": opponent_id,
            "amount_usdc": float(amount),
            "game": game,
            "visibility": visibility,
            "status": "open",
            "expires_at": expires_at.isoformat(),
            "message": f"ClawStation {visibility} challenge",
            "settlement_chain": settlement_chain,
        }
    )
    sb = get_supabase()
    try:
        result = sb.schema("gaming").table("challenges").insert(record).execute()
    except Exception as exc:
        err = str(exc).lower()
        if "settlement_chain" in err and ("column" in err or "schema cache" in err):
            record.pop("settlement_chain", None)
            result = sb.schema("gaming").table("challenges").insert(record).execute()
        else:
            raise
    if not result.data:
        raise RuntimeError("Challenge insert returned no data")
    ch = normalize_challenge(result.data[0])
    if ch is not None:
        ch["public_code"] = display_code(None, challenge_id=challenge_id)
    return ch


async def _get_open_challenge(challenge_id: str) -> Optional[dict]:
    from gaming.src.backend.services.match_codes import load_challenge_by_ref

    return load_challenge_by_ref(challenge_id)


async def _update_challenge_status(challenge_id: str, status: str) -> None:
    sb = get_supabase()
    sb.schema("gaming").table("challenges").update({"status": status}).eq("id", challenge_id).execute()


async def _create_bet(challenge: dict, opponent_id: str) -> Optional[dict]:
    bet_id = str(uuid.uuid4())
    record = {
        "id": bet_id,
        "challenge_id": challenge["id"],
        "challenger_id": challenge["creator_id"],
        "opponent_id": opponent_id,
        "amount_usdc": float(challenge["amount_usdc"]),
        "status": "pending",
    }
    sb = get_supabase()
    try:
        result = sb.schema("gaming").table("bets").insert(record).execute()
        return result.data[0] if result.data else None
    except Exception as exc:
        logger.warning("[Challenge] gaming.bets insert skipped: %s", exc)
        return None


@router.message(Command("challenge"))
async def cmd_challenge(message: types.Message) -> None:
    """Create a public or private gaming challenge."""
    user = message.from_user
    if user is None or not message.text:
        return

    opponent_tag, amount, game, visibility, chain_id, error = _parse_challenge_args(message.text)
    if error:
        await message.answer(f"❌ {error}\n\n{format_chain_help()}", parse_mode=None)
        return

    if not chain_has_escrow(chain_id):
        await message.answer(
            f"❌ Chain {chain_id} has no ClawEscrow deployed yet.\n\n"
            f"{format_chain_help()}\n\n"
            f"Use chain `base` for the live testnet escrow.",
            parse_mode=None,
        )
        return

    try:
        chain_meta = get_chain(chain_id)
    except ValueError as exc:
        await message.answer(f"❌ {exc}", parse_mode=None)
        return

    profile = await get_or_create_profile(user)

    # One active match at a time
    from gaming.src.backend.services.play_points import assert_can_start_or_accept
    from gaming.src.backend.services.safety import assert_money_ops_allowed

    gate = assert_money_ops_allowed(
        profile["id"], action="challenge", amount=amount, kind="stake"
    )
    if gate:
        await message.answer(gate, parse_mode=ParseMode.HTML)
        return

    blocked = assert_can_start_or_accept(profile["id"])
    if blocked:
        await message.answer(f"❌ {blocked}", parse_mode=None)
        return

    try:
        balance = await get_usdc_balance(profile["id"], chain_id=chain_id)
    except Exception as exc:
        logger.exception("[Challenge] Failed to fetch balance for %s", profile["id"])
        await message.answer(f"❌ Could not verify balance: {h(exc)}", parse_mode=ParseMode.HTML)
        return

    if balance < amount:
        await message.answer(
            f"❌ Insufficient balance. You have {bold(f'${balance:,.2f}')} but need {bold(f'${amount:,.2f}')}.\n"
            f"Deposit Base Sepolia USDC to the address from /start.",
            parse_mode=ParseMode.HTML,
        )
        return

    opponent: Optional[dict] = None
    if visibility == "private":
        if not opponent_tag:
            await message.answer(
                "❌ Private challenges need an opponent tag, e.g. @stillkenichi.",
                parse_mode=None,
            )
            return
        opponent = await get_profile_by_tag(opponent_tag)
        if not opponent:
            await message.answer(
                f"❌ Player {code('@' + opponent_tag)} not found.\n"
                f"They must open the bot and tap /start first so their gaming tag is created.",
                parse_mode=ParseMode.HTML,
            )
            return
        if opponent["id"] == profile["id"]:
            await message.answer("❌ You cannot challenge yourself.", parse_mode=None)
            return
        blocked_opp = assert_can_start_or_accept(opponent["id"])
        if blocked_opp:
            await message.answer(
                f"❌ @{opponent_tag} already has an open match. They must finish it first.",
                parse_mode=None,
            )
            return

    try:
        challenge = await _create_challenge(
            creator_id=profile["id"],
            opponent_id=opponent["id"] if opponent else None,
            amount=amount,
            game=game,
            visibility=visibility,
            settlement_chain=chain_id,
        )
    except Exception as exc:
        logger.exception("[Challenge] create failed for %s", profile["id"])
        await message.answer(f"❌ Could not create challenge: {h(exc)}", parse_mode=ParseMode.HTML)
        return

    from gaming.src.backend.services.match_codes import display_code, ensure_public_code

    my_tag = profile.get("gaming_tag") or "player"
    match_code = ensure_public_code(challenge) if challenge.get("id") else display_code(challenge)
    challenge_text = (
        f"⚔️ {bold('Challenge Created')}\n\n"
        f"From: {code('@' + my_tag)}\n"
        f"Game: {bold(game)}\n"
        f"Stake: {bold(f'${amount:,.2f} USDC')}\n"
        f"Chain: {bold(chain_meta.get('label') or chain_id)}\n"
        f"Visibility: {bold(visibility.title())}\n"
        f"Match: {code(match_code)}"
    )

    if visibility == "private" and opponent:
        try:
            await notify_user(
                opponent["id"],
                f"{challenge_text}\n\nTap below to accept or decline.",
                buttons=challenge_confirm_menu(challenge["id"]),
            )
        except Exception:
            logger.exception("[Challenge] notify opponent failed")
        await message.answer(
            f"✅ Private challenge sent to {code('@' + (opponent.get('gaming_tag') or opponent_tag))}.\n"
            f"Match code: {code(match_code)}\n"
            f"Chain: {bold(chain_id)}",
            parse_mode=ParseMode.HTML,
        )
    else:
        group_ok = False
        try:
            from gaming.src.bot.utils.community import post_public_challenge

            group_ok = await post_public_challenge(
                challenge_id=str(challenge.get("id") or ""),
                public_code=str(match_code),
                creator_tag=str(my_tag),
                amount=amount,
                game_label=str(game),
                game=str(game),
            )
        except Exception:
            logger.exception("[Challenge] community group post failed")
        extra = (
            "\n\n📣 Also posted in the community group."
            if group_ok
            else "\n\n(Public board only — group not linked: /link_community in the group.)"
        )
        await message.answer(
            challenge_text + "\n\nWaiting for an opponent to accept." + extra,
            parse_mode=ParseMode.HTML,
        )


@router.callback_query(F.data.startswith("challenge:accept:"))
async def cb_accept(callback: types.CallbackQuery) -> None:
    """Accept a challenge."""
    try:
        await callback.answer("Accepting…")
    except Exception:
        pass
    from gaming.src.backend.services.safety import is_paused, pause_message

    if is_paused():
        await callback.message.answer(pause_message(), parse_mode=ParseMode.HTML)
        return

    challenge_id = callback.data.split(":", 2)[2]
    challenge = await _get_open_challenge(challenge_id)
    if not challenge or challenge.get("status") != "open":
        await callback.message.answer("❌ Challenge is no longer available.", parse_mode=None)
        return

    accepter = await get_or_create_profile(callback.from_user)
    if challenge["creator_id"] == accepter["id"]:
        await callback.message.answer("❌ You cannot accept your own challenge.", parse_mode=None)
        return

    if challenge.get("visibility") == "private" and challenge.get("opponent_id") != accepter["id"]:
        await callback.message.answer("❌ This challenge is not for you.", parse_mode=None)
        return

    from gaming.src.backend.services.play_points import assert_can_start_or_accept

    # Allow accept if the only active match is THIS challenge (invited target)
    blocked = assert_can_start_or_accept(accepter["id"])
    if blocked and challenge.get("id") not in (blocked or ""):
        # If they have a different active match, block
        from gaming.src.backend.services.play_points import get_active_challenge

        active = get_active_challenge(accepter["id"])
        if active and active.get("id") != challenge.get("id"):
            await callback.message.answer(
                f"❌ You already have an open match.\n"
                f"Finish <code>{active.get('id')}</code> first.\n"
                f"/match_info {active.get('id')}",
                parse_mode=ParseMode.HTML,
            )
            return

    # Balance check for opponent
    amount = Decimal(str(challenge["amount_usdc"]))
    try:
        bal = await get_usdc_balance(accepter["id"])
        if bal < amount:
            await callback.message.answer(
                f"❌ Need {bold(f'${amount:,.2f}')} USDC to accept. You have {bold(f'${bal:,.2f}')}.",
                parse_mode=ParseMode.HTML,
            )
            return
    except Exception as exc:
        logger.warning("[Challenge] balance check on accept: %s", exc)

    sb = get_supabase()
    sb.schema("gaming").table("challenges").update(
        denormalize_challenge({"status": "accepted", "opponent_id": accepter["id"]})
    ).eq("id", challenge_id).execute()
    await _create_bet(challenge, accepter["id"])

    chain = challenge.get("settlement_chain") or default_chain_id()
    from gaming.src.bot.keyboards import match_actions_menu

    ch_full = await _get_open_challenge(challenge_id) or challenge
    ch_full = {**ch_full, "status": "accepted", "opponent_id": accepter["id"]}
    await callback.message.answer(
        f"✅ Challenge accepted.\n\n"
        f"Network: {bold(chain)}\n"
        f"Tap <b>Lock my stake</b> below.\n"
        f"(Challenger locks first, then you.)",
        parse_mode=ParseMode.HTML,
        reply_markup=match_actions_menu(ch_full, accepter["id"]),
    )
    await notify_user(
        challenge["creator_id"],
        f"🎮 Accepted by @{h(accepter.get('gaming_tag') or 'player')}.\n"
        f"Tap <b>My match</b> → <b>Lock my stake</b> first.",
        buttons=match_actions_menu(ch_full, challenge["creator_id"]),
    )


@router.callback_query(F.data.startswith("challenge:decline:"))
async def cb_decline(callback: types.CallbackQuery) -> None:
    """Decline a challenge."""
    await callback.answer()
    challenge_id = callback.data.split(":", 2)[2]
    challenge = await _get_open_challenge(challenge_id)
    if not challenge or challenge.get("status") != "open":
        await callback.message.answer("❌ Challenge is no longer available.", parse_mode=None)
        return

    decliner = await get_or_create_profile(callback.from_user)
    if challenge.get("visibility") == "private" and challenge.get("opponent_id") != decliner["id"]:
        await callback.message.answer("❌ This challenge is not for you.", parse_mode=None)
        return

    await _update_challenge_status(challenge_id, "declined")
    await callback.message.answer("❌ Challenge declined.", parse_mode=None)
    from gaming.src.backend.services.match_codes import display_code

    await notify_user(
        challenge["creator_id"],
        f"🚫 {code(decliner.get('gaming_tag') or 'opponent')} declined your challenge "
        f"{code(display_code(challenge))}.",
    )


@router.message(Command("chains"))
async def cmd_chains(message: types.Message) -> None:
    """List settlement chains."""
    await message.answer(format_chain_help(), parse_mode=None)
