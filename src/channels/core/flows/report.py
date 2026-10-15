"""Report a result (Telegram flow 11), one question per message.

photo → (in-game name, for win/lose games) → side (scoreline games) →
outcome (I won / I lost, or a typed score) → confirm → ``matches.submit_report``
→ settlement. The photo arrives already copied to our storage
(``evidence://…``, ``whatsapp/media.py``): Meta's media URLs expire in
minutes. The interview rules are Telegram's (``report_interview``), and the
AI check is the settlement's own ``verify_with_ai_vision``, which reads the
stored evidence. Conflicting reports go to the existing dispute path.
"""
from __future__ import annotations

import asyncio
import logging
import re

from gaming.src.channels.core import ids, match_notices
from gaming.src.channels.core.actions import matches as svc
from gaming.src.channels.core.flows import matchkit as mk
from gaming.src.channels.core.messages import Option

logger = logging.getLogger(__name__)

NAME = "report"
KEYWORDS = ("report",)
LIVE = ("locked", "playing", "submitted")


def _ri():
    from gaming.src.bot.utils import report_interview

    return report_interview


async def start(ctx, ref: str = "") -> None:
    """Without a match id: the one match that is waiting for this player's report."""
    if not ref:
        rows = await asyncio.to_thread(svc.list_mine, str(ctx.profile_id))
        live = [c for c in rows if c.get("status") in LIVE and not mk.reported(c, str(ctx.profile_id))]
        if not live:
            ctx.choose("No match is waiting for your result.", [ctx.menu_option()])
            return
        ref = str(live[0]["id"])
    await _begin(ctx, ref)


async def _begin(ctx, ref: str, evidence: str = "", caption: str = "") -> None:
    ch = await mk.load(ref)
    pid = str(ctx.profile_id)
    if not ch or svc.role(ch, pid) is None:
        ctx.say("Match not found.")
        return
    if ch.get("status") not in LIVE:
        ctx.choose(f"Results can be reported once both stakes are locked.\n{mk.status_line(ch, pid)}",
                   mk.actions(ctx, ch))
        return
    if mk.reported(ch, pid):
        ctx.choose("Your report is already in.", mk.actions(ctx, ch))
        return
    ctx.st.set(NAME, "photo", cid=str(ch["id"]))
    if evidence:
        await _got_photo(ctx, evidence, caption)
        return
    from gaming.src.backend.services.game_catalog import get_game

    screen = str((get_game(str(ch.get("game") or "")) or {}).get("result_screen") or "the final result screen")
    ctx.ask_media(
        f"*Report* `{svc.code_of(ch)}`\nSend a photo or screenshot of {screen}. "
        "We keep it privately as evidence for a fair ruling."
    )


async def on_button(ctx, act: str, arg: str) -> None:
    if act == "start":
        await start(ctx, arg)
    elif act == "side":
        await _side(ctx, arg)
    elif act == "out":
        await _outcome(ctx, arg)
    elif act == "go":
        await _submit(ctx)
    elif act == "check":
        await _check(ctx, arg)
    elif act == "dispute":
        await _dispute_ask(ctx, arg)
    elif act == "dispok":
        await _dispute(ctx, arg)
    else:
        await start(ctx)


async def on_media(ctx, media) -> None:
    if ctx.st.flow == NAME and ctx.st.step == "photo" and ctx.st.data.get("cid"):
        await _got_photo(ctx, media.ref, media.caption)
        return
    await bare_photo(ctx, media)


async def bare_photo(ctx, media) -> None:
    """A photo outside the interview: report it for the match that needs one."""
    rows = await asyncio.to_thread(svc.list_mine, str(ctx.profile_id))
    live = [c for c in rows if c.get("status") in LIVE and not mk.reported(c, str(ctx.profile_id))]
    if not live:
        ctx.say("Thanks. Photos are for match reports, and none of your matches is waiting for one.")
        return
    await _begin(ctx, str(live[0]["id"]), evidence=media.ref, caption=media.caption)


async def on_text(ctx, text: str) -> None:
    step = ctx.st.step
    if step == "photo":
        ctx.say("Please send a *photo* of the final screen (tap the clip or camera icon).")
    elif step == "name":
        await _name(ctx, text)
    elif step == "score":
        home, away = _ri().parse_score_message(text)
        if home is None:
            ctx.say("Type the score as HOME-AWAY, like *2-1*.")
            return
        ctx.st.data.update(home=home, away=away, binary_won=None)
        await _advance(ctx)
    else:
        ctx.say("Use the buttons above, or send *cancel*.")


