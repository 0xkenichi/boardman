"""My matches, accept/decline, lock stake, cancel (Telegram flows 8–10, 13).

Locking moves money, so "Lock my stake" first sends a nonce-bound Yes/No
prompt (``approvals``); only the matching "Yes" calls
``matches.lock_stake`` (the same code as Telegram's button). Every action
reloads the match and re-checks who may do what: old buttons stay tappable.
"""
from __future__ import annotations

import asyncio
import logging
from decimal import Decimal

from gaming.src.channels.core import approvals, ids, match_notices
from gaming.src.channels.core.actions import matches as svc
from gaming.src.channels.core.flows import matchkit as mk
from gaming.src.channels.core.messages import Choice, Option

logger = logging.getLogger(__name__)

NAME = "match"
KEYWORDS = ("matches", "match", "status")


async def start(ctx) -> None:
    ctx.st.clear()
    rows = await asyncio.to_thread(svc.list_mine, str(ctx.profile_id))
    if not rows:
        opts = [Option(ids.encode("challenge", "start"), "New challenge")] if ctx.enabled("challenge") else []
        ctx.choose("No open matches.", opts + [ctx.menu_option()])
        return
    if len(rows) == 1:
        await view(ctx, str(rows[0]["id"]))
        return
    opts = []
    for ch in rows:
        amt = f"${float(ch.get('amount_usdc') or 0):,.0f}"
        opts.append(Option(ids.encode(NAME, "view", str(ch["id"])), f"{svc.code_of(ch)} · {amt}",
                           mk.status_line(ch, str(ctx.profile_id))))
    ctx.choose("*My matches*", opts + [ctx.menu_option()], button_label="Matches")


async def on_button(ctx, act: str, arg: str) -> None:
    handlers = {
        "view": view, "accept": accept, "decline": decline, "lock": lock, "cancel": cancel,
    }
    fn = handlers.get(act)
    if fn is None or not arg:
        await start(ctx)
        return
    await fn(ctx, arg)


async def view(ctx, ref: str) -> None:
    ch = await mk.load(ref)
    pid = str(ctx.profile_id)
    if not ch or (svc.role(ch, pid) is None and not _joinable(ch)):
        ctx.say("Match not found.")
        await start(ctx)
        return
    other = svc.other_party(ch, pid) if svc.role(ch, pid) else ch.get("creator_id")
    tag = await mk.profile_tag(other)
    ctx.choose(mk.summary(ch, pid, tag), mk.actions(ctx, ch))


def _joinable(ch: dict) -> bool:
    return ch.get("status") == "open" and not ch.get("opponent_id")


async def join(ctx, code: str) -> None:
    """``JOIN <code>``: the WhatsApp equivalent of Telegram's ``/start m_<code>``."""
    ch = await mk.load(code)
    pid = str(ctx.profile_id)
    if not ch or ch.get("status") != "open":
        ctx.choose("That challenge is no longer open.", [ctx.menu_option()])
        return
    if svc.role(ch, pid) == "creator":
        ctx.say("That's your own challenge. Share the invite with a friend.")
        await view(ctx, str(ch["id"]))
        return
    if ch.get("opponent_id") and svc.role(ch, pid) is None:
        ctx.choose("That challenge was sent to someone else.", [ctx.menu_option()])
        return
    tag = await mk.profile_tag(ch.get("creator_id"))
    game = match_notices.game_label(str(ch.get("game") or ""))
    amt = Decimal(str(ch.get("amount_usdc") or 0))
    ctx.choose(
        f"*Challenge from {tag or 'a player'}*\nMatch `{svc.code_of(ch)}` · {game} · stake *${amt:,.2f}*\n\n"
        "If you accept, you both lock this stake in escrow and the winner takes the pot.",
        [Option(ids.encode(NAME, "accept", str(ch["id"])), "Accept"),
         Option(ids.encode(NAME, "decline", str(ch["id"])), "Decline"),
         ctx.menu_option()],
    )


async def accept(ctx, ref: str) -> None:
    if mk.geo_refused(ctx, "stake"):
        return
    me = {**(ctx.principal.profile or {}), "id": ctx.profile_id}
    try:
        ch = await svc.accept_challenge(ref, me)
    except svc.MatchRefused as exc:
        opts = [ctx.menu_option()]
        if exc.kind == "funds" and ctx.enabled("deposit"):
            opts.insert(0, Option(ids.encode("deposit", "start"), "Add money"))
        if exc.kind == "busy":
            opts.insert(0, Option(ids.encode(NAME, "start"), "My matches"))
        ctx.choose(exc.message, opts)
        return
    tag = await mk.profile_tag(ch["creator_id"])
    ctx.choose(
        f"Accepted. Match `{svc.code_of(ch)}`.\n{tag or 'The challenger'} locks first, then you. "
        "We'll message you when it's your turn.",
        [Option(ids.encode(NAME, "view", str(ch["id"])), "My match"), ctx.menu_option()],
    )
    await mk.notify_legacy(
        str(ch["creator_id"]),
        f"🎮 Accepted by @{me.get('gaming_tag') or 'player'}.\nTap <b>My match</b> → <b>Lock my stake</b> first.",
        match_notices.challenge_answered(ch, me, accepted=True),
        tg_buttons=mk.tg_match_menu(ch, str(ch["creator_id"])),
    )


