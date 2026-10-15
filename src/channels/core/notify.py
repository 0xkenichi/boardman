"""One door for proactive notices (CHANNELS_DESIGN §4.3).

``notify(profile_id, Notice)`` picks the profile's identities in
``notify_priority`` order and, per identity:

* Telegram: free-form message, any time (today's ``notify_user``).
* WhatsApp: needs recorded opt-in. Inside the 24 h customer-service window
  (last inbound < 23 h ago, an hour of margin) it sends a free-form session
  message; outside it sends the approved utility template for the notice kind
  (``whatsapp/templates.py``); with no template for the kind, it skips.

The first delivery wins unless ``all_channels`` (security notices). Every
attempt is written to ``channel_outbox``; WhatsApp status webhooks update it.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Optional, Protocol

from gaming.src.channels.core import store
from gaming.src.channels.core.identity.repo import Identity, IdentityRepo, get_repo, utcnow
from gaming.src.channels.core.messages import Option, Out, Text, Choice

logger = logging.getLogger(__name__)

WINDOW = timedelta(hours=23)


@dataclass
class Notice:
    kind: str  # template key: account_linked, deposit_received, match_result, ...
    params: dict[str, Any] = field(default_factory=dict)
    text: str = ""  # the free-form body (window / Telegram)
    options: list[Option] = field(default_factory=list)
    # Quick-reply payloads for the template, in the template's button order.
    # Defaults to the option ids when empty.
    template_payloads: list[str] = field(default_factory=list)

    def payloads(self, n: int) -> list[str]:
        src = self.template_payloads or [o.id for o in self.options]
        return list(src)[:n]

    def as_outs(self) -> list[Out]:
        if self.options:
            return [Choice(self.text, list(self.options))]
        return [Text(self.text)]


@dataclass
class Delivery:
    channel: str
    mode: str  # session | template | skipped
    ok: bool
    template: Optional[str] = None
    provider_message_id: Optional[str] = None
    error: Optional[str] = None


class Deliverer(Protocol):
    channel: str

    async def send_session(self, ident: Identity, outs: list[Out]) -> Optional[str]: ...

    async def send_template(self, ident: Identity, notice: Notice) -> tuple[Optional[str], Optional[str]]:
        """Returns (template name or None if the kind has none, provider id)."""
        ...


def in_window(ident: Identity, now: datetime) -> bool:
    return ident.last_inbound_at is not None and ident.last_inbound_at > now - WINDOW


def _record(profile_id: str, ident: Identity, notice: Notice, d: Delivery) -> None:
    try:
        now = store.now_ms()
        with store.db().transaction() as tx:
            tx.execute(
                "INSERT INTO channel_outbox (channel, external_id, profile_id, kind, mode, template, "
                "provider_message_id, status, error, created_at_ms, updated_at_ms) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (ident.channel, ident.external_id, profile_id, notice.kind, d.mode, d.template,
                 d.provider_message_id, "sent" if d.ok else "failed", (d.error or "")[:300] or None,
                 now, now),
            )
    except Exception:
        logger.warning("[notify] outbox write failed", exc_info=True)


def update_status(provider_message_id: str, status: str, error: Optional[str] = None) -> int:
    """Apply a delivery receipt (sent / delivered / read / failed)."""
    with store.db().transaction() as tx:
        return tx.rowcount(
            "UPDATE channel_outbox SET status = ?, error = COALESCE(?, error), updated_at_ms = ? "
            "WHERE provider_message_id = ?",
            (status, error, store.now_ms(), provider_message_id),
        )


class NotificationService:
    def __init__(self, deliverers: dict[str, Deliverer], repo: Optional[IdentityRepo] = None) -> None:
        self.deliverers = deliverers
        self._repo = repo

    @property
    def repo(self) -> IdentityRepo:
        return self._repo or get_repo()

    async def notify(self, profile_id: str, notice: Notice, *, all_channels: bool = False,
                     exclude: Optional[tuple[str, str]] = None,
                     only: Optional[set[str]] = None,
                     now: Optional[datetime] = None) -> list[Delivery]:
        now = now or utcnow()
        idents = await asyncio.to_thread(self.repo.for_profile, profile_id)
        results: list[Delivery] = []
        for ident in idents:
            if exclude and (ident.channel, ident.external_id) == exclude:
                continue
            if only is not None and ident.channel not in only:
                continue
            d = await self._deliver(ident, notice, now)
            if d is None:
                continue
            results.append(d)
            await asyncio.to_thread(_record, profile_id, ident, notice, d)
            if d.ok and not all_channels:
                break
        return results

    async def _deliver(self, ident: Identity, notice: Notice, now: datetime) -> Optional[Delivery]:
        dv = self.deliverers.get(ident.channel)
        if dv is None:
            return None
        if ident.opted_out_at is not None and (ident.opted_in_at is None or ident.opted_out_at >= ident.opted_in_at):
            return None
        try:
            if ident.channel == "whatsapp":
                if not ident.opted_in:
                    return None
                if in_window(ident, now):
                    pid = await dv.send_session(ident, notice.as_outs())
                    return Delivery(ident.channel, "session", True, provider_message_id=pid)
                name, pid = await dv.send_template(ident, notice)
                if name is None:
                    return Delivery(ident.channel, "skipped", False, error="no template for kind")
                return Delivery(ident.channel, "template", True, template=name, provider_message_id=pid)
            pid = await dv.send_session(ident, notice.as_outs())
            return Delivery(ident.channel, "session", pid is not None, provider_message_id=pid or None)
        except Exception as exc:
            logger.warning("[notify] %s delivery failed", ident.channel, exc_info=True)
            return Delivery(ident.channel, "session", False, error=type(exc).__name__)


class TelegramDeliverer:
    """Telegram has no window or templates: render and use ``notify_user``."""

    channel = "telegram"

    async def send_session(self, ident: Identity, outs: list[Out]) -> Optional[str]:
        from gaming.src.bot.utils.notify import notify_user
        from gaming.src.channels.telegram.render import render_for_notify

        text, markup = render_for_notify(outs)
        ok = await notify_user(ident.profile_id, text, buttons=markup, direct=True)
        return "" if ok else None  # Telegram ids are not tracked

    async def send_template(self, ident: Identity, notice: Notice):
        return None, None


_override: Optional[NotificationService] = None


def set_default_service(svc: Optional[NotificationService]) -> None:
    """Install a service for this process (tests; ``None`` restores the default)."""
    global _override
    _override = svc


def default_service() -> NotificationService:
    if _override is not None:
        return _override
    deliverers: dict[str, Deliverer] = {"telegram": TelegramDeliverer()}
    try:
        from gaming.src.channels import config

        if config.whatsapp_enabled():
            from gaming.src.channels.whatsapp.deliver import WhatsAppDeliverer
            from gaming.src.channels.whatsapp.client import client_from_env

            client = client_from_env()
            if client is not None:
                deliverers["whatsapp"] = WhatsAppDeliverer(client)
    except Exception:
        logger.warning("[notify] WhatsApp deliverer unavailable", exc_info=True)
    return NotificationService(deliverers)


async def notify(profile_id: str, notice: Notice, **kw: Any) -> list[Delivery]:
    """Module-level convenience: the default service."""
    return await default_service().notify(profile_id, notice, **kw)
