"""
repositories/analytics.py — Leaderboard, reputation, retention, active users, admin analytics.
All moved from db_layer.py. Note: leaderboard/reputation/retention have N+1 query issues
flagged in the audit — refactoring to single queries or Postgres RPCs is a follow-up.
"""
import uuid
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional
from backend.supabase_client import get_supabase

logger = logging.getLogger(__name__)


def _get_supabase():
    return get_supabase()


def _validate_uuid(value: str, field_name: str = "id"):
    """Raise ValueError if value is not a valid UUID string."""
    try:
        uuid.UUID(str(value))
    except (ValueError, AttributeError):
        raise ValueError(f"Invalid UUID for field '{field_name}': {value}")


# ─── Top 10 / Qualified Players ──────────────────────────────────────────────

def get_top10_qualified(limit: int = 10):
    """Get Top 10 players by play points for auto-market eligibility."""
    supabase = _get_supabase()
    res = supabase.table("profiles").select("""
        id, display_name, play_points, total_wins, total_losses,
        is_verified, is_content_creator, is_over_18
    """).order("play_points", desc=True).limit(limit).execute()

    if res.data:
        for item in res.data:
            item['public_wins'] = item.get('total_wins', 0)
            item['public_losses'] = item.get('total_losses', 0)
            item['creator_badges'] = item.get('creator_badges', [])
    return res.data if res.data else []


def is_top10_player(profile_id: str) -> bool:
    """Check if player is in Top 10 by play points."""
    _validate_uuid(profile_id, "profile_id")
    top10 = get_top10_qualified(limit=10)
    return any(p["id"] == profile_id for p in top10)


# ─── Reputation ───────────────────────────────────────────────────────────────

def _is_player_in_receipt(receipt: dict, profile_id: str, get_bet_fn=None) -> bool:
    """Check if player is involved in a proof of play receipt."""
    # Avoid circular import — get_bet_fn is passed in from parent scope
    bet_id = receipt.get("bet_id")
    if not bet_id:
        return False

    if get_bet_fn is None:
        from repositories.quests import get_bet
        get_bet_fn = get_bet

    bet = get_bet_fn(bet_id)
    if not bet:
        return False

    return (str(bet.get("creator_id")) == profile_id or
            str(bet.get("opponent_id")) == profile_id)


