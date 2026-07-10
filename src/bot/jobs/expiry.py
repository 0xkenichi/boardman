"""APScheduler job that expires stale open challenges."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from backend.supabase_client import get_supabase

logger = logging.getLogger(__name__)


def _get_supabase():
    return get_supabase()


async def expire_challenges() -> int:
    """Flip ``gaming.challenges`` rows that are still open past their expiry.

    Returns the number of rows updated.
    """
    sb = _get_supabase()
    now = datetime.now(timezone.utc).isoformat()
    try:
        result = (
            sb.schema("gaming")
            .table("challenges")
            .update({"status": "expired"})
            .eq("status", "open")
            .lt("expires_at", now)
            .execute()
        )
        expired = len(result.data) if result.data else 0
        logger.info("[Expiry] Expired %s stale challenge(s)", expired)
        return expired
    except Exception:
        logger.exception("[Expiry] Failed to expire stale challenges")
        return 0


def start_expiry_scheduler(interval_minutes: int = 5) -> AsyncIOScheduler:
    """Start an async scheduler that runs ``expire_challenges`` periodically."""
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        expire_challenges,
        "interval",
        minutes=interval_minutes,
        id="clawstation_challenge_expiry",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("[Expiry] Scheduler started (interval=%sm)", interval_minutes)
    return scheduler
