"""Submit match scores and screenshots; AI vision + settlement.

Score formats:
  /submit_score <id> 3           → your goals only (legacy)
  /submit_score <id> 5-3         → full scoreline home-away
  Photo caption: /submit_score <id> [5-3]

AI only runs when a Telegram **photo** is attached (not a local file path).
"""
from __future__ import annotations

import base64
import logging
import re
import tempfile
from pathlib import Path
from typing import Any, Optional

from aiogram import Bot, F, Router, types
from aiogram.enums import ParseMode
from aiogram.filters import Command

from backend.supabase_client import get_supabase
from gaming.src.backend.services.challenge_compat import denormalize_challenge, normalize_challenge
from gaming.src.bot.keyboards import back_menu
from gaming.src.bot.utils.db import get_or_create_profile
from gaming.src.bot.utils.notify import notify_user
from gaming.src.bot.utils.text import bold, code, h
from gaming.src.backend.services.match_codes import display_code as _match_code

logger = logging.getLogger(__name__)

router = Router()

_USAGE = (
    "Usage (use short match code, e.g. K7M2P9QX):\n"
    "• /submit_score CODE 5-3          full scoreline (home-away)\n"
    "• /submit_score CODE 3            your goals only\n"
    "• Send a PHOTO with caption:      /submit_score CODE [5-3]\n\n"
    "Also set sides before playing:\n"
    "• /set_side CODE home|away\n"
    "• /set_team CODE home \"Real Madrid\"\n"
    "• /set_team CODE away \"Barcelona\"\n"
    "• /link_psn or /link_xbox for console IDs\n\n"
    "⚠️ AI vision only works on Telegram photos (attach image in chat).\n"
    "Do NOT paste a Mac/PC file path as text."
)


def _safe_row(result) -> Optional[dict]:
    if result is None:
        return None
    data = getattr(result, "data", None)
    if data is None:
        return None
    if isinstance(data, list):
        return data[0] if data else None
    if isinstance(data, dict):
        return data
    return None


def _parse_score_token(token: str) -> tuple[Optional[int], Optional[int], Optional[int]]:
    """Parse '5-3', '5:3', or '5'.

    Returns (single_score, home, away). single_score set for legacy one-int form.
    """
    token = (token or "").strip()
    m = re.fullmatch(r"(\d+)\s*[-:]\s*(\d+)", token)
    if m:
        return None, int(m.group(1)), int(m.group(2))
    if re.fullmatch(r"\d+", token):
        return int(token), None, None
    return None, None, None


def _normalize_caption(text: str) -> str:
    """Strip bot mention: /submit_score@BotName → /submit_score"""
    t = (text or "").strip()
    t = re.sub(r"^/submit_score@[A-Za-z0-9_]+", "/submit_score", t, flags=re.I)
    return t


def _is_submit_caption(text: str) -> bool:
    t = _normalize_caption(text).lower()
    return t.startswith("/submit_score")


def _parse_args(text: str) -> tuple[Optional[str], Optional[int], Optional[int], Optional[int]]:
    """Returns (challenge_id, single_score, home, away)."""
    raw = _normalize_caption(text)
    parts = raw.split(maxsplit=2)
    challenge_id = parts[1] if len(parts) > 1 else None
    if len(parts) < 3:
        return challenge_id, None, None, None
    single, home, away = _parse_score_token(parts[2].split()[0] if parts[2] else "")
    return challenge_id, single, home, away


def _extract_image_file_id(message: types.Message) -> Optional[str]:
    """Photo (compressed) or document image (full-res screenshot)."""
    if message.photo:
        return message.photo[-1].file_id
    doc = message.document
    if doc and (doc.mime_type or "").startswith("image/"):
        return doc.file_id
    # reply-to image
    reply = message.reply_to_message
    if reply:
        if reply.photo:
            return reply.photo[-1].file_id
        if reply.document and (reply.document.mime_type or "").startswith("image/"):
            return reply.document.file_id
    return None


async def _load_challenge(challenge_id: str) -> Optional[dict]:
    """Accept short public match code or internal UUID."""
    if not challenge_id:
        return None
    from gaming.src.backend.services.match_codes import load_challenge_by_ref

    return load_challenge_by_ref(challenge_id)


