"""Backend of the passkey wallet pages (``/app/wallet/setup``, ``/app/approve/<token>``).

Called only by the Vercel BFF with the master key, like the withdraw page;
``X-Boardman-Caller`` is the signed-in web session's profile when there is
one. Every route answers 404 while ``SELF_CUSTODY_WALLETS_ENABLED`` is off.

The approve POST does not move money (the player's passkey already did): it
records the hashes and asks the chain. A match advances only on the escrow's
own event, never on this request.
"""
from __future__ import annotations

import asyncio
from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from gaming.src.backend.api.channels_web import require_platform
from gaming.src.backend.services.self_custody import config
from gaming.src.backend.services.self_custody.intents import IntentRefused

router = APIRouter(prefix="/api/self-custody", tags=["self-custody"])

NO_STORE = {"Cache-Control": "no-store"}


def _off() -> JSONResponse:
    return JSONResponse({"ok": False, "error": "not_found"}, status_code=404, headers=NO_STORE)


def _refused(exc: IntentRefused) -> JSONResponse:
    return JSONResponse(exc.body(), status_code=exc.status_code, headers=NO_STORE)


class RegisterBody(BaseModel):
    address: str = Field(min_length=42, max_length=42)
    credential_id: str = Field(min_length=8, max_length=512)


class SubmitBody(BaseModel):
    tx_hash: str = Field(min_length=66, max_length=66)
    user_op_hash: Optional[str] = Field(default=None, max_length=66)
    amount: str = Field(min_length=1, max_length=32)
    challenge_id: Optional[str] = Field(default=None, max_length=64)


@router.get("/setup")
async def setup_view(t: Optional[str] = Query(default=None, max_length=128),
                     caller: Optional[str] = Depends(require_platform)):
    if not config.enabled():
        return _off()
    from gaming.src.backend.services.self_custody import setup

    try:
        out = await asyncio.to_thread(setup.view, t, caller=caller)
    except IntentRefused as exc:
        return _refused(exc)
    return JSONResponse(out, headers=NO_STORE)


@router.post("/setup")
async def setup_register(body: RegisterBody, t: Optional[str] = Query(default=None, max_length=128),
                         caller: Optional[str] = Depends(require_platform)):
    if not config.enabled():
        return _off()
    from gaming.src.backend.services.self_custody import notices, setup

    try:
        out = await asyncio.to_thread(setup.register, t, address=body.address,
                                      credential_id=body.credential_id, caller=caller)
    except IntentRefused as exc:
        return _refused(exc)
    if out.pop("created", False):
        await notices.wallet_linked(out["profile_id"], out["address"])
    out.pop("profile_id", None)
    return JSONResponse(out, headers=NO_STORE)


@router.get("/approve/{token}")
async def approve_view(token: str, caller: Optional[str] = Depends(require_platform)):
    if not config.enabled():
        return _off()
    from gaming.src.backend.services.self_custody import intents

    try:
        out = await asyncio.to_thread(intents.view, token, session_profile_id=caller)
    except IntentRefused as exc:
        return _refused(exc)
    return JSONResponse(out, headers=NO_STORE)


@router.post("/approve/{token}")
async def approve_submit(token: str, body: SubmitBody, caller: Optional[str] = Depends(require_platform)):
    if not config.enabled():
        return _off()
    from gaming.src.backend.services.self_custody import intents, notices

    try:
        out = await asyncio.to_thread(
            intents.submit, token, tx_hash=body.tx_hash, user_op_hash=body.user_op_hash, amount=body.amount,
            challenge_id=body.challenge_id, session_profile_id=caller,
        )
    except IntentRefused as exc:
        return _refused(exc)
    if out.pop("newly_confirmed", False):
        await notices.confirmed(out["intent_id"])
    out.pop("intent_id", None)
    return JSONResponse(out, status_code=200 if out.get("ok") else 422, headers=NO_STORE)
