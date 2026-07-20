"""
One-tap rematch: reuse last stake/game/chain with a past rival.
Skips tag/amount/game/chain wizard — opponent only Accepts then both Lock.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Optional

from backend.supabase_client import get_supabase
from gaming.src.backend.services.challenge_compat import denormalize_challenge
from gaming.src.backend.services.match_codes import display_code, new_challenge_public_code
from gaming.src.backend.services.play_points import assert_can_start_or_accept
from gaming.src.backend.services.rematch_public import get_recent_rivals
from gaming.src.backend.services.safety import assert_money_ops_allowed, validate_stake

logger = logging.getLogger(__name__)


async def create_quick_rematch(
    creator_id: str,
    opponent_id: str,
    *,
    stake: Optional[float] = None,
    game: Optional[str] = None,
    chain: Optional[str] = None,
) -> dict[str, Any]:
    """Create a private open challenge using last settings with this rival."""
    if creator_id == opponent_id:
        raise ValueError("Can't rematch yourself")

    blocked = assert_can_start_or_accept(creator_id)
    if blocked:
        raise ValueError(blocked.replace("Tap 🎮 My match", "Finish your open match first"))

    blocked_o = assert_can_start_or_accept(opponent_id)
    if blocked_o:
        raise ValueError("Opponent already has an open match — try later")

    # Defaults from most recent match with this rival
    rivals = get_recent_rivals(creator_id, limit=20)
    prior = next((r for r in rivals if r["profile_id"] == opponent_id), None)
    amount = Decimal(str(stake if stake is not None else (prior or {}).get("stake") or 1))
    game_s = game or (prior or {}).get("game") or "EAFC"
    chain_s = chain or (prior or {}).get("chain") or "arc"

    err = validate_stake(amount)
    if err:
        raise ValueError(err)

    gate = assert_money_ops_allowed(
        creator_id, action="challenge", amount=amount, kind="stake"
    )
    if gate:
        raise ValueError(gate.replace("<b>", "").replace("</b>", ""))

    challenge_id = str(uuid.uuid4())
    public_code = new_challenge_public_code()
    expires = datetime.now(timezone.utc) + timedelta(hours=24)
    record = denormalize_challenge(
        {
            "id": challenge_id,
            "public_code": public_code,
            "creator_id": creator_id,
            "opponent_id": opponent_id,
            "amount_usdc": float(amount),
            "game": game_s,
            "visibility": "private",
            "status": "open",
            "expires_at": expires.isoformat(),
            "message": "Rematch (quick)",
            "settlement_chain": chain_s,
        }
    )
    sb = get_supabase()
    try:
        sb.schema("gaming").table("challenges").insert(record).execute()
    except Exception:
        record.pop("public_code", None)
        try:
            sb.schema("gaming").table("challenges").insert(record).execute()
            public_code = display_code(None, challenge_id=challenge_id)
        except Exception as exc:
            logger.exception("[QuickRematch] insert failed")
            raise ValueError(f"Could not create rematch: {exc}") from exc

    return {
        "challenge_id": challenge_id,
        "public_code": public_code,
        "stake": float(amount),
        "game": game_s,
        "chain": chain_s,
        "opponent_id": opponent_id,
        "opponent_tag": (prior or {}).get("tag") or "player",
    }