def _side_for(profile_id: str, challenge: dict) -> Optional[str]:
    if profile_id == challenge.get("creator_id"):
        return challenge.get("creator_side")
    if profile_id == challenge.get("opponent_id"):
        return challenge.get("opponent_side")
    return None


def _my_goals_from_scoreline(side: Optional[str], home: int, away: int) -> int:
    """Map home-away scoreline to this player's goals using their declared side."""
    if side == "home":
        return home
    if side == "away":
        return away
    # Unknown side: store home goals as creator convention (legacy)
    return home


async def _store_report(
    challenge_id: str,
    profile_id: str,
    *,
    single_score: Optional[int] = None,
    home: Optional[int] = None,
    away: Optional[int] = None,
) -> dict:
    sb = get_supabase()
    challenge = await _load_challenge(challenge_id)
    if not challenge:
        raise ValueError("Challenge not found")

    # Always use internal UUID for DB ops (user may pass short public_code)
    uuid_id = challenge["id"]

    is_creator = profile_id == challenge["creator_id"]
    is_opponent = profile_id == challenge.get("opponent_id")
    if not is_creator and not is_opponent:
        raise ValueError("Not a participant")

    status = challenge.get("status")
    if status not in ("locked", "creator_locked", "submitted", "playing", "accepted"):
        raise ValueError(f"Challenge status is {status}, cannot submit score")

    update: dict[str, Any] = {}
    side = _side_for(profile_id, challenge)

    if home is not None and away is not None:
        if is_creator:
            update["creator_reported_home"] = home
            update["creator_reported_away"] = away
            update["creator_score"] = _my_goals_from_scoreline(side or "home", home, away)
        else:
            update["opponent_reported_home"] = home
            update["opponent_reported_away"] = away
            update["opponent_score"] = _my_goals_from_scoreline(side or "away", home, away)
    elif single_score is not None:
        if is_creator:
            update["creator_score"] = single_score
        else:
            update["opponent_score"] = single_score
    else:
        raise ValueError("Missing score")

    # Merge with existing to decide if both have reported
    merged = {**challenge, **update}
    both = (
        merged.get("creator_score") is not None and merged.get("opponent_score") is not None
    ) or (
        merged.get("creator_reported_home") is not None
        and merged.get("opponent_reported_home") is not None
    )
    if both:
        update["status"] = "submitted"
    elif status == "locked":
        update["status"] = "playing"

    sb.schema("gaming").table("challenges").update(denormalize_challenge(update)).eq(
        "id", uuid_id
    ).execute()
    return (await _load_challenge(uuid_id)) or challenge


async def _download_photo_b64(bot: Bot, file_id: str) -> str:
    tg_file = await bot.get_file(file_id)
    path = tg_file.file_path
    if not path:
        raise RuntimeError("Telegram file path missing")
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    try:
        await bot.download_file(path, destination=tmp_path)
        return base64.b64encode(tmp_path.read_bytes()).decode("ascii")
    finally:
        try:
            tmp_path.unlink(missing_ok=True)
        except Exception:
            pass


async def _run_ai_on_screenshot(image_b64: str, challenge: dict) -> dict:
    """Extract score with match context (sides, teams, console IDs)."""
    try:
        from gaming.src.backend.score_verifier import get_score_verifier

        verifier = get_score_verifier()
        context = {
            "home_team": challenge.get("home_team"),
            "away_team": challenge.get("away_team"),
            "creator_side": challenge.get("creator_side"),
            "opponent_side": challenge.get("opponent_side"),
            "creator_console_id": challenge.get("creator_console_id"),
            "opponent_console_id": challenge.get("opponent_console_id"),
            "console_platform": challenge.get("console_platform"),
            "game": challenge.get("game") or challenge.get("game_type"),
        }
        # Prefer contextual verify if available
        if hasattr(verifier, "verify_screenshot_with_context"):
            result = await verifier.verify_screenshot_with_context(image_b64, context)
        else:
            result = await verifier.verify_screenshot(image_b64)
        return {
            "ok": result.is_valid,
            "player1_score": result.player1_score,
            "player2_score": result.player2_score,
            "team1_name": getattr(result, "team1_name", None),
            "team2_name": getattr(result, "team2_name", None),
            "team1_home_away": getattr(result, "team1_home_away", None),
            "team2_home_away": getattr(result, "team2_home_away", None),
            "player1_id": getattr(result, "player1_id", None),
            "player2_id": getattr(result, "player2_id", None),
            "confidence": float(result.confidence or 0),
            "game": result.game_detected,
            "error": result.error,
            "score_string": result.score_string() if result.is_valid else None,
        }
    except Exception as exc:
        logger.exception("[SubmitScore] AI vision failed")
        return {"ok": False, "error": str(exc), "confidence": 0.0}


