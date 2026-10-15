"""Answers to nonce-bound approval prompts: ``v1|ap|y|<nonce>`` / ``v1|ap|n|<nonce>``.

The nonce is consumed (owner, chat, expiry, single use and, on WhatsApp, the
prompt's message id) before the approved action runs.
"""
from __future__ import annotations

import asyncio

from gaming.src.channels.core import approvals

NAME = "ap"


def _actions():
    from gaming.src.channels.core.flows import match

    return {"lock": ("match", match.do_lock)}


async def start(ctx) -> None:
    ctx.say("That button is no longer active.")


async def on_button(ctx, act: str, arg: str) -> None:
    if act not in ("y", "n") or not arg:
        await start(ctx)
        return
    context_id = ctx.event.context_id if ctx.event is not None else ""
    try:
        action, payload = await asyncio.to_thread(
            approvals.consume, ctx.principal, arg, approve=act == "y", context_id=context_id
        )
    except approvals.ApprovalRefused as exc:
        ctx.choose(exc.message, [ctx.menu_option()])
        return
    flow, fn = _actions().get(action, (None, None))
    if fn is None or not ctx.enabled(flow):
        ctx.say("That option is not available here yet.")
        return
    if act == "n":
        ctx.choose("OK, nothing was locked.", [ctx.menu_option()])
        return
    await fn(ctx, payload)
