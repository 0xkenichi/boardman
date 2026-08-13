"""
notification_services.py - Unified notification dispatcher
Sends push (FCM/APNs), email (Bird primary, Resend fallback), and SMS (Africa's Talking)
"""

import os
import json
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from backend.supabase_client import get_supabase
from dotenv import load_dotenv

# Import event bus for fan-out
from backend.realtime_server import publish_event

load_dotenv()

logger = logging.getLogger(__name__)

# ─── Clients ────────────────────────────────────────────────────────────────────
db = get_supabase()

# ─── Service Configuration ──────────────────────────────────────────────────────
BIRD_EMAIL_API_KEY = os.getenv("BIRD_EMAIL_API_KEY", "")
BIRD_FROM_EMAIL = os.getenv("BIRD_FROM_EMAIL", "onboarding@playingsidequest.fun")
BIRD_FROM_NOREPLY = os.getenv("BIRD_FROM_NOREPLY", BIRD_FROM_EMAIL)
BIRD_FROM_NAME = os.getenv("BIRD_FROM_NAME", "sideQuest")

RESEND_API_KEY = os.getenv("RESEND_API_KEY")
RESEND_FROM_EMAIL = os.getenv("RESEND_FROM_EMAIL", BIRD_FROM_EMAIL)
RESEND_FROM_NAME = os.getenv("RESEND_FROM_NAME", "sideQuest")

AFRICASTALKING_API_KEY = os.getenv("AFRICASTALKING_API_KEY")
AFRICASTALKING_USERNAME = os.getenv("AFRICASTALKING_USERNAME", "sidequest")
AFRICASTALKING_SENDER_ID = os.getenv("AFRICASTALKING_SENDER_ID", "SIDEQUEST")

FCM_SERVER_KEY = os.getenv("FCM_SERVER_KEY")
# APNs removed - mobile apps not in scope yet

# ────────────────────────────────────────────────────────────────────────────────