def _map_ai_to_home_away(ai: dict, challenge: dict) -> tuple[Optional[int], Optional[int]]:
    """Map AI left/right (player1/player2) to home/away goals using team names or labels."""
    p1, p2 = ai.get("player1_score"), ai.get("player2_score")
    if p1 is None or p2 is None:
        return None, None

    t1_ha = (ai.get("team1_home_away") or "").lower()
    t2_ha = (ai.get("team2_home_away") or "").lower()
    if t1_ha == "home" and t2_ha == "away":
        return int(p1), int(p2)
    if t1_ha == "away" and t2_ha == "home":
        return int(p2), int(p1)

    # Match declared club names
    home_team = (challenge.get("home_team") or "").lower()
    away_team = (challenge.get("away_team") or "").lower()
    t1 = (ai.get("team1_name") or "").lower()
    t2 = (ai.get("team2_name") or "").lower()
    if home_team and t1 and home_team in t1:
        return int(p1), int(p2)
    if home_team and t2 and home_team in t2:
        return int(p2), int(p1)
    if away_team and t1 and away_team in t1:
        return int(p2), int(p1)

    # Default: left = home (EA FC full-time screen convention often home left)
    return int(p1), int(p2)


async def _maybe_settle(challenge_id: str) -> None:
    try:
        from gaming.src.backend.services.clawstation_settlement import settle_challenge

        result = await settle_challenge(challenge_id)
        logger.info("[SubmitScore] settle %s → %s", challenge_id, result)
    except Exception:
        logger.exception("[SubmitScore] settle failed for %s", challenge_id)


def _format_match_context(challenge: dict) -> str:
    lines = []
    ht, at = challenge.get("home_team"), challenge.get("away_team")
    if ht or at:
        lines.append(f"Clubs: {ht or '?'} (H) vs {at or '?'} (A)")
    cs, os_ = challenge.get("creator_side"), challenge.get("opponent_side")
    if cs or os_:
        lines.append(f"Creator side: {cs or '?'} · Opponent side: {os_ or '?'}")
    if challenge.get("creator_console_id") or challenge.get("opponent_console_id"):
        lines.append(
            f"Console: {challenge.get('console_platform') or '?'} · "
            f"creator={challenge.get('creator_console_id') or '—'} · "
            f"opp={challenge.get('opponent_console_id') or '—'}"
        )
    return "\n".join(lines)


