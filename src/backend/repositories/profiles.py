"""
repositories/profiles.py — Profile CRUD, stats, platform linking, email linking.
All methods moved from db_layer.py without modification.
"""
import os
import re
import uuid
import logging
from typing import Optional
from backend.supabase_client import get_supabase

logger = logging.getLogger(__name__)

# ─── Allowed values for enum-like fields ─────────────────────────────────────
VALID_PLATFORMS = frozenset([
    "whatsapp_id", "telegram_id", "google_id", "psn_id", "xbox_id"
])


def _validate_uuid(value: str, field_name: str = "id"):
    """Raise ValueError if value is not a valid UUID string."""
    try:
        uuid.UUID(str(value))
    except (ValueError, AttributeError):
        raise ValueError(f"Invalid UUID for field '{field_name}': {value}")


def _get_supabase():
    """Return a shared Supabase client."""
    return get_supabase()


# ─── Profile Repository ───────────────────────────────────────────────────────

def get_profile_by_platform(platform: str, platform_id: str):
    """platform must be one of VALID_PLATFORMS to prevent column injection."""
    supabase = _get_supabase()
    if platform not in VALID_PLATFORMS:
        raise ValueError(f"Invalid platform column: '{platform}'")
    if not platform_id or not isinstance(platform_id, str):
        raise ValueError("platform_id must be a non-empty string")
    if not re.match(r'^[\w\+\-\.\:@]+$', platform_id):
        raise ValueError(f"platform_id contains invalid characters: {platform_id}")

    res = supabase.table("profiles").select("""
        id, display_name, telegram_id, whatsapp_id, google_id, psn_id, xbox_id,
        email, is_public_available,
        balance, is_whitelisted,
        wallet_address, linked_wallet, circle_wallet_id,
        play_points, total_wins, total_losses,
        location_city, location_visible, created_at, updated_at
    """).eq(platform, platform_id).execute()
    return res.data[0] if res.data else None


def get_profile_by_email(email: str):
    """Get profile by email address"""
    supabase = _get_supabase()
    email = email.lower().strip()
    res = supabase.table("profiles").select("""
        id, display_name, username, telegram_id, whatsapp_id, google_id, psn_id, xbox_id,
        email, password_hash,
        balance, is_whitelisted,
        wallet_address, linked_wallet, circle_wallet_id,
        play_points, total_wins, total_losses,
        location_city, location_visible, created_at, updated_at
    """).eq("email", email).maybe_single().execute()
    return res.data if res and res.data else None


def get_profile_by_circle_wallet(circle_wallet_id: str) -> dict | None:
    """Get profile by Circle wallet identifier."""
    supabase = _get_supabase()

    # 1️⃣ Try by circle_wallet_id (new accounts)
    res = supabase.table("profiles").select("""
        id, display_name, telegram_id, whatsapp_id, google_id, psn_id, xbox_id,
        email, is_public_available,
        balance, is_whitelisted,
        wallet_address, play_points, total_wins, total_losses,
        location_city, location_visible, created_at, updated_at
    """).eq("circle_wallet_id", circle_wallet_id).maybe_single().execute()
    if res.data:
        return res.data

    # 2️⃣ Fallback: try by linked_wallet (older accounts — custodial address)
    res = supabase.table("profiles").select("""
        id, display_name, telegram_id, whatsapp_id, google_id, psn_id, xbox_id,
        email, is_public_available,
        balance, is_whitelisted,
        wallet_address, play_points, total_wins, total_losses,
        location_city, location_visible, created_at, updated_at
    """).eq("linked_wallet", circle_wallet_id).maybe_single().execute()
    if res.data:
        return res.data

    # 3️⃣ Last resort: try wallet_address (another legacy field)
    res = supabase.table("profiles").select("""
        id, display_name, telegram_id, whatsapp_id, google_id, psn_id, xbox_id,
        email, is_public_available,
        balance, is_whitelisted,
        wallet_address, play_points, total_wins, total_losses,
        location_city, location_visible, created_at, updated_at
    """).eq("wallet_address", circle_wallet_id).maybe_single().execute()
    return res.data if res.data else None


