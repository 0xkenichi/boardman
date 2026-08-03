"""
Public Rematch data: leaderboard, open challenges, chain metrics, match history.

Used by bot handlers and (via similar queries) the web /rematch pages.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from backend.supabase_client import get_supabase
from gaming.src.backend.services.challenge_compat import normalize_challenge, normalize_list
from gaming.src.backend.services.match_codes import display_code
from gaming.src.backend.services.play_points import tier_from_play_points, tier_label

logger = logging.getLogger(__name__)


def _sb():
    return get_supabase()


def reputation_score(wins: int, losses: int, draws: int, play_points: int, no_shows: int = 0) -> int:
    """Simple 0–100 reputation for display (not a second economy)."""
    total = max(0, wins + losses + draws)
    if total == 0:
        base = 50
    else:
        wr = wins / total
        base = int(40 + wr * 45)  # 40–85 from win rate
    # PLAY participation bump (capped)
    base += min(10, play_points // 1000)
    base -= min(30, no_shows * 8)
    return max(0, min(100, base))


def get_leaderboard(limit: int = 25) -> list[dict[str, Any]]:
    """Top players by PLAY points."""
    try:
        r = (
            _sb()
            .table("profiles")
            .select(
                "id,display_name,gaming_tag,play_points,play_win_streak,play_best_streak,"
                "gaming_wins,gaming_losses,gaming_draws,gaming_tier"
            )
            .gt("play_points", 0)
            .order("play_points", desc=True)
            .limit(limit)
            .execute()
        )
    except Exception as exc:
        logger.warning("[RematchPublic] leaderboard failed: %s", exc)
        return []

    out = []
    for i, row in enumerate(r.data or [], 1):
        wins = int(row.get("gaming_wins") or 0)
        losses = int(row.get("gaming_losses") or 0)
        draws = int(row.get("gaming_draws") or 0)
        play = int(row.get("play_points") or 0)
        rep = reputation_score(wins, losses, draws, play)
        out.append(
            {
                "rank": i,
                "tag": row.get("gaming_tag") or "—",
                "name": row.get("display_name") or "Player",
                "play_points": play,
                "tier": tier_from_play_points(play),
                "tier_label": tier_label(tier_from_play_points(play)),
                "wins": wins,
                "losses": losses,
                "draws": draws,
                "streak": int(row.get("play_win_streak") or 0),
                "reputation": rep,
            }
        )
    return out


def get_open_public_challenges(limit: int = 30) -> list[dict[str, Any]]:
    """Open public challenges waiting for an opponent."""
    try:
        r = (
            _sb()
            .schema("gaming")
            .table("challenges")
            .select("*")
            .eq("status", "open")
            .order("created_at", desc=True)
            .limit(80)
            .execute()
        )
    except Exception as exc:
        logger.warning("[RematchPublic] open challenges failed: %s", exc)
        return []

    rows = normalize_list(r.data or [])
    out = []
    for ch in rows:
        vis = (ch.get("visibility") or ch.get("theme") or "private").lower()
        # public board: theme/visibility public OR no opponent yet with public flag
        if vis not in ("public",) and ch.get("opponent_id"):
            continue
        if vis == "private" and ch.get("opponent_id"):
            continue
        # Show open seats: status open and (public OR no target)
        if ch.get("opponent_id") and vis != "public":
            continue
        if vis != "public" and not ch.get("opponent_id"):
            # private open invites still reserved — skip on public board
            # unless no target_id means open lobby style
            if (ch.get("visibility") or ch.get("theme") or "").lower() != "public":
                continue
        creator = ch.get("creator_id") or ch.get("issuer_id")
        tag = _tag_for_profile(creator) if creator else "—"
        out.append(
            {
                "id": ch.get("id"),
                "code": display_code(ch),
                "stake": float(ch.get("amount_usdc") or ch.get("stake_amount") or 0),
                "game": ch.get("game") or ch.get("game_type") or "EAFC",
                "chain": ch.get("settlement_chain") or "arc",
                "creator_tag": tag,
                "status": ch.get("status"),
                "created_at": ch.get("created_at"),
            }
        )
        if len(out) >= limit:
            break
    return out


def _tag_for_profile(profile_id: str) -> str:
    try:
        r = (
            _sb()
            .table("profiles")
            .select("gaming_tag,display_name")
            .eq("id", profile_id)
            .limit(1)
            .execute()
        )
        row = (r.data or [None])[0]
        if not row:
            return "player"
        return row.get("gaming_tag") or row.get("display_name") or "player"
    except Exception:
        return "player"


def get_chain_metrics() -> dict[str, Any]:
    """Settled volume / counts by chain (best-effort)."""
    chains = {"arc": {}, "base": {}, "avalanche": {}}
    try:
        r = (
            _sb()
            .schema("gaming")
            .table("challenges")
            .select("id,status,stake_amount,settlement_chain")
            .eq("status", "resolved")
            .limit(500)
            .execute()
        )
    except Exception as exc:
        logger.warning("[RematchPublic] metrics failed: %s", exc)
        return {
            "resolved_total": 0,
            "by_chain": {
                "arc": {"matches": 0, "volume_usdc": 0},
                "base": {"matches": 0, "volume_usdc": 0},
                "avalanche": {"matches": 0, "volume_usdc": 0},
            },
        }

    by = {
        "arc": {"matches": 0, "volume_usdc": 0.0},
        "base": {"matches": 0, "volume_usdc": 0.0},
        "avalanche": {"matches": 0, "volume_usdc": 0.0},
    }
    total = 0
    for row in r.data or []:
        total += 1
        chain = (row.get("settlement_chain") or "base").lower()
        if chain not in by:
            by[chain] = {"matches": 0, "volume_usdc": 0.0}
        stake = float(row.get("stake_amount") or 0)
        # dual lock → volume ≈ 2 * stake
        by[chain]["matches"] += 1
        by[chain]["volume_usdc"] += stake * 2

    return {"resolved_total": total, "by_chain": by}


def get_match_history(
    profile_id: str,
    limit: int = 15,
    *,
    include_open: bool = True,
) -> list[dict[str, Any]]:
    """Recent matches for a player (same source as Telegram /profile)."""
    statuses = [
        "resolved",
        "cancelled",
        "disputed",
        "locked",
        "playing",
        "submitted",
        "accepted",
        "creator_locked",
        "opponent_locked",
    ]
    if include_open:
        statuses.append("open")
    rows: list = []
    for col in ("issuer_id", "target_id"):
        try:
            r = (
                _sb()
                .schema("gaming")
                .table("challenges")
                .select("*")
                .eq(col, profile_id)
                .in_("status", statuses)
                .order("created_at", desc=True)
                .limit(limit)
                .execute()
            )
            rows.extend(r.data or [])
        except Exception:
            pass
    # Dedupe by id
    seen = set()
    uniq = []
    for raw in rows:
        i = raw.get("id")
        if i in seen:
            continue
        seen.add(i)
        uniq.append(normalize_challenge(raw))
    uniq.sort(key=lambda c: c.get("created_at") or "", reverse=True)
    out = []
    for ch in uniq[:limit]:
        winner = ch.get("winner_id")
        result = "—"
        if ch.get("status") == "resolved":
            if winner == profile_id:
                result = "W"
            elif winner:
                result = "L"
            else:
                result = "D"
        out.append(
            {
                "id": ch.get("id"),
                "code": display_code(ch),
                "public_code": display_code(ch),
                "status": ch.get("status"),
                "stake": ch.get("amount_usdc") or ch.get("stake_amount"),
                "amount_usdc": ch.get("amount_usdc") or ch.get("stake_amount"),
                "chain": ch.get("settlement_chain") or "—",
                "settlement_chain": ch.get("settlement_chain") or "arc",
                "game": ch.get("game") or ch.get("game_type") or "—",
                "game_id": ch.get("game") or ch.get("game_type") or "—",
                "game_label": ch.get("game") or ch.get("game_type") or "—",
                "result": result,
                "created_at": ch.get("created_at"),
                "creator_id": ch.get("creator_id") or ch.get("issuer_id"),
                "opponent_id": ch.get("opponent_id") or ch.get("target_id"),
            }
        )
    return out


def get_recent_rivals(profile_id: str, limit: int = 8) -> list[dict[str, Any]]:
    """Past opponents for one-tap rematch (most recent first, unique)."""
    history_rows: list = []
    for col in ("issuer_id", "target_id"):
        try:
            r = (
                _sb()
                .schema("gaming")
                .table("challenges")
                .select("*")
                .eq(col, profile_id)
                .in_("status", ["resolved", "cancelled", "disputed"])
                .order("created_at", desc=True)
                .limit(40)
                .execute()
            )
            history_rows.extend(r.data or [])
        except Exception:
            pass

    seen: set[str] = set()
    rivals: list[dict[str, Any]] = []
    for raw in history_rows:
        ch = normalize_challenge(raw)
        if not ch:
            continue
        a = ch.get("creator_id")
        b = ch.get("opponent_id")
        other = b if a == profile_id else a if b == profile_id else None
        if not other or other in seen:
            continue
        seen.add(other)
        tag = _tag_for_profile(other)
        stake = float(ch.get("amount_usdc") or ch.get("stake_amount") or 1)
        rivals.append(
            {
                "profile_id": other,
                "tag": tag,
                "stake": stake,
                "game": ch.get("game") or ch.get("game_type") or "EAFC",
                "chain": ch.get("settlement_chain") or "arc",
                "last_code": display_code(ch),
                "last_status": ch.get("status"),
            }
        )
        if len(rivals) >= limit:
            break
    return rivals


def format_leaderboard_text(rows: list[dict], limit: int = 10) -> str:
    if not rows:
        return "No ranked players yet — settle a match to appear."
    lines = ["🏆 <b>Rematch leaderboard</b> (PLAY points)\n"]
    for r in rows[:limit]:
        lines.append(
            f"{r['rank']}. @{r['tag']} · <b>{r['play_points']:,}</b> PLAY · "
            f"rep {r['reputation']} · {r['wins']}W/{r['losses']}L"
        )
    lines.append("\nFull board: playingsidequest.fun/rematch/leaderboard")
    return "\n".join(lines)


def format_metrics_text(m: dict) -> str:
    lines = [
        "📊 <b>Rematch testnet metrics</b>\n",
        f"Resolved matches (sample): <b>{m.get('resolved_total', 0)}</b>\n",
    ]
    for chain, data in (m.get("by_chain") or {}).items():
        lines.append(
            f"• {chain}: {data.get('matches', 0)} matches · "
            f"~${float(data.get('volume_usdc') or 0):,.0f} dual-lock volume"
        )
    lines.append("\nArc earns 1.5× PLAY · Avalanche 1.25× · Base 1.0×")
    return "\n".join(lines)
