"""Link account: a one-time code issued on a signed-in channel, sent from the
new one (CHANNELS_DESIGN §2.3)."""
from __future__ import annotations

import asyncio
from urllib.parse import quote

from gaming.src.channels import config
from gaming.src.channels.core.identity import service as identity
from gaming.src.channels.core.identity.emptiness import profile_is_empty
from gaming.src.channels.core.notify import Notice

NAME = "link"
KEYWORDS = ("link",)


def mask_identity(channel: str, external_id: str) -> str:
    tail = external_id[-4:] if len(external_id) >= 4 else external_id
    if channel == "whatsapp":
        return f"WhatsApp +{external_id[:3]}•••{tail}"
    if channel == "telegram":
        return f"Telegram account •••{tail}"
    return f"{channel} •••{tail}"


async def start(ctx) -> None:
    ctx.st.clear()
    if not ctx.principal.known:
        ctx.say("Send the code from your other app like this: *LINK ABCD-EFGH*")
        return
    try:
        code, _ = await asyncio.to_thread(identity.issue_link_code, ctx.principal)
    except identity.LinkError as exc:
        ctx.say(str(exc))
        return
    shown = identity.format_code(code)
    minutes = int(identity.link_ttl().total_seconds() // 60)
    body = (
        f"Your link code: *{shown}*\n"
        f"It works once and expires in {minutes} minutes. Never share it with anyone."
    )
    if ctx.channel == "telegram":
        number = config.whatsapp_display_number()
        text = f"LINK {shown}"
        if number:
            ctx.link(body + "\n\nOn WhatsApp, send it to Boardman:", f"https://wa.me/{number}?text={quote(text)}",
                     "Open WhatsApp")
        else:
            ctx.say(body + f"\n\nOn the other app, send: *{text}*")
        return
    bot = config.telegram_bot_username()
    if bot:
        ctx.link(body + "\n\nOn Telegram, tap below (or send */link " + shown + "* to the bot):",
                 f"https://t.me/{bot}?start=link_{identity.normalize_code(code)}", "Open Telegram")
    else:
        ctx.say(body + f"\n\nOn Telegram, send */link {shown}* to the Boardman bot.")


async def keyword(ctx, rest: str) -> None:
    code = identity.normalize_code(rest)
    if code:
        await redeem(ctx, code)
    else:
        await start(ctx)


async def on_button(ctx, act: str, arg: str) -> None:
    await start(ctx)


async def redeem(ctx, code: str) -> None:
    ev = ctx.event
    phone = ev.phone if ev else None
    res = await identity.redeem_link_code(
        ctx.channel,
        ctx.principal.external_id,
        code,
        profile_is_empty=profile_is_empty,
        phone=phone,
        address=(ev.address or phone) if ev else None,
        handle=(ev.profile_name or None) if ev else None,
    )
    if res.status == "rate_limited":
        ctx.say("Too many tries. Wait 10 minutes and ask for a new code.")
        return
    if res.status == "invalid":
        ctx.say("That code is wrong, used or expired. Ask for a new one with *link* in your other app.")
        return
    if res.status == "conflict":
        ctx.say("That account already has a different number on this app. Contact support to change it.")
        return
    if res.status == "refused_funded":
        ctx.say(identity.SUPPORT_TEXT)
        return
    if res.status == "already_linked":
        ctx.say("This chat is already linked to that account.")
        return
    fresh = await asyncio.to_thread(identity.resolve, ctx.channel, ctx.principal.external_id, phone=phone)
    ctx.principal.profile_id = fresh.profile_id
    ctx.principal.profile = fresh.profile
    ctx.principal.withdraw_hold_until = fresh.withdraw_hold_until
    ctx.principal.country_signals = fresh.country_signals
    ctx.st.clear()
    hours = int(identity.withdraw_hold().total_seconds() // 3600)
    ctx.say(
        f"Linked to *@{fresh.display_name}*. Your balance and matches are the same everywhere.\n"
        f"For your safety, withdrawals from this chat open in {hours} hours."
    )
    who = mask_identity(ctx.channel, ctx.principal.external_id)
    ctx.notify(
        res.profile_id,
        Notice(
            kind="account_linked",
            params={"identity": who},
            text=f"{who} was linked to your Boardman account. Not you? Contact support now.",
        ),
        all_channels=True,
        exclude_self=True,
    )
    from gaming.src.channels.core.flows import menu

    await menu.start(ctx)
