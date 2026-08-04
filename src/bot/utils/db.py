"""Supabase-backed helpers for ClawStation bot profiles."""
from __future__ import annotations

import logging
import re
import time
from typing import Any, Optional

from aiogram.types import User

from backend.supabase_client import get_supabase

logger = logging.getLogger(__name__)

_PROFILE_SELECT = (
    "id, display_name, gaming_tag, gaming_tier, gaming_reputation_score, telegram_id, "
    "gaming_tx_password_hash, circle_wallet_id, gaming_deposit_address, gaming_psn_id, "
    "gaming_xbox_id, gaming_backup_email, gaming_bio, wallet_balance_usdc, "
    "gaming_telegram_chat_id, play_points, play_win_streak, play_best_streak, "
    "gaming_wins, gaming_losses, gaming_draws"
)

# Short-lived profile cache so every button tap doesn't round-trip Supabase.
# telegram_id -> (monotonic_ts, profile_dict)
_PROFILE_CACHE: dict[int, tuple[float, dict]] = {}
_PROFILE_CACHE_TTL = 45.0  # seconds


def invalidate_profile_cache(telegram_id: Optional[int] = None) -> None:
    """Drop cached profile(s). Call after wallet/tag changes if needed."""
    if telegram_id is None:
        _PROFILE_CACHE.clear()
    else:
        _PROFILE_CACHE.pop(int(telegram_id), None)


def _get_supabase():
    return get_supabase()


def _row(result: Any) -> Optional[dict]:
    """Safely unwrap a supabase execute() result (maybe_single can return None)."""
    if result is None:
        return None
    data = getattr(result, "data", None)
    if data is None:
        return None
    if isinstance(data, list):
        return data[0] if data else None
    if isinstance(data, dict):
        return data
    return None


def _rows(result: Any) -> list:
    if result is None:
        return []
    data = getattr(result, "data", None)
    if data is None:
        return []
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return [data]
    return []


def _display_name(user: User) -> str:
    if user.full_name and user.full_name.strip():
        return user.full_name.strip()
    if user.username:
        return user.username
    return "Gamer"


def _preferred_gaming_tag(user: User) -> str:
    """Prefer Telegram @username so challenges map 1:1 to social identity."""
    if user.username:
        cleaned = re.sub(r"[^a-zA-Z0-9_]", "", user.username)[:24]
        if cleaned:
            return cleaned.lower()
    base = f"user{user.id}"[-12:]
    return f"sq_{base}"


def _fetch_by_telegram_id(telegram_id: int) -> Optional[dict]:
    sb = _get_supabase()
    # Use limit(1) instead of maybe_single — more reliable across supabase-py versions.
    try:
        result = (
            sb.table("profiles")
            .select(_PROFILE_SELECT)
            .eq("telegram_id", telegram_id)
            .limit(1)
            .execute()
        )
    except Exception:
        # Older DB without play_points columns
        result = (
            sb.table("profiles")
            .select(
                "id, display_name, gaming_tag, gaming_tier, gaming_reputation_score, "
                "telegram_id, circle_wallet_id, gaming_deposit_address, "
                "gaming_telegram_chat_id, wallet_balance_usdc"
            )
            .eq("telegram_id", telegram_id)
            .limit(1)
            .execute()
        )
    return _row(result)


def _tag_taken(tag: str, exclude_id: Optional[str] = None) -> bool:
    sb = _get_supabase()
    q = sb.table("profiles").select("id").eq("gaming_tag", tag).limit(1)
    if exclude_id:
        q = q.neq("id", exclude_id)
    return _row(q.execute()) is not None


async def get_or_create_profile(user: User) -> dict:
    """Get or create a profile for a Telegram user (by ``telegram_id``).

    Supabase client is sync — run off the event loop so other bot handlers stay snappy.
    Cached ~45s per telegram_id so menu taps stay fast.
    """
    import asyncio
    import copy

    tid = int(user.id)
    hit = _PROFILE_CACHE.get(tid)
    if hit is not None:
        ts, prof = hit
        if time.monotonic() - ts < _PROFILE_CACHE_TTL and prof.get("id"):
            return copy.deepcopy(prof)

    profile = await asyncio.to_thread(_get_or_create_profile_sync, user)
    if profile and profile.get("id"):
        _PROFILE_CACHE[tid] = (time.monotonic(), copy.deepcopy(profile))
        # Bound cache size (casual bot: few hundred users max in memory)
        if len(_PROFILE_CACHE) > 500:
            cutoff = time.monotonic() - _PROFILE_CACHE_TTL
            stale = [k for k, (t, _) in _PROFILE_CACHE.items() if t < cutoff]
            for k in stale:
                _PROFILE_CACHE.pop(k, None)
    return profile


