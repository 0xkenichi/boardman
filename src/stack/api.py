"""
Rematch Stack HTTP API v0 — discovery + public board for builders.

Money-moving routes stay on existing authenticated endpoints until v1.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter

from gaming.src.stack.facade import get_stack

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/stack/v0", tags=["rematch-stack"])


@router.get("/health")
async def stack_health():
    """Stack liveness and dependency checks."""
    return get_stack().health().to_dict()


@router.get("/catalog")
async def stack_catalog():
    """Capability discovery for builder clients."""
    return get_stack().capabilities().to_dict()


@router.get("/chains")
async def stack_chains(include_disabled: bool = False):
    """Settlement chains. Default: live only (Arc testnet). ?include_disabled=1 for roadmap."""
    chains = get_stack().list_chains(include_disabled=include_disabled)
    return {
        "success": True,
        "network": "testnet",
        "live": [c.id for c in chains if c.enabled],
        "chains": [c.to_dict() for c in chains],
    }


@router.get("/public/board")
async def stack_public_board():
    """Public leaderboard + open challenges (same shape as /api/rematch/public)."""
    try:
        return get_stack().public_board()
    except Exception as exc:
        logger.exception("[Stack] public board failed: %s", exc)
        return {
            "success": False,
            "leaderboard": [],
            "open_challenges": [],
            "metrics": {},
            "error": str(exc),
        }