@router.message(Command("submit_score"))
async def cmd_submit_score(message: types.Message, bot: Bot) -> None:
    """Text score submission (no AI — attach a photo for vision).

    Also: reply to an image with /submit_score ID 5-3 (handled above if reply has image).
    """
    user = message.from_user
    # Photo/document with caption /submit_score is handled by media_submit_score
    if message.photo or message.document:
        return
    if user is None or not message.text:
        return

    # If user pasted a screenshot path by mistake, warn clearly
    if (
        ".png" in message.text.lower()
        or ".jpg" in message.text.lower()
        or "/var/folders/" in message.text
        or "/Users/" in message.text
    ):
        await message.answer(
            "❌ That looks like a local file path — Telegram cannot read your Mac disk.\n\n"
            "Do this instead:\n"
            "1. Tap 📎 → Photo or File\n"
            "2. Pick the screenshot\n"
            "3. Caption: <code>/submit_score MATCH_CODE 5-3</code>\n"
            "4. Send\n\n"
            "Or: send the image first, then <b>reply</b> to it with the command.",
            parse_mode=ParseMode.HTML,
            reply_markup=back_menu(),
        )
        return

    # Reply to image already handled by reply_submit_score; if that didn't fire, try here
    if message.reply_to_message and _extract_image_file_id(message):
        await _process_screenshot_message(
            message, bot, message.text, file_id_override=_extract_image_file_id(message)
        )
        return

    challenge_id, single, home, away = _parse_args(message.text)
    if not challenge_id or (single is None and home is None):
        await message.answer(_USAGE, reply_markup=back_menu(), parse_mode=None)
        return

    profile = await get_or_create_profile(user)
    try:
        challenge = await _store_report(
            challenge_id, profile["id"], single_score=single, home=home, away=away
        )
    except ValueError as exc:
        await message.answer(f"❌ {h(exc)}", reply_markup=back_menu(), parse_mode=ParseMode.HTML)
        return

    if home is not None and away is not None:
        score_txt = f"{home}-{away}"
    else:
        score_txt = str(single)

    from gaming.src.backend.services.match_report import analyze_reports
    from gaming.src.bot.utils.flow import report_status, waiting_on_opponent
    from gaming.src.bot.utils.notify import get_balance_snapshot

    analysis = analyze_reports(challenge)
    bal = await get_balance_snapshot(profile["id"])
    await message.answer(
        f"✅ <b>Report confirmed</b>\n"
        f"Scoreline: {bold(score_txt)}\n"
        f"Match: {code(_match_code(None, challenge_id))}\n\n"
        f"{report_status(challenge)}\n\n"
        f"<b>Your balances</b>\n{bal}\n\n"
        f"💡 Optional proof: attach FT photo with caption\n"
        f"{code(f'/submit_score {_match_code(None, challenge_id)} {score_txt}')}",
        reply_markup=back_menu(),
        parse_mode=ParseMode.HTML,
    )

    if analysis["action"] in ("wait_opponent", "wait_creator"):
        who = "opponent" if analysis["action"] == "wait_opponent" else "challenger"
        await message.answer(
            waiting_on_opponent(challenge_id, who),
            parse_mode=ParseMode.HTML,
        )
        # Nudge the other side immediately
        other_id = (
            challenge.get("opponent_id")
            if analysis["action"] == "wait_opponent"
            else challenge.get("creator_id")
        )
        if other_id and other_id != profile["id"]:
            await notify_user(
                other_id,
                f"📊 Your opponent reported on {code(_match_code(None, challenge_id))}.\n"
                f"Your turn — FT photo + caption:\n"
                f"{code(f'/submit_score {_match_code(None, challenge_id)} 5-3')}",
            )
    elif analysis["action"] in ("settle_ready", "wait_screenshots", "conflict"):
        other_id = (
            challenge["creator_id"]
            if profile["id"] == challenge.get("opponent_id")
            else challenge.get("opponent_id")
        )
        if other_id:
            await notify_user(
                other_id,
                f"📊 Update on {code(_match_code(None, challenge_id))}: {analysis['reason']}\n"
                f"{code(f'/match_info {_match_code(None, challenge_id)}')}",
            )
        await _maybe_settle(challenge_id)


@router.message(F.photo | F.document)
async def media_submit_score(message: types.Message, bot: Bot) -> None:
    """Screenshot as photo OR image file/document + caption /submit_score …"""
    user = message.from_user
    caption = message.caption or ""

    # Image without submit caption → short hint (don't swallow unrelated photos silently)
    if not _is_submit_caption(caption):
        if message.photo or (
            message.document and (message.document.mime_type or "").startswith("image/")
        ):
            # Only hint if looks like a lone screenshot (no other text command)
            if not (message.caption or "").strip():
                await message.answer(
                    "📸 Got an image. To use it as match proof, <b>edit/resend</b> with caption:\n"
                    "<code>/submit_score MATCH_CODE 5-3</code>\n\n"
                    "Or: reply to this image with that command.",
                    parse_mode=ParseMode.HTML,
                )
        return

    await _process_screenshot_message(message, bot, caption)


