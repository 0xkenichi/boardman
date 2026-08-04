"""Make button taps feel instant and stop double-clicks from double-replying.

Telegram keeps a loading spinner on the button until ``callback.answer()`` runs.
If we hit Supabase/Circle first, users re-tap → two handlers → two messages.

This middleware:
  1. Answers the callback immediately (spinner gone).
  2. Drops a duplicate (same user + same data) within ~1.4s.
  3. Logs handlers that take longer than 1.5s so we can find remaining stalls.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Awaitable, Callable, Dict, Optional

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, TelegramObject

logger = logging.getLogger(__name__)

# Same button re-tap window (seconds)
_DEBOUNCE_SEC = 1.4
_SLOW_HANDLER_SEC = 1.5


class UxCallbackMiddleware(BaseMiddleware):
    def __init__(self, debounce_sec: float = _DEBOUNCE_SEC) -> None:
        self.debounce_sec = debounce_sec
        # (telegram_user_id, callback_data) -> monotonic time of first accept
        self._recent: Dict[tuple, float] = {}

    def _prune(self, now: float) -> None:
        if len(self._recent) < 200:
            return
        cutoff = now - max(5.0, self.debounce_sec * 3)
        self._recent = {k: t for k, t in self._recent.items() if t >= cutoff}

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        if not isinstance(event, CallbackQuery):
            return await handler(event, data)

        # 1) Instant ack — stops spinner so users don't mash the button
        try:
            await event.answer()
        except Exception:
            # Already answered, expired, or network blip — keep going
            pass
        data["callback_acked"] = True

        # Handlers often call callback.answer() again — make that a no-op so
        # they don't throw and skip sending the real reply.
        async def _already_answered(*_a, **_k):
            return True

        try:
            object.__setattr__(event, "answer", _already_answered)
        except Exception:
            try:
                event.answer = _already_answered  # type: ignore[method-assign]
            except Exception:
                pass

        uid = event.from_user.id if event.from_user else 0
        key = (uid, event.data or "")
        now = time.monotonic()
        last = self._recent.get(key)
        if last is not None and (now - last) < self.debounce_sec:
            logger.info(
                "[UX] debounce drop user=%s data=%s dt=%.2fs",
                uid,
                (event.data or "")[:48],
                now - last,
            )
            return None

        self._recent[key] = now
        self._prune(now)

        t0 = time.monotonic()
        try:
            return await handler(event, data)
        finally:
            elapsed = time.monotonic() - t0
            if elapsed >= _SLOW_HANDLER_SEC:
                logger.warning(
                    "[UX] slow callback %.2fs data=%s user=%s",
                    elapsed,
                    (event.data or "")[:64],
                    uid,
                )


async def safe_callback_answer(
    callback: CallbackQuery,
    text: Optional[str] = None,
    *,
    show_alert: bool = False,
) -> None:
    """Answer a callback if middleware did not already (or for toast text).

    Prefer empty instant ack via middleware; only use this when you need a
    short toast like \"Locking…\" and the query is still valid.
    """
    try:
        if text:
            await callback.answer(text, show_alert=show_alert)
        else:
            await callback.answer()
    except Exception:
        pass