class EmailService:
    """Bird-based transactional email sender with Resend fallback."""

    @staticmethod
    def _bird_base_url() -> str:
        """Extract region from Bird API key (e.g. bk_eu1_... → eu1)."""
        import re
        if BIRD_EMAIL_API_KEY:
            m = re.match(r"^bk_([a-z0-9]+)_", BIRD_EMAIL_API_KEY)
            if m:
                return f"https://{m.group(1)}.platform.bird.com"
        return "https://eu1.platform.bird.com"

    @staticmethod
    async def send(
        to_email: str,
        subject: str,
        html_body: str,
        text_body: Optional[str] = None,
        profile_id: Optional[str] = None,
        notification_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Send email via Bird API (primary) with Resend fallback.
        """
        # ── Bird primary ──────────────────────────────────────────────────────
        if BIRD_EMAIL_API_KEY:
            try:
                import httpx

                payload = {
                    "from": f"{BIRD_FROM_NAME} <{BIRD_FROM_NOREPLY}>",
                    "to": [to_email],
                    "subject": subject,
                    "html": html_body,
                    "category": "transactional",
                }
                if text_body:
                    payload["text"] = text_body

                async with httpx.AsyncClient(timeout=30) as client:
                    resp = await client.post(
                        f"{EmailService._bird_base_url()}/v1/email/messages",
                        headers={
                            "Authorization": f"Bearer {BIRD_EMAIL_API_KEY}",
                            "Content-Type": "application/json",
                        },
                        json=payload,
                    )

                if resp.status_code in (200, 202):
                    data = resp.json()
                    message_id = data.get("id")
                    logger.info(f"Email sent via Bird to {to_email}: {message_id}")
                    if notification_id or profile_id:
                        await EmailService._log_sent(message_id, notification_id, profile_id)
                    return {"success": True, "message_id": message_id, "provider": "bird"}
                else:
                    logger.warning(f"Bird failed {resp.status_code}: {resp.text[:200]}")
            except Exception as e:
                logger.warning(f"Bird send error: {e}")

        # ── Resend fallback ───────────────────────────────────────────────────
        if RESEND_API_KEY:
            try:
                import httpx

                headers = {
                    "Authorization": f"Bearer {RESEND_API_KEY}",
                    "Content-Type": "application/json"
                }

                payload = {
                    "from": f"{RESEND_FROM_NAME} <{RESEND_FROM_EMAIL}>",
                    "to": [to_email],
                    "subject": subject,
                    "html": html_body
                }
                if text_body:
                    payload["text"] = text_body

                async with httpx.AsyncClient(timeout=30) as client:
                    resp = await client.post(
                        "https://api.resend.com/emails",
                        headers=headers,
                        json=payload
                    )

                if resp.status_code in (200, 201):
                    data = resp.json()
                    message_id = data.get("id")
                    logger.info(f"Email sent via Resend to {to_email}: {message_id}")
                    if notification_id or profile_id:
                        await EmailService._log_sent(message_id, notification_id, profile_id)
                    return {"success": True, "message_id": message_id, "provider": "resend"}
                else:
                    logger.error(f"Resend failed {resp.status_code}: {resp.text}")
                    return {"success": False, "error": resp.text[:200]}
            except Exception as e:
                logger.error(f"Resend send error: {e}", exc_info=True)
                return {"success": False, "error": str(e)}

        logger.error("No email provider configured (BIRD_EMAIL_API_KEY or RESEND_API_KEY)")
        return {"success": False, "error": "email_service_unavailable"}
    
    @staticmethod
    async def _log_sent(message_id: str, notification_id: str = None, profile_id: str = None):
        """Update email_queue with sent status."""
        try:
            update_data = {
                "status": "sent",
                "sent_at": datetime.now(timezone.utc).isoformat()
            }
            if message_id:
                update_data["external_id"] = message_id
            
            query = db.table("email_queue").update(update_data)
            if notification_id:
                query = query.eq("notification_id", notification_id)
            if profile_id:
                query = query.eq("profile_id", profile_id)
            
            await query.execute()
        except Exception as e:
            logger.warning(f"Failed to update email_queue: {e}")


class PushNotificationService:
    """FCM (Android) + APNs (iOS) push notification sender."""
    
    @staticmethod
    async def send(
        profile_id: str,
        title: str,
        body: str,
        data: Optional[Dict[str, Any]] = None,
        badge: Optional[int] = None,
        sound: str = "default"
    ) -> Dict[str, Any]:
        """
        Send push notification to user's registered devices.
        """
        # Get active push tokens for user
        tokens = await PushNotificationService._get_active_tokens(profile_id)
        if not tokens:
            return {"success": False, "error": "no_devices"}
        
        results = []
        for tokenrecord in tokens:
            token = tokenrecord["token"]
            platform = tokenrecord["platform"]
            
            if platform == "android":
                result = await PushNotificationService._send_fcm(token, title, body, data, badge, sound)
            else:
                result = {"success": False, "error": "unknown_platform"}
            
            results.append(result)
        
        # Update token activity
        await PushNotificationService._touch_tokens([t["id"] for t in tokens])
        
        successful = sum(1 for r in results if r.get("success"))
        return {
            "success": successful > 0,
            "sent": successful,
            "total": len(results)
        }
    
    @staticmethod
    async def _get_active_tokens(profile_id: str) -> List[dict]:
        """Fetch active push tokens for profile."""
        try:
            res = await db.table("push_tokens") \
                .select("id, token, platform") \
                .eq("profile_id", profile_id) \
                .eq("is_active", True) \
                .execute()
            return res.data or []
        except Exception as e:
            logger.error(f"Failed to fetch push tokens: {e}")
            return []
    
    @staticmethod
    async def _touch_tokens(token_ids: List[str]):
        """Update last_used_at for tokens."""
        try:
            for tid in token_ids:
                await db.table("push_tokens") \
                    .update({"last_used_at": datetime.now(timezone.utc).isoformat()}) \
                    .eq("id", tid).execute()
        except Exception:
            pass
    
    @staticmethod
    async def _send_fcm(
        token: str, title: str, body: str,
        data: Optional[Dict], badge: Optional[int], sound: str
    ) -> Dict[str, Any]:
        """Send FCM (Firebase Cloud Messaging) push."""
        if not FCM_SERVER_KEY:
            return {"success": False, "error": "fcm_not_configured"}
        
        try:
            import httpx
            
            headers = {
                "Authorization": f"key={FCM_SERVER_KEY}",
                "Content-Type": "application/json"
            }
            
            payload = {
                "to": token,
                "notification": {
                    "title": title,
                    "body": body,
                    "sound": sound
                },
                "data": data or {}
            }
            if badge is not None:
                payload["notification"]["badge"] = badge
            
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    "https://fcm.googleapis.com/fcm/send",
                    headers=headers,
                    json=payload
                )
            
            if resp.status_code == 200:
                result = resp.json()
                success = result.get("success", 0) > 0
                return {"success": success, "response": result}
            else:
                return {"success": False, "error": f"HTTP {resp.status_code}"}
                
        except Exception as e:
            logger.error(f"FCM send error: {e}")
            return {"success": False, "error": str(e)}
    
    @staticmethod
    async def _send_apns(
        token: str, title: str, body: str,
        data: Optional[Dict], badge: Optional[int], sound: str
    ) -> Dict[str, Any]:
        """APNs removed - return disabled."""
        return {"success": False, "error": "apns_not_configured"}


class SMSService:
    """Africa's Talking SMS sender."""
    
    BASE_URL = "https://api.africastalking.com/version1/messaging"
    
    @staticmethod
    async def send(
        phone_number: str,
        message: str,
        profile_id: Optional[str] = None,
        notification_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Send SMS via Africa's Talking API.
        """
        if not AFRICASTALKING_API_KEY:
            return {"success": False, "error": "sms_service_unavailable"}
        
        try:
            import httpx
            
            headers = {
                "apikey": AFRICASTALKING_API_KEY,
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json"
            }
            
            payload = {
                "username": AFRICASTALKING_USERNAME,
                "to": phone_number,
                "message": message[:160],  # SMS length limit
                "from": AFRICASTALKING_SENDER_ID
            }
            
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(
                    SMSService.BASE_URL,
                    headers=headers,
                    data=payload
                )
            
            if resp.status_code == 201:
                data = resp.json()
                messages = data.get("responses", [{}])[0]
                status = messages.get("status")
                message_id = messages.get("messageId")
                
                if status == "OK":
                    logger.info(f"SMS sent to {phone_number}: {message_id}")
                    
                    # Log to sms_queue
                    if notification_id or profile_id:
                        await SMSService._log_sent(message_id, notification_id, profile_id)
                    
                    return {"success": True, "message_id": message_id}
                else:
                    error = messages.get("error", "Unknown error")
                    logger.error(f"SMS send failed: {error}")
                    return {"success": False, "error": error}
            else:
                return {"success": False, "error": f"HTTP {resp.status_code}"}
                
        except Exception as e:
            logger.error(f"SMS send error: {e}", exc_info=True)
            return {"success": False, "error": str(e)}
    
    @staticmethod
    async def _log_sent(message_id: str, notification_id: str = None, profile_id: str = None):
        """Update sms_queue with sent status."""
        try:
            update_data = {
                "status": "sent",
                "sent_at": datetime.now(timezone.utc).isoformat()
            }
            if message_id:
                update_data["external_id"] = message_id
            
            query = db.table("sms_queue").update(update_data)
            if notification_id:
                query = query.eq("notification_id", notification_id)
            if profile_id:
                query = query.eq("profile_id", profile_id)
            
            await query.execute()
        except Exception:
            pass


# ─── Unified Notification Dispatcher ────────────────────────────────────────────

class NotificationDispatcher:
    """
    Dispatches notifications via all configured channels:
    - In-app (directly stored in notifications table)
    - Push (FCM/APNs)
    - Email (Resend)
    - SMS (Africa's Talking)
    """
    
    @staticmethod
    async def dispatch(
        recipient_id: str,
        notification_type: str,
        title: str,
        body: str,
        data: Optional[Dict] = None,
        priority: str = "normal",
        channels: Optional[List[str]] = None,
        force_channels: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Dispatch a notification to all configured channels.
        
        Args:
            recipient_id: Profile UUID of recipient
            notification_type: Type of notification (for filtering/settings)
            title: Short title
            body: Main message body
            data: Additional structured data
            priority: low/normal/high/urgent
            channels: List of channels to use (overrides user settings)
            force_channels: Bypass settings and force these channels
        
        Returns:
            Dict with dispatch results per channel
        """
        if data is None:
            data = {}
        
        results = {}
        
        try:
            # 1. Always store in-app notification
            notification = await NotificationDispatcher._create_in_app(
                recipient_id, notification_type, title, body, data, priority
            )
            notification_id = notification.get("id") if notification else None
            
            # 2. Determine which channels to use
            if force_channels:
                active_channels = force_channels
            else:
                settings = await NotificationDispatcher._get_user_settings(recipient_id, notification_type)
                active_channels = settings.get("active_channels", ["in_app"])
            
            # 3. Dispatch to each channel
            for channel in active_channels:
                if channel == "in_app":
                    results[channel] = {"success": True, "notification_id": notification_id}
                
                elif channel == "push":
                    push_result = await PushNotificationService.send(
                        profile_id=recipient_id,
                        title=title,
                        body=body,
                        data={**data, "type": notification_type, "notification_id": notification_id},
                        badge=1
                    )
                    results[channel] = push_result
                
                elif channel == "email":
                    html_body = NotificationDispatcher._render_email_template(notification_type, title, body, data)
                    text_body = body
                    email = await NotificationDispatcher._get_user_email(recipient_id)
                    if email:
                        email_result = await EmailService.send(
                            to_email=email,
                            subject=f"[sideQuest] {title}",
                            html_body=html_body,
                            text_body=text_body,
                            profile_id=recipient_id,
                            notification_id=notification_id
                        )
                        results[channel] = email_result
                    else:
                        results[channel] = {"success": False, "error": "no_email"}
                
                elif channel == "sms":
                    sms_message = f"{title}: {body}"[:160]
                    phone = await NotificationDispatcher._get_user_phone(recipient_id)
                    if phone:
                        sms_result = await SMSService.send(
                            phone_number=phone,
                            message=sms_message,
                            profile_id=recipient_id,
                            notification_id=notification_id
                        )
                        results[channel] = sms_result
                    else:
                        results[channel] = {"success": False, "error": "no_phone"}
            
            # 4. Publish event for WebSocket fan-out
            await publish_event(
                event_type="notification.sent",
                payload={
                    "notification_id": notification_id,
                    "recipient_id": recipient_id,
                    "type": notification_type,
                    "title": title,
                    "channels": active_channels,
                    "results": results
                },
                recipient_id=recipient_id
            )
            
            return {"success": True, "notification_id": notification_id, "results": results}
            
        except Exception as e:
            logger.error(f"Notification dispatch failed: {e}", exc_info=True)
            return {"success": False, "error": str(e)}
    
    @staticmethod
    async def _create_in_app(
        recipient_id: str, ntype: str, title: str, body: str, 
        data: Dict, priority: str
    ) -> Optional[dict]:
        """Create notification record in DB."""
        try:
            result = await db.table("notifications").insert({
                "recipient_id": recipient_id,
                "type": ntype,
                "title": title,
                "body": body,
                "data": data,
                "channels": ["in_app"],
                "priority": priority,
                "status": "pending",
                "created_at": datetime.now(timezone.utc).isoformat()
            }).execute()
            
            notif = result.data[0] if result.data else None
            if notif:
                logger.info(f"Notification created: id={notif['id']} type={ntype} recipient={recipient_id}")
            return notif
        except Exception as e:
            logger.error(f"In-app notification create failed: {e}")
            return None
    
    @staticmethod
    async def _get_user_settings(profile_id: str, ntype: str) -> Dict:
        """Get user's notification channel preferences for this type."""
        try:
            res = await db.table("notification_settings") \
                .select("*") \
                .eq("profile_id", profile_id) \
                .eq("notification_type", ntype) \
                .maybe_single() \
                .execute()
            
            settings = res.data or {}
            
            # Determine active channels based on user prefs
            active = ["in_app"]  # Always on
            if settings.get("channel_push", True):
                active.append("push")
            if settings.get("channel_email", False):
                active.append("email")
            if settings.get("channel_sms", False):
                active.append("sms")
            
            return {"active_channels": active}
        except Exception:
            return {"active_channels": ["in_app"]}
    
    @staticmethod
    async def _get_user_email(profile_id: str) -> Optional[str]:
        """Get user email from profile."""
        try:
            res = await db.table("profiles") \
                .select("email") \
                .eq("id", profile_id) \
                .maybe_single() \
                .execute()
            return res.data.get("email") if res.data else None
        except Exception:
            return None
    
    @staticmethod
    async def _get_user_phone(profile_id: str) -> Optional[str]:
        """Get user phone (WhatsApp number) from profile."""
        try:
            res = await db.table("profiles") \
                .select("whatsapp_number") \
                .eq("id", profile_id) \
                .maybe_single() \
                .execute()
            return res.data.get("whatsapp_number") if res.data else None
        except Exception:
            return None
    
    @staticmethod
    def _render_email_template(ntype: str, title: str, body: str, data: Dict) -> str:
        """Render HTML email body for notification type."""
        from html import escape as html_escape
        quest_id = data.get("quest_id")
        quest_link = f"https://sidequest.fun/quests/{quest_id}" if quest_id else "https://sidequest.fun"
        
        safe_title = html_escape(title)
        safe_body = html_escape(body)
        
        return f"""
        <!DOCTYPE html>
        <html>
        <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; padding: 20px; background: #0a0a0a; color: #fff;">
            <div style="max-width: 600px; margin: 0 auto; background: #1a1a1a; border-radius: 12px; padding: 24px;">
                <h1 style="color: #ccff00; font-size: 24px; margin-bottom: 16px;">{safe_title}</h1>
                <p style="font-size: 16px; line-height: 1.6; margin-bottom: 24px;">{safe_body}</p>
                <div style="text-align: center;">
                    <a href="{quest_link}" style="background: #ccff00; color: #000; padding: 12px 24px; border-radius: 8px; text-decoration: none; font-weight: bold;">
                        Open sideQuest
                    </a>
                </div>
                <hr style="border: 0; border-top: 1px solid #333; margin: 24px 0;">
                <p style="color: #888; font-size: 12px;">
                    You received this email because you're a sideQuest Hero.
                    <br><a href="https://sidequest.fun/settings" style="color: #888;">Adjust notification settings</a>
                </p>
            </div>
        </body>
        </html>
        """


# ─── Webhook Integration ─────────────────────────────────────────────────────────

class NotificationWebhooks:
    """
    Endpoints for external services to trigger notifications.
    (e.g., blockchain events, gaming platform results, flash expiry)
    """
    
    @staticmethod
    async def handle_quest_invite(quest_id: str, inviter_id: str, invitee_id: str):
        """Webhook: quest invite notification."""
        # Fetch quest and inviter details
        quest = await db.table("quests").select("title, quest_type, date_time").eq("id", quest_id).maybe_single().execute()
        inviter = await db.table("profiles").select("display_name").eq("id", inviter_id).maybe_single().execute()
        
        if not quest.data or not inviter.data:
            return
        
        await NotificationDispatcher.dispatch(
            recipient_id=invitee_id,
            notification_type="quest_invite",
            title=f"{inviter.data['display_name']} invited you to a quest",
            body=f"Join '{quest.data['title']}' ({quest.data['quest_type']})",
            data={"quest_id": quest_id, "inviter_id": inviter_id},
            priority="normal",
            force_channels=["in_app", "push"]
        )
    
    @staticmethod
    async def handle_bet_challenge(challenge_id: str, challenger_id: str, opponent_id: str, bet_details: Dict):
        """Webhook: bet challenge notification."""
        challenger = await db.table("profiles").select("display_name").eq("id", challenger_id).maybe_single().execute()
        
        if not challenger.data:
            return
        
        await NotificationDispatcher.dispatch(
            recipient_id=opponent_id,
            notification_type="bet_challenge",
            title=f"{challenger.data['display_name']} challenged you",
            body=f"Stake: ${bet_details.get('amount', 0):.2f} • Game: {bet_details.get('game_type', 'Unknown')}",
            data={
                "bet_id": challenge_id,
                "challenger_id": challenger_id,
                "amount": bet_details.get("amount"),
                "game_type": bet_details.get("game_type")
            },
            priority="high",
            force_channels=["in_app", "push"]
        )
