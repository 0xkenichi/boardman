"""Challenge a friend (Telegram flow 7, redesigned for 3 buttons / 10 rows).

game category → game (paged list) → stake (presets or typed) → opponent
(@tag, a WhatsApp number of a Boardman player, or an invite link anyone can
accept) → confirm → ``matches.create_challenge``. An invite has no
opponent: the creator shares ``wa.me/<number>?text=JOIN <code>`` (and the
web and Telegram links) instead of us messaging someone who never opted in.
"""
from __future__ import annotations

import asyncio
import re
from decimal import Decimal, InvalidOperation
from urllib.parse import quote

from gaming.src.channels import config
from gaming.src.channels.core import ids, match_notices
from gaming.src.channels.core.actions import matches as svc
from gaming.src.channels.core.flows import matchkit as mk
from gaming.src.channels.core.messages import Option

NAME = "challenge"
KEYWORDS = ("challenge", "play")

_PHONE = re.compile(r"^\+?[\d\s\-()]{8,20}$")


def _clean(label: str) -> str:
    return re.sub(r"^[^\w]+", "", label or "").strip() or label


def stake_range() -> tuple[Decimal, Decimal, bool]:
    """(min, max, real?) for a new challenge: real-money matches use the
    lower real-money cap (services/stake_caps.py)."""
    from gaming.src.backend.services import stake_caps
    from gaming.src.backend.services.realms import is_real_chain, new_challenge_chain
    from gaming.src.backend.services.safety import MAX_STAKE_USDC, MIN_STAKE_USDC

    real = is_real_chain(new_challenge_chain())
    hi = min(MAX_STAKE_USDC, stake_caps.max_stake_usdc()) if real else MAX_STAKE_USDC
    return MIN_STAKE_USDC, hi, real


def presets() -> list[Decimal]:
    lo, hi, _real = stake_range()
    out = [Decimal(p) for p in (2, 5, 10, 25) if lo <= Decimal(p) <= hi]
    return out[:3] or [lo]


def money_note(real: bool) -> str:
    if not real:
        return "Practice chips (no cash value)."
    from gaming.src.backend.services import stake_caps

    return f"*Real money* (USDC). {stake_caps.limits_text()}"


async def start(ctx) -> None:
    ctx.st.clear()
    if mk.geo_refused(ctx, "stake"):
        return
    from gaming.src.backend.services.play_points import assert_can_start_or_accept
    from gaming.src.backend.services.safety import is_paused, pause_message

    if is_paused():
        ctx.say(svc.plain(pause_message()))
        return
    if await asyncio.to_thread(assert_can_start_or_accept, str(ctx.profile_id)):
        opts = [Option(ids.encode("match", "start"), "My matches")] if ctx.enabled("match") else []
        ctx.choose("You already have an open match. Finish it first: one match at a time.",
                   opts + [ctx.menu_option()])
        return
    from gaming.src.backend.services.game_catalog import list_categories

    ctx.st.set(NAME, "category")
    opts = [Option(ids.encode(NAME, "cat", c["id"]), _clean(c["label"])) for c in list_categories()]
    ctx.choose("*New challenge*\nWhere do you play?", opts + [ctx.menu_option("Cancel")],
               button_label="Pick")


async def on_button(ctx, act: str, arg: str) -> None:
    if act == "start":
        await start(ctx)
    elif act == "cat":
        await _games(ctx, arg)
    elif act == "game":
        await _game(ctx, arg)
    elif act == "amt":
        await _amount(ctx, arg)
    elif act == "opp":
        await _opponent_mode(ctx, arg)
    elif act == "send":
        await _send(ctx)
    else:
        await start(ctx)


async def on_text(ctx, text: str) -> None:
    step = ctx.st.step
    if step == "stake":
        await _amount(ctx, text)
    elif step in ("opponent", "tag", "phone"):
        await _opponent_text(ctx, text)
    else:
        ctx.say("Use the options above, or send *cancel*.")


