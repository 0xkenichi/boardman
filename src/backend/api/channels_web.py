"""Backend for the web withdraw page (``/app/withdraw/<token>``).

Called only by the Vercel BFF with the master key. ``X-Boardman-Caller`` is
the signed-in web session's profile when there is one; a link opened in a
session for another account is refused. The POST is a geo-fenced money route
(``config/compliance/geo_fence.json``), so the browser's country is checked
too. The link token is the bearer; the PIN is the second factor.
"""
from __future__ import annotations

import asyncio
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from gaming.src.backend.rematch_auth import extract_api_key, resolve_api_key
from gaming.src.channels.core import withdraw_links
from gaming.src.channels.core.withdraw_links import LinkRefused

router = APIRouter(prefix="/api/channels", tags=["channels"])


def require_platform(
    x_rematch_key: Optional[str] = Header(default=None, alias="X-Rematch-Key"),
    x_boardman_key: Optional[str] = Header(default=None, alias="X-Boardman-Key"),
    x_stack_key: Optional[str] = Header(default=None, alias="X-Stack-Key"),
    authorization: Optional[str] = Header(default=None),
    x_boardman_caller: Optional[str] = Header(default=None, alias="X-Boardman-Caller"),
) -> Optional[str]:
    principal = resolve_api_key(extract_api_key(
        x_rematch_key=x_rematch_key, x_boardman_key=x_boardman_key,
        x_stack_key=x_stack_key, authorization=authorization,
    ))
    if principal is None:
        raise HTTPException(status_code=401, detail="invalid or missing API key")
    if not principal.is_master:
        raise HTTPException(status_code=403, detail="channels routes are platform only")
    return (x_boardman_caller or "").strip() or None


class ConfirmBody(BaseModel):
    pin: str = Field(min_length=1, max_length=64)
    pin_confirm: Optional[str] = Field(default=None, max_length=64)
    amount: Optional[str] = Field(default=None, max_length=32)


def _refused(exc: LinkRefused) -> JSONResponse:
    return JSONResponse(exc.body(), status_code=exc.status_code, headers={"Cache-Control": "no-store"})


@router.get("/withdraw/{token}")
async def withdraw_link_view(token: str, caller: Optional[str] = Depends(require_platform)):
    try:
        return await asyncio.to_thread(withdraw_links.view, token, session_profile_id=caller)
    except LinkRefused as exc:
        return _refused(exc)


@router.post("/withdraw/{token}")
async def withdraw_link_confirm(token: str, body: ConfirmBody,
                                caller: Optional[str] = Depends(require_platform)):
    try:
        out = await withdraw_links.confirm(
            token, pin=body.pin, pin_confirm=body.pin_confirm, amount=body.amount,
            session_profile_id=caller,
        )
    except LinkRefused as exc:
        return _refused(exc)
    return JSONResponse(out, status_code=200 if out.get("ok") else 422, headers={"Cache-Control": "no-store"})