def _get_or_create_profile_sync(user: User) -> dict:
    """Sync body for :func:`get_or_create_profile`."""
    sb = _get_supabase()
    table = sb.table("profiles")

    profile = _fetch_by_telegram_id(user.id)
    if profile:
        updates: dict = {}
        preferred = _preferred_gaming_tag(user)
        current_tag = (profile.get("gaming_tag") or "").strip()
        # Upgrade auto-generated sq_* tags to the real username once available.
        if user.username and (not current_tag or current_tag.startswith("sq_")):
            if current_tag != preferred:
                try:
                    if not _tag_taken(preferred, exclude_id=profile["id"]):
                        updates["gaming_tag"] = preferred
                except Exception:
                    logger.warning(
                        "[DB] Tag clash check failed for %s", profile["id"], exc_info=True
                    )
        if not profile.get("display_name") or profile.get("display_name") in (
            "Anonymous",
            "Gamer",
        ):
            updates["display_name"] = _display_name(user)
        if updates:
            try:
                table.update(updates).eq("id", profile["id"]).execute()
                profile = {**profile, **updates}
            except Exception:
                logger.warning(
                    "[DB] Soft identity refresh failed for %s", profile["id"], exc_info=True
                )
        return profile

    preferred = _preferred_gaming_tag(user)
    try:
        tag = preferred if not _tag_taken(preferred) else f"sq_{preferred}_{str(user.id)[-4:]}"[:32]
    except Exception:
        tag = f"sq_user{user.id}"[-28:]

    insert_data = {
        "telegram_id": user.id,
        "display_name": _display_name(user),
        "gaming_tag": tag,
    }
    try:
        # .select() after insert so PostgREST returns the row
        created = table.insert(insert_data).select(_PROFILE_SELECT).execute()
    except Exception as exc:
        # Race: another /start inserted between select and insert
        logger.warning(
            "[DB] Insert failed for telegram_id=%s (%s); re-fetching", user.id, exc
        )
        profile = _fetch_by_telegram_id(user.id)
        if profile:
            return profile
        logger.exception("[DB] Failed to create profile for telegram_id=%s", user.id)
        raise RuntimeError(f"Failed to create profile: {exc}") from exc

    row = _row(created)
    if row:
        return row

    # Some clients return empty data on insert even when successful
    profile = _fetch_by_telegram_id(user.id)
    if profile:
        return profile
    raise RuntimeError("Profile creation returned no data")


def _get_profile_by_tag_sync(tag: str) -> Optional[dict]:
    sb = _get_supabase()
    raw = tag.lstrip("@").strip()
    candidates = [raw, raw.lower()]
    if not raw.startswith("sq_"):
        candidates.append(f"sq_{raw}")
        candidates.append(f"sq_{raw.lower()}")
    seen: set[str] = set()
    for candidate in candidates:
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        try:
            result = (
                sb.table("profiles")
                .select(_PROFILE_SELECT)
                .eq("gaming_tag", candidate)
                .limit(1)
                .execute()
            )
            row = _row(result)
            if row:
                return row
        except Exception:
            logger.warning("[DB] get_profile_by_tag failed for %s", candidate, exc_info=True)
            continue
    return None


async def get_profile_by_tag(tag: str) -> Optional[dict]:
    """Look up a profile by ``gaming_tag`` (with or without @ / sq_ prefix)."""
    import asyncio

    return await asyncio.to_thread(_get_profile_by_tag_sync, tag)


async def update_telegram_chat_id(user_id: str, chat_id: int) -> None:
    """Cache the user's Telegram chat id on their profile (required for challenge DMs)."""
    sb = _get_supabase()
    try:
        sb.table("profiles").update({"gaming_telegram_chat_id": chat_id}).eq(
            "id", user_id
        ).execute()
    except Exception:
        logger.exception("[DB] Failed to update gaming_telegram_chat_id for %s", user_id)
        raise
