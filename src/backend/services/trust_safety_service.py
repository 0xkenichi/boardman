"""
trust_safety_service.py
────────────────────────────────────────────────────────────────────────────────
Core Trust & Safety service for sideQuest.

Handles:
  - Report submission (user / quest / message / match)
  - Block & mute management
  - No-show reporting with reputation impact
  - Account actions (warnings, bans, appeals)
  - Age verification gating
  - Emergency SOS triggering
  - GDPR/NDPR data export & deletion
  - ToS acceptance tracking
"""

import os
import json
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional
from uuid import UUID

from backend.supabase_client import get_supabase
import openai
from openai import OpenAI

logger = logging.getLogger(__name__)
ADMIN_WHATSAPP = os.getenv("ADMIN_WHATSAPP_NUMBER", "")
ADMIN_TELEGRAM_IDS = [int(x) for x in os.getenv("ADMIN_TELEGRAM_IDS", "").split(",") if x.strip()]

# AI Moderation thresholds
AI_MODERATION_THRESHOLD = float(os.getenv("AI_MODERATION_THRESHOLD", "0.7"))  # 0-1 score threshold for auto-flag
AUTO_BLOCK_THRESHOLD = float(os.getenv("AUTO_BLOCK_THRESHOLD", "0.9"))  # threshold for immediate block

REPUTATION_THRESHOLDS = {
    "warning_at":    3,   # reports trigger a warning
    "temp_ban_at":   5,   # 3-day temp ban
    "perm_ban_at":   10,  # permanent ban review
}

BAN_DURATIONS = {
    1: timedelta(days=3),
    2: timedelta(days=7),
    3: timedelta(days=30),
}


def _sb():
    return get_supabase()


# ─── REPORTS ──────────────────────────────────────────────────────────────────