@router.message(Command("submit_score"), F.reply_to_message)
async def reply_submit_score(message: types.Message, bot: Bot) -> None:
    """Reply to a photo/document with /submit_score ID 5-3."""
    user = message.from_user
    if user is None or not message.text:
        return
    if not message.reply_to_message:
        return
    file_id = _extract_image_file_id(message)
    if not file_id:
        # Fall through: normal text submit_score may also match — handled by cmd
        return
    # Build a synthetic caption from the command text for the shared pipeline
    await _process_screenshot_message(message, bot, message.text, file_id_override=file_id)


async def _process_screenshot_message(
    message: types.Message,
    bot: Bot,
    caption: str,
    file_id_override: Optional[str] = None,
) -> None:
    """Shared path for photo/document/reply image proof."""
    user = message.from_user
    if user is None:
        return

    challenge_ref, single, home, away = _parse_args(caption)
    if not challenge_ref:
        await message.answer(
            "❌ Caption must be: /submit_score MATCH_CODE [5-3]\n"
            "Example: /submit_score K7M2P9QX 5-3",
            reply_markup=back_menu(),
            parse_mode=None,
        )
        return

    await message.answer("📥 Got your screenshot — processing…", parse_mode=None)

    profile = await get_or_create_profile(user)
    challenge = await _load_challenge(challenge_ref)
    if not challenge:
        await message.answer("❌ Challenge not found.", reply_markup=back_menu(), parse_mode=None)
        return
    challenge_id = challenge["id"]  # internal UUID only
    match_code = _match_code(challenge)

    is_creator = profile["id"] == challenge["creator_id"]
    is_opponent = profile["id"] == challenge.get("opponent_id")
    if not is_creator and not is_opponent:
        await message.answer("❌ You are not part of this challenge.", reply_markup=back_menu(), parse_mode=None)
        return

    status = challenge.get("status")
    if status not in ("locked", "creator_locked", "submitted", "playing", "accepted"):
        await message.answer(
            f"❌ Challenge status is {status}; cannot submit proof.",
            reply_markup=back_menu(),
            parse_mode=None,
        )
        return

    file_id = file_id_override or _extract_image_file_id(message)
    if not file_id:
        await message.answer(
            "❌ No image found. Send as Photo or File (PNG/JPG), not a path.\n"
            f"Or reply to the image with /submit_score {match_code} 5-3",
            reply_markup=back_menu(),
            parse_mode=None,
        )
        return

    column = "screenshot_creator_url" if is_creator else "screenshot_opponent_url"
    sb = get_supabase()
    update: dict = {column: file_id}
    if status == "locked":
        update["status"] = "playing"
    try:
        sb.schema("gaming").table("challenges").update(denormalize_challenge(update)).eq(
            "id", challenge_id
        ).execute()
    except Exception:
        logger.exception("[SubmitScore] failed to save screenshot ref")
        await message.answer("❌ Could not save screenshot to database.", parse_mode=None)
        return

    challenge = await _load_challenge(challenge_id) or challenge
    await message.answer("🔍 AI reading screenshot…", parse_mode=None)

    ai_line = ""
    ai_home: Optional[int] = None
    ai_away: Optional[int] = None
    try:
        image_b64 = await _download_photo_b64(bot, file_id)
        ai = await _run_ai_on_screenshot(image_b64, challenge)
        if ai.get("ok"):
            ai_home, ai_away = _map_ai_to_home_away(ai, challenge)
            conf = ai.get("confidence") or 0
            clubs = ""
            if ai.get("team1_name") or ai.get("team2_name"):
                clubs = f"\nClubs: {ai.get('team1_name') or '?'} vs {ai.get('team2_name') or '?'}"
            ids = ""
            if ai.get("player1_id") or ai.get("player2_id"):
                ids = f"\nIDs: {ai.get('player1_id') or '—'} / {ai.get('player2_id') or '—'}"
            ai_line = (
                f"\nAI scoreline: {bold(f'{ai_home}-{ai_away}')} "
                f"(conf {bold(f'{conf:.0%}')}){clubs}{ids}"
            )
            ai_update: dict[str, Any] = {
                "ai_verified_score": f"{ai_home}-{ai_away}",
                "ai_confidence": conf,
                "ai_home_score": ai_home,
                "ai_away_score": ai_away,
                "ai_player_ids": {
                    "player1": ai.get("player1_id"),
                    "player2": ai.get("player2_id"),
                },
                "ai_raw": {
                    "team1": ai.get("team1_name"),
                    "team2": ai.get("team2_name"),
                    "t1_ha": ai.get("team1_home_away"),
                    "t2_ha": ai.get("team2_home_away"),
                    "p1": ai.get("player1_score"),
                    "p2": ai.get("player2_score"),
                    "game": ai.get("game"),
                },
            }
            try:
                sb.schema("gaming").table("challenges").update(
                    denormalize_challenge(ai_update)
                ).eq("id", challenge_id).execute()
            except Exception:
                logger.warning("[SubmitScore] AI columns missing — apply migration 050")
        else:
            ai_line = f"\nAI could not read score: {h(ai.get('error') or 'unreadable')}"
    except Exception as exc:
        logger.exception("[SubmitScore] photo AI path failed")
        ai_line = f"\nAI skip: {h(exc)}"

    final_home, final_away = home, away
    final_single = single
    if final_home is None and ai_home is not None and ai_away is not None:
        final_home, final_away = ai_home, ai_away

    reply = f"✅ Screenshot saved.{ai_line}"
    if final_home is not None and final_away is not None:
        try:
            challenge = await _store_report(
                challenge_id, profile["id"], home=final_home, away=final_away
            )
            reply += f"\nRecorded: {bold(f'{final_home}-{final_away}')}"
        except ValueError as exc:
            await message.answer(
                f"✅ Screenshot saved, but score error: {h(exc)}",
                reply_markup=back_menu(),
                parse_mode=ParseMode.HTML,
            )
            return
    elif final_single is not None:
        try:
            challenge = await _store_report(
                challenge_id, profile["id"], single_score=final_single
            )
            reply += f"\nRecorded goals: {bold(final_single)}"
        except ValueError as exc:
            await message.answer(
                f"✅ Screenshot saved, but score error: {h(exc)}",
                reply_markup=back_menu(),
                parse_mode=ParseMode.HTML,
            )
            return
    else:
        reply += (
            f"\nCould not get a score. Reply with:\n"
            f"{code(f'/submit_score {_match_code(None, challenge_id)} 5-3')}"
        )

    from gaming.src.bot.utils.notify import get_balance_snapshot

    bal = await get_balance_snapshot(profile["id"])
    reply += f"\n\n<b>Your balances</b>\n{bal}"
    await message.answer(reply, reply_markup=back_menu(), parse_mode=ParseMode.HTML)

    refreshed = await _load_challenge(challenge_id)
    if not refreshed:
        return

    both_scores = (
        refreshed.get("creator_score") is not None
        and refreshed.get("opponent_score") is not None
    )
    both_shots = bool(
        refreshed.get("screenshot_creator_url") and refreshed.get("screenshot_opponent_url")
    )
    if both_scores or both_shots:
        if both_shots and refreshed.get("status") != "submitted":
            try:
                sb.schema("gaming").table("challenges").update(
                    denormalize_challenge({"status": "submitted"})
                ).eq("id", challenge_id).execute()
            except Exception:
                pass
        other_id = (
            refreshed["creator_id"]
            if profile["id"] == refreshed.get("opponent_id")
            else refreshed.get("opponent_id")
        )
        if other_id:
            await notify_user(
                other_id,
                f"📊 Proof in for {code(_match_code(None, challenge_id))}. Settling if ready…\n"
                f"{code(f'/match_info {_match_code(None, challenge_id)}')}",
            )
        await _maybe_settle(challenge_id)
        # After settle, re-send balances if match resolved
        refreshed2 = await _load_challenge(challenge_id)
        if refreshed2 and refreshed2.get("status") == "resolved":
            bal2 = await get_balance_snapshot(profile["id"])
            await message.answer(
                f"✅ Match resolved.\n\n<b>Updated balances</b>\n{bal2}\n\n"
                f"/profile · /balance",
                parse_mode=ParseMode.HTML,
                reply_markup=back_menu(),
            )


