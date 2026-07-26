"""
repositories/quests.py — Quest/Challenge CRUD, discovery, joining, privacy filtering.
Bets, challenges, sessions, friend circles, and tags. All moved from db_layer.py.
"""
import re
import uuid
import logging
from supabase_client import get_supabase

logger = logging.getLogger(__name__)


def _get_supabase():
    return get_supabase()


def _validate_uuid(value: str, field_name: str = "id"):
    """Raise ValueError if value is not a valid UUID string."""
    try:
        uuid.UUID(str(value))
    except (ValueError, AttributeError):
        raise ValueError(f"Invalid UUID for field '{field_name}': {value}")


def _validate_positive_amount(amount, field_name: str = "amount"):
    """Raise ValueError if amount is not a positive number."""
    try:
        val = float(amount)
    except (TypeError, ValueError):
        raise ValueError(f"Invalid amount for field '{field_name}': {amount}")
    if val <= 0:
        raise ValueError(f"Amount '{field_name}' must be positive, got: {val}")
    return val


# ─── Friend Circles ───────────────────────────────────────────────────────────

def create_friend_circle(user_id: str, name: str, description: str = ""):
    """Create a friend circle (group)."""
    supabase = _get_supabase()
    _validate_uuid(user_id, "user_id")
    data = {
        "user_id": user_id,
        "name": name[:100],
        "description": description[:500] if description else ""
    }
    res = supabase.table("friend_circles").insert(data).execute()
    return res.data[0] if res.data else None


def get_user_circles(user_id: str):
    """Get all circles for a user."""
    supabase = _get_supabase()
    _validate_uuid(user_id, "user_id")
    res = supabase.table("friend_circles").select("""
        id, user_id, name, description, created_at
    """).eq("user_id", user_id).order("created_at", desc=True).execute()
    return res.data if res.data else []


def get_circle_by_id(circle_id: str):
    """Get a specific circle."""
    supabase = _get_supabase()
    _validate_uuid(circle_id, "circle_id")
    res = supabase.table("friend_circles").select("""
        id, user_id, name, description, created_at
    """).eq("id", circle_id).single().execute()
    return res.data if res.data else None


def add_member_to_circle(circle_id: str, member_id: str):
    """Add a member to a friend circle."""
    supabase = _get_supabase()
    _validate_uuid(circle_id, "circle_id")
    _validate_uuid(member_id, "member_id")

    # Check if already a member
    existing = supabase.table("circle_members").select("*").eq(
        "circle_id", circle_id
    ).eq("member_id", member_id).execute()

    if existing.data:
        return None

    data = {
        "circle_id": circle_id,
        "member_id": member_id
    }
    res = supabase.table("circle_members").insert(data).execute()
    return res.data[0] if res.data else None


def remove_member_from_circle(circle_id: str, member_id: str):
    """Remove a member from a friend circle."""
    supabase = _get_supabase()
    _validate_uuid(circle_id, "circle_id")
    _validate_uuid(member_id, "member_id")

    res = supabase.table("circle_members").delete().eq(
        "circle_id", circle_id
    ).eq("member_id", member_id).execute()
    return res.data[0] if res.data else None


def get_circle_members(circle_id: str):
    """Get all members of a circle."""
    supabase = _get_supabase()
    _validate_uuid(circle_id, "circle_id")
    res = supabase.table("circle_members").select("""
        member_id, profiles!circle_members_member_id_fkey(id, display_name, username, avatar_url)
    """).eq("circle_id", circle_id).execute()
    return res.data if res.data else []


def update_circle_visibility(circle_id: str, visibility: str):
    """Update circle visibility (public, private, nakama)."""
    supabase = _get_supabase()
    _validate_uuid(circle_id, "circle_id")
    if visibility not in ["public", "private", "nakama"]:
        raise ValueError(f"Invalid visibility: {visibility}")

    res = supabase.table("friend_circles").update({
        "visibility": visibility
    }).eq("id", circle_id).execute()
    return res.data[0] if res.data else None


def delete_friend_circle(circle_id: str):
    """Delete a friend circle."""
    supabase = _get_supabase()
    _validate_uuid(circle_id, "circle_id")
    res = supabase.table("friend_circles").delete().eq("id", circle_id).execute()
    return res.data[0] if res.data else None