async def _got_photo(ctx, ref: str, caption: str = "") -> None:
    if not ref:
        ctx.say("That photo could not be saved. Please send it again.")
        return
    ch = await mk.load(ctx.st.data["cid"])
    if not ch:
        ctx.st.clear()
        ctx.say("Match not found.")
        return
    from gaming.src.backend.services.game_catalog import parse_result_caption

    ri = _ri()
    pid = str(ctx.profile_id)
    home = away = binary_won = None
    cap = (caption or "").strip()
    if cap:
        home, away, _ = parse_result_caption(ri.game_id_of(ch), cap, side=ri.my_side(ch, pid),
                                             is_creator=ri.is_creator(ch, pid))
        tok = cap.split()[0].lower()
        binary_won = True if tok in ("w", "win", "won") else False if tok in ("l", "lost", "lose", "loss") else None
    ctx.st.data.update(evidence=ref, home=home, away=away, binary_won=binary_won, screen_name="")
    ctx.say("Photo saved.")
    await _advance(ctx)


async def _advance(ctx) -> None:
    from gaming.src.backend.services.game_catalog import is_binary_outcome

    ri = _ri()
    d = ctx.st.data
    ch = await mk.load(d.get("cid") or "")
    if not ch:
        ctx.st.clear()
        ctx.say("Match not found.")
        return
    pid = str(ctx.profile_id)
    cid = str(ch["id"])
    home, away, won = d.get("home"), d.get("away"), d.get("binary_won")
    if won is not None and (home is None or away is None):
        try:
            home, away = ri.resolve_home_away(ch, pid, binary_won=won, home=home, away=away)
            d.update(home=home, away=away)
        except Exception:
            pass
    miss = ri.missing_for_ruling(ch, pid, has_photo=True, home=home, away=away, binary_won=won,
                                 screen_name=str(d.get("screen_name") or ""))
    if "name" in miss:
        ctx.st.step = "name"
        ctx.say("Type your in-game name exactly as it shows on the screenshot.")
        return
    if "side" in miss:
        ctx.st.step = "side"
        ctx.choose("Were you HOME or AWAY on the scoreboard?",
                   [Option(ids.encode(NAME, "side", "home"), "I was HOME"),
                    Option(ids.encode(NAME, "side", "away"), "I was AWAY")])
        return
    if "outcome" in miss:
        if is_binary_outcome(ri.game_id_of(ch)):
            ctx.st.step = "outcome"
            ctx.choose("Did you win?", [Option(ids.encode(NAME, "out", "W"), "I won"),
                                        Option(ids.encode(NAME, "out", "L"), "I lost")])
        else:
            ctx.st.step = "score"
            ctx.say("Type the final score as HOME-AWAY, like *2-1*.")
        return
    try:
        home, away = ri.resolve_home_away(ch, pid, binary_won=won, home=home, away=away)
    except ValueError as exc:
        ctx.say(str(exc))
        return
    d.update(home=home, away=away)
    ctx.st.step = "confirm"
    claim = ("You won" if won else "You lost") if won is not None else f"Score {home}-{away} (home-away)"
    name = f"\nIn-game name: {d['screen_name']}" if d.get("screen_name") else ""
    ctx.choose(
        f"*Confirm your report* for `{svc.code_of(ch)}`\n{claim}{name}\nPhoto attached.\n\n"
        "We only pay out when both reports agree; otherwise support reviews the photos.",
        [Option(ids.encode(NAME, "go"), "Submit"), Option(ids.encode(NAME, "start", cid), "Start over"),
         ctx.menu_option("Cancel")],
    )


async def _name(ctx, text: str) -> None:
    name = (text or "").strip()
    if not 2 <= len(name) <= 48 or re.fullmatch(r"\d+\s*[-:]\s*\d+", name) or name.upper() in ("W", "L"):
        ctx.say("Type your in-game name exactly as on the screenshot (2 to 48 characters), like *Finch*.")
        return
    ch = await mk.load(ctx.st.data.get("cid") or "")
    if not ch:
        ctx.st.clear()
        ctx.say("Match not found.")
        return
    try:
        await asyncio.to_thread(svc.save_ingame_name, ch, str(ctx.profile_id), name)
    except svc.MatchRefused as exc:
        ctx.say(exc.message)
        return
    ctx.st.data["screen_name"] = name
    await _advance(ctx)


async def _side(ctx, side: str) -> None:
    ch = await mk.load(ctx.st.data.get("cid") or "")
    if ctx.st.flow != NAME or not ch:
        ctx.say("That report has expired. Tap *Report result* again.")
        return
    try:
        await asyncio.to_thread(svc.choose_side, ch, str(ctx.profile_id), side)
    except svc.MatchRefused as exc:
        ctx.say(exc.message)
        return
    await _advance(ctx)


