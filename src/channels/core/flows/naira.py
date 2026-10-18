"""Naira through Paycrest: top up from a Nigerian bank, or cash out to one.

Only exists when the rail is live (``PAYCREST_ENABLED=1`` and
``REAL_MONEY_ENABLED=1``). The chat never asks for BVN/NIN or a PIN: KYC is
typed on a one-time web page, cash-outs are confirmed with the PIN on the
withdraw page. Every quote is shown before the player commits.

Top up:   amount → quote → [Continue] → secure page (KYC + refund account) →
          the account to pay arrives in the chat
Cash out: bank → account number → name check → amount → quote →
          [Continue] → PIN page
"""
from __future__ import annotations

import asyncio

from gaming.src.channels.core import geo, ids
from gaming.src.channels.core.messages import Option

NAME = "naira"
KEYWORDS = ("naira", "paycrest", "ngn")
PRESETS_NGN = ("5000", "20000", "50000")

REAL_MONEY = "This is real money (USDC on mainnet)."


def _geo(ctx, kind: str) -> bool:
    d = geo.check_money(ctx.principal, kind)
    if d is not None:
        ctx.st.clear()
        ctx.say(geo.refusal_text(d))
        return True
    return False


async def start(ctx) -> None:
    ctx.st.set(NAME, "pick")
    ctx.choose(
        "*Naira with Paycrest*\n"
        "Top up from your Nigerian bank, or cash out to it. Paycrest converts naira and USDC; "
        f"its 0.5% fee is in the rate and every quote is shown before you confirm. {REAL_MONEY}",
        [Option(ids.encode(NAME, "in"), "Top up with naira", "Bank transfer → play wallet"),
         Option(ids.encode(NAME, "out"), "Cash out to bank", "Play wallet → your bank"),
         ctx.menu_option()],
    )


async def on_button(ctx, act: str, arg: str) -> None:
    if act == "start":
        if arg == "in":
            await _in(ctx)
        elif arg == "out":
            await _out(ctx)
        else:
            await start(ctx)
        return
    handlers = {
        "in": lambda: _in(ctx),
        "amt": lambda: _in_quote(ctx, arg),
        "in_go": lambda: _in_go(ctx),
        "out": lambda: _out(ctx),
        "bank": lambda: _bank_picked(ctx, arg),
        "acct_ok": lambda: _acct_ok(ctx),
        "out_go": lambda: _out_go(ctx),
    }
    h = handlers.get(act)
    if h is None:
        await start(ctx)
        return
    await h()


async def on_text(ctx, text: str) -> None:
    step = ctx.st.step
    if step == "in_amount":
        await _in_quote(ctx, text)
    elif step == "out_bank":
        await _bank_search(ctx, text)
    elif step == "out_acct":
        await _acct(ctx, text)
    elif step == "out_amount":
        await _out_quote(ctx, text)
    else:
        await start(ctx)


# ── top up ──────────────────────────────────────────────────────────────────


async def _in(ctx) -> None:
    if _geo(ctx, "deposit"):
        return
    from gaming.src.backend.services.paycrest import config

    lim = config.limits()
    ctx.st.set(NAME, "in_amount")
    ctx.choose(
        "*Top up with naira*\nHow much naira will you send? "
        f"(₦{lim.onramp_min_ngn:,.0f} to ₦{lim.onramp_max_ngn:,.0f})\nPick one or type an amount, e.g. 15000.",
        [Option(ids.encode(NAME, "amt", a), f"₦{int(a):,}") for a in PRESETS_NGN] + [ctx.menu_option("Cancel")],
    )


