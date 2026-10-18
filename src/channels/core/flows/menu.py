"""Main menu, STOP and START."""
from __future__ import annotations

import asyncio

from gaming.src.channels import config
from gaming.src.channels.core import ids
from gaming.src.channels.core.messages import Option

ENTRIES = (
    ("balance", "Wallet", "Balance and play address"),
    ("deposit", "Add money", "Naira (Paystack) or USDC"),
    ("withdraw", "Withdraw", "Confirm on the web with your PIN"),
    ("naira", "Naira (Paycrest)", "Top up or cash out with your bank"),
    ("link", "Link account", "Use Telegram and WhatsApp together"),
)


def options(ctx) -> list[Option]:
    return [
        Option(ids.encode(flow, "start"), label, desc)
        for flow, label, desc in ENTRIES
        if ctx.enabled(flow)
    ]


async def start(ctx) -> None:
    ctx.st.clear()
    opts = options(ctx)
    site = config.site_url()
    body = (
        f"*Boardman* · skill matches settled in USDC.\n"
        f"Matches, the board and spectator bets: {site}/app"
    )
    if not opts:
        ctx.say(body + "\n\nMore of Boardman is coming to this chat soon.")
        return
    ctx.choose(body + "\n\nWhat do you want to do?", opts, button_label="Menu")


async def on_button(ctx, act: str, arg: str) -> None:
    await start(ctx)


async def stop(ctx) -> None:
    from gaming.src.channels.core.identity.service import opt_out

    if ctx.principal.known:
        await asyncio.to_thread(opt_out, ctx.channel, ctx.principal.external_id)
    ctx.st.clear()
    ctx.say("You won't get match or wallet notices here any more. Send START to turn them back on.")


async def resubscribe(ctx) -> None:
    from gaming.src.channels.core.identity.service import opt_in

    if ctx.principal.known:
        await asyncio.to_thread(opt_in, ctx.channel, ctx.principal.external_id)
        ctx.say("Notices are back on. Send STOP any time to turn them off.")
        await start(ctx)
        return
    from gaming.src.channels.core.flows import onboarding

    await onboarding.start(ctx)
