"""Telegram's legacy "Lock my stake" button for self-custody players.

When ``SELF_CUSTODY_WALLETS_ENABLED`` is on and the player has a passkey
wallet (or ``SELF_CUSTODY_REQUIRED`` is on and they don't), the button
answers with an "Approve with passkey" (or "Set up wallet") URL button instead
of locking from the custodial wallet. Off: returns False and the handler runs
exactly as before.
"""
from __future__ import annotations

import asyncio
import logging
from html import escape

from aiogram import types
from aiogram.enums import ParseMode

logger = logging.getLogger(__name__)


async def maybe_send_lock_link(message: types.Message, user: types.User, profile: dict, cid: str) -> bool:
    from gaming.src.backend.services.self_custody import config, routing

    if not config.enabled():
        return False
    from gaming.src.channels.core.actions import matches as svc

    ch = await asyncio.to_thread(svc.load, cid)
    if not ch or svc.role(ch, str(profile["id"])) is None:
        return False
    route = await asyncio.to_thread(routing.lock_route, str(profile["id"]), ch)
    if route == routing.CUSTODIAL:
        return False
    from gaming.src.backend.services.self_custody import intents, setup
    from gaming.src.channels.core.flows.match import passkey_lock_text
    from gaming.src.channels.telegram.web_pin import _keyboard

    try:
        if route == routing.SETUP:
            url, _ = await asyncio.to_thread(setup.issue_link, str(profile["id"]), channel="telegram",
                                             external_id=str(user.id))
            await message.answer(
                "🔑 <b>Set up your wallet first</b>\n\nStakes now lock from a wallet only you control, approved "
                "with a passkey (Face ID or fingerprint). It takes a minute. Then tap <b>Lock my stake</b> again.",
                parse_mode=ParseMode.HTML, reply_markup=_keyboard("Set up wallet", url),
                disable_web_page_preview=True,
            )
            return True
        prepared = await intents.prepare_lock(str(profile["id"]), ch, channel="telegram", external_id=str(user.id))
    except intents.IntentRefused as exc:
        await message.answer(f"❌ {escape(exc.message)}", parse_mode=ParseMode.HTML)
        return True
    text = escape(passkey_lock_text(ch, prepared)).replace("*", "").replace("`", "")
    await message.answer(f"🔐 {text}", parse_mode=ParseMode.HTML,
                         reply_markup=_keyboard("Approve with passkey", prepared.url),
                         disable_web_page_preview=True)
    return True
