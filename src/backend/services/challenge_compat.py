"""
Map between ClawStation code field names and the live gaming.challenges columns.

Live DB (legacy + migration 047/049 escrow columns):
  issuer_id, target_id, stake_amount, game_type, theme, message, status, ...
  creator_lock_tx_*, opponent_lock_tx_*, scores, screenshots, dispute_*,
  settlement_chain, ai_* ...

Code expects (migration 045 names):
  creator_id, opponent_id, amount_usdc, game, visibility, ...
"""
from __future__ import annotations

from typing import Any, Optional

_CODE_ONLY = {
    "creator_id",
    "opponent_id",
    "amount_usdc",
    "game",
    "visibility",
}

_TO_DB = {
    "creator_id": "issuer_id",
    "opponent_id": "target_id",
    "amount_usdc": "stake_amount",
    "game": "game_type",
    "visibility": "theme",
}

# Columns that may not exist on older DBs — strip on insert if insert fails handled by caller.
OPTIONAL_COLUMNS = {
    "settlement_chain",
    "ai_creator_score",
    "ai_opponent_score",
    "ai_confidence",
    "ai_verified_score",
    "ai_verified_at",
    "ai_winner_id",
    "creator_lock_tx_id",
    "creator_lock_tx_hash",
    "opponent_lock_tx_id",
    "opponent_lock_tx_hash",
    "resolved_tx_hash",
    "winner_id",
    "screenshot_creator_url",
    "screenshot_opponent_url",
    "creator_score",
    "opponent_score",
    "dispute_reason",
    "dispute_raised_at",
    "admin_resolved_by",
    "admin_resolution_note",
}


def normalize_challenge(row: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
    """Return a challenge dict with code-facing field names filled in."""
    if not row:
        return row
    out = dict(row)
    out["creator_id"] = row.get("creator_id") or row.get("issuer_id")
    out["opponent_id"] = (
        row["opponent_id"] if row.get("opponent_id") is not None else row.get("target_id")
    )
    amount = row.get("amount_usdc")
    if amount is None:
        amount = row.get("stake_amount")
    out["amount_usdc"] = amount
    out["game"] = row.get("game") or row.get("game_type") or "EA FC"
    vis = row.get("visibility") or row.get("theme")
    if vis not in ("public", "private"):
        vis = "private"
    out["visibility"] = vis
    # Default settlement chain for legacy rows
    out["settlement_chain"] = (
        row.get("settlement_chain")
        or row.get("chain")
        or "base"
    )
    return out


def denormalize_challenge(data: dict[str, Any]) -> dict[str, Any]:
    """Map a code-facing payload to live DB column names for insert/update."""
    out: dict[str, Any] = {}
    for key, value in data.items():
        if key in _TO_DB:
            out[_TO_DB[key]] = value
        elif key in _CODE_ONLY:
            continue
        else:
            out[key] = value
    return out


def normalize_list(rows: Optional[list]) -> list:
    return [normalize_challenge(r) for r in (rows or []) if r]
