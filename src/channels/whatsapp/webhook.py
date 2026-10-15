"""``/webhooks/whatsapp``: Meta's verification handshake and signed deliveries.

Mounted only when ``WHATSAPP_ENABLED=1`` (``src/backend/main.py``). ``/webhooks/``
is a geo-fence exempt prefix: Meta calls from US data centres, and US is on
the blocked list. Authentication is the HMAC signature instead.

POST acks fast: verify the signature on the raw bytes, parse, dedupe on the
wamid, queue, and process after the response (FastAPI background task).
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Query, Request
from fastapi.responses import JSONResponse, PlainTextResponse

from gaming.src.channels.whatsapp import inbound
from gaming.src.channels.whatsapp.parse import parse
from gaming.src.channels.whatsapp.signature import verify_signature, verify_subscription

logger = logging.getLogger(__name__)

router = APIRouter(tags=["whatsapp"])


@router.get("/webhooks/whatsapp")
def whatsapp_verify(
    hub_mode: Optional[str] = Query(default=None, alias="hub.mode"),
    hub_verify_token: Optional[str] = Query(default=None, alias="hub.verify_token"),
    hub_challenge: Optional[str] = Query(default=None, alias="hub.challenge"),
):
    challenge = verify_subscription(hub_mode, hub_verify_token, hub_challenge)
    if challenge is None:
        return PlainTextResponse("forbidden", status_code=403)
    return PlainTextResponse(challenge)


def _enqueue_all(events, statuses) -> list:
    fresh = [ev for ev in events if inbound.enqueue(ev)]
    if statuses:
        from gaming.src.channels.core.notify import update_status

        for s in statuses:
            try:
                if s.message_id:
                    update_status(s.message_id, s.status, s.error)
            except Exception:
                logger.warning("[whatsapp] status update failed", exc_info=True)
    return fresh


def _process(events) -> None:
    from gaming.src.channels.whatsapp.client import client_from_env

    client = client_from_env()
    if client is None:
        logger.error("[whatsapp] WHATSAPP_ACCESS_TOKEN / WHATSAPP_PHONE_NUMBER_ID not set; replies dropped")
        return
    inbound.process(events, client, media_client=client)


@router.post("/webhooks/whatsapp")
async def whatsapp_receive(request: Request, background: BackgroundTasks):
    raw = await request.body()
    if not verify_signature(raw, request.headers.get("x-hub-signature-256")):
        logger.warning("[whatsapp] rejected webhook: bad or missing signature")
        return JSONResponse({"ok": False, "error": "bad_signature"}, status_code=401)
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return JSONResponse({"ok": False, "error": "bad_json"}, status_code=400)
    events, statuses = parse(payload)
    fresh = await asyncio.to_thread(_enqueue_all, events, statuses)
    if fresh:
        background.add_task(_process, fresh)
    return {"ok": True, "queued": len(fresh)}
