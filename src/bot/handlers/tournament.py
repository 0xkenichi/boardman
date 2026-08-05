"""
Tournament Mode bot commands (v0).

Ops (admin / @stillkenichi):
  /tcreate [4|8] [entry] [game_id] [title...]
  /tstart CODE
  /tstart CODE force
  /twinner CODE MATCH_KEY @winner_or_profile
  /tcancel CODE [reason]

Players:
  /tlist
  /tjoin CODE
  /tleave CODE
  /tstatus CODE

Money off until TOURNAMENTS_MONEY_LIVE=1.
"""
from __future__ import annotations

import logging
import re
from html import escape

from aiogram import F, Router, types
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from gaming.src.backend.services.safety import is_admin
from gaming.src.backend.services.tournament import (
    TournamentError,
    cancel_tournament,
    create_tournament,
    format_tournament_card,
    get_tournament,
    join_tournament,
    leave_tournament,
    list_tournaments,
    money_live,
    report_match_winner,
    start_tournament,
    tournaments_enabled,
)
from gaming.src.bot.keyboards import main_menu
from gaming.src.bot.utils.db import get_or_create_profile

logger = logging.getLogger(__name__)
router = Router(name="tournament")


def _is_ops(user: types.User | None) -> bool:
    if not user:
        return False
    if is_admin(user.id):
        return True
    if (user.username or "").strip().lower() == "stillkenichi":
        return True
    return False


