"""Player notices and ops alerts from any thread (webhook, worker, request).

Notices go through the channels notifier (Telegram any time; WhatsApp in
the 24 h window, or the ``withdrawal_update`` template for cash-outs).
The worker loop registers the API's event loop with ``set_loop`` so notices
raised in worker threads run on it.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

_loop: Optional[asyncio.AbstractEventLoop] = None
_tasks: set = set()


def set_loop(loop: Optional[asyncio.AbstractEventLoop]) -> None:
    global _loop
    _loop = loop


def _run(coro: Any) -> None:
    try:
        running = asyncio.get_running_loop()
    except RuntimeError:
        running = None
    if running is not None:
        t = running.create_task(coro)
        _tasks.add(t)
        t.add_done_callback(_tasks.discard)
        return
    if _loop is not None and _loop.is_running():
        asyncio.run_coroutine_threadsafe(coro, _loop)
        return
    try:
        asyncio.run(coro)
    except Exception:
        logger.debug("[paycrest] notice delivery failed", exc_info=True)


def tell(profile_id: str, text: str, *, kind: str = "naira_update", params: Optional[dict] = None) -> None:
    """Best effort: a lost notice never blocks money movement."""
    try:
        from gaming.src.channels.core.notify import Notice, notify

        _run(notify(profile_id, Notice(kind=kind, params=params or {}, text=text)))
    except Exception:
        logger.debug("[paycrest] notice skipped", exc_info=True)


def alert_admins(text: str) -> None:
    logger.warning("[paycrest] ops: %s", text)
    try:
        from gaming.src.channels.core.actions.deposit import alert_admins as _alert

        _run(_alert(text))
    except Exception:
        logger.debug("[paycrest] admin alert skipped", exc_info=True)
