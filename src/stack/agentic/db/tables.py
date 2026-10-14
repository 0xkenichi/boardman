"""The document tables, shared by the services and the legacy-file bridge."""
from __future__ import annotations

import logging
from typing import Any

from gaming.src.stack.agentic.db.docs import DocTable

logger = logging.getLogger(__name__)

# Settled records the old hot files kept; everything else was "archive".
HOT_SETTLED_MATCHES = 8
HOT_SETTLED_BOOKS = 50

# A settlement that has started (or finished) can only move forward.
_FORWARD_ONLY = {
    "settled": {"settled"},
    "settling": {"settling", "settled", "settle_failed"},
}


def match_guard(cur: dict[str, Any], merged: dict[str, Any]) -> dict[str, Any]:
    """Refuse a stale whole-record save that would rewind a settlement."""
    was = str(cur.get("status") or "")
    allowed = _FORWARD_ONLY.get(was)
    if allowed is not None and str(merged.get("status") or "") not in allowed:
        logger.error(
            "[store] refused to move match %s from %s to %s via a stale save",
            cur.get("match_id"), was, merged.get("status"),
        )
        merged["status"] = was
        for k in ("escrow", "settled_at", "result", "winner_agent_id"):
            if k in cur:
                merged[k] = cur[k]
    return merged


def book_guard(cur: dict[str, Any], merged: dict[str, Any]) -> dict[str, Any]:
    if cur.get("status") == "settled" and merged.get("status") != "settled":
        logger.error("[store] refused to reopen settled book %s via a stale save", cur.get("match_id"))
        merged["status"] = "settled"
        merged["payouts"] = cur.get("payouts")
    return merged


MATCHES = DocTable("agentic_matches", "match_id", root_key="matches", guard=match_guard)
BOOKS = DocTable("spectator_books", "match_id", root_key="books", guard=book_guard)
LP_POOLS = DocTable("lp_pools", "agent_id", root_key="pools", default_status="active")

MATCH_SETTLED_ORDER = "settled_at DESC, updated_at DESC"
BOOK_SETTLED_ORDER = "settled_at DESC, created_at DESC"


def hot_matches() -> list[dict[str, Any]]:
    return MATCHES.hot(HOT_SETTLED_MATCHES, settled_order=MATCH_SETTLED_ORDER)


def hot_books() -> list[dict[str, Any]]:
    return BOOKS.hot(HOT_SETTLED_BOOKS, settled_order=BOOK_SETTLED_ORDER)
