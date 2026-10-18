"""Paycrest naira rail HTTP surface.

* ``POST /webhooks/paycrest``: Paycrest order updates. Verified with
  ``X-Paycrest-Signature`` (hex HMAC-SHA256 of the raw body, keyed with the
  Paycrest API Secret), fail closed; deduped by body hash; answered 2xx at
  once (Paycrest retries non-2xx for 24 h) with slow chain work deferred.
  Exempt from the geo-fence like every ``/webhooks/`` route.
* ``GET/POST /api/channels/naira/{token}``: backend of the one-time naira
  page (KYC + refund account → Paycrest order → virtual account to pay).
  Platform only (the Vercel BFF with the master key), like the withdraw
  page; the POST is a geo-fenced money route.

Every route answers 404 while the rail is off (``PAYCREST_ENABLED`` and
``REAL_MONEY_ENABLED`` both required).
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, Header, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from gaming.src.backend.api.channels_web import require_platform
from gaming.src.backend.services.paycrest import config
from gaming.src.backend.services.paycrest.client import verify_signature
from gaming.src.channels.core.withdraw_links import LinkRefused

logger = logging.getLogger(__name__)

router = APIRouter(tags=["paycrest"])

MAX_BODY = 256 * 1024
NO_STORE = {"Cache-Control": "no-store"}


def _off() -> JSONResponse:
    return JSONResponse({"ok": False, "error": "not_found"}, status_code=404)


@router.post("/webhooks/paycrest")
async def paycrest_webhook(
    request: Request,
    background: BackgroundTasks,
    x_paycrest_signature: Optional[str] = Header(default=None, alias="X-Paycrest-Signature"),
):
    if not config.enabled():
        return _off()
    raw = await request.body()
    if len(raw) > MAX_BODY:
        return JSONResponse({"ok": False, "error": "too_large"}, status_code=413)
    if not verify_signature(raw, x_paycrest_signature, config.api_secret()):
        logger.warning("[paycrest] webhook signature rejected")
        return JSONResponse({"ok": False, "error": "bad_signature"}, status_code=401)
    from gaming.src.backend.services.paycrest import events

    def defer(fn, *args) -> None:
        background.add_task(fn, *args)

    out = await asyncio.to_thread(events.handle_webhook, raw, defer=defer)
    return JSONResponse(out, status_code=200)


class KycBody(BaseModel):
    full_name: str = Field(min_length=3, max_length=120)
    birth_date: str = Field(min_length=10, max_length=10)
    id_type: str = Field(min_length=3, max_length=16)
    id_number: str = Field(min_length=11, max_length=16)
    email: Optional[str] = Field(default=None, max_length=120)
    phone: Optional[str] = Field(default=None, max_length=20)

    def __repr__(self) -> str:  # never log KYC
        return "KycBody(<redacted>)"


class RefundBody(BaseModel):
    institution: str = Field(min_length=4, max_length=16)
    account_identifier: str = Field(min_length=10, max_length=12)


class NairaSubmit(BaseModel):
    kyc: KycBody
    refund: RefundBody


def _refused(exc: LinkRefused) -> JSONResponse:
    return JSONResponse(exc.body(), status_code=exc.status_code, headers=NO_STORE)


@router.get("/api/channels/naira/{token}")
async def naira_view(token: str, caller: Optional[str] = Depends(require_platform)):
    if not config.enabled():
        return _off()
    from gaming.src.backend.services.paycrest import onramp

    try:
        out = await asyncio.to_thread(onramp.view, token, session_profile_id=caller)
    except LinkRefused as exc:
        return _refused(exc)
    return JSONResponse(out, headers=NO_STORE)


@router.post("/api/channels/naira/{token}")
async def naira_submit(token: str, body: NairaSubmit, caller: Optional[str] = Depends(require_platform)):
    if not config.enabled():
        return _off()
    from gaming.src.backend.services.paycrest import onramp

    try:
        out = await asyncio.to_thread(
            onramp.submit, token, kyc=body.kyc.model_dump(), refund=body.refund.model_dump(),
            session_profile_id=caller,
        )
    except LinkRefused as exc:
        return _refused(exc)
    return JSONResponse(out, status_code=200 if out.get("ok") else 422, headers=NO_STORE)
