"""
gaming.py - Gaming quest specific endpoints

Integrates with existing staking, AI verification, and blockchain systems.
For quest_type: 'gaming' only.
"""

import logging

from fastapi import APIRouter

from backend.supabase_client import get_supabase
from backend.utils.errors import safe_error_response

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/gaming", tags=["gaming"])


@router.get("/status")
async def gaming_status():
    return {"status": "active", "message": "Gaming vertical is live via Telegram bot"}


@router.get("/active-matches")
async def get_active_matches():
    """Get all active (OPEN/LOCKED) matches."""
    supabase = get_supabase()
    try:
        result = supabase.table("bets").select("*").in_(
            "status", ["OPEN", "LOCKED"]
        ).order("created_at", desc=True).limit(50).execute()
        matches = result.data if result.data else []
        return {"success": True, "matches": matches, "count": len(matches)}
    except Exception as e:
        logger.error(f"Error fetching active matches: {e}", exc_info=True)
        raise safe_error_response(500, "Failed to load active matches", e)


@router.get("/match/{match_id}")
async def get_match_details(match_id: str):
    """Get full details for a specific match."""
    supabase = get_supabase()
    try:
        result = supabase.table("bets").select("*").or_(
            f"short_id.eq.{match_id},id.eq.{match_id}"
        ).single().execute()
        if not result.data:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Match not found")
        return {"success": True, "match": result.data}
    except Exception as e:
        logger.error(f"Error fetching match {match_id}: {e}", exc_info=True)
        raise safe_error_response(500, "Failed to load match details", e)


@router.get("/leaderboard")
async def get_gaming_leaderboard():
    """Get top players by wins."""
    supabase = get_supabase()
    try:
        result = supabase.table("profiles").select(
            "id, display_name, total_wins, total_losses, play_points"
        ).order("total_wins", desc=True).limit(20).execute()
        players = result.data if result.data else []
        return {"success": True, "leaderboard": players}
    except Exception as e:
        logger.error(f"Error fetching leaderboard: {e}", exc_info=True)
        raise safe_error_response(500, "Failed to load leaderboard", e)