"""Self-custody wallet confirmations in the chat (Telegram and WhatsApp alike).

``v1|scw|y|<nonce>`` / ``v1|scw|n|<nonce>``  "Is this your wallet?" answers
``v1|scw|r|``                                 show the prompt again (wallet screen)
``v1|scw|c|<request id>``                     cancel a wallet change

The nonce is single use, expires, and only the profile the request belongs
to can answer it (``self_custody.setup.answer``). Gated by
``SELF_CUSTODY_WALLETS_ENABLED`` (``channels.config.flow_enabled``).
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from gaming.src.channels.core import ids
from gaming.src.channels.core.messages import Option

NAME = "scw"


def when_utc(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%d %b %Y, %H:%M UTC")


def _notice(text: str, options: list | None = None):
    from gaming.src.channels.core.notify import Notice

    return Notice(kind="wallet_update", text=text, options=list(options or []))


def cancel_option(request_id: str) -> Option:
    return Option(ids.encode(NAME, "c", request_id), "Cancel the change")


async def start(ctx) -> None:
    from gaming.src.channels.core.flows import balance

    await balance.start(ctx)


async def on_button(ctx, act: str, arg: str) -> None:
    from gaming.src.backend.services.self_custody import notices, setup

    pid = str(ctx.profile_id or "")
    if act in ("y", "n"):
        out = await asyncio.to_thread(setup.answer, pid, arg, approve=act == "y")
        _answered(ctx, pid, out)
        return
    if act == "r":
        got = await asyncio.to_thread(setup.reissue_confirm, pid)
        if got is None:
            ctx.choose("Nothing is waiting for your confirmation.", [ctx.menu_option()])
            return
        req, nonce = got
        ctx.choose(notices.confirm_text(req["kind"], req["address"], req.get("previous_address")),
                   notices.confirm_options(nonce))
        return
    if act == "c":
        req = await asyncio.to_thread(setup.cancel, pid, arg)
        if req is None:
            ctx.choose("There is no wallet change to cancel.", [ctx.menu_option()])
            return
        text = (f"Wallet change cancelled: `{req['address']}` will NOT become your wallet."
                + (f"\nYour wallet stays `{req['previous_address']}`." if req.get("previous_address") else ""))
        ctx.choose(text, [ctx.menu_option()])
        ctx.notify(pid, _notice(text), all_channels=True, exclude_self=True)
        return
    await start(ctx)


def _answered(ctx, pid: str, out: dict) -> None:
    result = out.get("result")
    if result == "refused":
        ctx.choose(out["message"], [ctx.menu_option()])
        return
    addr = out["address"]
    if result == "declined":
        text = (f"OK, `{addr}` was NOT linked. Nothing changed.\n"
                "If you didn't start this, someone may have opened your setup link. Never share Boardman links.")
        ctx.choose(text, [ctx.menu_option()])
        ctx.notify(pid, _notice(f"A wallet link request for `{addr}` was declined. Nothing changed."),
                   all_channels=True, exclude_self=True)
        return
    if result == "active":
        text = (f"🔑 Your passkey wallet is linked: `{addr}`\nYou hold the keys; Boardman can't move your money.")
        ctx.choose(text, [Option(ids.encode("balance", "start"), "Wallet"), ctx.menu_option()])
        ctx.notify(pid, _notice(f"Your passkey wallet is linked: `{addr}`\nIf this wasn't you, contact support now."),
                   all_channels=True, exclude_self=True)
        return
    if result == "cooling":
        text = (f"Wallet change scheduled. `{addr}` becomes your wallet on {when_utc(out['active_at_ms'])}.\n"
                f"Until then `{out.get('previous_address')}` stays your wallet and new top-ups go to your "
                "Boardman play wallet.\nNot you? Tap *Cancel the change* and contact support.")
        opts = [cancel_option(out["request_id"])]
        ctx.choose(text, opts + [ctx.menu_option()])
        ctx.notify(pid, _notice(text, opts), all_channels=True, exclude_self=True)
        return
    ctx.choose("Something went wrong. Nothing changed.", [ctx.menu_option()])
