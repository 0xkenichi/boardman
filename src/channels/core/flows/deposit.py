"""Add money: Paystack naira link, or the crypto play address (flows 4 and 6).

Bank-transfer proof uploads and the Stellar/Avalanche rails stay on Telegram
until Phase 2.
"""
from __future__ import annotations

from gaming.src.channels.core import geo, ids
from gaming.src.channels.core.actions import deposit as dep
from gaming.src.channels.core.actions.wallet import play_address
from gaming.src.channels.core.messages import Option

NAME = "deposit"
KEYWORDS = ("deposit", "fund", "topup", "top-up", "add")
PRESETS_NGN = ("5000", "10000", "20000")


def _geo_refusal(ctx) -> bool:
    d = geo.check_money(ctx.principal, "deposit")
    if d is not None:
        ctx.st.clear()
        ctx.say(geo.refusal_text(d))
        return True
    return False


async def start(ctx) -> None:
    ctx.st.set(NAME, "method")
    if _geo_refusal(ctx):
        return
    opts = []
    if dep.paystack_ready():
        opts.append(Option(ids.encode(NAME, "ngn"), "Pay with Naira", "Card, bank or USSD via Paystack"))
    opts.append(Option(ids.encode(NAME, "crypto"), "Send USDC", "To your play address on Arc"))
    opts.append(ctx.menu_option())
    ctx.choose("*Add money*\nHow do you want to pay?", opts)


async def on_button(ctx, act: str, arg: str) -> None:
    if act == "start":
        await start(ctx)
        return
    if _geo_refusal(ctx):
        return
    if act == "crypto":
        ctx.st.clear()
        addr = ""
        try:
            addr = await play_address(ctx.profile_id)
        except Exception:
            pass
        ctx.choose(dep.crypto_instructions(addr), [ctx.menu_option()])
        return
    if act == "ngn":
        if not dep.paystack_ready():
            ctx.say("Naira payments are not switched on yet. Use *Send USDC* for now.")
            return
        from gaming.src.backend.services.fiat_topup import commercial_rate, fee_floor

        ctx.st.set(NAME, "ngn_amount")
        opts = [Option(ids.encode(NAME, "amt", a), f"₦{int(a):,}") for a in PRESETS_NGN]
        ctx.choose(
            f"How much *Naira* will you pay?\nRate ₦{commercial_rate():,.0f} per $1, "
            f"fee the larger of ${fee_floor()} or 5%.\n\nPick one or type an amount (e.g. 15000).",
            opts,
        )
        return
    if act == "amt":
        await _start_paystack(ctx, arg)
        return
    if act == "check":
        await _check(ctx, arg)
        return
    await start(ctx)


async def on_text(ctx, text: str) -> None:
    if ctx.st.step == "ngn_amount":
        await _start_paystack(ctx, text)
        return
    await start(ctx)


async def _start_paystack(ctx, raw: str) -> None:
    profile = dict(ctx.principal.profile or {})
    profile.setdefault("id", ctx.profile_id)
    try:
        started = await dep.start_paystack(
            profile, channel=ctx.channel, external_id=ctx.principal.external_id,
            raw_amount=raw, display_name=ctx.principal.display_name,
        )
    except dep.DepositError as exc:
        ctx.st.set(NAME, "ngn_amount")
        ctx.say(f"{exc}\nType another amount, or send *cancel*.")
        return
    ctx.st.set(NAME, "paystack", ref=started.ref)
    ctx.link(
        f"*Paystack top-up ready* (ref `{started.ref}`)\n"
        f"You pay ₦{started.amount_ngn:,.0f}, you get *${started.credit_usdc:,.2f} USDC* ({started.fee_note}).\n"
        "Pay on Paystack, then come back and tap *I've paid*.",
        started.url,
        "Pay on Paystack",
    )
    ctx.choose("After paying:", [Option(ids.encode(NAME, "check", started.ref), "I've paid"),
                                 ctx.menu_option()])


async def _check(ctx, ref: str) -> None:
    res = await dep.check_paystack(ctx.profile_id, ref)
    again = [Option(ids.encode(NAME, "check", ref), "Check again"), ctx.menu_option()]
    if res.status == "unknown":
        ctx.say("I can't find that top-up on your account.")
        return
    if res.status == "credited":
        ctx.st.clear()
        ctx.choose(f"Already credited: ${res.credit_usdc:,.2f} USDC.", [ctx.menu_option()])
        return
    if res.status == "paid":
        ctx.st.clear()
        ctx.choose(f"*Payment confirmed.* We're sending ${res.credit_usdc:,.2f} USDC to your play wallet "
                   "and will message you when it lands.", [ctx.menu_option()])
        return
    if res.status == "mismatch":
        ctx.st.clear()
        ctx.choose(f"You paid ₦{res.paid_ngn:,.2f}, which doesn't match the quote. Support will adjust "
                   f"the credit (ref `{ref}`).", [ctx.menu_option()])
        return
    if res.status == "pending":
        ctx.choose(f"Not paid yet (Paystack says: {res.detail}). Finish checkout, then check again.", again)
        return
    ctx.choose("Could not reach Paystack. Try again in a minute.", again)