async def decline(ctx, ref: str) -> None:
    me = {**(ctx.principal.profile or {}), "id": ctx.profile_id}
    try:
        ch = await svc.decline_challenge(ref, me)
    except svc.MatchRefused as exc:
        ctx.choose(exc.message, [ctx.menu_option()])
        return
    ctx.choose("Declined. Nothing was charged.", [ctx.menu_option()])
    await mk.notify_legacy(
        str(ch["creator_id"]),
        f"🚫 <code>{me.get('gaming_tag') or 'opponent'}</code> declined your challenge "
        f"<code>{svc.code_of(ch)}</code>.",
        match_notices.challenge_answered(ch, me, accepted=False),
    )


def _lock_problem(ch: dict, pid: str):
    who = svc.role(ch, pid)
    if who is None:
        return "Not your match."
    st = ch.get("status")
    if who == "creator":
        if ch.get("creator_lock_tx_id") or st in ("creator_locked", "locked", "playing", "submitted"):
            return "You already locked your stake."
        if st != "accepted":
            return "Wait until your opponent accepts, then lock."
        return None
    if ch.get("opponent_lock_tx_id") or st in ("locked", "playing", "submitted"):
        return "You already locked your stake."
    if st != "creator_locked":
        return "Wait for the challenger to lock first. We'll message you."
    return None


async def lock(ctx, ref: str) -> None:
    """Step 1: the approval prompt (no money moves here)."""
    ch = await mk.load(ref)
    pid = str(ctx.profile_id)
    if not ch:
        ctx.say("Match not found.")
        return
    problem = _lock_problem(ch, pid)
    if problem:
        ctx.choose(problem, mk.actions(ctx, ch))
        return
    if mk.geo_refused(ctx, "lock"):
        return
    amount = Decimal(str(ch["amount_usdc"]))
    nonce = await asyncio.to_thread(
        approvals.issue, ctx.principal, "lock", {"challenge_id": str(ch["id"]), "amount": str(amount)}
    )
    minutes = approvals.ttl_ms() // 60000
    ctx.out.append(Choice(
        f"*Lock ${amount:,.2f} USDC?*\nIt moves from your play balance into escrow for match "
        f"`{svc.code_of(ch)}` until the result is in. This request expires in {minutes} minutes.",
        [Option(ids.encode("ap", "y", nonce), "Yes, lock it"), Option(ids.encode("ap", "n", nonce), "No")],
        bind=nonce,
    ))


async def do_lock(ctx, payload: dict) -> None:
    """Step 2, after an approved prompt: the real escrow lock."""
    cid = str(payload.get("challenge_id") or "")
    ch = await mk.load(cid)
    if not ch:
        ctx.say("Match not found.")
        return
    if Decimal(str(ch.get("amount_usdc"))) != Decimal(str(payload.get("amount"))):
        ctx.say("This match changed since you were asked. Nothing was locked.")
        return
    problem = _lock_problem(ch, str(ctx.profile_id))
    if problem:
        ctx.choose(problem, mk.actions(ctx, ch))
        return
    if mk.geo_refused(ctx, "lock"):
        return
    me = {**(ctx.principal.profile or {}), "id": ctx.profile_id}
    try:
        res = await svc.lock_stake(cid, me)
    except svc.MatchRefused as exc:
        opts = [ctx.menu_option()]
        if exc.kind == "funds" and ctx.enabled("deposit"):
            opts.insert(0, Option(ids.encode("deposit", "start"), "Add money"))
        ctx.choose(exc.message, opts)
        return
    ch2 = res.challenge
    code = svc.code_of(ch2)
    if res.both_locked:
        ctx.choose(
            f"*Both stakes locked* for `{code}`.\nPlay the match, then tap *Report result* and send "
            "a photo of the final screen.",
            [Option(ids.encode("report", "start", str(ch2["id"])), "Report result"), ctx.menu_option()],
        )
        await mk.notify_legacy(
            str(ch2["creator_id"]),
            "🎮 Both stakes locked!\n\nPlay the match, then <b>Submit result</b> with a photo.",
            match_notices.match_ready(ch2),
            tg_buttons=mk.tg_match_menu(ch2, str(ch2["creator_id"])),
        )
        return
    ctx.choose(f"Stake locked. Waiting for your opponent to lock on `{code}`; we'll message you.",
               [Option(ids.encode(NAME, "view", str(ch2["id"])), "My match"), ctx.menu_option()])
    if ch2.get("opponent_id"):
        await mk.notify_legacy(
            str(ch2["opponent_id"]),
            f"🔐 Challenger locked their stake on <code>{code}</code>.\nYour turn: <b>Lock my stake</b>.",
            match_notices.opponent_locked(ch2),
            tg_buttons=mk.tg_match_menu(ch2, str(ch2["opponent_id"])),
        )


async def cancel(ctx, ref: str) -> None:
    from gaming.src.backend.services.rematch_cancel import execute_cancel

    ch = await mk.load(ref)
    pid = str(ctx.profile_id)
    if not ch or svc.role(ch, pid) is None:
        ctx.say("Match not found.")
        return
    try:
        res = await execute_cancel(pid, str(ch["id"]))
    except Exception as exc:
        ctx.choose(f"Could not cancel: {exc}", [ctx.menu_option()])
        return
    ctx.choose(str(res.get("message") or res.get("reason") or "Done."), [ctx.menu_option()])
    other = svc.other_party(ch, pid)
    if other and res.get("success"):
        await mk.notify_legacy(other, f"Match <code>{svc.code_of(ch)}</code>: {res.get('message') or 'cancelled'}",
                               None)
