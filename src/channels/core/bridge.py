"""Legacy notices → the player's chat channel (CHANNELS_DESIGN §3.3 step 2).

The bot jobs, the settlement service and the Telegram handlers all notify
through ``bot.utils.notify.notify_user(profile_id, html, buttons)``. That
function asks ``deliver`` first: when the recipient plays on WhatsApp (a
WhatsApp identity, opted in, and either no Telegram chat or a WhatsApp
``notify_priority`` ahead of Telegram's) the notice goes through the core
notifier instead: free-form inside the 24 h window, the approved template
outside it. Every other recipient gets exactly the Telegram message as before.

Callers that know what happened pass a structured ``Notice`` (template
params, aligned quick-reply payloads). Calls that don't are converted here:
HTML becomes the core's ``*bold*`` markup and the legacy Telegram callbacks
that have a core equivalent become core buttons; such a "generic" notice has
no template, so outside the window it is skipped (and logged in the outbox).
"""
from __future__ import annotations

import asyncio
import logging
import re
from typing import Any, Optional

from gaming.src.channels import config
from gaming.src.channels.core import ids
from gaming.src.channels.core.messages import MENU_ID, Option

logger = logging.getLogger(__name__)

_UUID = r"[0-9a-fA-F-]{36}"
# Legacy Telegram callback → core button id (None: no core equivalent; dropped).
_CALLBACKS: list[tuple[re.Pattern, Any]] = [
    (re.compile(rf"^challenge:accept:({_UUID})$"), lambda m: ids.encode("match", "accept", m.group(1))),
    (re.compile(rf"^challenge:decline:({_UUID})$"), lambda m: ids.encode("match", "decline", m.group(1))),
    (re.compile(rf"^ui:lock:({_UUID})$"), lambda m: ids.encode("match", "lock", m.group(1))),
    (re.compile(rf"^ui:report:({_UUID})$"), lambda m: ids.encode("report", "start", m.group(1))),
    (re.compile(rf"^ui:(?:info|settle):({_UUID})$"), lambda m: ids.encode("match", "view", m.group(1))),
    (re.compile(r"^ui:match$"), lambda m: ids.encode("match", "start")),
    (re.compile(r"^(?:menu:main|m_main)$"), lambda m: MENU_ID),
    (re.compile(r"^menu:wallet$"), lambda m: ids.encode("balance", "start")),
    (re.compile(r"^(?:ui:get_money|ui:get_usdc)$"), lambda m: ids.encode("deposit", "start")),
]


def core_button(callback: str) -> Optional[str]:
    if ids.is_core(callback):
        return callback
    for rx, make in _CALLBACKS:
        m = rx.match(callback or "")
        if m:
            return make(m)
    return None


def _buttons(markup: Any) -> list[tuple[str, Optional[str], Optional[str]]]:
    """(label, callback, url) for each button of an aiogram keyboard."""
    out = []
    for row in getattr(markup, "inline_keyboard", None) or []:
        for b in row:
            out.append((str(getattr(b, "text", "") or ""), getattr(b, "callback_data", None),
                        getattr(b, "url", None)))
    return out


def _clean_label(label: str) -> str:
    # Drop leading emoji / symbols: WhatsApp titles are short and plain.
    return re.sub(r"^[^\w@$₦(]+", "", label).strip() or label.strip()


def from_legacy(html_text: str, markup: Any = None):
    """A generic ``Notice`` from a legacy Telegram DM."""
    from gaming.src.channels.core.actions.matches import plain
    from gaming.src.channels.core.notify import Notice

    opts: list[Option] = []
    seen: set[str] = set()
    links: list[str] = []
    for label, cb, url in _buttons(markup):
        if url:
            links.append(f"{_clean_label(label)}: {url}")
            continue
        cid = core_button(cb or "")
        if cid and cid not in seen and len(opts) < 10:
            seen.add(cid)
            opts.append(Option(cid, _clean_label(label)[:24] or "Open"))
    text = plain(html_text)
    if links:
        text += "\n\n" + "\n".join(links)
    return Notice(kind="generic", text=text or "Boardman update", options=opts)


def preferred_channel(profile_id: str) -> Optional[str]:
    """``whatsapp`` when this profile's notices belong on WhatsApp, else None (sync)."""
    if not profile_id or not config.whatsapp_enabled():
        return None
    from gaming.src.channels.core.identity.repo import get_repo

    repo = get_repo()
    idents = repo.for_profile(str(profile_id))
    wa = next((i for i in idents if i.channel == "whatsapp"), None)
    if wa is None or not wa.opted_in:
        return None
    tg = [i.notify_priority for i in idents if i.channel == "telegram"]
    if not tg:
        prof = repo.get_profile(str(profile_id)) or {}
        if not (prof.get("gaming_telegram_chat_id") or prof.get("telegram_id")):
            return "whatsapp"
        tg = [100]
    return "whatsapp" if wa.notify_priority < min(tg) else None


async def deliver(profile_id: str, html_text: str, markup: Any = None, notice: Any = None) -> Optional[bool]:
    """Send through the core when the recipient is a WhatsApp player.

    Returns None when the caller should send on Telegram as before, else
    whether a delivery succeeded.
    """
    try:
        channel = await asyncio.to_thread(preferred_channel, profile_id)
    except Exception:
        logger.warning("[channels] channel lookup failed; falling back to Telegram", exc_info=True)
        return None
    if channel is None:
        return None
    from gaming.src.channels.core.notify import default_service

    n = notice if notice is not None else from_legacy(html_text, markup)
    try:
        results = await default_service().notify(str(profile_id), n, only={channel})
    except Exception:
        logger.warning("[channels] %s notice failed kind=%s", channel, getattr(n, "kind", "?"), exc_info=True)
        return False
    return any(d.ok for d in results)