def _tag_map(profile_ids: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    if not profile_ids:
        return out
    try:
        from backend.supabase_client import get_supabase

        # batch in chunks
        for i in range(0, len(profile_ids), 50):
            chunk = profile_ids[i : i + 50]
            r = (
                get_supabase()
                .table("profiles")
                .select("id,gaming_tag,display_name")
                .in_("id", chunk)
                .execute()
            )
            for row in r.data or []:
                out[row["id"]] = row.get("gaming_tag") or row.get("display_name") or row["id"][:8]
    except Exception:
        logger.exception("[Tournament] tag map failed")
    return out


def _card(t: dict) -> str:
    ids = [e.get("profile_id") for e in (t.get("entries") or []) if e.get("profile_id")]
    for m in t.get("bracket") or []:
        for k in ("player_a", "player_b", "winner_id"):
            if m.get(k):
                ids.append(m[k])
    tags = _tag_map(list({x for x in ids if x}))
    return format_tournament_card(t, tags=tags)


def _disabled_msg() -> str:
    return (
        "🏆 Tournaments are switched off right now "
        "(<code>TOURNAMENTS_ENABLED=0</code>)."
    )


@router.message(Command("tlist"))
@router.message(Command("tournaments"))
async def cmd_tlist(message: types.Message) -> None:
    if not tournaments_enabled():
        await message.answer(_disabled_msg(), parse_mode=ParseMode.HTML, reply_markup=main_menu())
        return
    try:
        rows = list_tournaments(status=None, visibility=None, limit=15)
    except Exception as exc:
        await message.answer(f"❌ {escape(str(exc))}", reply_markup=main_menu())
        return
    open_rows = [r for r in rows if r.get("status") == "open"]
    live_rows = [r for r in rows if r.get("status") == "live"]
    lines = [
        "🏆 <b>Boardman cups</b>",
        f"{'💵 Money LIVE' if money_live() else '🧪 Dry-run seats (no USDC yet)'}",
        "",
    ]
    if not rows:
        lines.append("No cups yet. Ops: <code>/tcreate 8 10 mobile.8_ball_pool</code>")
    else:
        if open_rows:
            lines.append("<b>Open</b>")
            for t in open_rows:
                n = len(t.get("entries") or [])
                lines.append(
                    f"· <code>{t.get('code')}</code> · {n}/{t.get('preset')} · "
                    f"${float(t.get('entry_usdc') or 0):.0f} · {_esc(t.get('game_id'))}"
                )
        if live_rows:
            lines.append("\n<b>Live</b>")
            for t in live_rows:
                lines.append(
                    f"· <code>{t.get('code')}</code> · {_esc(t.get('title'))} · live"
                )
        other = [r for r in rows if r.get("status") not in ("open", "live")]
        if other:
            lines.append("\n<b>Recent</b>")
            for t in other[:5]:
                lines.append(
                    f"· <code>{t.get('code')}</code> · {t.get('status')}"
                )
    lines.append("\nJoin: <code>/tjoin CODE</code> · Status: <code>/tstatus CODE</code>")
    await message.answer("\n".join(lines), parse_mode=ParseMode.HTML, reply_markup=main_menu())


@router.message(Command("tstatus"))
async def cmd_tstatus(message: types.Message) -> None:
    if not tournaments_enabled():
        await message.answer(_disabled_msg(), parse_mode=ParseMode.HTML)
        return
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Usage: /tstatus CODE", reply_markup=main_menu())
        return
    t = get_tournament(parts[1].strip())
    if not t:
        await message.answer("Cup not found.", reply_markup=main_menu())
        return
    await message.answer(_card(t), parse_mode=ParseMode.HTML, reply_markup=main_menu())


@router.message(Command("tjoin"))
async def cmd_tjoin(message: types.Message) -> None:
    if not tournaments_enabled():
        await message.answer(_disabled_msg(), parse_mode=ParseMode.HTML)
        return
    user = message.from_user
    if not user:
        return
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Usage: /tjoin CODE", reply_markup=main_menu())
        return
    profile = await get_or_create_profile(user)
    try:
        t = join_tournament(parts[1].strip(), profile["id"])
    except TournamentError as exc:
        await message.answer(f"❌ {escape(str(exc))}", reply_markup=main_menu())
        return
    except Exception as exc:
        logger.exception("[Tournament] join")
        await message.answer(f"❌ {escape(str(exc))}", reply_markup=main_menu())
        return
    note = ""
    if not money_live():
        note = "\n\n🧪 <i>Dry-run: seat reserved — no USDC locked. " "When we go live, entry will lock on join.</i>"
    await message.answer(
        f"✅ Joined cup <code>{escape(t.get('code') or '')}</code>."
        f"{note}\n\n{_card(t)}",
        parse_mode=ParseMode.HTML,
        reply_markup=main_menu(),
    )


@router.message(Command("tleave"))
async def cmd_tleave(message: types.Message) -> None:
    if not tournaments_enabled():
        await message.answer(_disabled_msg(), parse_mode=ParseMode.HTML)
        return
    user = message.from_user
    if not user:
        return
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Usage: /tleave CODE", reply_markup=main_menu())
        return
    profile = await get_or_create_profile(user)
    try:
        t = leave_tournament(parts[1].strip(), profile["id"])
    except TournamentError as exc:
        await message.answer(f"❌ {escape(str(exc))}", reply_markup=main_menu())
        return
    await message.answer(
        f"Left cup <code>{escape(t.get('code') or '')}</code>.\n\n{_card(t)}",
        parse_mode=ParseMode.HTML,
        reply_markup=main_menu(),
    )


# ── Ops ──────────────────────────────────────────────────────────────────────


@router.message(Command("tcreate"))
async def cmd_tcreate(message: types.Message) -> None:
    """Ops: /tcreate 8 10 mobile.8_ball_pool Friday Night Pool"""
    user = message.from_user
    if not _is_ops(user):
        await message.answer("Ops only — use /tlist to browse cups.", reply_markup=main_menu())
        return
    if not tournaments_enabled():
        await message.answer(_disabled_msg(), parse_mode=ParseMode.HTML)
        return
    # /tcreate [preset] [entry] [game_id] [title...]
    text = (message.text or "").strip()
    parts = text.split(maxsplit=4)
    # parts[0]=/tcreate
    preset = 8
    entry = 10.0
    game_id = "mobile.8_ball_pool"
    title = "Boardman Cup"
    try:
        if len(parts) >= 2:
            preset = int(parts[1])
        if len(parts) >= 3:
            entry = float(parts[2])
        if len(parts) >= 4:
            game_id = parts[3]
        if len(parts) >= 5:
            title = parts[4]
    except ValueError:
        await message.answer(
            "Usage: <code>/tcreate 8 10 mobile.8_ball_pool Friday Night</code>\n"
            "preset: 4 | 8 | 16 · entry USDC · game_id · title",
            parse_mode=ParseMode.HTML,
            reply_markup=main_menu(),
        )
        return

    profile = await get_or_create_profile(user)
    try:
        t = create_tournament(
            host_profile_id=profile["id"],
            game_id=game_id,
            preset=preset,
            entry_usdc=entry,
            title=title,
            visibility="public",
        )
    except TournamentError as exc:
        await message.answer(f"❌ {escape(str(exc))}", reply_markup=main_menu())
        return

    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(
            text="📋 Status", callback_data=f"t:status:{t['code']}"
        )
    )
    await message.answer(
        f"✅ Cup created (money {'LIVE' if money_live() else 'dry-run'}).\n\n{_card(t)}",
        parse_mode=ParseMode.HTML,
        reply_markup=kb.as_markup(),
    )


