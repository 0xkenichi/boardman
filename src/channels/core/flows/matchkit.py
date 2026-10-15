"""Helpers shared by the challenge, match and report flows (not a flow)."""
from __future__ import annotations

import asyncio
from typing import Any, Optional

from gaming.src.channels.core import geo, ids
from gaming.src.channels.core.actions import matches as svc
from gaming.src.channels.core.match_notices import game_label
from gaming.src.channels.core.messages import Option


def geo_refused(ctx, money_kind: str) -> bool:
    """Say why and stop when the phone country (WhatsApp) blocks money actions."""
    d = geo.check_money(ctx.principal, money_kind)
    if d is not None:
        ctx.st.clear()
        ctx.say(geo.refusal_text(d))
        return True
    return False


def status_line(ch: dict, pid: str) -> str:
    st = ch.get("status")
    me = svc.role(ch, pid)
    reported_me = _reported(ch, me)
    reported_them = _reported(ch, "opponent" if me == "creator" else "creator")
    if st == "open":
        if me == "creator":
            return "Waiting for your opponent to accept." if ch.get("opponent_id") else \
                "Waiting for someone to accept your invite."
        return "Waiting for you to accept."
    if st == "accepted":
        return "Lock your stake (you lock first)." if me == "creator" else "Waiting for the challenger to lock."
    if st == "creator_locked":
        return "Your turn: lock your stake." if me == "opponent" else "Waiting for your opponent to lock."
    if st in ("locked", "playing", "submitted"):
        if reported_me and not reported_them:
            return "Your report is in. Waiting for your opponent."
        if reported_them and not reported_me:
            return "Your opponent reported. Your turn to report."
        if reported_me and reported_them:
            return "Both reported. Settling once results agree."
        return "Both stakes locked. Play, then report the result."
    if st == "disputed":
        return "Under review by support. Funds stay in escrow."
    return f"Status: {st}."


def _reported(ch: dict, who: Optional[str]) -> bool:
    if who == "creator":
        return ch.get("creator_score") is not None or ch.get("creator_reported_home") is not None
    if who == "opponent":
        return ch.get("opponent_score") is not None or ch.get("opponent_reported_home") is not None
    return False


def reported(ch: dict, pid: str) -> bool:
    return _reported(ch, svc.role(ch, pid))


def summary(ch: dict, pid: str, opponent_tag: str = "") -> str:
    code = svc.code_of(ch)
    game = game_label(str(ch.get("game") or ""))
    amt = f"${float(ch.get('amount_usdc') or 0):,.2f}"
    lines = [f"*Match* `{code}`", f"{game} · stake *{amt}*"]
    if opponent_tag:
        lines.append(f"Against: {opponent_tag}")
    lines += ["", status_line(ch, pid)]
    return "\n".join(lines)


def actions(ctx, ch: dict) -> list[Option]:
    """What this player can do now (re-validated when tapped)."""
    pid = str(ctx.profile_id)
    cid = str(ch["id"])
    st = ch.get("status")
    me = svc.role(ch, pid)
    opts: list[Option] = []
    if st == "open" and me is None and ctx.enabled("match"):
        opts += [Option(ids.encode("match", "accept", cid), "Accept"),
                 Option(ids.encode("match", "decline", cid), "Decline")]
    elif st == "open" and me == "opponent":
        opts += [Option(ids.encode("match", "accept", cid), "Accept"),
                 Option(ids.encode("match", "decline", cid), "Decline")]
    elif st == "open" and me == "creator":
        opts.append(Option(ids.encode("match", "cancel", cid), "Cancel challenge"))
    elif (st == "accepted" and me == "creator") or (st == "creator_locked" and me == "opponent"):
        opts.append(Option(ids.encode("match", "lock", cid), "Lock my stake"))
    elif st in ("locked", "playing", "submitted") and me and ctx.enabled("report"):
        if not reported(ch, pid):
            opts.append(Option(ids.encode("report", "start", cid), "Report result"))
        else:
            opts.append(Option(ids.encode("report", "check", cid), "Check result"))
        opts.append(Option(ids.encode("report", "dispute", cid), "Dispute"))
    elif st == "creator_locked" and me == "creator":
        opts.append(Option(ids.encode("match", "cancel", cid), "Cancel and refund"))
    opts.append(ctx.menu_option())
    return opts


async def load(ref: str) -> Optional[dict]:
    return await asyncio.to_thread(svc.load, ref)


async def profile_tag(profile_id: Optional[str]) -> str:
    if not profile_id:
        return ""

    def _get() -> str:
        try:
            from gaming.src.channels.core.identity.repo import get_repo

            prof = get_repo().get_profile(str(profile_id)) or {}
            tag = prof.get("gaming_tag") or ""
            return f"@{tag}" if tag else ""
        except Exception:
            return ""

    return await asyncio.to_thread(_get)


async def notify_legacy(profile_id: str, html: str, notice: Any, *, tg_buttons: Any = None) -> None:
    """Tell the other player on their channel: the notice for WhatsApp players,
    Telegram's own HTML (and legacy buttons) for everyone else."""
    from gaming.src.bot.utils.notify import notify_user

    try:
        await notify_user(profile_id, html, buttons=tg_buttons, notice=notice)
    except Exception:
        import logging

        logging.getLogger(__name__).warning("[channels] notice to other player failed", exc_info=True)


def tg_match_menu(ch: dict, profile_id: str):
    try:
        from gaming.src.bot.keyboards import match_actions_menu

        return match_actions_menu(ch, profile_id)
    except Exception:
        return None


def tg_accept_menu(cid: str):
    try:
        from gaming.src.bot.keyboards import challenge_confirm_menu

        return challenge_confirm_menu(cid)
    except Exception:
        return None