def get_player_reputation(profile_id: str):
    """
    Calculate comprehensive reputation score for a player.
    Combines W-L record, $PLAY points, on-chain activity, and badges.

    Reputation Formula:
    - Base: play_points (1:1)
    - W-L bonus: (wins * 50) - (losses * 10)
    - Total match bonus: (total_wins * 10) - (total_losses * 2)
    - Verified bonus: +500
    - Content creator bonus: +300
    - Creator badges: +100 per badge
    - Proof of Play receipts: +50 per receipt

    Returns normalized reputation tier (Bronze/Silver/Gold/Platinum/Diamond)
    """
    supabase = _get_supabase()
    _validate_uuid(profile_id, "profile_id")

    from repositories.profiles import get_profile_by_id
    profile = get_profile_by_id(profile_id)
    if not profile:
        return None

    # Base stats - use only columns that definitely exist
    play_points = float(profile.get("play_points", 0))
    total_wins = int(profile.get("total_wins", 0))
    total_losses = int(profile.get("total_losses", 0))

    # Use total stats for both public and total (for compatibility)
    public_wins = total_wins
    public_losses = total_losses

    # Default values for newer columns that may not exist
    is_verified = bool(profile.get("is_verified", False))
    is_content_creator = bool(profile.get("is_content_creator", False))
    creator_badges = profile.get("creator_badges", []) or []

    # Calculate reputation score
    reputation_score = play_points  # Base: 1:1 with play points
    reputation_score += (public_wins * 50) - (public_losses * 10)  # W-L bonus
    reputation_score += (total_wins * 10) - (total_losses * 2)  # Total match bonus

    if is_verified:
        reputation_score += 500
    if is_content_creator:
        reputation_score += 300
    reputation_score += len(creator_badges) * 100

    # Proof of Play receipts bonus — use RPC to avoid N+1 query
    try:
        rpc_result = supabase.rpc("get_player_reputation_stats", {"p_profile_id": profile_id}).execute()
        if rpc_result.data and len(rpc_result.data) > 0:
            proof_of_play_count = int(rpc_result.data[0].get("proof_of_play_count", 0))
        else:
            proof_of_play_count = 0
    except Exception:
        # RPC might not exist yet (e.g., before migration runs)
        proof_of_play_count = 0

    reputation_score += proof_of_play_count * 50

    # Determine tier
    if reputation_score >= 10000:
        tier = "Diamond"
    elif reputation_score >= 5000:
        tier = "Platinum"
    elif reputation_score >= 2000:
        tier = "Gold"
    elif reputation_score >= 500:
        tier = "Silver"
    else:
        tier = "Bronze"

    # Calculate win rates
    public_win_rate = round((public_wins / max(public_wins + public_losses, 1)) * 100, 1)
    total_win_rate = round((total_wins / max(total_wins + total_losses, 1)) * 100, 1)

    return {
        "profile_id": profile_id,
        "display_name": profile.get("display_name"),
        "reputation": round(reputation_score, 2),
        "tier": tier,
        "play_points": play_points,
        "public_stats": {
            "wins": public_wins,
            "losses": public_losses,
            "win_rate": public_win_rate
        },
        "total_stats": {
            "wins": total_wins,
            "losses": total_losses,
            "win_rate": total_win_rate
        },
        "badges": creator_badges,
        "is_verified": is_verified,
        "is_content_creator": is_content_creator,
        "proof_of_play_count": proof_of_play_count,
        "on_chain_activity_score": proof_of_play_count * 50
    }


# ─── Leaderboard ──────────────────────────────────────────────────────────────

def get_game_leaderboard(game_type: str, limit: int = 50) -> list:
    """Get leaderboard for a specific game."""
    return get_leaderboard_by_state("game", game_type, limit)


def get_region_leaderboard(region: str, limit: int = 50) -> list:
    """Get leaderboard for a specific region."""
    return get_leaderboard_by_state("region", region, limit)


def get_tier_leaderboard(tier: str, limit: int = 50) -> list:
    """Get leaderboard for a specific reputation tier."""
    return get_leaderboard_by_state("tier", tier, limit)


def get_leaderboard_by_state(state_type: str = "global", state_value: str = None,
                              limit: int = 50, min_reputation: int = 0):
    """
    Get leaderboard filtered by state (game, region, tier, or global).

    OPTIMIZED: Uses get_leaderboard_with_scores RPC to avoid N+1 queries.
    The RPC returns profile data with proof_of_play counts aggregated server-side,
    and (for game type filter) a has_game_activity flag to avoid per-profile bet lookups.
    """
    supabase = _get_supabase()

    rpc_game_type = state_value.upper() if state_type == "game" and state_value else None

    try:
        rpc_result = supabase.rpc("get_leaderboard_with_scores", {
            "p_limit": limit * 2,
            "p_game_type": rpc_game_type
        }).execute()

        if not rpc_result.data:
            return []

        leaderboard = []
        for row in rpc_result.data:
            if state_type == "region" and state_value and row.get("location_city") != state_value:
                continue
            if state_type == "tier" and state_value and row.get("tier") != state_value:
                continue
            if state_type == "game" and not row.get("has_game_activity", False):
                continue

            reputation = float(row.get("reputation_score", 0))
            if reputation < min_reputation:
                continue

            leaderboard.append({
                "id": row["profile_id"],
                "display_name": row.get("display_name"),
                "reputation": round(reputation, 2),
                "tier": row.get("tier"),
                "play_points": float(row.get("play_points", 0)),
                "public_wins": int(row.get("public_wins", 0)),
                "public_losses": int(row.get("public_losses", 0)),
                "public_win_rate": float(row.get("public_win_rate", 0)),
                "total_wins": int(row.get("total_wins", 0)),
                "total_losses": int(row.get("total_losses", 0)),
                "is_content_creator": bool(row.get("is_content_creator", False)),
                "is_verified": bool(row.get("is_verified", False)),
                "creator_badges": row.get("creator_badges") or [],
                "location_city": row.get("location_city"),
                "proof_of_play_count": int(row.get("proof_of_play_count", 0))
            })

        leaderboard.sort(key=lambda x: x["reputation"], reverse=True)
        return leaderboard[:limit]

    except Exception as e:
        logger.warning(f"get_leaderboard_with_scores RPC failed, using fallback: {e}")
        return _get_leaderboard_by_state_fallback(state_type, state_value, limit, min_reputation)