@router.message(Command("set_side"))
async def cmd_set_side(message: types.Message) -> None:
    """Declare home or away for this challenge."""
    user = message.from_user
    if user is None or not message.text:
        return
    parts = message.text.split()
    if len(parts) < 3 or parts[2].lower() not in ("home", "away"):
        await message.answer(
            "Usage: /set_side MATCH_CODE home|away\n"
            "Example: /set_side df0626e5-… home",
            parse_mode=None,
        )
        return
    challenge_ref, side = parts[1], parts[2].lower()
    profile = await get_or_create_profile(user)
    challenge = await _load_challenge(challenge_ref)
    if not challenge:
        await message.answer("❌ Challenge not found.", parse_mode=None)
        return
    challenge_id = challenge["id"]
    match_code = _match_code(challenge)
    is_creator = profile["id"] == challenge["creator_id"]
    is_opponent = profile["id"] == challenge.get("opponent_id")
    if not is_creator and not is_opponent:
        await message.answer("❌ Not a participant.", parse_mode=None)
        return

    other_side = "away" if side == "home" else "home"
    update: dict = {}
    if is_creator:
        update["creator_side"] = side
        # Auto-assign opponent opposite if empty
        if not challenge.get("opponent_side"):
            update["opponent_side"] = other_side
    else:
        update["opponent_side"] = side
        if not challenge.get("creator_side"):
            update["creator_side"] = other_side

    # Conflict if both claim same side
    if is_creator and challenge.get("opponent_side") == side:
        await message.answer(
            f"❌ Opponent already set {side}. Pick {other_side} or they must change.",
            parse_mode=None,
        )
        return
    if is_opponent and challenge.get("creator_side") == side:
        await message.answer(
            f"❌ Creator already set {side}. Pick {other_side} or they must change.",
            parse_mode=None,
        )
        return

    get_supabase().schema("gaming").table("challenges").update(
        denormalize_challenge(update)
    ).eq("id", challenge_id).execute()

    team_hint = f'/set_team {match_code} {side} "Club Name"'
    await message.answer(
        f"✅ You are {bold(side.upper())} for {code(match_code)}.\n"
        f"Optional: {code(team_hint)}",
        parse_mode=ParseMode.HTML,
    )


