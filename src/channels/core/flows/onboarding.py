"""First contact from a sender with no profile (WhatsApp; Telegram creates
profiles in its own /start). They pick a gaming tag, or link the account they
already have with a code (CHANNELS_DESIGN §2.2)."""
from __future__ import annotations

import asyncio

from gaming.src.channels.core import ids
from gaming.src.channels.core.identity.service import LinkError, create_profile_for_channel, resolve
from gaming.src.channels.core.messages import Option

NAME = "onboarding"


async def start(ctx) -> None:
    ctx.st.set(NAME, "welcome")
    opts = [Option(ids.encode(NAME, "new"), "I'm new")]
    if ctx.enabled("link"):
        opts.append(Option(ids.encode(NAME, "link"), "I play on Telegram"))
    ctx.choose(
        "Welcome to *Boardman*: skill 1v1s with stakes held in escrow and settled in USDC.\n\n"
        "We'll send your match and wallet notices in this chat. Send STOP any time to turn them off.",
        opts,
    )


async def on_button(ctx, act: str, arg: str) -> None:
    if act == "new":
        ctx.st.set(NAME, "tag")
        ctx.say("Pick a gaming tag: 3 to 20 letters, digits or _ (for example *ada_9ja*).")
        return
    if act == "link" and ctx.enabled("link"):
        ctx.st.set(NAME, "welcome")
        ctx.say(
            "In Telegram, open the Boardman bot and send /link. "
            "Then send the code here, like: *LINK ABCD-EFGH*"
        )
        return
    await start(ctx)


async def on_text(ctx, text: str) -> None:
    if ctx.st.flow != NAME or ctx.st.step != "tag":
        await start(ctx)
        return
    ev = ctx.event
    try:
        await asyncio.to_thread(
            create_profile_for_channel,
            ctx.channel,
            ctx.principal.external_id,
            text,
            display_name=(ev.profile_name if ev else "") or "",
            phone=ev.phone if ev else None,
            address=(ev.address or ev.phone) if ev else None,
        )
    except LinkError as exc:
        ctx.say(str(exc))
        return
    fresh = await asyncio.to_thread(
        resolve, ctx.channel, ctx.principal.external_id, phone=ev.phone if ev else None
    )
    ctx.principal.profile_id = fresh.profile_id
    ctx.principal.identity_id = fresh.identity_id
    ctx.principal.profile = fresh.profile
    ctx.principal.country_signals = fresh.country_signals
    ctx.st.clear()
    ctx.say(f"You're in, *@{fresh.display_name}*.")
    from gaming.src.channels.core.flows import menu

    await menu.start(ctx)