# ─── Proof of Play ────────────────────────────────────────────────────────────

def create_proof_of_play(bet_id: str, session_id: str = None, tx_hash: str = "",
                         chain: str = "base", block_number: int = None,
                         verification_data: dict = None):
    """Create a proof of play receipt."""
    supabase = _get_supabase()
    _validate_uuid(bet_id, "bet_id")
    if session_id:
        _validate_uuid(session_id, "session_id")
    data = {
        "bet_id": bet_id,
        "session_id": session_id,
        "tx_hash": tx_hash,
        "chain": chain,
        "block_number": block_number,
        "verification_data": verification_data or {},
        "is_verified": bool(tx_hash)
    }
    res = supabase.table("proof_of_play_receipts").insert(data).execute()
    return res.data[0] if res.data else None


def get_proof_of_play(bet_id: str = None, session_id: str = None):
    """Get proof of play receipts."""
    supabase = _get_supabase()
    query = supabase.table("proof_of_play_receipts").select("*")
    if bet_id:
        _validate_uuid(bet_id, "bet_id")
        query = query.eq("bet_id", bet_id)
    elif session_id:
        _validate_uuid(session_id, "session_id")
        query = query.eq("session_id", session_id)
    res = query.order("created_at", desc=True).execute()
    return res.data if res.data else []


# ─── Base Markets ─────────────────────────────────────────────────────────────

def create_base_market(bet_id: str = None, session_id: str = None,
                       market_type: str = "match_winner", question: str = "",
                       outcomes: list = None, liquidity_usdc: float = 0,
                       spread_fee_pct: float = 0.05):
    """Create a Base Markets prediction pool."""
    supabase = _get_supabase()
    if bet_id:
        _validate_uuid(bet_id, "bet_id")
    if session_id:
        _validate_uuid(session_id, "session_id")
    data = {
        "bet_id": bet_id,
        "session_id": session_id,
        "market_type": market_type,
        "question": question,
        "outcomes": outcomes or [],
        "liquidity_usdc": liquidity_usdc,
        "spread_fee_pct": spread_fee_pct
    }
    res = supabase.table("base_markets").insert(data).execute()
    return res.data[0] if res.data else None


def get_base_market(market_id: str = None, bet_id: str = None):
    """Get base market by ID or bet_id."""
    supabase = _get_supabase()
    query = supabase.table("base_markets").select("*")
    if market_id:
        query = query.eq("market_id", market_id)
    elif bet_id:
        _validate_uuid(bet_id, "bet_id")
        query = query.eq("bet_id", bet_id)
    else:
        return None
    res = query.single().execute()
    return res.data if res.data else None


def update_base_market_status(market_id: str, status: str, market_id_external: str = None):
    """Update base market status."""
    supabase = _get_supabase()
    update_data = {"status": status, "updated_at": "now()"}
    if market_id_external:
        update_data["market_id"] = market_id_external
    res = supabase.table("base_markets").update(update_data).eq("id", market_id).execute()
    return res.data[0] if res.data else None


