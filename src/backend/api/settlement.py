"""
Settlement admin API.

Endpoints:
  POST /settlement/run                  — settle all ready challenges (api key)
  POST /settlement/{id}                 — settle a single challenge (api key)
  POST /settlement/{id}/admin_resolve   — admin picks winner for dispute
"""
from __future__ import annotations

import logging
import os
import secrets

from fastapi import APIRouter, Header, HTTPException, Request

from gaming.src.backend.services.clawstation_settlement import (
    SettlementError,
    admin_resolve_challenge,
    settle_all_pending,
    settle_challenge,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/settlement", tags=["settlement"])


def _require_key(request: Request, x_api_key: str | None = Header(default=None)) -> None:
    """Validate the settlement API key from header or env fallback."""
    expected = os.getenv("SETTLEMENT_API_KEY")
    if not expected:
        logger.error("[SettlementAPI] SETTLEMENT_API_KEY not configured")
        raise HTTPException(status_code=500, detail="Settlement API key not configured")

    provided = x_api_key or request.headers.get("x-api-key")
    if not provided:
        raise HTTPException(status_code=401, detail="Missing X-API-Key header")
    if not secrets.compare_digest(provided, expected):
        raise HTTPException(status_code=403, detail="Invalid API key")


@router.post("/run")
async def run_settlement(
    request: Request,
    x_api_key: str | None = Header(default=None),
) -> dict:
    """Resolve all challenges that are ready for settlement."""
    _require_key(request, x_api_key)
    try:
        results = await settle_all_pending()
        return {"success": True, "results": results}
    except Exception as exc:
        logger.exception("[SettlementAPI] Bulk settlement failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/{challenge_id}")
async def settle_one(
    challenge_id: str,
    request: Request,
    x_api_key: str | None = Header(default=None),
) -> dict:
    """Resolve a single challenge by ID."""
    _require_key(request, x_api_key)
    try:
        result = await settle_challenge(challenge_id)
        return result
    except SettlementError as exc:
        logger.warning("[SettlementAPI] Settlement error for %s: %s", challenge_id, exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("[SettlementAPI] Settlement failed for %s", challenge_id)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/{challenge_id}/admin_resolve")
async def admin_resolve(
    challenge_id: str,
    request: Request,
    body: dict,
    x_api_key: str | None = Header(default=None),
) -> dict:
    """Admin override: resolve a disputed challenge by picking the winner."""
    _require_key(request, x_api_key)
    winner_id = body.get("winner_id")
    admin_profile_id = body.get("admin_profile_id")
    note = body.get("note")

    if not winner_id or not admin_profile_id:
        raise HTTPException(status_code=400, detail="winner_id and admin_profile_id required")

    try:
        result = await admin_resolve_challenge(challenge_id, admin_profile_id, winner_id, note)
        return result
    except SettlementError as exc:
        logger.warning("[SettlementAPI] Admin resolve error for %s: %s", challenge_id, exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("[SettlementAPI] Admin resolve failed for %s", challenge_id)
        raise HTTPException(status_code=500, detail=str(exc)) from exc
