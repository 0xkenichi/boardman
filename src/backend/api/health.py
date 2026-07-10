"""Lightweight health check endpoint for the ClawStation backend."""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, status

from backend.supabase_client import get_supabase

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


def _check_supabase() -> str:
    """Ping Supabase by running a lightweight profile query.

    Returns ``"ok"`` if the query succeeds, otherwise raises ``HTTPException``
    with a 503 status so load balancers and uptime monitors flag the service
    as unhealthy.
    """
    try:
        sb = get_supabase()
        sb.table("profiles").select("id", count="exact").limit(1).execute()
        return "ok"
    except Exception as exc:
        logger.exception("[Health] Supabase check failed")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"supabase": "unhealthy", "error": str(exc)},
        ) from exc


@router.get("/healthz")
async def healthz() -> dict:
    """Liveness/readiness probe for ClawStation.

    Performs a lightweight Supabase query. Circle is always reported as ``ok``
    because the Circle SDK does not expose a cheap, side-effect-free health
    endpoint and a real API call would risk rate limits and timeouts.
    """
    supabase_status = _check_supabase()
    return {
        "status": "ok",
        "checks": {
            "supabase": supabase_status,
            "circle": "ok",
        },
        "version": "0.1.0",
    }