def get_active_base_markets():
    """Get all active base markets."""
    supabase = _get_supabase()
    res = supabase.table("base_markets").select("*").eq("status", "active").order("created_at", desc=True).execute()
    return res.data if res.data else []


# ─── Admin Analytics ──────────────────────────────────────────────────────────

def get_total_users() -> int:
    """Get total number of registered users."""
    supabase = _get_supabase()
    res = supabase.table("profiles").select("id", count="exact").execute()
    return res.count if res.count is not None else 0


def get_active_users(days: int = 7) -> int:
    """Get number of users active in the last N days."""
    supabase = _get_supabase()
    cutoff_date = (datetime.utcnow() - timedelta(days=days)).isoformat()
    res = supabase.table("global_activity_logs").select("user_id").gte("created_at", cutoff_date).execute()
    unique_users = set([log["user_id"] for log in res.data if log.get("user_id")])
    return len(unique_users)


def get_total_volume_usd() -> float:
    """Get total bet volume (sum of all bet amounts)."""
    supabase = _get_supabase()
    res = supabase.table("bets").select("amount").execute()
    total = sum([float(bet["amount"]) for bet in res.data if bet.get("amount")])
    return total


def get_total_staked_usdc() -> float:
    """Get total USDC currently staked in open/active bets."""
    supabase = _get_supabase()
    res = supabase.table("bets").select("amount").execute()
    total = sum([float(bet["amount"]) for bet in res.data if bet.get("amount")])
    return total


def get_retention_rate(cohort_days: int = 30) -> float:
    """
    Calculate retention rate: percentage of users who returned after their first activity.

    OPTIMIZED: Uses get_retention_stats RPC to avoid N+1 query per user.
    The RPC calculates cohort size and retained users in a single query using
    window functions and EXISTS subquery — no per-user loops.
    """
    supabase = _get_supabase()

    try:
        rpc_result = supabase.rpc("get_retention_stats", {
            "p_cohort_days": cohort_days
        }).execute()

        if rpc_result.data and len(rpc_result.data) > 0:
            return float(rpc_result.data[0].get("retention_rate", 0.0))
        return 0.0

    except Exception as e:
        logger.warning(f"get_retention_stats RPC failed, using fallback: {e}")
        return _get_retention_rate_fallback(cohort_days)


def get_daily_user_growth(days: int = 30) -> list:
    """Get daily new user registrations."""
    supabase = _get_supabase()
    from datetime import datetime, timedelta
    cutoff_date = (datetime.utcnow() - timedelta(days=days)).date().isoformat()

    # Count profiles created per day
    res = supabase.table("profiles").select(
        "created_at"
    ).gte("created_at", cutoff_date).execute()

    # Group by date
    daily_counts = {}
    for profile in res.data:
        date_str = profile["created_at"][:10]  # Extract date part
        daily_counts[date_str] = daily_counts.get(date_str, 0) + 1

    # Fill missing dates
    result = []
    for i in range(days):
        date = (datetime.utcnow() - timedelta(days=i)).date().isoformat()
        result.append({"date": date, "count": daily_counts.get(date, 0)})

    return list(reversed(result))


def get_daily_volume_breakdown(days: int = 30) -> list:
    """Get daily volume breakdown (bets placed, wins, fees)."""
    supabase = _get_supabase()
    from datetime import datetime, timedelta
    cutoff_date = (datetime.utcnow() - timedelta(days=days)).isoformat()

    # Get bets in date range
    bets_res = supabase.table("bets").select(
        "amount", "status", "created_at"
    ).gte("created_at", cutoff_date).execute()

    # Get fees in date range
    fees_res = supabase.table("platform_fees").select(
        "amount_usd", "created_at"
    ).gte("created_at", cutoff_date).execute()

    # Aggregate by date
    daily_data = {}
    for bet in bets_res.data:
        date = bet["created_at"][:10]
        if date not in daily_data:
            daily_data[date] = {"date": date, "bets_count": 0, "bets_amount": 0, "fees": 0}
        daily_data[date]["bets_count"] += 1
        daily_data[date]["bets_amount"] += float(bet.get("amount", 0))

    for fee in fees_res.data:
        date = fee["created_at"][:10]
        if date not in daily_data:
            daily_data[date] = {"date": date, "bets_count": 0, "bets_amount": 0, "fees": 0}
        daily_data[date]["fees"] += float(fee.get("amount_usd", 0))

    result = list(daily_data.values())
    result.sort(key=lambda x: x["date"])
    return result