async def _in_quote(ctx, raw: str) -> None:
    if _geo(ctx, "deposit"):
        return
    from gaming.src.backend.services.paycrest import onramp, quotes, store
    from gaming.src.backend.services.paycrest.models import PaycrestError

    amount = onramp.parse_ngn(raw)
    if amount is None:
        ctx.say("Send the naira amount as a number, like 15000.")
        return
    problem = await asyncio.to_thread(onramp.limit_problem, ctx.profile_id, amount, now_ms=store.now_ms())
    if problem:
        ctx.say(f"{problem}\nType another amount, or send *cancel*.")
        return
    try:
        q = await asyncio.to_thread(quotes.quote_onramp, amount, now_ms=store.now_ms())
    except PaycrestError:
        ctx.say("Paycrest can't quote naira right now. Try again in a few minutes.")
        return
    ctx.st.set(NAME, "in_confirm", amount_ngn=str(amount))
    ctx.choose(
        f"*Naira top-up quote*\n{q.text()}\n\n{REAL_MONEY} "
        "Next you'll confirm your identity on a secure Boardman page (Paycrest needs your BVN or NIN for "
        "every naira payment; we never ask for it in chat), then you'll get an account to pay.",
        [Option(ids.encode(NAME, "in_go"), "Continue"), ctx.menu_option("Cancel")],
    )