def get_or_create_profile(platform: str, platform_id: str):
    """Get or create a profile by platform credentials."""
    supabase = _get_supabase()
    profile = get_profile_by_platform(platform, platform_id)
    if not profile:
        # Only tag early adopters if on mainnet (testnet users are excluded)
        is_mainnet = os.getenv("NETWORK") == "mainnet"
        is_early = False

        if is_mainnet:
            # Check if this is an early adopter (first 1000 users on mainnet)
            count_res = supabase.table("profiles").select("id", count="exact", head=True).execute()
            total_users = int(count_res.headers.get("x-total-count", 0))
            is_early = total_users < 1000

        # Create new profile
        profile_data = {
            "telegram_id": None,
            "whatsapp_id": None,
            "google_id": None,
            "psn_id": None,
            "xbox_id": None,
            "balance": 0,
            "is_whitelisted": is_early,
            "wallet_address": None,
            "play_points": 0,
            "total_wins": 0,
            "total_losses": 0,
            "location_city": None,
            "location_visible": False,
        }
        profile_data[platform] = platform_id

        res = supabase.table("profiles").insert(profile_data).execute()
        if res.data:
            profile = res.data[0]
    return profile


def link_platform_to_profile(profile_id: str, platform: str, platform_id: str):
    """Link a platform ID to a profile."""
    supabase = _get_supabase()
    _validate_uuid(profile_id, "profile_id")
    if platform not in VALID_PLATFORMS:
        raise ValueError(f"Invalid platform: {platform}")

    existing = get_profile_by_platform(platform, platform_id)
    if existing:
        return None

    res = supabase.table("profiles").update({platform: platform_id}).eq("id", profile_id).execute()
    return res.data[0] if res.data else None


def link_email_to_profile(profile_id: str, email: str):
    """Link email to profile for cross-platform sync"""
    supabase = _get_supabase()
    _validate_uuid(profile_id, "profile_id")
    email = email.lower().strip()
    existing = get_profile_by_email(email)
    if existing:
        return None
    res = supabase.table("profiles").update({"email": email}).eq("id", profile_id).execute()
    return res.data[0] if res.data else None


def get_all_profiles():
    """Get all user profiles"""
    supabase = _get_supabase()
    res = supabase.table("profiles").select("""
        id, display_name, telegram_id, whatsapp_id, google_id, psn_id, xbox_id,
        email, is_public_available,
        balance, is_whitelisted,
        wallet_address, linked_wallet, circle_wallet_id,
        play_points, total_wins, total_losses,
        location_city, location_visible, created_at
    """).execute()
    return res.data if res.data else []


def get_profile_by_id(profile_id: str):
    """Get profile by UUID"""
    supabase = _get_supabase()
    _validate_uuid(profile_id, "profile_id")
    res = supabase.table("profiles").select("""
        id, display_name, telegram_id, whatsapp_id, google_id, psn_id, xbox_id,
        email, is_public_available,
        balance, is_whitelisted,
        wallet_address, linked_wallet, circle_wallet_id,
        play_points, total_wins, total_losses,
        location_city, location_visible, created_at, updated_at,
        discovery_radius_km, lifecycle_stage, category_affinity_vector,
        is_early_adopter, is_verified, is_content_creator, creator_badges,
        is_admin, reputation, quests_completed, archetype, nakama_count
    """).eq("id", profile_id).single().execute()
    return res.data if res.data else None


def get_profile_by_uuid(profile_id: str):
    """Alias for get_profile_by_id"""
    return get_profile_by_id(profile_id)


def get_profile_by_flw_tx_ref_prefix(prefix: str):
    """Finds a profile whose ID starts with the given prefix."""
    supabase = _get_supabase()
    try:
        res = supabase.table("profiles").select("""
            id, display_name, telegram_id, whatsapp_id, google_id, psn_id, xbox_id,
            email, is_public_available,
            balance, is_whitelisted,
            wallet_address, linked_wallet, circle_wallet_id,
            play_points, total_wins, total_losses,
            location_city, location_visible, created_at, updated_at
        """).like("id", f"{prefix}%").maybe_single().execute()
        return res.data
    except Exception as e:
        logger.exception("Profile lookup by prefix failed: %s", e)
        return None


# ─── Profile Updates ──────────────────────────────────────────────────────────

ALLOWED_PROFILE_FIELDS = frozenset([
    "display_name", "username", "avatar_url", "avatar_config",
    "bio", "location_city", "location_visible", "tos_accepted",
    "notification_prefs", "category_affinity_vector",
])


def update_profile_field(profile_id: str, field: str, value):
    """Update a single allowed field on a profile."""
    supabase = _get_supabase()
    _validate_uuid(profile_id, "profile_id")
    if field not in ALLOWED_PROFILE_FIELDS:
        raise ValueError(f"Field '{field}' is not allowed for update")
    try:
        res = supabase.table("profiles").update({field: value}).eq("id", profile_id).execute()
        return res.data[0] if res.data else None
    except Exception as e:
        logger.exception("Profile field update failed: %s", e)
        return None