# ─── Activity Logs ────────────────────────────────────────────────────────────

def log_activity(user_id, event_type: str, amount_usd=0, details: dict = None):
    """Write to the immutable global_activity_logs table."""
    supabase = _get_supabase()
    VALID_EVENT_TYPES = frozenset([
        "DEPOSIT", "STAKE", "WIN", "FEE", "WITHDRAWAL",
        "WITHDRAWAL_REQUEST", "PAYOUT_CONFIRMED", "FEE_COLLECTED"
    ])
    if event_type not in VALID_EVENT_TYPES:
        raise ValueError(f"Invalid event_type: '{event_type}'")
    if user_id is not None:
        _validate_uuid(user_id, "user_id")
    data = {
        "user_id": user_id,
        "event_type": event_type,
        "amount_usd": float(amount_usd),
        "details": details or {}
    }
    res = supabase.table("global_activity_logs").insert(data).execute()
    return res.data[0] if res.data else None


def get_activity_logs(user_id: str = None, limit: int = 100):
    """Get activity logs, optionally filtered by user_id"""
    supabase = _get_supabase()
    if user_id:
        _validate_uuid(user_id, "user_id")
        res = supabase.table("global_activity_logs").select("*").eq("user_id", user_id).order("created_at", desc=True).limit(limit).execute()
    else:
        res = supabase.table("global_activity_logs").select("*").order("created_at", desc=True).limit(limit).execute()
    return res.data if res.data else []


def log_fee(bet_id: str, amount_usd: float):
    """Log a platform fee."""
    supabase = _get_supabase()
    _validate_uuid(bet_id, "bet_id")
    try:
        val = float(amount_usd)
    except (TypeError, ValueError):
        raise ValueError(f"Invalid amount for field 'fee amount_usd': {amount_usd}")
    if val <= 0:
        raise ValueError(f"Amount 'fee amount_usd' must be positive, got: {val}")
    data = {"bet_id": bet_id, "amount_usd": amount_usd}
    res = supabase.table("platform_fees").insert(data).execute()
    return res.data[0] if res.data else None


# ─── System Config ────────────────────────────────────────────────────────────

def get_system_config(key: str) -> Optional[dict]:
    """Get a system config key-value pair."""
    supabase = _get_supabase()
    res = supabase.table("system_config").select("*").eq("key", key).single().execute()
    return res.data if res.data else None


def set_system_config(key: str, value: str):
    """Set a system config key-value pair (upsert)."""
    supabase = _get_supabase()
    supabase.table("system_config").upsert(
        {"key": key, "value": value, "updated_at": "now()"},
        on_conflict="key"
    ).execute()


# ══════════════════════════════════════════════════════════════════════════════
# FALLBACK IMPLEMENTATIONS (used when RPCs are not yet available)
# These preserve the original N+1 behavior as a safe fallback until migration runs.
# ══════════════════════════════════════════════════════════════════════════════

