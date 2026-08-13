"""
flash_expiry_job.py - Background job to expire Flash Quests
Uses BullMQ (Redis-based) or simple cron scheduling.
"""

import os
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional
from backend.supabase_client import get_supabase
from dotenv import load_dotenv
import json

load_dotenv()

logger = logging.getLogger(__name__)

# ─── Clients ────────────────────────────────────────────────────────────────────
db = None

# ─── Configuration ──────────────────────────────────────────────────────────────
JOB_CHECK_INTERVAL = int(os.getenv("FLASH_EXPIRY_CHECK_INTERVAL", "60"))  # seconds
BATCH_SIZE = int(os.getenv("FLASH_EXPIRY_BATCH_SIZE", "100"))

# ────────────────────────────────────────────────────────────────────────────────

class FlashExpiryWorker:
    """
    Background worker that periodically scans for expired flash quests
    and processes their expiration (notifications, status updates).
    """
    
    def __init__(self):
        self.running = False
        self.worker_id = os.getenv("WORKER_ID", "worker-1")
    
    async def start(self):
        """Start the expiry worker loop."""
        global db
        # Initialize Supabase async client
        url = os.getenv("NEXT_PUBLIC_SUPABASE_URL") or os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY")
        if not url or not key:
            raise RuntimeError("Supabase credentials missing for flash expiry worker")
        db = await create_async_client(url, key)
        logger.info("Flash expiry worker DB connected")
        
        self.running = True
        logger.info(f"Flash expiry worker starting (check every {JOB_CHECK_INTERVAL}s)")
        
        while self.running:
            try:
                await self.check_and_expire_quests()
                await asyncio.sleep(JOB_CHECK_INTERVAL)
            except Exception as e:
                logger.error(f"Flash expiry worker error: {e}", exc_info=True)
                await asyncio.sleep(10)
    
    async def stop(self):
        """Stop the worker."""
        self.running = False
        logger.info("Flash expiry worker stopped")
    
    async def check_and_expire_quests(self):
        """
        Find all flash quests that have passed their expiry time
        and transition them to 'expired' status.
        """
        try:
            now = datetime.now(timezone.utc)
            
            # Find flash quests that are still 'open' but expired
            res = await db.table("quests") \
                .select("id, title, creator_id, is_flash, expires_at, status") \
                .eq("is_flash", True) \
                .eq("status", "open") \
                .lte("expires_at", now.isoformat()) \
                .limit(BATCH_SIZE) \
                .execute()
            
            expired_quests = res.data or []
            
            if not expired_quests:
                logger.debug("No flash quests to expire")
                return
            
            logger.info(f"Expiring {len(expired_quests)} flash quests")
            
            for quest in expired_quests:
                await self._expire_quest(quest)
            
        except Exception as e:
            logger.error(f"Error checking flash expiry: {e}", exc_info=True)
    
    async def _expire_quest(self, quest: Dict[str, Any]):
        """
        Expire a single flash quest: update status, notify owner, notify participants.
        """
        quest_id = quest["id"]
        quest_title = quest.get("title", "Unknown")
        creator_id = quest.get("creator_id")
        
        try:
            # 1. Update quest status to 'expired'
            await db.table("quests") \
                .update({"status": "expired"}) \
                .eq("id", quest_id) \
                .execute()
            
            logger.info(f"Flash quest expired: {quest_id} ({quest_title})")
            
            # 2. Log expiry event
            await db.table("flash_expiry_log").insert({
                "quest_id": quest_id,
                "scheduled_expiry": quest["expires_at"],
                "actual_expiry": datetime.now(timezone.utc).isoformat(),
                "status": "expired",
                "processed_by": self.worker_id
            }).execute()
            
            # 3. Notify quest creator
            if creator_id:
                from notification_services import NotificationDispatcher
                await NotificationDispatcher.dispatch(
                    recipient_id=creator_id,
                    notification_type="flash_expiry",
                    title="Your Flash Quest expired",
                    body=f"'{quest_title}' didn't get participants in time.",
                    data={"quest_id": quest_id, "is_flash": True},
                    priority="normal",
                    force_channels=["in_app"]
                )
            
            # 4. Notify participants who joined (if any) that quest expired
            participants_res = await db.table("quest_participants") \
                .select("profile_id") \
                .eq("quest_id", quest_id) \
                .execute()
            
            participants = participants_res.data or []
            
            for p in participants:
                await NotificationDispatcher.dispatch(
                    recipient_id=p["profile_id"],
                    notification_type="flash_expiry",
                    title="Flash Quest expired",
                    body=f"'{quest_title}' has expired.",
                    data={"quest_id": quest_id, "is_flash": True},
                    priority="low",
                    force_channels=["in_app"]
                )
            
        except Exception as e:
            logger.error(f"Error expiring quest {quest_id}: {e}", exc_info=True)
            # Log failure
            try:
                await db.table("flash_expiry_log").insert({
                    "quest_id": quest_id,
                    "scheduled_expiry": quest["expires_at"],
                    "status": "failed",
                    "error_message": str(e),
                    "processed_by": self.worker_id
                }).execute()
            except:
                pass


# ─── Job Scheduling ─────────────────────────────────────────────────────────────

async def schedule_flash_expiry_job(
    quest_id: str,
    expires_at: datetime
) -> Optional[str]:
    """
    Schedule a flash quest expiry job (persistent, survives restarts).
    Uses BullMQ-style delayed job record in DB.
    """
    try:
        # Create a temporary async Supabase client to avoid dependency on global db
        url = os.getenv("NEXT_PUBLIC_SUPABASE_URL") or os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY")
        if not url or not key:
            raise RuntimeError("Supabase credentials missing for scheduling")
        temp_db = await create_async_client(url, key)
        
        job_id = f"flash-expiry-{quest_id}-{int(expires_at.timestamp())}"
        
        await temp_db.table("flash_expiry_log").insert({
            "job_id": job_id,
            "quest_id": quest_id,
            "scheduled_expiry": expires_at.isoformat(),
            "status": "pending"
        }).execute()
        
        logger.info(f"Flash expiry job scheduled: quest={quest_id} expires_at={expires_at}")
        return job_id
        
    except Exception as e:
        logger.error(f"Failed to schedule flash expiry job: {e}")
        return None


async def cancel_flash_expiry_job(quest_id: str) -> bool:
    """
    Cancel a pending flash expiry job (if quest was deleted or extended).
    """
    try:
        result = await db.table("flash_expiry_log") \
            .update({"status": "cancelled"}) \
            .eq("quest_id", quest_id) \
            .eq("status", "pending") \
            .execute()
        
        cancelled = len(result.data) > 0 if result.data else False
        if cancelled:
            logger.info(f"Flash expiry job cancelled for quest {quest_id}")
        return cancelled
        
    except Exception as e:
        logger.error(f"Failed to cancel flash expiry job: {e}")
        return False


# ─── Worker Entry Point ──────────────────────────────────────────────────────────

async def main():
    """Run flash expiry worker as standalone process."""
    global db

    # Initialize DB
    db = get_supabase()
    
    worker = FlashExpiryWorker()
    
    try:
        await worker.start()
    except KeyboardInterrupt:
        logger.info("Shutting down flash expiry worker...")
        await worker.stop()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s"
    )
    asyncio.run(main())
