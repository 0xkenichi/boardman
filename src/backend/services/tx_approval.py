"""
Telegram-mediated approval for spectator spends (bets + LP deposits).

Flow:
  1. Web backend checks the profile's per-action approval mode.
       - 'always' → execute immediately (user pre-approved this action type)
       - 'ask'    → create a pending approval, DM the user via the Boardman
                    bot with [✅ Yes] [❌ No] [🔁 Always approve] buttons,
                    then wait (poll) up to ``timeout_sec`` for the decision.
  2. The Telegram bot resolves the approval (yes/no/always) in the shared
     Supabase row; the web request sees the result and executes or declines.

Table: gaming.tx_approvals (see supabase/migrations/001_approval_flow.sql)
Mode columns on profiles: approval_mode_spectator_bet / approval_mode_lp_deposit
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from backend.supabase_client import get_supabase

DEFAULT_APPROVAL_TIMEOUT_SEC = 120  # product decision: 2 minutes

ACTION_MODE_COLUMNS = {
    "spectator_bet": "approval_mode_spectator_bet",
    "lp_deposit": "approval_mode_lp_deposit",
}
VALID_ACTIONS = set(ACTION_MODE_COLUMNS)
VALID_MODES = ("ask", "always")


def _sb():
    return get_supabase()


def _row(result) -> Optional[dict]:
    if result is None:
        return None
    data = getattr(result, "data", None)
    if isinstance(data, list):
        return data[0] if data else None
    if isinstance(data, dict):
        return data
    return None


def get_approval_mode(profile_id: str, action: str) -> str:
    """Current approval mode ('ask' | 'always') for a profile + action type."""
    col = ACTION_MODE_COLUMNS.get(action)
    if not col:
        return "ask"
    try:
        r = _sb().table("profiles").select(col).eq("id", profile_id).limit(1).execute()
        row = _row(r)
        val = (row or {}).get(col)
        return val if val in VALID_MODES else "ask"
    except Exception:
        return "ask"


def set_approval_mode(profile_id: str, action: str, mode: str) -> None:
    """Persist the per-action approval preference."""
    col = ACTION_MODE_COLUMNS.get(action)
    if not col or mode not in VALID_MODES:
        return
    try:
        _sb().table("profiles").update({col: mode}).eq("id", profile_id).execute()
    except Exception:
        pass


def _approval_text(action: str, payload: dict) -> str:
    amount = float(payload.get("amount") or 0)
    if action == "lp_deposit":
        agent = str(payload.get("agent_name") or payload.get("agent_id") or "the agent")
        return (
            f"💧 <b>Approve LP deposit?</b>\n\n"
            f"You're about to provide <b>${amount:,.2f}</b> of liquidity to "
            f"<b>{agent}</b>'s bankroll.\n\n"
            f"<i>You take a share of skill profits and a haircut on losses. "
            f"Withdrawable anytime from free capital.</i>"
        )
    side = str(payload.get("side") or "a")
    who = "Raja" if side in ("a", "raja", "white") else "Nero"
    return (
        f"🎯 <b>Approve arena bet?</b>\n\n"
        f"You're about to bet <b>${amount:,.2f}</b> on <b>{who}</b>.\n\n"
        f"Tap <b>Yes</b> to approve once, <b>Always approve</b> to skip the "
        f"prompt for { 'bets' if action == 'spectator_bet' else 'LP deposits' }."
    )


def create_approval_row(
    profile_id: str,
    action: str,
    payload: dict,
    timeout_sec: int = DEFAULT_APPROVAL_TIMEOUT_SEC,
) -> str:
    """Insert a pending approval; returns its id."""
    aid = str(uuid.uuid4())
    expires = datetime.now(timezone.utc) + timedelta(seconds=timeout_sec)
    try:
        _sb().schema("gaming").table("tx_approvals").insert(
            {
                "id": aid,
                "profile_id": profile_id,
                "action": action,
                "payload": payload,
                "status": "pending",
                "expires_at": expires.isoformat(),
            }
        ).execute()
    except Exception:
        raise
    return aid


def get_approval_row(approval_id: str) -> Optional[dict]:
    try:
        r = (
            _sb()
            .schema("gaming")
            .table("tx_approvals")
            .select("*")
            .eq("id", approval_id)
            .limit(1)
            .execute()
        )
        return _row(r)
    except Exception:
        return None


def _mark_status(approval_id: str, status: str) -> None:
    try:
        _sb().schema("gaming").table("tx_approvals").update(
            {"status": status, "decided_at": datetime.now(timezone.utc).isoformat()}
        ).eq("id", approval_id).execute()
    except Exception:
        pass


def resolve_approval(approval_id: str, decision: str, always: bool = False) -> dict:
    """
    Called by the Telegram bot when the user taps Yes / No / Always approve.

    decision: 'yes' | 'no'
    always:   also persist per-action 'always' mode for future spends
    """
    row = get_approval_row(approval_id)
    if not row:
        return {"ok": False, "reason": "approval_not_found"}
    if row.get("status") != "pending":
        return {"ok": False, "reason": "already_decided", "status": row.get("status")}

    status = "approved" if decision == "yes" else "denied"
    _mark_status(approval_id, status)

    profile_id = row.get("profile_id")
    action = row.get("action") or ""
    if always and status == "approved" and action in ACTION_MODE_COLUMNS:
        set_approval_mode(profile_id, action, "always")

    return {
        "ok": True,
        "status": status,
        "always": always,
        "profile_id": profile_id,
        "action": action,
        "payload": row.get("payload") or {},
    }


async def _notify(profile_id: str, text: str, buttons) -> bool:
    try:
        from gaming.src.bot.utils.notify import notify_user

        return await notify_user(profile_id, text, buttons=buttons)
    except Exception:
        return False


async def request_approval(
    profile_id: str,
    action: str,
    payload: dict,
    timeout_sec: int = DEFAULT_APPROVAL_TIMEOUT_SEC,
) -> dict:
    """
    Gate a spend behind Telegram approval.

    Returns {'status': 'approved'|'always'|'denied'|'expired', ...}.
    'always' means the user had pre-approved this action type (no prompt sent).
    """
    if action not in VALID_ACTIONS:
        return {"status": "denied", "reason": f"unknown action {action}"}

    if get_approval_mode(profile_id, action) == "always":
        return {"status": "approved", "mode": "always", "skipped": True}

    started = await start_approval(profile_id, action, payload, timeout_sec)
    if started.get("status") != "pending":
        return started
    return await poll_approval(started["approval_id"], timeout_sec)


async def start_approval(
    profile_id: str,
    action: str,
    payload: dict,
    timeout_sec: int = DEFAULT_APPROVAL_TIMEOUT_SEC,
) -> dict:
    """Send the Telegram prompt and return immediately (no wait)."""
    if action not in VALID_ACTIONS:
        return {"status": "denied", "reason": f"unknown action {action}"}
    if get_approval_mode(profile_id, action) == "always":
        return {"status": "approved", "mode": "always", "skipped": True}

    approval_id = create_approval_row(profile_id, action, payload, timeout_sec)
    from gaming.src.bot.keyboards import approval_menu

    sent = await _notify(
        profile_id,
        _approval_text(action, payload),
        approval_menu(approval_id),
    )
    if not sent:
        _mark_status(approval_id, "expired")
        return {
            "status": "telegram_unreachable",
            "approval_id": approval_id,
            "reason": "telegram_unreachable",
            "message": (
                "Could not DM you in Telegram. Open @myboardmanOfficialBot and tap Start, "
                "then try the bet / LP again."
            ),
        }
    return {"status": "pending", "approval_id": approval_id, "mode": "ask"}


async def poll_approval(approval_id: str, timeout_sec: int) -> dict:
    """Poll Supabase until the bot resolves the approval or it expires."""
    deadline = asyncio.get_event_loop().time() + timeout_sec
    while True:
        row = get_approval_row(approval_id)
        status = (row or {}).get("status") or "pending"
        if status in ("approved", "denied"):
            return {"status": status, "approval_id": approval_id, "mode": "ask"}
        if asyncio.get_event_loop().time() >= deadline:
            _mark_status(approval_id, "expired")
            return {"status": "expired", "approval_id": approval_id}
        await asyncio.sleep(1.5)
