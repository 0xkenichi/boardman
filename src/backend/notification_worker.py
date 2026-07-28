"""
notification_worker.py - Background worker for processing queued notifications
Consumes email_queue and sms_queue tables, sends via external APIs.
"""

import os
import asyncio
import logging
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from supabase import create_async_client, Client
from dotenv import load_dotenv
import json

load_dotenv()

logger = logging.getLogger(__name__)

# ─── Configuration ──────────────────────────────────────────────────────────────
db: Client = None
WORKER_ID = os.getenv("WORKER_ID", "notification-worker-1")
BATCH_SIZE = int(os.getenv("NOTIFICATION_BATCH_SIZE", "50"))
POLL_INTERVAL = int(os.getenv("NOTIFICATION_POLL_INTERVAL", "10"))

# ────────────────────────────────────────────────────────────────────────────────

class NotificationWorker:
    """
    Background worker that processes the email_queue and sms_queue tables.
    Runs continuously, picks up pending notifications, dispatches to external services.
    """
    
    def __init__(self):
        self.running = False
    
    async def start(self):
        """Start notification processing loop."""
        global db
        
        db = await create_async_client(
            os.getenv("NEXT_PUBLIC_SUPABASE_URL") or os.getenv("SUPABASE_URL"),
            os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY")
        )
        
        self.running = True
        logger.info("Notification worker starting")
        
        while self.running:
            try:
                # Process email queue
                await self._process_email_queue()
                
                # Process SMS queue
                await self._process_sms_queue()
                
                # Wait before next batch
                await asyncio.sleep(POLL_INTERVAL)
                
            except Exception as e:
                logger.error(f"Notification worker error: {e}", exc_info=True)
                await asyncio.sleep(5)
    
    async def stop(self):
        self.running = False
        logger.info("Notification worker stopped")
    
    # ─── Email Queue ──────────────────────────────────────────────────────────────
    
    async def _process_email_queue(self):
        """Fetch and send pending emails."""
        try:
            # Get batch of pending emails scheduled for now or earlier
            now = datetime.now(timezone.utc).isoformat()
            
            res = await db.table("email_queue") \
                .select("*") \
                .eq("status", "pending") \
                .lte("scheduled_at", now) \
                .limit(BATCH_SIZE) \
                .execute()
            
            emails = res.data or []
            
            for email in emails:
                await self._send_email(email)
                
        except Exception as e:
            logger.error(f"Email queue processing error: {e}")
    
    async def _send_email(self, email_record: Dict):
        """Send a single queued email."""
        email_id = email_record["id"]
        
        try:
            from notification_services import EmailService
            
            result = await EmailService.send(
                to_email=email_record["recipient_email"],
                subject=email_record["subject"],
                html_body=email_record.get("body_html", ""),
                text_body=email_record.get("body_text"),
                profile_id=email_record.get("profile_id"),
                notification_id=email_record.get("notification_id")
            )
            
            if result["success"]:
                # Status updated by EmailService._log_sent
                logger.info(f"Email sent: id={email_id}")
            else:
                await self._mark_failed("email_queue", email_id, result["error"])
                
        except Exception as e:
            logger.error(f"Email send failed for queue id {email_id}: {e}")
            await self._mark_failed("email_queue", email_id, str(e))
    
    # ─── SMS Queue ────────────────────────────────────────────────────────────────
    
    async def _process_sms_queue(self):
        """Fetch and send pending SMS."""
        try:
            now = datetime.now(timezone.utc).isoformat()
            
            res = await db.table("sms_queue") \
                .select("*") \
                .eq("status", "pending") \
                .lte("scheduled_at", now) \
                .limit(BATCH_SIZE) \
                .execute()
            
            sms_messages = res.data or []
            
            for sms in sms_messages:
                await self._send_sms(sms)
                
        except Exception as e:
            logger.error(f"SMS queue processing error: {e}")
    
    async def _send_sms(self, sms_record: Dict):
        """Send a single queued SMS."""
        sms_id = sms_record["id"]
        
        try:
            from notification_services import SMSService
            
            result = await SMSService.send(
                phone_number=sms_record["phone_number"],
                message=sms_record["message"],
                profile_id=sms_record.get("profile_id"),
                notification_id=sms_record.get("notification_id")
            )
            
            if result["success"]:
                logger.info(f"SMS sent: id={sms_id}")
            else:
                await self._mark_failed("sms_queue", sms_id, result["error"])
                
        except Exception as e:
            logger.error(f"SMS send failed for queue id {sms_id}: {e}")
            await self._mark_failed("sms_queue", sms_id, str(e))
    
    # ─── Helpers ──────────────────────────────────────────────────────────────────
    
    async def _mark_failed(self, table: str, record_id: str, error: str):
        """Mark a queued record as failed with error message."""
        try:
            await db.table(table) \
                .update({
                    "status": "failed",
                    "error_message": error[:500],
                    "sent_at": datetime.now(timezone.utc).isoformat()
                }) \
                .eq("id", record_id) \
                .execute()
        except Exception as e:
            logger.error(f"Failed to mark {table} record {record_id} as failed: {e}")


# ─── Entry Point ─────────────────────────────────────────────────────────────────

async def main():
    """Run notification worker as standalone process."""
    worker = NotificationWorker()
    
    try:
        await worker.start()
    except KeyboardInterrupt:
        logger.info("Shutting down notification worker...")
        await worker.stop()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s"
    )
    asyncio.run(main())