# ─── Bets ─────────────────────────────────────────────────────────────────────

def get_all_bets():
    """Get all bets from the database"""
    supabase = _get_supabase()
    res = supabase.table("bets").select("""
        id, creator_id, opponent_id, amount, stake_usd, game_type, status,
        is_on_chain, challenge_type, is_public, session_id, short_id,
        match_type, timeout_minutes, locked_at, creator_report,
        opponent_report, creator_screenshot, opponent_screenshot,
        onchain_match_id, onchain_status, resolve_tx_hash, cancel_tx_hash,
        created_at, updated_at
    """).execute()
    return res.data if res.data else []


def get_bets_by_user(user_id: str):
    """Get all bets for a specific user"""
    supabase = _get_supabase()
    _validate_uuid(user_id, "user_id")
    res = supabase.table("bets").select("""
        id, creator_id, opponent_id, amount, stake_usd, game_type, status,
        is_on_chain, challenge_type, is_public, session_id, short_id,
        match_type, timeout_minutes, locked_at, creator_report,
        opponent_report, creator_screenshot, opponent_screenshot,
        onchain_match_id, onchain_status, resolve_tx_hash, cancel_tx_hash,
        created_at, updated_at
    """).or_(f"creator_id.eq.{user_id},opponent_id.eq.{user_id}").execute()
    return res.data if res.data else []


def create_bet(creator_uuid: str, amount, game_type: str, is_on_chain: bool = False, on_chain_pool_id: int = None,
               challenge_type: str = "private", is_public: bool = False, session_id: str = None):
    _validate_uuid(creator_uuid, "creator_uuid")
    amount = _validate_positive_amount(amount, "bet amount")
    # Sanitise game_type
    if not isinstance(game_type, str) or not re.match(r'^[\w\s\-]+$', game_type):
        raise ValueError(f"Invalid game_type: {game_type}")
    if challenge_type not in ("private", "public", "content_stream"):
        raise ValueError(f"Invalid challenge_type: {challenge_type}")
    if session_id:
        _validate_uuid(session_id, "session_id")
    supabase = _get_supabase()
    data = {
        "creator_id": creator_uuid,
        "amount": amount,
        "stake_usd": amount,
        "game_type": game_type[:64],
        "status": "OPEN",
        "is_on_chain": bool(is_on_chain),
        "challenge_type": challenge_type,
        "is_public": bool(is_public),
        "session_id": session_id
    }
    if on_chain_pool_id is not None:
        data["on_chain_pool_id"] = int(on_chain_pool_id)
    res = supabase.table("bets").insert(data).execute()
    return res.data[0] if res.data else None


def get_open_bets(public_only: bool = False):
    supabase = _get_supabase()
    query = supabase.table("bets").select("""
        id, creator_id, opponent_id, amount, stake_usd, game_type, status,
        is_on_chain, challenge_type, is_public, session_id, short_id,
        match_type, timeout_minutes, locked_at, creator_report,
        opponent_report, creator_screenshot, opponent_screenshot,
        onchain_match_id, onchain_status, resolve_tx_hash, cancel_tx_hash,
        created_at, updated_at, profiles!creator_id(psn_id, xbox_id, display_name, is_verified, is_content_creator, creator_badges, is_over_18, avatar_url)
    """).eq("status", "OPEN")
    if public_only:
        query = query.eq("is_public", True)
    res = query.execute()
    return res.data


def get_public_challenges(limit: int = 50):
    """Get open public challenges with profile info."""
    supabase = _get_supabase()
    res = supabase.table("challenges").select("""
        *,
        issuer:profiles!challenges_issuer_id_fkey(id, display_name, is_verified, is_content_creator, creator_badges, is_over_18, avatar_url),
        target:profiles!challenges_target_id_fkey(id, display_name, is_verified, is_content_creator, creator_badges, is_over_18, avatar_url)
    """).eq("status", "open").order("created_at", desc=True).limit(limit).execute()
    return res.data if res.data else []


def match_bet(bet_id: str, opponent_uuid: str):
    supabase = _get_supabase()
    _validate_uuid(bet_id, "bet_id")
    _validate_uuid(opponent_uuid, "opponent_uuid")
    # Atomic status guard: only update if status is still OPEN
    res = supabase.table("bets").update({
        "opponent_id": opponent_uuid,
        "status": "MATCHED"
    }).eq("id", bet_id).eq("status", "OPEN").execute()
    return res.data[0] if res.data else None