async def _games(ctx, category: str) -> None:
    from gaming.src.backend.services.game_catalog import list_games

    games = [g for g in list_games(category=category) if "|" not in g["game_id"]]
    opts = []
    for g in games:
        try:
            gid = ids.encode(NAME, "game", g["game_id"])
        except ValueError:
            continue
        desc = "Win/lose" if str(g.get("outcome_type") or "").startswith("binary") else "Scoreline"
        opts.append(Option(gid, _clean(str(g.get("display_name") or g["game_id"])), desc))
    if not opts:
        ctx.say("No games in that category right now.")
        await start(ctx)
        return
    ctx.st.set(NAME, "game", category=category)
    ctx.choose("Pick the game:", opts, button_label="Games")


async def _game(ctx, game_id: str) -> None:
    from gaming.src.backend.services.game_catalog import get_game

    g = get_game(game_id)
    if not g or not g.get("enabled", True):
        ctx.say("That game is not available.")
        await start(ctx)
        return
    lo, hi, real = stake_range()
    ctx.st.set(NAME, "stake", game=g["game_id"])
    opts = [Option(ids.encode(NAME, "amt", str(p)), f"${p:,.0f}") for p in presets()]
    ctx.choose(
        f"*{match_notices.game_label(g['game_id'])}*\nHow much USDC each? "
        f"Pick one or type an amount (${lo:,.0f} to ${hi:,.0f}).\n{money_note(real)}",
        opts,
    )


async def _amount(ctx, raw: str) -> None:
    from gaming.src.backend.services import stake_caps
    from gaming.src.backend.services.realms import new_challenge_chain
    from gaming.src.backend.services.safety import validate_stake

    if not ctx.st.data.get("game"):
        await start(ctx)
        return
    try:
        amount = Decimal((raw or "").strip().lstrip("$").replace(",", "")).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        ctx.say("Send the stake as a number, like 5.")
        return
    err = validate_stake(amount)
    if err:
        ctx.say(svc.plain(err).lstrip("❌ ").strip())
        return
    capped = await asyncio.to_thread(stake_caps.check, str(ctx.profile_id), new_challenge_chain(), amount)
    if capped:
        ctx.say(capped)
        return
    ctx.st.set(NAME, "opponent", game=ctx.st.data["game"], amount=str(amount))
    ctx.choose(
        f"Stake: *${amount:,.2f}* each.\nWho are you playing? Send their tag (like @ada) "
        "or their WhatsApp number, or make an invite link to share.",
        [Option(ids.encode(NAME, "opp", "tag"), "By @tag"),
         Option(ids.encode(NAME, "opp", "phone"), "By phone number"),
         Option(ids.encode(NAME, "opp", "link"), "Invite link")],
    )


async def _opponent_mode(ctx, mode: str) -> None:
    d = ctx.st.data
    if not d.get("amount"):
        await start(ctx)
        return
    if mode == "tag":
        ctx.st.set(NAME, "tag", game=d["game"], amount=d["amount"])
        ctx.say("Send their Boardman tag, like *@ada*.")
    elif mode == "phone":
        ctx.st.set(NAME, "phone", game=d["game"], amount=d["amount"])
        ctx.say("Send their WhatsApp number with the country code, like *+234 801 234 5678*.")
    else:
        await _confirm(ctx, None)


async def _opponent_text(ctx, text: str) -> None:
    raw = (text or "").strip()
    step = ctx.st.step
    opp = None
    if raw.startswith("@") or (step == "tag" and not _PHONE.match(raw)):
        from gaming.src.bot.utils.db import _get_profile_by_tag_sync

        tag = raw.lstrip("@").strip()
        opp = await asyncio.to_thread(_get_profile_by_tag_sync, tag) if tag else None
        if not opp:
            ctx.choose(f"No player called @{tag or '?'}. Check the tag, or send them an invite link.",
                       [Option(ids.encode(NAME, "opp", "link"), "Invite link"), ctx.menu_option("Cancel")])
            return
    elif _PHONE.match(raw):
        opp = await asyncio.to_thread(_by_phone, raw)
        if not opp:
            ctx.choose("No Boardman player uses that number yet. Send them an invite link instead.",
                       [Option(ids.encode(NAME, "opp", "link"), "Invite link"), ctx.menu_option("Cancel")])
            return
    else:
        ctx.say("Send a tag like *@ada* or a number like *+234 801 234 5678*.")
        return
    if str(opp.get("id")) == str(ctx.profile_id):
        ctx.say("You can't challenge yourself. Send someone else's tag or number.")
        return
    await _confirm(ctx, opp)