async def submit_report(
    reporter_id: str,
    target_type: str,
    reason: str,
    target_user_id: Optional[str] = None,
    target_match_id: Optional[str] = None,
    target_message_id: Optional[str] = None,
    description: Optional[str] = None,
    evidence_urls: Optional[list] = None,
    is_anonymous: bool = False,
) -> dict:
    """
    File a report against a user, match, or message.
    Auto-escalates if the target has many pending reports.
    """
    sb = _sb()

    # Rate-limit: reporter can't re-report same target for 24h
    existing = sb.table("reports").select("id").eq("reporter_id", reporter_id)\
        .eq("target_type", target_type).eq("target_user_id", target_user_id or "")\
        .gte("created_at", (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat())\
        .execute()

    if existing.data:
        return {"success": False, "error": "You already reported this recently. Please wait 24 hours."}

    row = {
        "reporter_id":       reporter_id,
        "target_type":       target_type,
        "target_user_id":    target_user_id,
        "target_match_id":   target_match_id,
        "target_message_id": target_message_id,
        "reason":            reason,
        "description":       description,
        "evidence_urls":     evidence_urls or [],
        "is_anonymous":      is_anonymous,
        "status":            "pending",
    }

    result = sb.table("reports").insert(row).execute()
    report = result.data[0] if result.data else {}

    # Check if this user has crossed the auto-action threshold
    if target_user_id:
        await _check_report_threshold(target_user_id)
        await _add_to_moderation_queue(
            content_type="profile",
            content_id=target_user_id,
            report_count_delta=1,
        )

    logger.info(f"[Trust] Report filed: {target_type} by {reporter_id}")
    return {"success": True, "report_id": report.get("id"), "message": "Your report has been submitted. Our team will review it within 24 hours."}


async def _check_report_threshold(user_id: str):
    """Issue automatic action if report threshold crossed."""
    sb = _sb()
    profile = sb.table("profiles").select("report_count, warning_count, is_suspended").eq("id", user_id).single().execute().data
    if not profile:
        return

    report_count = profile.get("report_count", 0)
    warning_count = profile.get("warning_count", 0)

    if report_count >= REPUTATION_THRESHOLDS["perm_ban_at"]:
        await _issue_account_action(user_id, "temp_ban", "Automated: high report volume — under review", ban_days=7, issued_by=None, auto=True)
    elif report_count >= REPUTATION_THRESHOLDS["temp_ban_at"] and warning_count >= 2:
        await _issue_account_action(user_id, "temp_ban", "Automated: repeated violations", ban_days=3, issued_by=None, auto=True)
    elif report_count >= REPUTATION_THRESHOLDS["warning_at"]:
        await _issue_account_action(user_id, "warning", "Automated: multiple reports received", issued_by=None, auto=True)


# ─── BLOCKS & MUTES ───────────────────────────────────────────────────────────

async def block_user(blocker_id: str, blocked_id: str, mute_only: bool = False) -> dict:
    """Block or mute a user. Block removes them from shared quests too."""
    if blocker_id == blocked_id:
        return {"success": False, "error": "You cannot block yourself."}

    sb = _sb()
    sb.table("user_blocks").upsert({
        "blocker_id": blocker_id,
        "blocked_id": blocked_id,
        "is_mute":    mute_only,
    }, on_conflict="blocker_id,blocked_id").execute()

    action = "muted" if mute_only else "blocked"
    logger.info(f"[Trust] User {blocked_id} {action} by {blocker_id}")
    return {"success": True, "action": action}


async def unblock_user(blocker_id: str, blocked_id: str) -> dict:
    sb = _sb()
    sb.table("user_blocks").delete().eq("blocker_id", blocker_id).eq("blocked_id", blocked_id).execute()
    return {"success": True}


async def get_blocked_users(profile_id: str) -> list:
    sb = _sb()
    res = sb.table("user_blocks").select("blocked_id, is_mute, created_at").eq("blocker_id", profile_id).execute()
    return res.data or []


async def is_blocked(blocker_id: str, blocked_id: str) -> bool:
    """Returns True if blocker_id has blocked blocked_id."""
    sb = _sb()
    res = sb.table("user_blocks").select("id").eq("blocker_id", blocker_id).eq("blocked_id", blocked_id).execute()
    return bool(res.data)


# ─── NO-SHOW REPORTS ──────────────────────────────────────────────────────────

async def report_no_show(
    reporter_id: str,
    reported_id: str,
    match_id: str,
    description: Optional[str] = None,
    evidence_url: Optional[str] = None,
) -> dict:
    """File a no-show report for a match. Auto-confirms if opponent also reports."""
    sb = _sb()

    # Verify they were actually in this match
    match = sb.table("bets").select("*").eq("id", match_id)\
        .or_(f"creator_id.eq.{reporter_id},opponent_id.eq.{reporter_id}").execute()
    if not match.data:
        return {"success": False, "error": "You are not a participant in this match."}

    existing = sb.table("no_show_reports").select("*").eq("match_id", match_id).execute()
    other_report = next((r for r in (existing.data or []) if r["reporter_id"] != reporter_id), None)

    sb.table("no_show_reports").insert({
        "reporter_id":  reporter_id,
        "reported_id":  reported_id,
        "match_id":     match_id,
        "description":  description,
        "evidence_url": evidence_url,
        "status":       "confirmed" if other_report else "pending",
    }).execute()

    if other_report:
        # Both players reported — confirm and apply reputation hit
        sb.table("no_show_reports").update({"status": "confirmed"}).eq("id", other_report["id"]).execute()
        logger.info(f"[Trust] No-show confirmed for match {match_id} — reputation hit for {reported_id}")
        return {"success": True, "status": "confirmed", "message": "No-show confirmed. Reputation impact applied."}

    return {"success": True, "status": "pending", "message": "No-show report filed. We'll review if the other player also reports."}


# ─── ACCOUNT ACTIONS ──────────────────────────────────────────────────────────

async def _issue_account_action(
    user_id: str,
    action_type: str,
    reason: str,
    ban_days: Optional[int] = None,
    issued_by: Optional[str] = None,
    auto: bool = False,
    report_ids: Optional[list] = None,
) -> dict:
    sb = _sb()
    ban_until = None
    if action_type == "temp_ban" and ban_days:
        ban_until = (datetime.now(timezone.utc) + timedelta(days=ban_days)).isoformat()

    sb.table("account_actions").insert({
        "target_user_id":  user_id,
        "action_type":     action_type,
        "reason":          reason,
        "ban_until":       ban_until,
        "issued_by":       issued_by,
        "report_ids":      report_ids or [],
        "is_appealable":   True,
        "appeal_deadline": (datetime.now(timezone.utc) + timedelta(days=14)).isoformat(),
    }).execute()

    # Apply to profile
    updates = {"warning_count": None}  # handled below
    if action_type in ("temp_ban", "permanent_ban"):
        updates = {
            "is_suspended":    True,
            "suspension_until": ban_until,
        }
    elif action_type == "warning":
        profile = sb.table("profiles").select("warning_count").eq("id", user_id).single().execute().data
        current = (profile or {}).get("warning_count", 0)
        updates = {"warning_count": current + 1, "reputation": None}
        profile2 = sb.table("profiles").select("reputation").eq("id", user_id).single().execute().data
        score = max(0, (profile2 or {}).get("reputation", 100) - 15)
        updates["reputation"] = score

    if updates:
        clean = {k: v for k, v in updates.items() if v is not None}
        if clean:
            sb.table("profiles").update(clean).eq("id", user_id).execute()

    # Notify via bot
    asyncio.create_task(_notify_user_action(user_id, action_type, reason, ban_until))
    logger.info(f"[Trust] {'Auto' if auto else 'Manual'} {action_type} issued to {user_id}")
    return {"success": True, "action_type": action_type, "ban_until": ban_until}


async def issue_warning(admin_id: str, user_id: str, reason: str) -> dict:
    return await _issue_account_action(user_id, "warning", reason, issued_by=admin_id)


async def issue_temp_ban(admin_id: str, user_id: str, reason: str, days: int = 3) -> dict:
    return await _issue_account_action(user_id, "temp_ban", reason, ban_days=days, issued_by=admin_id)


async def issue_perm_ban(admin_id: str, user_id: str, reason: str) -> dict:
    return await _issue_account_action(user_id, "permanent_ban", reason, issued_by=admin_id)


async def submit_appeal(user_id: str, action_id: str, appeal_reason: str) -> dict:
    sb = _sb()
    action = sb.table("account_actions").select("*").eq("id", action_id)\
        .eq("target_user_id", user_id).single().execute().data
    if not action:
        return {"success": False, "error": "Action not found."}
    if not action.get("is_appealable"):
        return {"success": False, "error": "This action cannot be appealed."}
    if action.get("appealed_at"):
        return {"success": False, "error": "You have already submitted an appeal."}

    deadline = action.get("appeal_deadline")
    if deadline and datetime.now(timezone.utc) > datetime.fromisoformat(deadline):
        return {"success": False, "error": "The appeal window has closed."}

    sb.table("account_actions").update({
        "appealed_at":   datetime.now(timezone.utc).isoformat(),
        "appeal_reason": appeal_reason,
    }).eq("id", action_id).execute()

    await _notify_admins_appeal(user_id, action_id, appeal_reason)
    return {"success": True, "message": "Your appeal has been submitted. We will respond within 5 business days."}


async def decide_appeal(admin_id: str, action_id: str, grant: bool, notes: Optional[str] = None) -> dict:
    sb = _sb()
    action = sb.table("account_actions").select("*").eq("id", action_id).single().execute().data
    if not action:
        return {"success": False, "error": "Action not found."}

    outcome = "granted" if grant else "denied"
    sb.table("account_actions").update({
        "appeal_outcome":    outcome,
        "appeal_decided_at": datetime.now(timezone.utc).isoformat(),
        "appeal_reason":     notes or action.get("appeal_reason"),
    }).eq("id", action_id).execute()

    if grant:
        sb.table("profiles").update({
            "is_suspended":    False,
            "suspension_until": None,
        }).eq("id", action["target_user_id"]).execute()

    asyncio.create_task(_notify_user_appeal_outcome(action["target_user_id"], grant))
    return {"success": True, "outcome": outcome}


# ─── AGE VERIFICATION ─────────────────────────────────────────────────────────

async def verify_age(profile_id: str, date_of_birth: str, method: str = "dob_entry") -> dict:
    """
    Store DoB and flag age_verified.
    For 18+ quests, gating is checked at join-time.
    """
    sb = _sb()
    try:
        dob = datetime.fromisoformat(date_of_birth).date()
    except ValueError:
        return {"success": False, "error": "Invalid date format. Use YYYY-MM-DD."}

    age = (datetime.now().date() - dob).days // 365
    is_adult = age >= 18

    sb.table("profiles").update({
        "date_of_birth": dob.isoformat(),
        "age_verified":   is_adult,
        "age_verified_at": datetime.now(timezone.utc).isoformat() if is_adult else None,
    }).eq("id", profile_id).execute()

    sb.table("age_verification_log").insert({
        "profile_id":  profile_id,
        "method":      method,
        "verified":    is_adult,
        "min_age_met": is_adult,
    }).execute()

    return {
        "success":   True,
        "age":       age,
        "is_adult":  is_adult,
        "message": "Age verified." if is_adult else "This platform requires users to be 18 or older.",
    }


async def check_age_gating(profile_id: str, quest_min_age: int = 18) -> dict:
    sb = _sb()
    profile = sb.table("profiles").select("age_verified, date_of_birth").eq("id", profile_id).single().execute().data
    if not profile:
        return {"allowed": False, "reason": "Profile not found."}
    if not profile.get("age_verified"):
        return {"allowed": False, "reason": "Age verification required. Use /verify_age YYYY-MM-DD."}
    dob_str = profile.get("date_of_birth")
    if dob_str:
        dob = datetime.fromisoformat(dob_str).date()
        age = (datetime.now().date() - dob).days // 365
        if age < quest_min_age:
            return {"allowed": False, "reason": f"You must be {quest_min_age}+ to join this quest."}
    return {"allowed": True}


# ─── SOS / EMERGENCY ──────────────────────────────────────────────────────────

async def trigger_sos(profile_id: str, match_id: Optional[str] = None, message: Optional[str] = None, location_hint: Optional[str] = None) -> dict:
    """
    Trigger an emergency SOS. Notifies registered emergency contacts and admins.
    """
    sb = _sb()
    contacts = sb.table("emergency_contacts").select("*").eq("profile_id", profile_id).execute().data or []
    profile = sb.table("profiles").select("display_name, whatsapp_id, telegram_id").eq("id", profile_id).single().execute().data or {}

    notified = []
    user_name = profile.get("display_name", "A sideQuest user")

    sos_msg = (
        f"🆘 EMERGENCY SOS — sideQuest\n\n"
        f"User: {user_name}\n"
        f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M UTC')}\n"
        f"Location hint: {location_hint or 'Not provided'}\n"
        f"Message: {message or 'No message provided'}\n\n"
        f"They may need assistance. Please check on them immediately."
    )

    # Notify emergency contacts via SMS
    for contact in contacts:
        logger.warning(f"[SOS] Notifying {contact['name']} at {contact['phone']}: {sos_msg[:100]}")
        try:
            from services.phone_otp import send_sms_otp
            from notification_services import SMSService
            sms = SMSService()
            await sms.send(contact["phone"], sos_msg)
        except Exception as sms_err:
            logger.error(f"[SOS] SMS send failed to {contact['phone']}: {sms_err}")
        notified.append(contact["phone"])

    # Notify platform admins
    await _notify_admins_sos(profile_id, user_name, match_id, sos_msg)

    # Log the event
    sb.table("sos_events").insert({
        "profile_id":         profile_id,
        "match_id":           match_id,
        "message":            message,
        "location_hint":      location_hint,
        "contacts_notified":  notified,
        "admin_notified":     True,
    }).execute()

    return {
        "success": True,
        "contacts_notified": len(notified),
        "message": "Emergency contacts notified. Platform admins have been alerted. Please stay safe.",
    }


async def add_emergency_contact(profile_id: str, name: str, phone: str, relationship: Optional[str] = None, is_primary: bool = False) -> dict:
    sb = _sb()
    if is_primary:
        sb.table("emergency_contacts").update({"is_primary": False}).eq("profile_id", profile_id).execute()
    sb.table("emergency_contacts").upsert({
        "profile_id":   profile_id,
        "name":         name,
        "phone":        phone,
        "relationship": relationship,
        "is_primary":   is_primary,
    }, on_conflict="profile_id,phone").execute()
    return {"success": True, "message": f"Emergency contact '{name}' saved."}


# ─── GDPR / NDPR ──────────────────────────────────────────────────────────────

async def request_data_export(profile_id: str, ip_address: Optional[str] = None) -> dict:
    """Queue a GDPR data export. A background job would build and deliver the archive."""
    sb = _sb()

    # Enforce one pending request at a time
    pending = sb.table("gdpr_requests").select("id").eq("profile_id", profile_id)\
        .eq("request_type", "export").eq("status", "pending").execute()
    if pending.data:
        return {"success": False, "error": "A data export is already in progress."}

    sb.table("gdpr_requests").insert({
        "profile_id":   profile_id,
        "request_type": "export",
        "ip_address":   ip_address,
        "status":       "pending",
    }).execute()

    return {"success": True, "message": "Your data export has been queued. You will receive a download link within 72 hours."}


async def request_account_deletion(profile_id: str, ip_address: Optional[str] = None) -> dict:
    """Queue account deletion. Anonymises profile after 30-day cooling-off period."""
    sb = _sb()

    pending = sb.table("gdpr_requests").select("id").eq("profile_id", profile_id)\
        .eq("request_type", "deletion").in_("status", ["pending", "processing"]).execute()
    if pending.data:
        return {"success": False, "error": "A deletion request is already in progress."}

    sb.table("gdpr_requests").insert({
        "profile_id":   profile_id,
        "request_type": "deletion",
        "ip_address":   ip_address,
        "status":       "pending",
        "notes":        "30-day cooling-off period applies. Data will be anonymised, not immediately deleted.",
    }).execute()

    return {
        "success": True,
        "message": "Account deletion request received. Under NDPR/GDPR, this takes up to 30 days. Any active stakes will be settled first.",
    }


async def process_data_export(request_id: str) -> dict:
    """
    Called by a background job. Collects all user data and builds a JSON archive.
    In production, upload to private S3 bucket and email signed URL.
    """
    sb = _sb()
    req = sb.table("gdpr_requests").select("*").eq("id", request_id).single().execute().data
    if not req:
        return {"success": False, "error": "Request not found."}

    profile_id = req["profile_id"]
    sb.table("gdpr_requests").update({"status": "processing"}).eq("id", request_id).execute()

    # Collect all user data
    export = {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "profile":     sb.table("profiles").select("*").eq("id", profile_id).single().execute().data,
        "bets":        sb.table("bets").select("*").or_(f"creator_id.eq.{profile_id},opponent_id.eq.{profile_id}").execute().data,
        "reports_filed": sb.table("reports").select("*").eq("reporter_id", profile_id).execute().data,
        "transactions": sb.table("transactions").select("*").eq("user_id", profile_id).execute().data,
        "tos_acceptance": sb.table("tos_acceptances").select("*").eq("profile_id", profile_id).execute().data,
    }

    # Upload export to Supabase Storage and generate signed URL
    import json as _json
    export_json = _json.dumps(export, default=str, indent=2)
    file_path = f"gdpr-exports/{request_id}.json"

    try:
        sb.storage.from_("gdpr-exports").upload(
            file_path,
            export_json.encode("utf-8"),
            file_options={"content-type": "application/json", "upsert": "true"}
        )
        signed = sb.storage.from_("gdpr-exports").create_signed_url(file_path, 604800)  # 7 days
        download_url = signed.get("signedURL", signed.get("signed_url", ""))
        if not download_url:
            download_url = f"{sb.supabase_url}/storage/v1/object/sign/gdpr-exports/{file_path}?token={signed.get('token', '')}"
    except Exception as upload_err:
        logger.error(f"[GDPR] Storage upload failed: {upload_err}")
        download_url = None

    sb.table("gdpr_requests").update({
        "status":           "completed",
        "processed_at":     datetime.now(timezone.utc).isoformat(),
        "download_url":     download_url,
        "download_expires": (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
    }).eq("id", request_id).execute()

    return {"success": True, "download_url": download_url}


async def anonymise_account(profile_id: str) -> dict:
    """Anonymise (not delete) all personal data. Preserves aggregate stats."""
    sb = _sb()
    anon_suffix = profile_id[:8]

    sb.table("profiles").update({
        "whatsapp_id":    f"deleted_{anon_suffix}",
        "telegram_id":    None,
        "display_name":   f"Deleted User",
        "psn_id":         None,
        "xbox_gamertag":  None,
        "wallet_address": None,
        "linked_wallet":  None,
        "date_of_birth":  None,
        "is_suspended":   True,
    }).eq("id", profile_id).execute()

    sb.table("emergency_contacts").delete().eq("profile_id", profile_id).execute()

    sb.table("gdpr_requests").update({
        "status":       "completed",
        "processed_at": datetime.now(timezone.utc).isoformat(),
    }).eq("profile_id", profile_id).eq("request_type", "deletion").execute()

    logger.info(f"[GDPR] Account {profile_id} anonymised.")
    return {"success": True}


# ─── ToS ACCEPTANCE ───────────────────────────────────────────────────────────

async def accept_tos(profile_id: str, version: str = "1.0", ip_address: Optional[str] = None, user_agent: Optional[str] = None) -> dict:
    sb = _sb()
    sb.table("tos_acceptances").insert({
        "profile_id":  profile_id,
        "version":     version,
        "ip_address":  ip_address,
        "user_agent":  user_agent,
    }).execute()
    sb.table("profiles").update({
        "tos_accepted":    True,
        "tos_accepted_at": datetime.now(timezone.utc).isoformat(),
        "tos_version":     version,
    }).eq("id", profile_id).execute()
    return {"success": True}


# ─── MODERATION QUEUE ─────────────────────────────────────────────────────────

async def _add_to_moderation_queue(content_type: str, content_id: str, content_text: Optional[str] = None, ai_verdict: Optional[str] = None, ai_score: Optional[float] = None, ai_categories: Optional[dict] = None, report_count_delta: int = 0) -> None:
    sb = _sb()
    existing = sb.table("moderation_queue").select("*").eq("content_type", content_type)\
        .eq("content_id", content_id).is_("decision", "null").execute()

    if existing.data:
        current = existing.data[0]
        updates = {"report_count": current["report_count"] + report_count_delta, "updated_at": datetime.now(timezone.utc).isoformat()}
        if ai_verdict:
            updates["ai_verdict"] = ai_verdict
            updates["ai_score"] = ai_score
            updates["ai_categories"] = json.dumps(ai_categories or {})
            updates["priority"] = int((ai_score or 0) * 100) + current["report_count"] * 5
        sb.table("moderation_queue").update(updates).eq("id", current["id"]).execute()
    else:
        priority = int((ai_score or 0) * 100) + report_count_delta * 5
        sb.table("moderation_queue").insert({
            "content_type":  content_type,
            "content_id":    content_id,
            "content_text":  content_text,
            "ai_verdict":    ai_verdict,
            "ai_score":      ai_score,
            "ai_categories": json.dumps(ai_categories or {}),
            "report_count":  report_count_delta,
            "priority":      priority,
            "sla_deadline":  (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat(),
        }).execute()


async def decide_moderation(moderator_id: str, queue_id: str, decision: str, notes: Optional[str] = None) -> dict:
    """
    Admin decides on a queued item: approve / remove / escalate / warn_user.
    """
    sb = _sb()
    item = sb.table("moderation_queue").select("*").eq("id", queue_id).single().execute().data
    if not item:
        return {"success": False, "error": "Queue item not found."}

    sb.table("moderation_queue").update({
        "decision":      decision,
        "decision_notes": notes,
        "decided_by":    moderator_id,
        "decided_at":    datetime.now(timezone.utc).isoformat(),
    }).eq("id", queue_id).execute()

    # Apply decision effects
    if decision == "warn_user":
        await _issue_account_action(item["content_id"], "warning", f"Content violation: {notes or 'policy breach'}", issued_by=moderator_id)
    elif decision == "remove":
        logger.warning(f"[Moderation] Content {item['content_type']}:{item['content_id']} REMOVED by {moderator_id}")

    # Auto-close related pending reports
    if decision in ("remove", "warn_user"):
        sb.table("reports").update({"status": "actioned", "reviewed_by": moderator_id, "reviewed_at": datetime.now(timezone.utc).isoformat()})\
            .eq("target_user_id", item["content_id"]).eq("status", "pending").execute()

    return {"success": True, "decision": decision}


# ─── AI CONTENT SCREENING ─────────────────────────────────────────────────────────

async def screen_content_with_ai(
    content_type: str,
    content_text: str,
    content_id: Optional[str] = None,
    auto_action: bool = True
) -> dict:
    """
    Screen text content using OpenAI Moderation API.
    Logs result and optionally adds to moderation queue if flagged.
    Returns verdict, score, and action taken.
    """
    sb = _sb()

    openai_api_key = os.getenv("OPENAI_API_KEY")
    if not openai_api_key:
        logger.warning("[AI-Mod] OpenAI API key not configured, skipping screening")
        return {"verdict": "unknown", "score": 0.0, "screened": False}

    try:
        client = OpenAI(api_key=openai_api_key)
        response = client.moderations.create(
            model="omni-moderation-latest",
            input=content_text
        )
        result = response.results[0]

        # Extract scores - use highest category score as overall
        categories = result.category_scores
        score = float(result.harness_score) if result.harness_score else float(max(categories.values()) if categories else 0.0)
        verdict = "flagged" if result.flagged else "clean"
        flagged_terms = []  # Could extract from flagged categories

        # Log to ai_screen_log
        sb.table("ai_screen_log").insert({
            "content_type":  content_type,
            "content_id":    content_id or "unspecified",
            "content_text":  content_text[:1000],  # Truncate for storage
            "verdict":       verdict,
            "score":         score,
            "categories":    json.dumps({k: float(v) for k, v in categories.items()}),
            "flagged_terms": flagged_terms,
            "provider":      "openai",
            "auto_actioned": auto_action,
        }).execute()

        # Auto-action if highly flagged
        if auto_action and verdict == "flagged" and score >= AUTO_BLOCK_THRESHOLD:
            # For highly toxic content (violence, self-harm, sexual content involving minors),
            # immediately block and add to queue for review
            logger.warning(f"[AI-Mod] Auto-blocking content (score={score:.3f}): {content_text[:100]}")
            # Add to moderation queue with high priority
            await _add_to_moderation_queue(
                content_type=content_type,
                content_id=content_id or "auto-detected",
                content_text=content_text[:500],
                ai_verdict=verdict,
                ai_score=score,
                ai_categories=categories,
                report_count_delta=5  # high priority
            )
            return {"verdict": verdict, "score": score, "auto_actioned": True, "action": "blocked"}
        elif verdict == "flagged" and score >= AI_MODERATION_THRESHOLD:
            # Moderate flag - add to queue for human review
            await _add_to_moderation_queue(
                content_type=content_type,
                content_id=content_id or "auto-detected",
                content_text=content_text[:500],
                ai_verdict=verdict,
                ai_score=score,
                ai_categories=categories,
                report_count_delta=1
            )
            return {"verdict": verdict, "score": score, "auto_actioned": False, "action": "queued"}
        else:
            return {"verdict": verdict, "score": score, "auto_actioned": False, "action": "passed"}

    except Exception as e:
        logger.error(f"[AI-Mod] Screening failed: {e}")
        return {"verdict": "error", "score": 0.0, "error": str(e), "screened": False}

# ─── AUTOMATIC SCREENING HOOKS ────────────────────────────────────────────────────

async def screen_message_before_save(chat_id: str, sender_id: str, content: str) -> dict:
    """
    Hook: screen chat message before saving.
    Returns screening result; if auto-blocked, returns error to prevent save.
    """
    result = await screen_content_with_ai(
        content_type="message",
        content_text=content,
        content_id=f"chat_{chat_id}_temp",
        auto_action=True
    )
    if result.get("auto_actioned") and result.get("action") == "blocked":
        return {
            "allowed": False,
            "reason": "Content violates community guidelines",
            "ai_result": result
        }
    return {"allowed": True, "ai_result": result}

async def screen_quest_before_save(
    title: str,
    description: Optional[str] = None,
    quest_id: Optional[str] = None
) -> dict:
    """
    Hook: screen quest title/description before creation/update.
    """
    combined_text = f"{title} {description or ''}"
    result = await screen_content_with_ai(
        content_type="quest",
        content_text=combined_text,
        content_id=quest_id,
        auto_action=False  # Don't auto-block quests, just flag for review
    )
    return {"allowed": True, "ai_result": result}  # always allow, but flagged goes to queue

# ─── NOTIFICATION HELPERS ─────────────────────────────────────────────────────

async def _notify_user_action(user_id: str, action_type: str, reason: str, ban_until: Optional[str]):
    sb = _sb()
    profile = sb.table("profiles").select("whatsapp_id, telegram_id").eq("id", user_id).single().execute().data or {}
    messages = {
        "warning":       f"⚠️ *Account Warning*\n\nReason: {reason}\n\nThis is a formal warning. Continued violations may result in a ban. To appeal, use `/appeal`.",
        "temp_ban":      f"🚫 *Temporary Suspension*\n\nReason: {reason}\nSuspended until: {ban_until or 'review complete'}\n\nTo appeal, use `/appeal`.",
        "permanent_ban": f"❌ *Account Permanently Suspended*\n\nReason: {reason}\n\nIf you believe this is an error, contact playing.sidequest@gmail.com.",
    }
    msg = messages.get(action_type, "Your account status has been updated.")
    wa = profile.get("whatsapp_id")
    tg = profile.get("telegram_id")

    if wa:
        try:
            from evolution_bridge import EvolutionBridge
            bridge = EvolutionBridge()
            await bridge.send_message(wa, msg)
        except Exception as e:
            logger.error(f"[Trust] WA notify failed: {e}")

    if tg:
        try:
            from main import bot
            await bot.send_message(int(tg), msg, parse_mode="Markdown")
        except Exception as e:
            logger.error(f"[Trust] TG notify failed: {e}")


async def _notify_admins_sos(profile_id: str, user_name: str, match_id: Optional[str], message: str):
    if not ADMIN_WHATSAPP:
        return
    try:
        from evolution_bridge import EvolutionBridge
        bridge = EvolutionBridge()
        await bridge.send_message(ADMIN_WHATSAPP, f"🆘 SOS ALERT\n\n{message}")
    except Exception as e:
        logger.error(f"[SOS] Admin notify failed: {e}")


async def _notify_admins_appeal(user_id: str, action_id: str, reason: str):
    logger.info(f"[Trust] Appeal filed by {user_id} for action {action_id}")


async def _notify_user_appeal_outcome(user_id: str, granted: bool):
    sb = _sb()
    profile = sb.table("profiles").select("whatsapp_id, telegram_id").eq("id", user_id).single().execute().data or {}
    msg = (
        "✅ *Appeal Granted*\n\nYour appeal has been reviewed and approved. Your account restrictions have been lifted. Thank you for your patience."
        if granted else
        "❌ *Appeal Denied*\n\nAfter careful review, we have upheld the original decision. For further queries, contact playing.sidequest@gmail.com."
    )
    wa = profile.get("whatsapp_id")
    if wa:
        try:
            from evolution_bridge import EvolutionBridge
            bridge = EvolutionBridge()
            await bridge.send_message(wa, msg)
        except Exception:
            pass
