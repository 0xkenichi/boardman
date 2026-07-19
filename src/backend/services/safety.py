"""
ClawStation safety rails — free, env-driven, no paid services required.

Caps, pause switch, and simple rate limits so a bug or bad actor can't drain funds.
All knobs are environment variables (and optional admin Telegram IDs).
"""
from __future__ import annotations

import logging
import os
import threading
import time
from collections import defaultdict, deque
from decimal import Decimal
from typing import Optional

logger = logging.getLogger(__name__)

# ── Limits (override via env; mainnet-safe defaults are conservative) ─────────

MIN_STAKE_USDC = Decimal(os.getenv("CLAW_MIN_STAKE_USDC", "1"))
MAX_STAKE_USDC = Decimal(os.getenv("CLAW_MAX_STAKE_USDC", "25"))
MIN_WITHDRAW_USDC = Decimal(os.getenv("CLAW_MIN_WITHDRAW_USDC", "1"))
MAX_WITHDRAW_USDC = Decimal(os.getenv("CLAW_MAX_WITHDRAW_USDC", "50"))
DAILY_WITHDRAW_CAP_USDC = Decimal(os.getenv("CLAW_DAILY_WITHDRAW_CAP_USDC", "100"))

# How many money actions per user per hour
WITHDRAW_PER_HOUR = int(os.getenv("CLAW_WITHDRAW_PER_HOUR", "5"))
CHALLENGE_PER_HOUR = int(os.getenv("CLAW_CHALLENGE_PER_HOUR", "10"))
LOCK_PER_HOUR = int(os.getenv("CLAW_LOCK_PER_HOUR", "10"))

# Global kill switch — set CLAW_PAUSED=1 to freeze money movement
_paused_override: Optional[bool] = None  # runtime admin toggle
_pause_lock = threading.Lock()

# In-memory rate windows: key → deque of timestamps
_rate: dict[str, deque] = defaultdict(deque)
_rate_lock = threading.Lock()

# Daily withdraw totals: user_id → (day_key, total Decimal)
_daily_withdraw: dict[str, tuple[str, Decimal]] = {}
_daily_lock = threading.Lock()

# Idempotency: recent action keys (e.g. lock:challenge_id:user_id)
_recent_actions: dict[str, float] = {}
_idem_lock = threading.Lock()
IDEMPOTENCY_TTL_SEC = int(os.getenv("CLAW_IDEMPOTENCY_TTL_SEC", "90"))


def _env_paused() -> bool:
    v = (os.getenv("CLAW_PAUSED") or os.getenv("CLAWSTATION_PAUSED") or "").strip().lower()
    return v in ("1", "true", "yes", "on")


def is_paused() -> bool:
    with _pause_lock:
        if _paused_override is not None:
            return _paused_override
    return _env_paused()


def set_paused(paused: bool, reason: str = "") -> None:
    global _paused_override
    with _pause_lock:
        _paused_override = bool(paused)
    logger.warning("[Safety] pause=%s reason=%s", paused, reason or "admin")


def pause_message() -> str:
    return (
        "⏸ <b>ClawStation is paused</b>\n\n"
        "New challenges, stake locks, and withdrawals are temporarily disabled "
        "while we keep funds safe.\n\n"
        "You can still view Wallet, Profile, and My match status.\n"
        "Try again later."
    )


def admin_telegram_ids() -> set[int]:
    raw = os.getenv("CLAW_ADMIN_TELEGRAM_IDS") or os.getenv("ADMIN_TELEGRAM_IDS") or ""
    out: set[int] = set()
    for part in raw.replace(";", ",").split(","):
        part = part.strip()
        if not part:
            continue
        try:
            out.add(int(part))
        except ValueError:
            pass
    return out


def is_admin(telegram_id: Optional[int]) -> bool:
    if telegram_id is None:
        return False
    return int(telegram_id) in admin_telegram_ids()


def _prune_rate(key: str, window_sec: int = 3600) -> None:
    now = time.time()
    q = _rate[key]
    while q and now - q[0] > window_sec:
        q.popleft()


