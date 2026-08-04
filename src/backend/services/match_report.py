"""
Match reporting rules: agreement, conflicts, one-sided waits, no-shows.

Loser ghosting fix
──────────────────
If player A reports with proof (screenshot) and player B never reports:
  1. Nudge B after NUDGE_AFTER_MINUTES
  2. After NO_SHOW_HOURS → treat B as no-show
  3. AI verifies A's screenshot; if confidence is high enough → payout to
     the winner implied by A's report + sides (or AI mapping)
  4. If no proof / AI fails → dispute (admin), NOT automatic cancel that
     steals from an honest winner

If nobody reports after REPORT_TIMEOUT_HOURS → cancel + refund both.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Optional

from backend.supabase_client import get_supabase
from gaming.src.backend.services.challenge_compat import denormalize_challenge, normalize_list

logger = logging.getLogger(__name__)

# Nobody reported at all → cancel/refund
REPORT_TIMEOUT_HOURS = int(os.getenv("MATCH_REPORT_TIMEOUT_HOURS", "24"))
# One player reported with proof, other silent → no-show settle
NO_SHOW_HOURS = float(os.getenv("MATCH_NO_SHOW_HOURS", "6"))
NUDGE_AFTER_MINUTES = int(os.getenv("MATCH_REPORT_NUDGE_MINUTES", "30"))
REQUIRE_SCREENSHOTS = os.getenv("MATCH_REQUIRE_SCREENSHOTS", "true").lower() in (
    "1",
    "true",
    "yes",
)
# Min AI confidence to auto-pay on no-show
NO_SHOW_AI_CONFIDENCE = float(os.getenv("MATCH_NO_SHOW_AI_CONFIDENCE", "0.70"))


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _parse_ts(val: Any) -> Optional[datetime]:
    if not val:
        return None
    try:
        return datetime.fromisoformat(str(val).replace("Z", "+00:00"))
    except Exception:
        return None


def creator_has_report(ch: dict) -> bool:
    return (
        ch.get("creator_score") is not None
        or ch.get("creator_reported_home") is not None
        or bool(ch.get("screenshot_creator_url"))
    )


def opponent_has_report(ch: dict) -> bool:
    return (
        ch.get("opponent_score") is not None
        or ch.get("opponent_reported_home") is not None
        or bool(ch.get("screenshot_opponent_url"))
    )


def creator_has_proof(ch: dict) -> bool:
    """Score/scoreline + screenshot from creator."""
    has_score = (
        ch.get("creator_score") is not None or ch.get("creator_reported_home") is not None
    )
    return has_score and bool(ch.get("screenshot_creator_url"))


def opponent_has_proof(ch: dict) -> bool:
    has_score = (
        ch.get("opponent_score") is not None or ch.get("opponent_reported_home") is not None
    )
    return has_score and bool(ch.get("screenshot_opponent_url"))


def both_have_scores(ch: dict) -> bool:
    full = (
        ch.get("creator_reported_home") is not None
        and ch.get("creator_reported_away") is not None
        and ch.get("opponent_reported_home") is not None
        and ch.get("opponent_reported_away") is not None
    )
    legacy = ch.get("creator_score") is not None and ch.get("opponent_score") is not None
    return full or legacy


def both_have_screenshots(ch: dict) -> bool:
    return bool(ch.get("screenshot_creator_url") and ch.get("screenshot_opponent_url"))


def scorelines_agree(ch: dict) -> Optional[bool]:
    chh, cha = ch.get("creator_reported_home"), ch.get("creator_reported_away")
    oh, oa = ch.get("opponent_reported_home"), ch.get("opponent_reported_away")
    if None not in (chh, cha, oh, oa):
        try:
            return (int(chh), int(cha)) == (int(oh), int(oa))
        except (TypeError, ValueError):
            return False
    if ch.get("creator_score") is not None and ch.get("opponent_score") is not None:
        return None
    return None


def sides_conflict(ch: dict) -> bool:
    cs, os_ = ch.get("creator_side"), ch.get("opponent_side")
    return bool(cs and os_ and cs == os_)


def ingame_names_conflict(ch: dict) -> bool:
    """Both players claimed the same on-screen username (e.g. both 'Finch')."""
    c = (ch.get("creator_console_id") or "").strip().lower()
    o = (ch.get("opponent_console_id") or "").strip().lower()
    return bool(c and o and c == o)


def _binary_won_from_report(
    home: Any, away: Any, side: Optional[str], *, as_creator: bool
) -> Optional[bool]:
    if home is None or away is None:
        return None
    try:
        h, a = int(home), int(away)
    except (TypeError, ValueError):
        return None
    if h == a:
        return None
    home_wins = h > a
    if side == "home":
        return home_wins
    if side == "away":
        return not home_wins
    return home_wins if as_creator else not home_wins


def binary_both_claim_win(ch: dict) -> bool:
    """True if both players' mapped scorelines imply each of them won."""
    try:
        from gaming.src.backend.services.game_catalog import is_binary_outcome

        gid = str(ch.get("game") or ch.get("game_type") or "")
        if not is_binary_outcome(gid):
            return False
        c_won = _binary_won_from_report(
            ch.get("creator_reported_home"),
            ch.get("creator_reported_away"),
            ch.get("creator_side"),
            as_creator=True,
        )
        o_won = _binary_won_from_report(
            ch.get("opponent_reported_home"),
            ch.get("opponent_reported_away"),
            ch.get("opponent_side"),
            as_creator=False,
        )
        return c_won is True and o_won is True
    except Exception:
        return False