async def _in_go(ctx) -> None:
    if _geo(ctx, "deposit"):
        return
    from decimal import Decimal

    from gaming.src.backend.services.paycrest import onramp

    raw = ctx.st.data.get("amount_ngn")
    if ctx.st.step != "in_confirm" or not raw:
        await _in(ctx)
        return
    arc = ""
    try:
        from gaming.src.backend.services.paycrest.wallets import play_wallet

        arc = (await play_wallet(ctx.profile_id)).get("address") or ""
    except Exception:
        pass
    if not arc:
        ctx.say("Your play wallet isn't ready yet. Try again in a minute.")
        return
    try:
        started = await asyncio.to_thread(
            onramp.start, ctx.profile_id, channel=ctx.channel, external_id=ctx.principal.external_id,
            amount_ngn=Decimal(raw), arc_address=arc,
        )
    except onramp.NairaError as exc:
        ctx.say(exc.message)
        return
    ctx.st.clear()
    minutes = max(1, (started.expires_at_ms - _now()) // 60000)
    ctx.link(
        f"*Confirm your top-up of ₦{Decimal(raw):,.0f}*\n"
        "Open the secure page, enter your details and your own bank account (for refunds). "
        f"The link works once and expires in {minutes} minutes. Never share it.",
        started.url, "Open secure page",
    )


def _now() -> int:
    from gaming.src.backend.services.paycrest import store

    return store.now_ms()


# ── cash out ────────────────────────────────────────────────────────────────


async def _out(ctx) -> None:
    if _geo(ctx, "withdraw"):
        return
    if ctx.principal.withdraw_hold_active():
        ctx.st.clear()
        until = ctx.principal.withdraw_hold_until.strftime("%d %b %H:%M UTC")
        ctx.say(f"This chat was linked recently, so withdrawals from it open on {until}.")
        return
    from gaming.src.backend.services.paycrest import offramp

    banks = await asyncio.to_thread(offramp.popular_banks)
    ctx.st.set(NAME, "out_bank")
    opts = [Option(ids.encode(NAME, "bank", b["code"]), b["name"][:24]) for b in banks]
    ctx.choose("*Cash out to your bank*\nPick your bank, or type its name.", opts + [ctx.menu_option("Cancel")])


async def _bank_search(ctx, text: str) -> None:
    from gaming.src.backend.services.paycrest import offramp

    hits = await asyncio.to_thread(offramp.search_banks, text)
    if not hits:
        ctx.say("I couldn't find that bank. Type part of its name, like *Opay* or *Access*.")
        return
    if len(hits) == 1:
        await _bank_picked(ctx, hits[0]["code"])
        return
    ctx.choose("Which one?", [Option(ids.encode(NAME, "bank", b["code"]), b["name"][:24]) for b in hits]
               + [ctx.menu_option("Cancel")])


async def _bank_picked(ctx, code: str) -> None:
    if _geo(ctx, "withdraw"):
        return
    from gaming.src.backend.services.paycrest import onramp

    name = await asyncio.to_thread(onramp.institution_name, code)
    ctx.st.set(NAME, "out_acct", institution=code, institution_name=name)
    ctx.say(f"*{name}*: send your 10-digit account number.")


async def _acct(ctx, text: str) -> None:
    from gaming.src.backend.services.paycrest import offramp
    from gaming.src.backend.services.paycrest.onramp import NairaError

    code = ctx.st.data.get("institution") or ""
    try:
        bank = await asyncio.to_thread(offramp.resolve_account, code, text)
    except NairaError as exc:
        ctx.say(f"{exc.message}\nSend the account number again, or *cancel*.")
        return
    ctx.st.set(NAME, "out_acct_check", bank=bank)
    ctx.choose(
        f"The bank says this account belongs to *{bank['account_name']}* ({bank['label']}).\n"
        "Cash out only to your own account.",
        [Option(ids.encode(NAME, "acct_ok"), "Yes, that's me"), Option(ids.encode(NAME, "out"), "No, change"),
         ctx.menu_option("Cancel")],
    )


async def _acct_ok(ctx) -> None:
    bank = ctx.st.data.get("bank")
    if ctx.st.step != "out_acct_check" or not bank:
        await _out(ctx)
        return
    from gaming.src.backend.services.paycrest import config

    lim = config.limits()
    ctx.st.set(NAME, "out_amount", bank=bank)
    ctx.say(f"How many dollars of USDC to cash out? (${lim.offramp_min_usdc:,.2f} to ${lim.offramp_max_usdc:,.2f})")


async def _out_quote(ctx, raw: str) -> None:
    if _geo(ctx, "withdraw"):
        return
    from gaming.src.backend.services.paycrest import offramp, quotes, store
    from gaming.src.backend.services.paycrest.models import PaycrestError
    from gaming.src.channels.core.actions.withdraw import parse_amount

    amount = parse_amount(raw)
    if amount is None:
        ctx.say("Send the amount as a number of dollars, like 20.")
        return
    problem = await asyncio.to_thread(offramp.limit_problem, ctx.profile_id, amount, now_ms=store.now_ms())
    if problem:
        ctx.say(f"{problem}\nSend another amount, or *cancel*.")
        return
    try:
        q = await asyncio.to_thread(quotes.quote_offramp, amount, now_ms=store.now_ms())
    except PaycrestError:
        ctx.say("Paycrest can't quote naira right now. Try again in a few minutes.")
        return
    bank = ctx.st.data.get("bank") or {}
    ctx.st.set(NAME, "out_confirm", bank=bank, amount=str(amount))
    ctx.choose(
        f"*Cash-out quote*\n{q.text()}\nTo: {bank.get('account_name')}, {bank.get('label')}\n\n{REAL_MONEY} "
        "You'll confirm with your withdrawal PIN on a secure page.",
        [Option(ids.encode(NAME, "out_go"), "Continue"), ctx.menu_option("Cancel")],
    )


async def _out_go(ctx) -> None:
    if _geo(ctx, "withdraw"):
        return
    from decimal import Decimal

    from gaming.src.backend.services.paycrest import offramp
    from gaming.src.backend.services.paycrest.onramp import NairaError

    d = ctx.st.data
    if ctx.st.step != "out_confirm" or not d.get("bank") or not d.get("amount"):
        await _out(ctx)
        return
    amount = Decimal(d["amount"])
    try:
        prepared = await asyncio.to_thread(offramp.prepare, ctx.principal, amount, d["bank"])
    except NairaError as exc:
        ctx.say(exc.message)
        return
    ctx.st.clear()
    from gaming.src.channels.core import withdraw_links

    minutes = withdraw_links.ttl_ms() // 60000
    ctx.link(
        f"*Confirm your cash-out*\n${amount:,.2f} USDC to {d['bank'].get('label')} "
        f"(about ₦{prepared.quote.payout_ngn:,.0f}).\n\n"
        f"Open the secure page and enter your withdrawal PIN there. The link works once and expires in "
        f"{minutes} minutes. Never type your PIN in a chat and never share this link.",
        prepared.url, "Confirm cash-out",
    )