def _get_leaderboard_by_state_fallback(state_type: str = "global", state_value: str = None,
                                        limit: int = 50, min_reputation: int = 0):
    """Fallback N+1 implementation of get_leaderboard_by_state."""
    supabase = _get_supabase()
    from repositories.quests import get_bets_by_user
    from repositories.analytics import get_proof_of_play as _get_proof_of_play

    query = supabase.table("profiles").select(
        "id, display_name, play_points, total_wins, total_losses, location_city"
    ).order("play_points", desc=True).limit(limit * 2)
    res = query.execute()
    if not res.data:
        return []

    leaderboard = []
    for profile in res.data:
        try:
            receipts = _get_proof_of_play(bet_id=None, session_id=None)
            player_receipts = [r for r in receipts
                               if _is_player_in_receipt(r, profile["id"], get_bets_by_user)]
        except Exception:
            player_receipts = []

        play_points = float(profile.get("play_points", 0))
        total_wins = int(profile.get("total_wins", 0))
        total_losses = int(profile.get("total_losses", 0))
        is_verified = bool(profile.get("is_verified", False))
        is_content_creator = bool(profile.get("is_content_creator", False))
        creator_badges = profile.get("creator_badges", []) or []

        reputation_score = play_points
        reputation_score += (total_wins * 50) - (total_losses * 10)
        reputation_score += (total_wins * 10) - (total_losses * 2)
        if is_verified:
            reputation_score += 500
        if is_content_creator:
            reputation_score += 300
        reputation_score += len(creator_badges) * 100
        reputation_score += len(player_receipts) * 50

        if reputation_score >= 10000:
            tier = "Diamond"
        elif reputation_score >= 5000:
            tier = "Platinum"
        elif reputation_score >= 2000:
            tier = "Gold"
        elif reputation_score >= 500:
            tier = "Silver"
        else:
            tier = "Bronze"

        if state_type == "game" and state_value:
            game_bets = [b for b in get_bets_by_user(profile["id"])
                         if b.get("game_type", "").upper() == state_value.upper()]
            if not game_bets:
                continue
        elif state_type == "region" and state_value:
            if profile.get("location_city") != state_value:
                continue
        elif state_type == "tier" and state_value:
            if tier != state_value:
                continue

        if reputation_score < min_reputation:
            continue

        public_win_rate = round((total_wins / max(total_wins + total_losses, 1)) * 100, 1)
        leaderboard.append({
            "id": profile["id"],
            "display_name": profile.get("display_name"),
            "reputation": round(reputation_score, 2),
            "tier": tier,
            "play_points": play_points,
            "public_wins": total_wins,
            "public_losses": total_losses,
            "public_win_rate": public_win_rate,
            "total_wins": total_wins,
            "total_losses": total_losses,
            "is_content_creator": is_content_creator,
            "is_verified": is_verified,
            "creator_badges": creator_badges,
            "location_city": profile.get("location_city"),
            "proof_of_play_count": len(player_receipts)
        })

    leaderboard.sort(key=lambda x: x["reputation"], reverse=True)
    return leaderboard[:limit]


def _get_retention_rate_fallback(cohort_days: int = 30) -> float:
    """Fallback N+1 implementation of get_retention_rate."""
    supabase = _get_supabase()
    first_activity_res = supabase.table("global_activity_logs").select(
        "user_id", "created_at"
    ).order("created_at").execute()

    first_activity_by_user = {}
    for log in first_activity_res.data:
        user_id = log.get("user_id")
        if user_id and user_id not in first_activity_by_user:
            first_activity_by_user[user_id] = log["created_at"]

    cohort_users = 0
    retained_users = 0
    cutoff = datetime.utcnow() - timedelta(days=cohort_days)
    recent_cutoff = (datetime.utcnow() - timedelta(days=7)).isoformat()

    for user_id, first_date in first_activity_by_user.items():
        first_dt = datetime.fromisoformat(first_date.replace("Z", "+00:00"))
        if first_dt <= cutoff:
            cohort_users += 1
            recent_activity = supabase.table("global_activity_logs").select(
                "id"
            ).eq("user_id", user_id).gte("created_at", recent_cutoff).limit(1).execute()
            if recent_activity.data:
                retained_users += 1

    return (retained_users / cohort_users * 100) if cohort_users > 0 else 0.0