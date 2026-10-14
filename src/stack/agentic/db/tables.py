"""The document tables, shared by the services and the legacy-file bridge."""
from __future__ import annotations

import logging
import threading
from typing import Any, Callable

from gaming.src.stack.agentic.db.docs import DocTable

logger = logging.getLogger(__name__)

# Settled records the old hot files kept; everything else was "archive".
HOT_SETTLED_MATCHES = 8
HOT_SETTLED_BOOKS = 50

# A settlement that has started (or finished) can only move forward.
_FORWARD_ONLY = {
    "settled": {"settled"},
    "settling": {"settling", "settled", "settle_failed"},
    # An interrupted table being refunded (house abort journal).
    "aborting": {"aborting", "cancelled", "settle_failed"},
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

# NULLS LAST spelled out: SQLite sorts NULL last in DESC, Postgres first, and
# an undated settled record must never push the newest ones out of "hot".
MATCH_SETTLED_ORDER = "settled_at DESC NULLS LAST, updated_at DESC NULLS LAST"
BOOK_SETTLED_ORDER = "settled_at DESC NULLS LAST, created_at DESC NULLS LAST"


_PROJ_CACHE: dict[tuple, dict[str, tuple[int, Any]]] = {}
_PROJ_LOCK = threading.Lock()


def all_matches_projected(project: Callable[[dict[str, Any]], Any], *, chunk: int = 400) -> dict[str, Any]:
    """Every match (live and long-settled) through ``project``, cached.

    Each call reads only ``(match_id, version)`` for all rows (small ints);
    documents are fetched and projected again only for rows whose version
    changed since the last call. Every write bumps ``version``, so the cache
    can never serve a stale record. Returned values are shared read-only views.
    """
    from gaming.src.stack.agentic.db.docs import reading
    from gaming.src.stack.agentic.db.engine import get_db
    from gaming.src.stack.agentic.json_cache import freeze

    key = (get_db().key, id(project))
    with _PROJ_LOCK:
        cached = _PROJ_CACHE.setdefault(key, {})
        with reading() as tx:
            versions = {str(r["match_id"]): int(r["version"]) for r in tx.all(
                "SELECT match_id, version FROM agentic_matches", ()
            )}
            stale = [mid for mid, v in versions.items() if (cached.get(mid) or (None,))[0] != v]
            for i in range(0, len(stale), chunk):
                part = stale[i:i + chunk]
                marks = ",".join("?" for _ in part)
                for r in tx.all(
                    f"SELECT match_id, version, doc FROM agentic_matches WHERE match_id IN ({marks})", part
                ):
                    doc = tx.unjson(r["doc"]) or {}
                    cached[str(r["match_id"])] = (int(r["version"]), freeze(project(doc)))
        for gone in set(cached) - set(versions):
            cached.pop(gone, None)
        return {mid: val for mid, (_v, val) in cached.items()}


def hot_matches() -> list[dict[str, Any]]:
    return MATCHES.hot(HOT_SETTLED_MATCHES, settled_order=MATCH_SETTLED_ORDER)


def hot_books() -> list[dict[str, Any]]:
    return BOOKS.hot(HOT_SETTLED_BOOKS, settled_order=BOOK_SETTLED_ORDER)