async def _outcome(ctx, claim: str) -> None:
    if ctx.st.flow != NAME or not ctx.st.data.get("cid") or claim not in ("W", "L"):
        ctx.say("That report has expired. Tap *Report result* again.")
        return
    ctx.st.data.update(binary_won=claim == "W", home=None, away=None)
    await _advance(ctx)


async def _submit(ctx) -> None:
    d = ctx.st.data
    if ctx.st.flow != NAME or ctx.st.step != "confirm" or d.get("home") is None or not d.get("evidence"):
        ctx.say("That report was already sent or has expired.")
        return
    pid = str(ctx.profile_id)
    try:
        out = await svc.submit_report(d["cid"], pid, home=int(d["home"]), away=int(d["away"]),
                                      evidence_ref=str(d["evidence"]),
                                      screen_name=str(d.get("screen_name") or ""))
    except svc.MatchRefused as exc:
        ctx.st.clear()
        ctx.choose(exc.message, [ctx.menu_option()])
        return
    ctx.st.clear()
    ch = out.challenge
    cid = str(ch["id"])
    lines = [f"*Report submitted* for `{svc.code_of(ch)}`."]
    if out.fairness_hold:
        lines.append(f"Fairness hold: {out.fairness_hold} Support will review both photos; "
                     "no payout until it's clear.")
    other = svc.other_party(ch, pid)
    if other and not mk.reported(ch, other):
        await mk.notify_legacy(
            other,
            f"📊 Opponent reported on <code>{svc.code_of(ch)}</code>.\nYour turn: My match → report button.",
            match_notices.report_reminder(ch),
            tg_buttons=mk.tg_match_menu(ch, other),
        )
    res = await svc.settle(cid)
    action = res.get("action")
    if action == "resolved":
        lines.append("Settled. The result is on its way.")
    elif action in ("disputed", "disputed_no_show"):
        lines.append("The reports don't match, so support will review. Funds stay in escrow.")
    elif action in ("waiting_reports",):
        lines.append("Waiting for your opponent's report. If they stay silent, your proof can settle it.")
    else:
        lines.append("We'll settle as soon as the checks finish and message you.")
    ctx.choose("\n".join(lines), [Option(ids.encode("match", "view", cid), "My match"), ctx.menu_option()])


async def _check(ctx, ref: str) -> None:
    ch = await mk.load(ref)
    if not ch or svc.role(ch, str(ctx.profile_id)) is None:
        ctx.say("Match not found.")
        return
    res = await svc.settle(str(ch["id"]))
    ch = await mk.load(str(ch["id"])) or ch
    reason = f" ({res.get('reason')})" if res.get("reason") and res.get("action") != "resolved" else ""
    ctx.choose(f"Settlement check: {res.get('action')}{reason}\n\n{mk.status_line(ch, str(ctx.profile_id))}",
               mk.actions(ctx, ch))


async def _dispute_ask(ctx, ref: str) -> None:
    ch = await mk.load(ref)
    if not ch or svc.role(ch, str(ctx.profile_id)) is None:
        ctx.say("Match not found.")
        return
    ctx.choose(
        f"Open a dispute on `{svc.code_of(ch)}`? Support reviews both reports and photos; "
        "the stakes stay in escrow until they rule.",
        [Option(ids.encode(NAME, "dispok", str(ch["id"])), "Open dispute"), ctx.menu_option("Back")],
    )


async def _dispute(ctx, ref: str) -> None:
    pid = str(ctx.profile_id)
    reason = f"Player disputed via {ctx.channel}"
    try:
        ch, already = await svc.open_dispute(ref, pid, reason)
    except svc.MatchRefused as exc:
        ctx.choose(exc.message, [ctx.menu_option()])
        return
    code = svc.code_of(ch)
    if already:
        ctx.choose(f"Match `{code}` is already under review.\nSupport ID: `{ch['id']}`", [ctx.menu_option()])
        return
    ctx.choose(f"Dispute opened for `{code}`. Support will review and message you.\n"
               f"Support ID (only if they ask): `{ch['id']}`", [ctx.menu_option()])
    other = svc.other_party(ch, pid)
    if other:
        from gaming.src.backend.services.match_codes import format_dispute_copy

        await mk.notify_legacy(other, format_dispute_copy(ch, reason, for_opponent=True),
                               match_notices.match_disputed(ch, "Your opponent opened a dispute."))
    from gaming.src.channels.core.actions.deposit import alert_admins

    await alert_admins(f"⚠️ Dispute opened on {code} via {ctx.channel}\nSupport ID: {ch['id']}")