@router.message(Command("tstart"))
async def cmd_tstart(message: types.Message) -> None:
    user = message.from_user
    if not _is_ops(user):
        await message.answer("Ops only.", reply_markup=main_menu())
        return
    parts = (message.text or "").split()
    if len(parts) < 2:
        await message.answer(
            "Usage: /tstart CODE\nOps force (not full): /tstart CODE force",
            reply_markup=main_menu(),
        )
        return
    code = parts[1]
    force = len(parts) >= 3 and parts[2].lower() == "force"
    try:
        t = start_tournament(code, force=force)
    except TournamentError as exc:
        await message.answer(f"❌ {escape(str(exc))}", reply_markup=main_menu())
        return
    await message.answer(
        f"▶️ Cup <b>LIVE</b>.\n\n{_card(t)}",
        parse_mode=ParseMode.HTML,
        reply_markup=main_menu(),
    )
    # Notify entrants of R1 pairings
    try:
        from gaming.src.bot.utils.notify import notify_user

        for m in t.get("bracket") or []:
            if m.get("status") != "ready" or m.get("round") != 1:
                continue
            for pid in (m.get("player_a"), m.get("player_b")):
                if not pid:
                    continue
                opp = m.get("player_b") if pid == m.get("player_a") else m.get("player_a")
                await notify_user(
                    pid,
                    f"🏆 Cup <code>{escape(t.get('code') or '')}</code> started!\n"
                    f"Round 1 match <code>{escape(m.get('match_key') or '')}</code>\n"
                    f"Play your opponent, then ops set winner with "
                    f"<code>/twinner {escape(t.get('code') or '')} {escape(m.get('match_key') or '')} WINNER</code>",
                )
    except Exception:
        logger.exception("[Tournament] notify R1 failed")


@router.message(Command("twinner"))
async def cmd_twinner(message: types.Message) -> None:
    """Ops: /twinner CODE R1-M0 @tag_or_uuid"""
    user = message.from_user
    if not _is_ops(user):
        await message.answer("Ops only.", reply_markup=main_menu())
        return
    parts = (message.text or "").split(maxsplit=3)
    if len(parts) < 4:
        await message.answer(
            "Usage: <code>/twinner CODE R1-M0 @player</code>",
            parse_mode=ParseMode.HTML,
            reply_markup=main_menu(),
        )
        return
    code, match_key, who = parts[1], parts[2], parts[3].strip()
    t = get_tournament(code)
    if not t:
        await message.answer("Cup not found.", reply_markup=main_menu())
        return
    # resolve who → profile id
    winner_id = await _resolve_player(who, t)
    if not winner_id:
        await message.answer(
            "Could not resolve winner. Use @gaming_tag or profile UUID in the match.",
            reply_markup=main_menu(),
        )
        return
    try:
        t2 = report_match_winner(code, match_key, winner_id)
    except TournamentError as exc:
        await message.answer(f"❌ {escape(str(exc))}", reply_markup=main_menu())
        return
    await message.answer(
        f"✅ Match <code>{escape(match_key)}</code> recorded.\n\n{_card(t2)}",
        parse_mode=ParseMode.HTML,
        reply_markup=main_menu(),
    )


@router.message(Command("tcancel"))
async def cmd_tcancel(message: types.Message) -> None:
    user = message.from_user
    if not _is_ops(user):
        await message.answer("Ops only.", reply_markup=main_menu())
        return
    parts = (message.text or "").split(maxsplit=2)
    if len(parts) < 2:
        await message.answer("Usage: /tcancel CODE [reason]", reply_markup=main_menu())
        return
    reason = parts[2] if len(parts) > 2 else "ops"
    try:
        t = cancel_tournament(parts[1], reason=reason)
    except TournamentError as exc:
        await message.answer(f"❌ {escape(str(exc))}", reply_markup=main_menu())
        return
    await message.answer(
        f"🗑 Cup cancelled.\n\n{_card(t)}",
        parse_mode=ParseMode.HTML,
        reply_markup=main_menu(),
    )


@router.callback_query(F.data.startswith("t:status:"))
async def cb_tstatus(callback: types.CallbackQuery) -> None:
    code = (callback.data or "").split(":")[-1]
    t = get_tournament(code)
    if not t:
        await callback.message.answer("Cup not found.", reply_markup=main_menu())
        return
    await callback.message.answer(_card(t), parse_mode=ParseMode.HTML, reply_markup=main_menu())


async def _resolve_player(who: str, t: dict) -> str | None:
    who = who.strip().lstrip("@")
    # UUID?
    if re.match(
        r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$",
        who,
    ):
        return who
    # match entrants by tag
    from gaming.src.bot.utils.db import get_profile_by_tag

    prof = await get_profile_by_tag(who)
    if prof:
        return prof["id"]
    # partial id in roster
    for e in t.get("entries") or []:
        pid = e.get("profile_id") or ""
        if pid.startswith(who) or who in pid:
            return pid
    return None


def _esc(s) -> str:
    return escape(str(s or ""))