def check_rate(user_id: str, action: str, limit: int, window_sec: int = 3600) -> Optional[str]:
    """Return error string if over limit; else record and return None."""
    key = f"{action}:{user_id}"
    with _rate_lock:
        _prune_rate(key, window_sec)
        if len(_rate[key]) >= limit:
            return (
                f"⏳ Too many {action}s. Limit is {limit}/hour. "
                f"Wait a bit and try again."
            )
        _rate[key].append(time.time())
    return None


def check_idempotent(action_key: str) -> Optional[str]:
    """Block double-taps on the same money action for a short TTL."""
    now = time.time()
    with _idem_lock:
        # GC
        dead = [k for k, t in _recent_actions.items() if now - t > IDEMPOTENCY_TTL_SEC]
        for k in dead:
            _recent_actions.pop(k, None)
        if action_key in _recent_actions:
            return "⏳ That action is already in progress. Please wait…"
        _recent_actions[action_key] = now
    return None


def clear_idempotent(action_key: str) -> None:
    with _idem_lock:
        _recent_actions.pop(action_key, None)


def _today_key() -> str:
    # UTC day bucket
    return time.strftime("%Y-%m-%d", time.gmtime())


def _daily_total(user_id: str) -> Decimal:
    day = _today_key()
    prev_day, total = _daily_withdraw.get(user_id, (day, Decimal("0")))
    if prev_day != day:
        return Decimal("0")
    return total


def check_daily_withdraw(user_id: str, amount: Decimal) -> Optional[str]:
    """Peek only — does not commit. Call commit_daily_withdraw after success."""
    total = _daily_total(user_id)
    if total + amount > DAILY_WITHDRAW_CAP_USDC:
        return (
            f"❌ Daily withdraw limit is <b>${DAILY_WITHDRAW_CAP_USDC:,.0f}</b> USDC.\n"
            f"You've used <b>${total:,.2f}</b> today."
        )
    return None


def commit_daily_withdraw(user_id: str, amount: Decimal) -> None:
    day = _today_key()
    with _daily_lock:
        total = _daily_total(user_id)
        _daily_withdraw[user_id] = (day, total + amount)


def validate_stake(amount: Decimal) -> Optional[str]:
    if amount < MIN_STAKE_USDC:
        return f"❌ Min stake is ${MIN_STAKE_USDC}."
    if amount > MAX_STAKE_USDC:
        return f"❌ Max stake is ${MAX_STAKE_USDC} (safety cap)."
    return None


def validate_withdraw(amount: Decimal) -> Optional[str]:
    if amount < MIN_WITHDRAW_USDC:
        return f"❌ Min withdraw is ${MIN_WITHDRAW_USDC}."
    if amount > MAX_WITHDRAW_USDC:
        return f"❌ Max withdraw is ${MAX_WITHDRAW_USDC} per transfer."
    return None


def assert_money_ops_allowed(
    user_id: str,
    *,
    action: str = "action",
    amount: Optional[Decimal] = None,
    kind: str = "stake",  # stake | withdraw | lock
) -> Optional[str]:
    """
    Central gate for challenges, locks, withdraws.
    Returns HTML-safe error text or None if OK.
    """
    if is_paused():
        return pause_message()

    if kind in ("stake", "lock") and amount is not None:
        err = validate_stake(amount)
        if err:
            return err
    if kind == "withdraw" and amount is not None:
        err = validate_withdraw(amount)
        if err:
            return err
        err = check_daily_withdraw(user_id, amount)
        if err:
            return err

    limits = {
        "challenge": CHALLENGE_PER_HOUR,
        "lock": LOCK_PER_HOUR,
        "withdraw": WITHDRAW_PER_HOUR,
    }
    limit = limits.get(action, 20)
    return check_rate(user_id, action, limit)


def safety_status_text() -> str:
    return (
        f"🛡 <b>Safety status</b>\n\n"
        f"Paused: <b>{'YES' if is_paused() else 'no'}</b>\n"
        f"Stake: ${MIN_STAKE_USDC} – ${MAX_STAKE_USDC}\n"
        f"Withdraw: ${MIN_WITHDRAW_USDC} – ${MAX_WITHDRAW_USDC} "
        f"(day cap ${DAILY_WITHDRAW_CAP_USDC})\n"
        f"Rate: {CHALLENGE_PER_HOUR} challenges / {WITHDRAW_PER_HOUR} withdraws / hour"
    )