def _by_phone(raw: str):
    from gaming.src.channels.core.identity.repo import get_repo

    digits = "".join(c for c in raw if c.isdigit())
    repo = get_repo()
    ident = repo.get("whatsapp", digits)
    if ident is None:
        return None
    prof = repo.get_profile(ident.profile_id) or {}
    return {**prof, "id": ident.profile_id}


async def _confirm(ctx, opp) -> None:
    d = ctx.st.data
    amount = Decimal(d["amount"])
    who = f"@{opp.get('gaming_tag')}" if opp else "anyone you send your invite link to"
    ctx.st.set(NAME, "confirm", game=d["game"], amount=d["amount"],
               opponent_id=str(opp["id"]) if opp else None,
               opponent_tag=str(opp.get("gaming_tag") or "") if opp else "")
    _lo, _hi, real = stake_range()
    ctx.choose(
        f"*Confirm challenge*\nGame: {match_notices.game_label(d['game'])}\nStake: *${amount:,.2f}* each\n"
        f"Opponent: {who}\n{money_note(real)}\n\nWhen they accept, you both lock your stakes in escrow. Send it?",
        [Option(ids.encode(NAME, "send"), "Send it"), ctx.menu_option("Cancel")],
    )


async def _send(ctx) -> None:
    d = ctx.st.data
    if ctx.st.step != "confirm" or not d.get("amount"):
        ctx.say("That challenge was already sent or has expired.")
        await start(ctx)
        return
    if mk.geo_refused(ctx, "stake"):
        return
    opp = None
    if d.get("opponent_id"):
        opp = {"id": d["opponent_id"], "gaming_tag": d.get("opponent_tag") or "player"}
    creator = {**(ctx.principal.profile or {}), "id": ctx.profile_id}
    try:
        ch = await svc.create_challenge(svc.Draft(creator, Decimal(d["amount"]), d["game"], opp))
    except svc.MatchRefused as exc:
        ctx.st.clear()
        opts = [ctx.menu_option()]
        if exc.kind == "funds" and ctx.enabled("deposit"):
            opts.insert(0, Option(ids.encode("deposit", "start"), "Add money"))
        ctx.choose(exc.message, opts)
        return
    ctx.st.clear()
    code = svc.code_of(ch)
    game = match_notices.game_label(d["game"])
    if opp:
        ctx.choose(
            f"Challenge sent to *@{opp['gaming_tag']}*. Match `{code}`.\n"
            "When they accept, you lock first, then they do. We'll message you.",
            [Option(ids.encode("match", "start"), "My matches"), ctx.menu_option()],
        )
        tag = creator.get("gaming_tag") or "player"
        await mk.notify_legacy(
            str(opp["id"]),
            f"⚔️ <b>Challenge from @{tag}</b>\n\nMatch: <code>{code}</code>\n"
            f"Stake: <b>${Decimal(d['amount']):,.2f}</b>\nGame: <b>{game}</b>\n\nTap Accept or Decline:",
            match_notices.challenge_received(ch, creator),
            tg_buttons=mk.tg_accept_menu(str(ch["id"])),
        )
        return
    share, links = invite_text(code, game, Decimal(d["amount"]))
    ctx.say(f"*Invite ready*: match `{code}`.\nForward the next message to your friend or a group. "
            "The first person to accept plays you.\n\n" + links)
    ctx.link(share, f"https://wa.me/?text={quote(share)}", "Share invite")


def invite_text(code: str, game: str, amount: Decimal) -> tuple[str, str]:
    """(message to forward, the links on their own) for an invite code."""
    site = config.site_url()
    number = config.whatsapp_display_number()
    bot = config.telegram_bot_username()
    lines = []
    if number:
        lines.append(f"WhatsApp: https://wa.me/{number}?text={quote('JOIN ' + code)}")
    if bot:
        lines.append(f"Telegram: https://t.me/{bot}?start=m_{code}")
    lines.append(f"Web: {site}/app/match/{code}")
    links = "\n".join(lines)
    share = (f"I challenge you to {game} for ${amount:,.2f} USDC on Boardman (stakes held in escrow). "
             f"Accept here:\n{links}")
    return share, links