@router.message(Command("set_team"))
async def cmd_set_team(message: types.Message) -> None:
    """Set home or away club name for the match."""
    user = message.from_user
    if user is None or not message.text:
        return
    # /set_team <id> home|away <team name...>
    parts = message.text.split(maxsplit=3)
    if len(parts) < 4 or parts[2].lower() not in ("home", "away"):
        await message.answer(
            'Usage: /set_team MATCH_CODE home|away Club Name\n'
            'Example: /set_team df06… home Real Madrid',
            parse_mode=None,
        )
        return
    challenge_ref, which, team = parts[1], parts[2].lower(), parts[3].strip().strip('"')
    profile = await get_or_create_profile(user)
    challenge = await _load_challenge(challenge_ref)
    if not challenge:
        await message.answer("❌ Challenge not found.", parse_mode=None)
        return
    challenge_id = challenge["id"]
    if profile["id"] not in (challenge["creator_id"], challenge.get("opponent_id")):
        await message.answer("❌ Not a participant.", parse_mode=None)
        return

    col = "home_team" if which == "home" else "away_team"
    get_supabase().schema("gaming").table("challenges").update(
        denormalize_challenge({col: team})
    ).eq("id", challenge_id).execute()

    await message.answer(
        f"✅ {which.upper()} team set to {bold(team)}\nMatch: {code(_match_code(challenge))}",
        parse_mode=ParseMode.HTML,
    )


@router.message(Command("match_info"))
async def cmd_match_info(message: types.Message) -> None:
    """Show clear status + next action for a challenge."""
    user = message.from_user
    if user is None or not message.text:
        return
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Usage: /match_info MATCH_CODE", parse_mode=None)
        return
    challenge = await _load_challenge(parts[1].strip())
    if not challenge:
        await message.answer("❌ Challenge not found.", parse_mode=None)
        return
    from gaming.src.bot.utils.flow import report_status

    stake = challenge.get("amount_usdc")
    chain = challenge.get("settlement_chain") or "base"
    await message.answer(
        f"{report_status(challenge)}\n"
        f"Stake: ${stake} · Chain: {chain}",
        parse_mode=ParseMode.HTML,
        reply_markup=back_menu(),
    )