def approve_bet(bet_id: str, creator_uuid: str):
    supabase = _get_supabase()
    _validate_uuid(bet_id, "bet_id")
    _validate_uuid(creator_uuid, "creator_uuid")
    res = supabase.table("bets").update({
        "status": "PENDING_REPORTS"
    }).eq("id", bet_id).eq("creator_id", creator_uuid).eq("status", "MATCHED").execute()
    return res.data[0] if res.data else None


def resolve_bet(bet_id: str, winner_uuid: str):
    supabase = _get_supabase()
    _validate_uuid(bet_id, "bet_id")
    _validate_uuid(winner_uuid, "winner_uuid")
    res = supabase.table("bets").update({
        "status": "COMPLETED",
        "winner_id": winner_uuid
    }).eq("id", bet_id).in_("status", ["ACCEPTED", "PENDING_REPORTS", "LOCKED"]).execute()
    return res.data[0] if res.data else None


def cancel_bet(bet_id: str):
    """Mark a bet as CANCELLED (for timeouts, draws, disputes escalated)."""
    supabase = _get_supabase()
    _validate_uuid(bet_id, "bet_id")
    res = supabase.table("bets").update({
        "status": "CANCELLED"
    }).eq("id", bet_id).in_("status", ["OPEN", "LOCKED", "INVITED"]).execute()
    return res.data[0] if res.data else None


def get_bet(bet_id: str):
    supabase = _get_supabase()
    _validate_uuid(bet_id, "bet_id")
    res = supabase.table("bets").select("""
        id, creator_id, opponent_id, amount, stake_usd, game_type, status,
        is_on_chain, challenge_type, is_public, session_id, short_id,
        match_type, timeout_minutes, locked_at, creator_report,
        opponent_report, creator_screenshot, opponent_screenshot,
        onchain_match_id, onchain_status, resolve_tx_hash, cancel_tx_hash,
        created_at, updated_at
    """).eq("id", bet_id).single().execute()
    return res.data


# ─── Challenges ───────────────────────────────────────────────────────────────

def create_challenge(issuer_id: str, game_type: str, stake_amount: float,
                     target_id: str = None, message: str = "", theme: str = ""):
    """Create a public challenge."""
    supabase = _get_supabase()
    _validate_uuid(issuer_id, "issuer_id")
    if target_id:
        _validate_uuid(target_id, "target_id")
    data = {
        "issuer_id": issuer_id,
        "target_id": target_id,
        "game_type": game_type,
        "stake_amount": stake_amount,
        "message": message,
        "theme": theme
    }
    res = supabase.table("challenges").insert(data).execute()
    return res.data[0] if res.data else None


def get_challenge(challenge_id: str):
    """Get challenge by ID."""
    supabase = _get_supabase()
    _validate_uuid(challenge_id, "challenge_id")
    res = supabase.table("challenges").select("*").eq("id", challenge_id).single().execute()
    return res.data if res.data else None


def accept_challenge(challenge_id: str, bet_id: str = None):
    """Accept a public challenge."""
    supabase = _get_supabase()
    _validate_uuid(challenge_id, "challenge_id")
    update_data = {"status": "accepted", "updated_at": "now()"}
    if bet_id:
        _validate_uuid(bet_id, "bet_id")
        update_data["bet_id"] = bet_id
    res = supabase.table("challenges").update(update_data).eq("id", challenge_id).eq("status", "open").execute()
    return res.data[0] if res.data else None


def decline_challenge(challenge_id: str):
    """Decline a public challenge."""
    supabase = _get_supabase()
    _validate_uuid(challenge_id, "challenge_id")
    res = supabase.table("challenges").update({"status": "declined", "updated_at": "now()"}).eq("id", challenge_id).eq("status", "open").execute()
    return res.data[0] if res.data else None


def expire_challenge(challenge_id: str):
    """Mark challenge as expired."""
    supabase = _get_supabase()
    _validate_uuid(challenge_id, "challenge_id")
    res = supabase.table("challenges").update({"status": "expired", "updated_at": "now()"}).eq("id", challenge_id).eq("status", "open").execute()
    return res.data[0] if res.data else None


