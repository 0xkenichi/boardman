"""Skill-match notices for the core notifier (CHANNELS_DESIGN §4.3).

Each builder returns a ``Notice``: the free-form body and buttons used inside
the WhatsApp 24 h window (and on any core channel), the template ``params``
used outside it, and ``template_payloads`` aligned with the approved
template's quick-reply buttons (``whatsapp/templates.py``), so a "Lock my
stake" button never carries another action's payload.

Telegram players keep receiving the legacy HTML from ``notify_user``; these
notices travel next to it (``notify_user(..., notice=...)``) and are only used
when the recipient's channel is WhatsApp.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Optional

from gaming.src.channels.core import ids
from gaming.src.channels.core.messages import MENU_ID, Option
from gaming.src.channels.core.notify import Notice


def _code(ch: dict) -> str:
    from gaming.src.channels.core.actions.matches import code_of

    return code_of(ch)


def game_label(game_id: str) -> str:
    try:
        from gaming.src.backend.services.game_catalog import get_game

        g = get_game(game_id) or {}
        return str(g.get("display_name") or game_id or "a match")
    except Exception:
        return game_id or "a match"


def _money(v: Any) -> str:
    try:
        return f"{Decimal(str(v)):,.2f}"
    except Exception:
        return str(v)


def view_id(cid: str) -> str:
    return ids.encode("match", "view", str(cid))


def accept_id(cid: str) -> str:
    return ids.encode("match", "accept", str(cid))


def decline_id(cid: str) -> str:
    return ids.encode("match", "decline", str(cid))


def lock_id(cid: str) -> str:
    return ids.encode("match", "lock", str(cid))


def report_id(cid: str) -> str:
    return ids.encode("report", "start", str(cid))


WALLET_ID = ids.encode("balance", "start")


def _tag(profile: Optional[dict]) -> str:
    return "@" + str((profile or {}).get("gaming_tag") or "player")


def challenge_received(ch: dict, creator: dict) -> Notice:
    cid, code = ch["id"], _code(ch)
    game = game_label(str(ch.get("game") or ""))
    stake = _money(ch.get("amount_usdc"))
    return Notice(
        kind="challenge_received",
        params={"challenger": _tag(creator), "game": game, "stake": stake, "expires_in": "24 hours"},
        text=(f"*Challenge from {_tag(creator)}*\n"
              f"Match `{code}` · {game} · stake *${stake}*\n\n"
              "Both stakes go into escrow; the winner gets the pot. Accept or decline:"),
        options=[Option(accept_id(cid), "Accept"), Option(decline_id(cid), "Decline")],
        template_payloads=[accept_id(cid), decline_id(cid)],
    )


def challenge_answered(ch: dict, who: dict, *, accepted: bool) -> Notice:
    cid, code = ch["id"], _code(ch)
    game = game_label(str(ch.get("game") or ""))
    if accepted:
        text = (f"{_tag(who)} accepted your challenge `{code}`.\n"
                "You lock first, then they do. Tap *Lock my stake*.")
        opts = [Option(lock_id(cid), "Lock my stake"), Option(view_id(cid), "My match")]
    else:
        text = f"{_tag(who)} declined your challenge `{code}`. Nothing was charged."
        opts = [Option(MENU_ID, "Menu")]
    return Notice(
        kind="challenge_answered",
        params={"opponent": _tag(who), "answer": "accepted" if accepted else "declined", "game": game},
        text=text,
        options=opts,
        template_payloads=[view_id(cid)],
    )


def opponent_locked(ch: dict) -> Notice:
    """The creator locked: the opponent's turn."""
    cid, code = ch["id"], _code(ch)
    return Notice(
        kind="stake_locked",
        params={"match_code": code, "what": "your opponent locked their stake, lock yours to start"},
        text=f"Match `{code}`: the challenger locked their stake. Your turn: *Lock my stake*.",
        options=[Option(lock_id(cid), "Lock my stake"), Option(view_id(cid), "My match")],
        template_payloads=[lock_id(cid), report_id(cid)],
    )


def match_ready(ch: dict) -> Notice:
    """Both stakes locked: play, then report."""
    cid, code = ch["id"], _code(ch)
    game = game_label(str(ch.get("game") or ""))
    return Notice(
        kind="match_ready",
        params={"match_code": code, "game": game},
        text=(f"*Both stakes locked* for `{code}` ({game}).\n"
              "Play the match, then tap *Report result* and send a photo of the final screen."),
        options=[Option(report_id(cid), "Report result"), Option(view_id(cid), "My match")],
        template_payloads=[report_id(cid)],
    )


def report_deadline(hours: Optional[float] = None) -> str:
    if hours is None:
        try:
            from gaming.src.backend.services.match_report import NO_SHOW_HOURS

            hours = float(NO_SHOW_HOURS)
        except Exception:
            hours = 6.0
    at = datetime.now(timezone.utc) + timedelta(hours=hours)
    return at.strftime("%d %b %H:%M UTC")


def report_reminder(ch: dict, *, photo_only: bool = False) -> Notice:
    cid, code = ch["id"], _code(ch)
    deadline = report_deadline()
    if photo_only:
        text = f"Please send your final-screen photo for `{code}`. Tap *Report result*."
    else:
        text = (f"Your opponent reported `{code}`. Your turn: tap *Report result* by {deadline}.\n"
                "If you stay silent, their proof can settle the match (no-show).")
    return Notice(
        kind="report_reminder",
        params={"match_code": code, "deadline": deadline},
        text=text,
        options=[Option(report_id(cid), "Report result"), Option(view_id(cid), "My match")],
        template_payloads=[report_id(cid)],
    )


def match_result(ch: dict, *, won: Optional[bool], amount: Any, balance: Any) -> Notice:
    code = _code(ch)
    if won is True:
        outcome, line = "you won", f"*You won* `{code}`. ${_money(amount)} USDC was paid to your play balance."
    elif won is False:
        outcome, line = "you lost", f"You lost `{code}`. GG."
    else:
        outcome, line = "draw, stakes returned", f"`{code}` ended in a draw. Stakes were returned."
    return Notice(
        kind="match_result",
        params={"match_code": code, "outcome": outcome, "amount": _money(amount), "balance": _money(balance)},
        text=f"{line}\nBalance: *${_money(balance)}*",
        options=[Option(WALLET_ID, "Wallet"), Option(MENU_ID, "Menu")],
        template_payloads=[WALLET_ID],
    )


def match_disputed(ch: dict, reason: str = "") -> Notice:
    cid, code = ch["id"], _code(ch)
    extra = f"\n{reason}" if reason else ""
    return Notice(
        kind="match_disputed",
        params={"match_code": code},
        text=(f"*Reports don't match* on `{code}`.{extra}\n"
              "The match is under review; funds stay in escrow until support rules."),
        options=[Option(view_id(cid), "Match status")],
        template_payloads=[view_id(cid)],
    )


def match_refunded(ch: dict, *, reason: str, amount: Any) -> Notice:
    code = _code(ch)
    return Notice(
        kind="match_refunded",
        params={"match_code": code, "reason": reason, "amount": _money(amount)},
        text=f"Match `{code}` was {reason}. ${_money(amount)} USDC went back to your balance.",
        options=[Option(WALLET_ID, "Wallet")],
        template_payloads=[WALLET_ID],
    )
