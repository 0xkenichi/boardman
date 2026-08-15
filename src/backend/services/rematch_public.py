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


# Live gaming.challenges only — amount_usdc / visibility columns do NOT exist (42703).
_CHALLENGE_METRIC_COLS = "id,status,stake_amount,settlement_chain,theme,created_at"


def get_chain_metrics() -> dict[str, Any]:
    """Settled volume / counts by chain (stake_amount + settlement_chain)."""
    empty_by = {
        "arc": {"matches": 0, "volume_usdc": 0.0},
        "base": {"matches": 0, "volume_usdc": 0.0},
        "avalanche": {"matches": 0, "volume_usdc": 0.0},
    }
    try:
        r = (
            _sb()
            .schema("gaming")
            .table("challenges")
            .select(_CHALLENGE_METRIC_COLS)
            .eq("status", "resolved")
            .limit(1000)
            .execute()
        )
    except Exception as exc:
        logger.warning("[RematchPublic] metrics failed: %s", exc)
        return {
            "resolved_total": 0,
            "volume_usdc_resolved": 0.0,
            "by_chain": empty_by,
        }

    by = {k: dict(v) for k, v in empty_by.items()}
    total = 0
    volume_all = 0.0
    for row in r.data or []:
        total += 1
        chain = (row.get("settlement_chain") or "arc").lower()
        if chain not in by:
            by[chain] = {"matches": 0, "volume_usdc": 0.0}
        stake = float(row.get("stake_amount") or 0)
        dual = stake * 2
        by[chain]["matches"] += 1
        by[chain]["volume_usdc"] += dual
        volume_all += dual

    return {
        "resolved_total": total,
        "volume_usdc_resolved": round(volume_all, 2),
        "by_chain": by,
    }


def get_ops_metrics() -> dict[str, Any]:
    """Testnet ops dashboard: users, pipeline, volume, fees, gas samples.

    Live schema: challenges.stake_amount + theme (not amount_usdc / visibility).
    """
    chain = get_chain_metrics()
    out: dict[str, Any] = {
        "users_total": 0,
        "users_with_play_points": 0,
        "total_wins_profile": 0,
        "total_losses_profile": 0,
        "challenges_by_status": {},
        "challenges_sampled": 0,
        "open_public": 0,
        "locked_or_playing": 0,
        "resolved_total": int(chain.get("resolved_total") or 0),
        "cancelled_total": 0,
        "disputed_total": 0,
        "expired_total": 0,
        "volume_usdc_resolved": float(chain.get("volume_usdc_resolved") or 0),
        "volume_usdc_in_escrow_est": 0.0,
        "platform_fees_usdc": 0.0,
        "lock_in_count": 0,
        "payout_count": 0,
        "refund_count": 0,
        "gas_used_total": 0,
        "gas_samples": 0,
        "escrow_movements": {},
        "by_chain": chain.get("by_chain") or {},
        "notes": [
            "volume_usdc_resolved ≈ 2 × stake per resolved match (dual lock)",
        ],
    }

    try:
        pr = _sb().table("profiles").select("id", count="exact").limit(1).execute()
        out["users_total"] = int(pr.count or 0)
    except Exception as exc:
        logger.warning("[OpsMetrics] users_total: %s", exc)

    try:
        pp = (
            _sb()
            .table("profiles")
            .select("id", count="exact")
            .gt("play_points", 0)
            .limit(1)
            .execute()
        )
        out["users_with_play_points"] = int(pp.count or 0)
    except Exception:
        pass

    try:
        wr = (
            _sb()
            .table("profiles")
            .select("gaming_wins,gaming_losses")
            .gt("play_points", 0)
            .limit(200)
            .execute()
        )
        tw = tl = 0
        for row in wr.data or []:
            tw += int(row.get("gaming_wins") or 0)
            tl += int(row.get("gaming_losses") or 0)
        out["total_wins_profile"] = tw
        out["total_losses_profile"] = tl
    except Exception:
        pass

    try:
        cr = (
            _sb()
            .schema("gaming")
            .table("challenges")
            .select(_CHALLENGE_METRIC_COLS)
            .order("created_at", desc=True)
            .limit(1000)
            .execute()
        )
        by_status: dict[str, int] = {}
        resolved_vol = 0.0
        resolved_n = 0
        by_chain: dict[str, dict] = {
            "arc": {"matches": 0, "volume_usdc": 0.0},
            "base": {"matches": 0, "volume_usdc": 0.0},
            "avalanche": {"matches": 0, "volume_usdc": 0.0},
        }
        for row in cr.data or []:
            st = str(row.get("status") or "unknown")
            by_status[st] = by_status.get(st, 0) + 1
            stake = float(row.get("stake_amount") or 0)
            theme = (row.get("theme") or "").lower()
            if st == "resolved":
                resolved_n += 1
                resolved_vol += stake * 2
                cid = (row.get("settlement_chain") or "arc").lower()
                if cid not in by_chain:
                    by_chain[cid] = {"matches": 0, "volume_usdc": 0.0}
                by_chain[cid]["matches"] += 1
                by_chain[cid]["volume_usdc"] += stake * 2
            elif st == "cancelled":
                out["cancelled_total"] += 1
            elif st == "disputed":
                out["disputed_total"] += 1
            elif st == "expired":
                out["expired_total"] += 1
            elif st in (
                "locked",
                "playing",
                "submitted",
                "creator_locked",
                "opponent_locked",
                "accepted",
            ):
                out["locked_or_playing"] += 1
                if st in ("locked", "playing", "submitted"):
                    out["volume_usdc_in_escrow_est"] += stake * 2
                else:
                    out["volume_usdc_in_escrow_est"] += stake
            elif st == "open" and theme == "public":
                out["open_public"] += 1
        out["challenges_by_status"] = dict(sorted(by_status.items()))
        out["challenges_sampled"] = sum(by_status.values())
        if resolved_n:
            out["resolved_total"] = resolved_n
            out["volume_usdc_resolved"] = round(resolved_vol, 2)
            out["by_chain"] = by_chain
        out["volume_usdc_in_escrow_est"] = round(out["volume_usdc_in_escrow_est"], 2)
    except Exception as exc:
        logger.warning("[OpsMetrics] challenges: %s", exc)

    try:
        ar = (
            _sb()
            .schema("gaming")
            .table("escrow_audit")
            .select("movement,amount_usdc,metadata,status")
            .order("created_at", desc=True)
            .limit(1000)
            .execute()
        )
        moves: dict[str, int] = {}
        fees = 0.0
        gas_total = 0
        gas_n = 0
        for row in ar.data or []:
            m = str(row.get("movement") or "unknown")
            moves[m] = moves.get(m, 0) + 1
            st = (row.get("status") or "").lower()
            # Some rows use confirmed; treat missing status as countable for fees
            if m == "fee" and st in ("confirmed", "complete", ""):
                fees += float(row.get("amount_usdc") or 0)
            meta = row.get("metadata") or {}
            if isinstance(meta, dict) and meta.get("gas_used") is not None:
                try:
                    gas_total += int(meta["gas_used"])
                    gas_n += 1
                except (TypeError, ValueError):
                    pass
        out["escrow_movements"] = moves
        out["lock_in_count"] = int(moves.get("lock_in") or 0)
        out["payout_count"] = int(moves.get("payout") or 0)
        out["refund_count"] = int(moves.get("refund") or 0)
        out["platform_fees_usdc"] = round(fees, 4)
        out["gas_used_total"] = gas_total
        out["gas_samples"] = gas_n
        if not out["resolved_total"] and out["payout_count"]:
            out["resolved_total"] = out["payout_count"]
            out["notes"].append("resolved_total inferred from escrow payout rows")
    except Exception as exc:
        logger.warning("[OpsMetrics] escrow_audit: %s", exc)

    return out


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
    lines = ["🏆 <b>Boardman leaderboard</b> (PLAY points)\n"]
    for r in rows[:limit]:
        lines.append(
            f"{r['rank']}. @{r['tag']} · <b>{r['play_points']:,}</b> PLAY · "
            f"rep {r['reputation']} · {r['wins']}W/{r['losses']}L"
        )
    try:
        from gaming.src.bot.brand_assets import boardman_leaderboard_url

        board = boardman_leaderboard_url().replace("https://", "")
    except Exception:
        board = "boardman.playingsidequest.fun/leaderboard"
    lines.append(f"\nFull board: {board}")
    return "\n".join(lines)


