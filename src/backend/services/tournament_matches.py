"""
Tournament bracket ↔ 1v1 challenges.

Each ready bracket node becomes a private challenge:
  stake $0 (pot already paid via entry) · status playing · message encodes cup+match

On settle, report_match_winner advances bracket and spawns the next ready nodes.
"""
from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

# [CUP:ABC123:R1-M0] ...
_CUP_MSG = re.compile(
    r"\[CUP:([A-Z0-9]+):([A-Za-z0-9\-]+)\]",
    re.I,
)


def encode_cup_message(cup_code: str, match_key: str, title: str = "") -> str:
    return f"[CUP:{cup_code}:{match_key}] {title or 'Boardman cup match'}".strip()


def parse_cup_message(message: Optional[str]) -> Optional[tuple[str, str]]:
    if not message:
        return None
    m = _CUP_MSG.search(str(message))
    if not m:
        return None
    return m.group(1).upper(), m.group(2)


def create_match_challenge(
    tournament: dict[str, Any],
    match: dict[str, Any],
) -> Optional[dict[str, Any]]:
    """
    Insert a $0 private challenge for a ready bracket match.
    Returns {challenge_id, public_code} or None if supabase unavailable.
    """
    a, b = match.get("player_a"), match.get("player_b")
    if not a or not b:
        return None
    if match.get("challenge_id"):
        return {
            "challenge_id": match["challenge_id"],
            "public_code": match.get("public_code"),
            "already": True,
        }

    code = (tournament.get("code") or "").upper()
    match_key = match.get("match_key") or ""
    game = tournament.get("game_id") or "physical.chess"
    partner = (tournament.get("metadata") or {}).get("partner_code")
    title = tournament.get("title") or "Cup"
    msg = encode_cup_message(code, match_key, f"{title} · {match_key}")
    if partner:
        msg += f" · center {partner}"

    challenge_id = str(uuid.uuid4())
    expires = datetime.now(timezone.utc) + timedelta(hours=48)

    try:
        from backend.supabase_client import get_supabase
        from gaming.src.backend.services.challenge_compat import denormalize_challenge
        from gaming.src.backend.services.match_codes import display_code

        record = denormalize_challenge(
            {
                "id": challenge_id,
                "creator_id": a,
                "opponent_id": b,
                "amount_usdc": 0.0,
                "game": game,
                "visibility": "private",
                # Skip dual-lock: pot already funded. Report path works from playing/submitted.
                "status": "playing",
                "expires_at": expires.isoformat(),
                "message": msg,
                "settlement_chain": tournament.get("chain_id") or "arc",
            }
        )
        sb = get_supabase()
        try:
            sb.schema("gaming").table("challenges").insert(record).execute()
        except Exception:
            record.pop("settlement_chain", None)
            sb.schema("gaming").table("challenges").insert(record).execute()

        public_code = display_code(None, challenge_id=challenge_id)
        logger.info(
            "[TourMatch] spawned %s cup=%s %s vs %s → %s",
            match_key,
            code,
            str(a)[:8],
            str(b)[:8],
            public_code,
        )
        return {
            "challenge_id": challenge_id,
            "public_code": public_code,
            "already": False,
        }
    except Exception as exc:
        logger.warning(
            "[TourMatch] no 1v1 challenge for %s cup=%s (%s) — use /twinner or fix Supabase",
            match_key,
            code,
            exc,
        )
        return None


def attach_challenges_to_ready_matches(tournament: dict[str, Any]) -> dict[str, Any]:
    """
    For every ready match without challenge_id, spawn challenge and patch bracket.
    Returns updated tournament.
    """
    from gaming.src.backend.services.tournament import get_tournament, _save_bracket

    t = get_tournament(tournament.get("id") or tournament.get("code") or "")
    if not t or t.get("status") != "live":
        return tournament
    bracket = list(t.get("bracket") or [])
    changed = False
    for m in bracket:
        if m.get("status") != "ready":
            continue
        if m.get("challenge_id"):
            continue
        if not m.get("player_a") or not m.get("player_b"):
            continue
        created = create_match_challenge(t, m)
        if created and created.get("challenge_id"):
            m["challenge_id"] = created["challenge_id"]
            m["public_code"] = created.get("public_code")
            changed = True
    if changed:
        _save_bracket(t["id"], bracket)
        return get_tournament(t["id"]) or t
    return t


async def notify_ready_matches(tournament: dict[str, Any]) -> None:
    """DM both players for ready matches (with match code if any)."""
    try:
        from gaming.src.bot.utils.notify import notify_user
        from gaming.src.backend.services.game_catalog import display_name
    except Exception:
        return

    code = tournament.get("code") or ""
    game = display_name(tournament.get("game_id") or "")
    for m in tournament.get("bracket") or []:
        if m.get("status") != "ready":
            continue
        a, b = m.get("player_a"), m.get("player_b")
        mk = m.get("match_key") or "?"
        mcode = m.get("public_code") or "—"
        for pid, opp in ((a, b), (b, a)):
            if not pid:
                continue
            try:
                await notify_user(
                    pid,
                    f"🏆 <b>Cup match ready</b> · <code>{code}</code>\n"
                    f"Match: <code>{mk}</code> · {game}\n"
                    f"Boardman match code: <code>{mcode}</code>\n\n"
                    f"Play your opponent, then both <b>Report result</b> "
                    f"(photo + I won / I lost).\n"
                    f"Winner advances automatically.",
                )
            except Exception:
                logger.exception("[TourMatch] notify failed %s", pid)


def advance_from_settled_challenge(
    challenge: dict[str, Any],
    winner_id: str,
) -> Optional[dict[str, Any]]:
    """
    If challenge is a cup match, record winner and spawn next challenges.
    Returns updated tournament or None.
    """
    parsed = parse_cup_message(challenge.get("message"))
    if not parsed:
        return None
    cup_code, match_key = parsed
    from gaming.src.backend.services.tournament import (
        TournamentError,
        get_tournament,
        report_match_winner,
    )

    t = get_tournament(cup_code)
    if not t:
        logger.warning("[TourMatch] cup %s not found for challenge settle", cup_code)
        return None
    try:
        t2 = report_match_winner(cup_code, match_key, winner_id)
    except TournamentError as exc:
        logger.warning("[TourMatch] advance failed: %s", exc)
        return None

    # Attach challenges for newly ready matches
    t3 = attach_challenges_to_ready_matches(t2)
    return t3