def get_active_challenges(target_id: str = None):
    """Get all open challenges, optionally filtered by target."""
    supabase = _get_supabase()
    query = supabase.table("challenges").select("*").eq("status", "open").order("created_at", desc=True)
    if target_id:
        _validate_uuid(target_id, "target_id")
        query = query.eq("target_id", target_id)
    res = query.execute()
    return res.data if res.data else []


def get_player_challenges(player_id: str):
    """Get all challenges issued by or to a player."""
    supabase = _get_supabase()
    _validate_uuid(player_id, "player_id")
    res = supabase.table("challenges").select("*").or_(f"issuer_id.eq.{player_id},target_id.eq.{player_id}").order("created_at", desc=True).execute()
    return res.data if res.data else []


# ─── Sessions ─────────────────────────────────────────────────────────────────

def create_session(host_id: str, guest_id: str = None, title: str = "",
                   description: str = "", game_type: str = "",
                   status: str = "scheduled"):
    """Create a match session (for tracking series of matches)."""
    supabase = _get_supabase()
    _validate_uuid(host_id, "host_id")
    if guest_id:
        _validate_uuid(guest_id, "guest_id")
    data = {
        "host_id": host_id,
        "guest_id": guest_id,
        "title": title,
        "description": description,
        "game_type": game_type,
        "status": status
    }
    res = supabase.table("sessions").insert(data).execute()
    return res.data[0] if res.data else None


def get_session(session_id: str):
    """Get session by ID."""
    supabase = _get_supabase()
    _validate_uuid(session_id, "session_id")
    res = supabase.table("sessions").select("*").eq("id", session_id).single().execute()
    return res.data if res.data else None


def update_session_status(session_id: str, status: str):
    """Update session status."""
    supabase = _get_supabase()
    _validate_uuid(session_id, "session_id")
    res = supabase.table("sessions").update({"status": status, "updated_at": "now()"}).eq("id", session_id).execute()
    return res.data[0] if res.data else None


def get_sessions_by_player(player_id: str):
    """Get all sessions for a player (host or guest)."""
    supabase = _get_supabase()
    _validate_uuid(player_id, "player_id")
    res = supabase.table("sessions").select("*").or_(f"host_id.eq.{player_id},guest_id.eq.{player_id}").order("start_time", desc=True).execute()
    return res.data if res.data else []


# ─── Tags ─────────────────────────────────────────────────────────────────────

def get_all_tags():
    """Get all available tags."""
    supabase = _get_supabase()
    try:
        res = supabase.table("tags").select("*").order("name").execute()
        return res.data if res.data else []
    except Exception as e:
        logger.exception("Get all tags failed: %s", e)
        return []


def get_user_tags(user_id: str):
    """Get tags for a specific user."""
    supabase = _get_supabase()
    _validate_uuid(user_id, "user_id")
    try:
        res = supabase.table("user_tags").select(
            "tag_id, weight, pinned, added_at, tags(name, display, emoji, category)"
        ).eq("user_id", user_id).order("pinned", desc=True).order("added_at", desc=True).execute()
        return res.data if res.data else []
    except Exception as e:
        logger.exception("Get user tags failed: %s", e)
        return []


def add_user_tag(user_id: str, tag_id: str, pinned: bool = False):
    """Add a tag to a user."""
    supabase = _get_supabase()
    _validate_uuid(user_id, "user_id")
    _validate_uuid(tag_id, "tag_id")
    try:
        res = supabase.table("user_tags").upsert({
            "user_id": user_id,
            "tag_id": tag_id,
            "pinned": pinned,
            "weight": 1.0
        }).execute()
        return res.data[0] if res.data else None
    except Exception as e:
        logger.exception("Add user tag failed: %s", e)
        return None


def remove_user_tag(user_id: str, tag_id: str):
    """Remove a tag from a user."""
    supabase = _get_supabase()
    _validate_uuid(user_id, "user_id")
    _validate_uuid(tag_id, "tag_id")
    try:
        res = supabase.table("user_tags").delete().eq(
            "user_id", user_id
        ).eq("tag_id", tag_id).execute()
        return True
    except Exception as e:
        logger.exception("Remove user tag failed: %s", e)
        return False