def analyze_reports(ch: dict) -> dict[str, Any]:
    c_rep = creator_has_report(ch)
    o_rep = opponent_has_report(ch)
    agree = scorelines_agree(ch)

    if sides_conflict(ch):
        return {
            "action": "sides_conflict",
            "reason": "Both players claimed the same side (home/away).",
            "creator_reported": c_rep,
            "opponent_reported": o_rep,
        }

    if ingame_names_conflict(ch):
        return {
            "action": "identity_conflict",
            "reason": "Both players claimed the same in-game name on the screenshot. "
            "Each must use their own name (e.g. Finch vs Emmanuella).",
            "creator_reported": c_rep,
            "opponent_reported": o_rep,
        }

    if binary_both_claim_win(ch) and c_rep and o_rep:
        return {
            "action": "conflict",
            "reason": "Both players claim they won. Need matching reports or support review.",
            "creator_reported": True,
            "opponent_reported": True,
        }

    if not c_rep and not o_rep:
        return {
            "action": "wait_both",
            "reason": "Nobody has reported yet.",
            "creator_reported": False,
            "opponent_reported": False,
        }

    if c_rep and not o_rep:
        return {
            "action": "wait_opponent",
            "reason": "Creator reported; waiting on opponent.",
            "creator_reported": True,
            "opponent_reported": False,
            "reporter": "creator",
            "reporter_id": ch.get("creator_id"),
            "silent_id": ch.get("opponent_id"),
            "reporter_has_proof": creator_has_proof(ch),
        }

    if o_rep and not c_rep:
        return {
            "action": "wait_creator",
            "reason": "Opponent reported; waiting on creator.",
            "creator_reported": False,
            "opponent_reported": True,
            "reporter": "opponent",
            "reporter_id": ch.get("opponent_id"),
            "silent_id": ch.get("creator_id"),
            "reporter_has_proof": opponent_has_proof(ch),
        }

    if agree is False:
        return {
            "action": "conflict",
            "reason": "Scorelines disagree (different home-away numbers).",
            "creator_reported": True,
            "opponent_reported": True,
        }

    # Both players submitted the SAME home-away scoreline → settle without photos.
    # Photos still help AI/disputes, but agreeing scorelines are enough for payout.
    if agree is True:
        return {
            "action": "settle_ready",
            "reason": "Both players reported the same scoreline.",
            "creator_reported": True,
            "opponent_reported": True,
            "scorelines_agree": True,
        }

    # Scores present but not full scorelines (legacy single ints) or incomplete:
    # optionally require screenshots before auto-payout.
    if REQUIRE_SCREENSHOTS and not both_have_screenshots(ch):
        return {
            "action": "wait_screenshots",
            "reason": "Need FT screenshots from both players before auto-payout "
            "(or both report the same full scoreline e.g. 5-3).",
            "creator_reported": True,
            "opponent_reported": True,
            "missing_creator_shot": not bool(ch.get("screenshot_creator_url")),
            "missing_opponent_shot": not bool(ch.get("screenshot_opponent_url")),
        }

    if both_have_scores(ch) or both_have_screenshots(ch):
        return {
            "action": "settle_ready",
            "reason": "Both reported" + (" and scores agree" if agree else "") + ".",
            "creator_reported": True,
            "opponent_reported": True,
            "scorelines_agree": agree,
        }

    return {
        "action": "incomplete",
        "reason": "Reports incomplete.",
        "creator_reported": c_rep,
        "opponent_reported": o_rep,
    }