def format_metrics_text(m: dict) -> str:
    """Human-readable metrics for Telegram board / profile.

    Accepts either get_chain_metrics() or full get_ops_metrics().
    """
    lines = ["📊 <b>Boardman testnet metrics</b>\n"]

    if m.get("users_total") is not None:
        lines.append(
            f"Users: <b>{m.get('users_total', 0)}</b>"
            + (
                f" · PLAY active: <b>{m.get('users_with_play_points', 0)}</b>"
                if m.get("users_with_play_points") is not None
                else ""
            )
            + "\n"
        )

    if m.get("total_wins_profile") is not None or m.get("total_losses_profile") is not None:
        lines.append(
            f"Profile W/L (PLAY users): "
            f"<b>{m.get('total_wins_profile', 0)}W</b>/"
            f"<b>{m.get('total_losses_profile', 0)}L</b>\n"
        )

    lines.append(
        f"Resolved matches: <b>{m.get('resolved_total', 0)}</b> · "
        f"volume ~${float(m.get('volume_usdc_resolved') or 0):,.0f} USDC\n"
    )

    if m.get("locked_or_playing") is not None or m.get("open_public") is not None:
        lines.append(
            f"In play: <b>{m.get('locked_or_playing', 0)}</b> · "
            f"public open: <b>{m.get('open_public', 0)}</b> · "
            f"cancelled: <b>{m.get('cancelled_total', 0)}</b> · "
            f"disputed: <b>{m.get('disputed_total', 0)}</b>\n"
        )
        if m.get("volume_usdc_in_escrow_est"):
            lines.append(
                f"Est. in escrow: ~${float(m.get('volume_usdc_in_escrow_est') or 0):,.0f} USDC\n"
            )

    if m.get("platform_fees_usdc") is not None:
        lines.append(
            f"Platform fees: <b>${float(m.get('platform_fees_usdc') or 0):,.2f}</b>"
            + (
                f" · locks {m.get('lock_in_count', 0)} · "
                f"payouts {m.get('payout_count', 0)} · "
                f"refunds {m.get('refund_count', 0)}"
                if m.get("lock_in_count") is not None
                else ""
            )
            + "\n"
        )
    if m.get("gas_samples"):
        lines.append(
            f"Gas samples: <b>{m.get('gas_samples')}</b> txs · "
            f"gas_used total <b>{m.get('gas_used_total', 0):,}</b>\n"
        )

    hist = m.get("challenges_by_status") or {}
    if hist:
        bits = [f"{k}={v}" for k, v in sorted(hist.items())]
        lines.append(f"Status mix: <i>{', '.join(bits)}</i>\n")

    for chain, data in (m.get("by_chain") or {}).items():
        if not data.get("matches") and not data.get("volume_usdc"):
            continue
        lines.append(
            f"• {chain}: {data.get('matches', 0)} resolved · "
            f"~${float(data.get('volume_usdc') or 0):,.0f} dual-lock"
        )
    lines.append("\nArc 1.5× PLAY · Avalanche 1.25× · Base 1.0×")
    return "\n".join(lines)
