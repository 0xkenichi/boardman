"""Withdraw (flow 17), redesigned: no secret ever typed in the chat.

destination → amount → one-time web link. The PIN is entered (or first set)
on ``/app/withdraw/<token>``; the payout runs there with every existing check.
"""
from __future__ import annotations

import asyncio

from gaming.src.channels.core import geo, ids
from gaming.src.channels.core.actions import withdraw as wd
from gaming.src.channels.core.messages import Option

NAME = "withdraw"
KEYWORDS = ("withdraw", "cashout", "cash-out", "send")


def _refuse_early(ctx) -> bool:
    d = geo.check_money(ctx.principal, "withdraw")
    if d is not None:
        ctx.st.clear()
        ctx.say(geo.refusal_text(d))
        return True
    if ctx.principal.withdraw_hold_active():
        ctx.st.clear()
        until = ctx.principal.withdraw_hold_until.strftime("%d %b %H:%M UTC")
        ctx.say(f"This chat was linked recently, so withdrawals from it open on {until}. "
                "You can still withdraw from the app you signed up with.")
        return True
    return False


async def start(ctx) -> None:
    if _refuse_early(ctx):
        return
    from gaming.src.backend.services.safety import MAX_WITHDRAW_USDC, MIN_WITHDRAW_USDC

    ctx.st.set(NAME, "dest")
    ctx.choose(
        "*Withdraw USDC*\n"
        f"Per transfer: ${MIN_WITHDRAW_USDC:,.0f} to ${MAX_WITHDRAW_USDC:,.0f}.\n\n"
        "Where to? Send a wallet address (0x…) or a player tag (@name). "
        "To cash out to your bank, send to your exchange's USDC address on Arc.",
        [ctx.menu_option("Cancel")],
    )


async def on_button(ctx, act: str, arg: str) -> None:
    await start(ctx)


async def on_text(ctx, text: str) -> None:
    if _refuse_early(ctx):
        return
    parts = text.split()
    if ctx.st.step == "dest":
        # Accept "0xabc… 25" in one message too.
        try:
            dest = await wd.resolve_destination(ctx.principal, parts[0] if parts else "")
        except wd.WithdrawRefused as exc:
            ctx.say(str(exc))
            return
        ctx.st.set(NAME, "amount", address=dest.address, recipient_id=dest.recipient_id, tag=dest.tag)
        if len(parts) >= 2:
            await _amount(ctx, parts[1])
            return
        ctx.say(f"How much USDC to send to {dest.label()}? (for example 20)")
        return
    if ctx.st.step == "amount":
        await _amount(ctx, text)
        return
    await start(ctx)


async def _amount(ctx, raw: str) -> None:
    amount = wd.parse_amount(raw)
    if amount is None:
        ctx.say("Send the amount as a number, like 20.")
        return
    d = ctx.st.data
    dest = wd.Destination(d.get("address") or "", d.get("recipient_id"), d.get("tag"))
    try:
        issued = await asyncio.to_thread(wd.request_link, ctx.principal, dest, amount)
    except wd.WithdrawRefused as exc:
        ctx.say(f"{exc}\nSend another amount, or *cancel*.")
        return
    ctx.st.clear()
    ctx.link(wd.link_message(dest, amount), issued.url, "Confirm withdrawal")
