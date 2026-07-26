"""Public Rematch API endpoints used by the frontend at /rematch/*."""
from __future__ import annotations

import logging

from fastapi import APIRouter

from gaming.src.backend.services.rematch_public import (
    get_leaderboard,
    get_open_public_challenges,
    get_chain_metrics,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/rematch", tags=["rematch"])


@router.get("/public")
async def rematch_public():
    """Return the public rematch data consumed by the frontend leaderboard page.

    Response shape mirrors what the frontend expects: { leaderboard, open_challenges, metrics }
    """
    try:
        leaderboard = get_leaderboard(25)
        open_challenges = get_open_public_challenges(30)
        metrics = get_chain_metrics()
        return {
            "success": True,
            "leaderboard": leaderboard,
            "open_challenges": open_challenges,
            "metrics": metrics,
        }
    except Exception as exc:  # pragma: no cover - best-effort public endpoint
        logger.exception("Failed to build rematch public payload: %s", exc)
        return {"success": False, "leaderboard": [], "open_challenges": [], "metrics": {}}
