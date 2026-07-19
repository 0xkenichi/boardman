"""
$PLAY points + one-active-match gate for ClawStation.

$PLAY is a participation score (not USDC). Both winners and losers earn
points so every match feels valued. Hot streaks multiply win rewards.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Optional

from backend.supabase_client import get_supabase
from gaming.src.backend.services.challenge_compat import normalize_list

logger = logging.getLogger(__name__)

# Statuses that block opening/accepting another challenge
ACTIVE_MATCH_STATUSES = (
    "open",
    "accepted",
    "creator_locked",
    "locked",
    "playing",
    "submitted",
    "disputed",
)

# Base awards (before multiplier) — honest play only
PLAY_WIN = int(os.getenv("PLAY_POINTS_WIN", "100"))
PLAY_LOSS = int(os.getenv("PLAY_POINTS_LOSS", "40"))
PLAY_DRAW = int(os.getenv("PLAY_POINTS_DRAW", "50"))


def _no_show_penalty() -> int:
    """Always a negative delta. We never reward ghosting / no-show."""
    raw = os.getenv("PLAY_POINTS_NO_SHOW_PENALTY", "-50")
    try:
        v = int(raw)
    except ValueError:
        v = -50
    # If ops set +50 by mistake, treat as magnitude and flip to penalty
    if v >= 0:
        v = -abs(v) if v != 0 else -50
    return v


# Resolved at call-time via _no_show_penalty() so env can't accidentally reward bad behaviour
# Hot streak: mult = 1 + STREAK_STEP * min(streak_after_win, STREAK_CAP)
# e.g. step 0.15, cap 10 → 2.5x at 10-win streak
STREAK_STEP = float(os.getenv("PLAY_STREAK_STEP", "0.15"))
STREAK_CAP = int(os.getenv("PLAY_STREAK_CAP", "10"))
# Small bonus from stake size (USDC)
STAKE_BONUS_PER_USDC = float(os.getenv("PLAY_STAKE_BONUS_PER_USDC", "5"))
STAKE_BONUS_CAP = int(os.getenv("PLAY_STAKE_BONUS_CAP", "50"))


def _sb():
    return get_supabase()


def tier_from_play_points(points: int) -> str:
    """
    Rank derived from lifetime $PLAY (not a separate reputation number).

    Bronze → Diamond = how much you've played and stuck with ClawStation.
    Future: fee discounts, leaderboard badges, perks.
    """
    p = max(0, int(points or 0))
    if p >= 10_000:
        return "diamond"
    if p >= 5_000:
        return "platinum"
    if p >= 2_000:
        return "gold"
    if p >= 500:
        return "silver"
    return "bronze"


def tier_label(tier: str) -> str:
    return {
        "bronze": "Bronze (0+ $PLAY)",
        "silver": "Silver (500+ $PLAY)",
        "gold": "Gold (2,000+ $PLAY)",
        "platinum": "Platinum (5,000+ $PLAY)",
        "diamond": "Diamond (10,000+ $PLAY)",
    }.get((tier or "bronze").lower(), tier.title())


def streak_multiplier(win_streak_after: int) -> float:
    """Multiplier applied to win points based on streak length after this win."""
    n = max(0, min(int(win_streak_after), STREAK_CAP))
    if n <= 1:
        return 1.0
    return round(1.0 + STREAK_STEP * (n - 1), 3)


def stake_bonus(amount_usdc: Any) -> int:
    try:
        a = float(amount_usdc or 0)
    except (TypeError, ValueError):
        a = 0.0
    return int(min(STAKE_BONUS_CAP, max(0, round(a * STAKE_BONUS_PER_USDC))))


def get_active_challenge(profile_id: str) -> Optional[dict]:
    """Return one unfinished challenge this profile is in, if any.

    Live DB uses issuer_id/target_id/stake_amount (not creator_id/amount_usdc).
    """
    sb = _sb()
    # Only select columns that exist on the live gaming.challenges schema
    cols = "id,status,stake_amount,issuer_id,target_id,theme,game_type"

    def _query(col: str) -> list:
        try:
            r = (
                sb.schema("gaming")
                .table("challenges")
                .select(cols)
                .eq(col, profile_id)
                .in_("status", list(ACTIVE_MATCH_STATUSES))
                .limit(5)
                .execute()
            )
            return normalize_list(r.data or [])
        except Exception as exc:
            logger.warning("[PLAY] active match query %s failed: %s", col, exc)
            return []

    rows = _query("issuer_id") + _query("target_id")
    # Fallback for DBs that still have creator_id/opponent_id
    if not rows:
        rows = _query("creator_id") + _query("opponent_id")
    return rows[0] if rows else None


def assert_can_start_or_accept(profile_id: str) -> Optional[str]:
    """
    Return an error message if the user already has an active match.
    None means OK to proceed.
    """
    active = get_active_challenge(profile_id)
    if not active:
        return None
    cid = active.get("id", "?")
    st = active.get("status", "?")
    short = (cid or "?")[:8]
    return (
        f"You already have an open match ({st}).\n"
        f"#{short}\n\n"
        f"Finish it first — tap 🎮 My match (Lock → Side → Submit result).\n"
        f"Only one match at a time."
    )


def _load_play_stats(profile_id: str) -> dict:
    r = (
        _sb()
        .table("profiles")
        .select(
            "id,play_points,play_win_streak,play_best_streak,"
            "gaming_wins,gaming_losses,gaming_draws"
        )
        .eq("id", profile_id)
        .limit(1)
        .execute()
    )
    data = r.data
    if isinstance(data, list):
        data = data[0] if data else None
    if not data:
        return {
            "play_points": 0,
            "play_win_streak": 0,
            "play_best_streak": 0,
            "gaming_wins": 0,
            "gaming_losses": 0,
            "gaming_draws": 0,
        }
    return data


def _credit(
    profile_id: str,
    points: int,
    *,
    reason: str,
    challenge_id: Optional[str],
    multiplier: float,
    streak_before: int,
    streak_after: int,
    extra_profile: Optional[dict] = None,
    metadata: Optional[dict] = None,
) -> dict:
    """Atomically-ish: read balance, update profile, write ledger."""
    stats = _load_play_stats(profile_id)
    before = int(stats.get("play_points") or 0)
    # Never let balance go negative
    after = max(0, before + int(points))
    actual_delta = after - before  # may clip if penalty would go below 0
    update = {
        "play_points": after,
        "play_win_streak": streak_after,
        "play_best_streak": max(
            int(stats.get("play_best_streak") or 0),
            streak_after,
        ),
        "gaming_tier": tier_from_play_points(after),
    }
    if extra_profile:
        update.update(extra_profile)

    _sb().table("profiles").update(update).eq("id", profile_id).execute()

    try:
        _sb().schema("gaming").table("play_ledger").insert(
            {
                "profile_id": profile_id,
                "challenge_id": challenge_id,
                "reason": reason,
                "points": int(actual_delta),
                "multiplier": float(multiplier),
                "streak_before": streak_before,
                "streak_after": streak_after,
                "balance_after": after,
                "metadata": {
                    **(metadata or {}),
                    "requested_points": int(points),
                    "clipped": actual_delta != int(points),
                },
            }
        ).execute()
    except Exception as exc:
        logger.warning("[PLAY] ledger insert failed: %s", exc)

    return {
        "profile_id": profile_id,
        "points": int(actual_delta),
        "multiplier": multiplier,
        "balance_after": after,
        "streak_before": streak_before,
        "streak_after": streak_after,
        "reason": reason,
    }


async def award_match_play_points(
    challenge: dict,
    winner_id: Optional[str],
    *,
    no_show: bool = False,
) -> list[dict]:
    """
    Award $PLAY to both participants after a resolved match.

    winner_id None → draw (both get PLAY_DRAW).
    no_show → silent player is penalized (negative $PLAY); never rewarded.
    """
    creator_id = challenge.get("creator_id") or challenge.get("issuer_id")
    opponent_id = challenge.get("opponent_id") or challenge.get("target_id")
    challenge_id = challenge.get("id")
    amount = challenge.get("amount_usdc") or challenge.get("stake_amount") or 0
    bonus = stake_bonus(amount)

    results: list[dict] = []
    participants = [p for p in (creator_id, opponent_id) if p]

    if not participants:
        return results

    # Draw
    if winner_id is None and not no_show:
        for pid in participants:
            stats = _load_play_stats(pid)
            streak = int(stats.get("play_win_streak") or 0)
            pts = PLAY_DRAW + bonus
            results.append(
                _credit(
                    pid,
                    pts,
                    reason="draw",
                    challenge_id=challenge_id,
                    multiplier=1.0,
                    streak_before=streak,
                    streak_after=streak,
                    extra_profile={
                        "gaming_draws": int(stats.get("gaming_draws") or 0) + 1,
                    },
                    metadata={"stake_bonus": bonus, "base": PLAY_DRAW},
                )
            )
        return results

    for pid in participants:
        stats = _load_play_stats(pid)
        streak_before = int(stats.get("play_win_streak") or 0)
        wins = int(stats.get("gaming_wins") or 0)
        losses = int(stats.get("gaming_losses") or 0)

        if pid == winner_id:
            streak_after = streak_before + 1
            mult = streak_multiplier(streak_after)
            base = PLAY_WIN
            pts = int(round(base * mult)) + bonus
            results.append(
                _credit(
                    pid,
                    pts,
                    reason="win",
                    challenge_id=challenge_id,
                    multiplier=mult,
                    streak_before=streak_before,
                    streak_after=streak_after,
                    extra_profile={"gaming_wins": wins + 1},
                    metadata={
                        "stake_bonus": bonus,
                        "base": base,
                        "hot_streak": streak_after,
                    },
                )
            )
        else:
            # Honest loss (reported): participation +. No-show (ghosted): always −.
            if no_show:
                pts = _no_show_penalty()  # always < 0
                assert pts < 0, "no-show must never award points"
                reason = "no_show_loss"
                meta = {"base": pts, "penalty": True, "bad_behaviour": True}
            else:
                pts = max(0, PLAY_LOSS) + max(0, bonus // 2)
                reason = "loss"
                meta = {"stake_bonus": max(0, bonus // 2), "base": PLAY_LOSS}
            results.append(
                _credit(
                    pid,
                    pts,
                    reason=reason,
                    challenge_id=challenge_id,
                    multiplier=1.0,
                    streak_before=streak_before,
                    streak_after=0,
                    extra_profile={"gaming_losses": losses + 1},
                    metadata=meta,
                )
            )

    return results


def format_play_award_line(award: dict) -> str:
    pts = int(award.get("points", 0) or 0)
    reason = award.get("reason", "")
    mult = award.get("multiplier") or 1
    streak = award.get("streak_after") or 0
    bal = award.get("balance_after")
    sign = f"+{pts}" if pts >= 0 else str(pts)
    if reason == "win" and mult and mult > 1:
        return (
            f"🎮 {sign} $PLAY (win ×{mult:.2f} hot streak {streak}) · total {bal}"
        )
    if reason == "no_show_loss":
        return (
            f"🎮 {sign} $PLAY (no-show penalty — ghosting is not rewarded) · total {bal}"
        )
    labels = {
        "win": "win",
        "loss": "played",
        "draw": "draw",
    }
    return f"🎮 {sign} $PLAY ({labels.get(reason, reason)}) · total {bal}"