def hours_since_update(ch: dict) -> float:
    ts = _parse_ts(ch.get("updated_at")) or _parse_ts(ch.get("created_at"))
    if not ts:
        return 0.0
    return max(0.0, (_utcnow() - ts).total_seconds() / 3600.0)


def should_nudge(ch: dict) -> bool:
    analysis = analyze_reports(ch)
    if analysis["action"] not in ("wait_opponent", "wait_creator", "wait_screenshots"):
        return False
    if ch.get("report_nudge_sent"):
        return False
    return (hours_since_update(ch) * 60) >= NUDGE_AFTER_MINUTES


def no_show_due(ch: dict) -> Optional[dict]:
    """
    If one side reported with proof and the other is silent past NO_SHOW_HOURS,
    return analysis dict for no-show settlement. Else None.
    """
    if ch.get("status") not in ("playing", "locked", "submitted"):
        return None
    analysis = analyze_reports(ch)
    if analysis["action"] not in ("wait_opponent", "wait_creator"):
        return None
    if not analysis.get("reporter_has_proof"):
        return None
    if hours_since_update(ch) < NO_SHOW_HOURS:
        return None
    analysis["action"] = "no_show_settle"
    analysis["reason"] = (
        f"Silent player did not report within {NO_SHOW_HOURS}h after opponent "
        f"submitted proof. Settling from reporter's screenshot + claim."
    )
    return analysis


def abandon_due(ch: dict) -> bool:
    """Nobody reported (or only text without proof) past full timeout → cancel."""
    if ch.get("status") not in ("playing", "locked", "submitted"):
        return False
    analysis = analyze_reports(ch)
    if hours_since_update(ch) < REPORT_TIMEOUT_HOURS:
        return False
    # No-show with proof is handled separately (pay winner)
    if analysis["action"] in ("wait_opponent", "wait_creator") and analysis.get(
        "reporter_has_proof"
    ):
        return False
    return analysis["action"] in (
        "wait_both",
        "wait_opponent",
        "wait_creator",
        "wait_screenshots",
        "incomplete",
    )


def winner_from_reporter_claim(ch: dict, reporter: str) -> Optional[str]:
    """
    Infer winner profile id from the reporting player's home-away scoreline
    and declared sides. Returns None for draw or insufficient data.
    """
    if reporter == "creator":
        h, a = ch.get("creator_reported_home"), ch.get("creator_reported_away")
        side = ch.get("creator_side") or "home"
    else:
        h, a = ch.get("opponent_reported_home"), ch.get("opponent_reported_away")
        side = ch.get("opponent_side") or "away"

    if h is not None and a is not None:
        try:
            h, a = int(h), int(a)
        except (TypeError, ValueError):
            return None
        if h == a:
            return None  # draw
        home_wins = h > a
        if home_wins:
            if ch.get("creator_side") == "home":
                return ch["creator_id"]
            if ch.get("opponent_side") == "home":
                return ch["opponent_id"]
            # default creator=home if sides missing
            return ch["creator_id"] if side == "home" or reporter == "creator" else ch.get(
                "opponent_id"
            )
        # away wins
        if ch.get("creator_side") == "away":
            return ch["creator_id"]
        if ch.get("opponent_side") == "away":
            return ch["opponent_id"]
        return ch.get("opponent_id") if side == "home" or reporter == "creator" else ch[
            "creator_id"
        ]

    # Legacy single "my goals" only — cannot fairly decide no-show without scoreline
    return None


async def mark_nudge_sent(challenge_id: str) -> None:
    sb = get_supabase()
    try:
        sb.schema("gaming").table("challenges").update(
            denormalize_challenge({"report_nudge_sent": True})
        ).eq("id", challenge_id).execute()
    except Exception:
        logger.debug("[MatchReport] report_nudge_sent column missing")


async def load_active_matches() -> list[dict]:
    sb = get_supabase()
    result = (
        sb.schema("gaming")
        .table("challenges")
        .select("*")
        .in_("status", ["locked", "playing", "submitted", "disputed"])
        .execute()
    )
    return normalize_list(result.data or [])


# Back-compat aliases used by older job code
def should_timeout_one_sided(ch: dict) -> bool:
    return abandon_due(ch) or no_show_due(ch) is not None
