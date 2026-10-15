"""WhatsApp side of ``core.notify``: session messages and utility templates."""
from __future__ import annotations

import asyncio
from typing import Any, Optional

from gaming.src.channels.core.identity.repo import Identity
from gaming.src.channels.core.messages import Out
from gaming.src.channels.whatsapp import render, templates


class WhatsAppDeliverer:
    channel = "whatsapp"

    def __init__(self, client: Any) -> None:
        self.client = client

    def _to(self, ident: Identity) -> str:
        return ident.address or ident.external_id

    async def send_session(self, ident: Identity, outs: list[Out]) -> Optional[str]:
        last = None
        for msg in render.render_all(outs):
            render.validate(msg)
            last = await asyncio.to_thread(self.client.send, self._to(ident), msg)
        return last

    async def send_template(self, ident: Identity, notice: Any) -> tuple[Optional[str], Optional[str]]:
        tpl = templates.for_kind(notice.kind)
        if tpl is None:
            return None, None
        payloads = [o.id for o in getattr(notice, "options", [])][: len(tpl.buttons)]
        msg = templates.message(tpl, notice.params, payloads)
        wamid = await asyncio.to_thread(self.client.send, self._to(ident), msg)
        return tpl.name, wamid