def create_profile(profile_id: str, profile_data: dict):
    """Create a new profile row."""
    supabase = _get_supabase()
    _validate_uuid(profile_id, "profile_id")
    profile_data["id"] = profile_id
    try:
        res = supabase.table("profiles").insert(profile_data).execute()
        return res.data[0] if res.data else None
    except Exception as e:
        logger.exception("Profile creation failed: %s", e)
        return None


ALLOWED_UPDATE_FIELDS = frozenset([
    "display_name", "username", "avatar_url", "avatar_config",
    "bio", "location_city", "location_visible", "tos_accepted",
    "notification_prefs", "category_affinity_vector",
    "is_content_creator", "creator_badges", "is_verified",
])


def update_profile(profile_id: str, update_data: dict):
    """Update multiple allowed fields on a profile."""
    supabase = _get_supabase()
    _validate_uuid(profile_id, "profile_id")
    filtered = {k: v for k, v in update_data.items() if k in ALLOWED_UPDATE_FIELDS}
    if not filtered:
        return None
    try:
        res = supabase.table("profiles").update(filtered).eq("id", profile_id).execute()
        return res.data[0] if res.data else None
    except Exception as e:
        logger.exception("Profile update failed: %s", e)
        return None


def increment_public_stats(profile_id: str, result: str):
    """Increment public W-L stats. result: 'win', 'loss'"""
    supabase = _get_supabase()
    _validate_uuid(profile_id, "profile_id")
    try:
        if result == "win":
            res = supabase.table("profiles").select("public_wins").eq("id", profile_id).single().execute()
            current = int(res.data.get("public_wins", 0)) if res.data else 0
            supabase.table("profiles").update({"public_wins": current + 1}).eq("id", profile_id).execute()
        elif result == "loss":
            res = supabase.table("profiles").select("public_losses").eq("id", profile_id).single().execute()
            current = int(res.data.get("public_losses", 0)) if res.data else 0
            supabase.table("profiles").update({"public_losses": current + 1}).eq("id", profile_id).execute()
    except Exception as e:
        logger.exception("Failed to increment public stats for %s: %s", profile_id, e)


def add_creator_badge(profile_id: str, badge: str):
    """Add a creator badge to profile."""
    supabase = _get_supabase()
    _validate_uuid(profile_id, "profile_id")
    res = supabase.table("profiles").select("creator_badges").eq("id", profile_id).single().execute()
    badges = res.data.get("creator_badges", []) if res.data else []
    if badge not in badges:
        badges.append(badge)
        supabase.table("profiles").update({"creator_badges": badges}).eq("id", profile_id).execute()


def set_content_creator(profile_id: str, is_creator: bool = True):
    """Mark profile as content creator."""
    supabase = _get_supabase()
    _validate_uuid(profile_id, "profile_id")
    badges = supabase.table("profiles").select("creator_badges").eq("id", profile_id).single().execute().data.get("creator_badges", [])
    if is_creator and "content_creator" not in badges:
        badges.append("content_creator")
    supabase.table("profiles").update({
        "is_content_creator": is_creator,
        "creator_badges": badges
    }).eq("id", profile_id).execute()


def set_verified(profile_id: str, is_verified: bool = True):
    """Mark profile as verified."""
    supabase = _get_supabase()
    _validate_uuid(profile_id, "profile_id")
    supabase.table("profiles").update({"is_verified": is_verified}).eq("id", profile_id).execute()


# ─── Whitelist / Counts ───────────────────────────────────────────────────────

def set_whitelisted(profile_id: str, status: bool = True):
    _validate_uuid(profile_id, "profile_id")
    supabase = _get_supabase()
    res = supabase.table("profiles").update({"is_whitelisted": bool(status)}).eq("id", profile_id).execute()
    return res.data[0] if res.data else None


def get_whitelist_count():
    supabase = _get_supabase()
    res = supabase.table("profiles").select("id", count="exact").eq("is_whitelisted", True).execute()
    return res.count if res.count is not None else 0


def get_user_count():
    """Returns the total number of registered profiles."""
    supabase = _get_supabase()
    res = supabase.table("profiles").select("id", count="exact").execute()
    return res.count if res.count is not None else 0


def get_early_adopter_count():
    """Returns the number of users currently tagged as early adopters."""
    supabase = _get_supabase()
    res = supabase.table("profiles").select("id", count="exact").eq("is_early_adopter", True).execute()
    return res.count if res.count is not None else 0