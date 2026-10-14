"""Legacy JSON file names served from the database.

``store.load_json`` / ``store.save_json`` delegate here for the files that
moved into the database, so callers outside the ledger package (API handlers,
metrics, the AFM dashboard) keep working with the same shapes.
"""
from __future__ import annotations

from typing import Any

from gaming.src.stack.agentic.db import tables


def load(name: str, default: Any) -> Any:
    if name == "ledger.json":
        from gaming.src.stack.agentic import ledger

        return ledger.snapshot()
    if name == "matches.json":
        return tables.MATCHES.snapshot(tables.hot_matches(), "match_id")
    if name == "matches_archive.json":
        hot = {m.get("match_id") for m in tables.hot_matches()}
        rows = [m for m in tables.MATCHES.query("status = ?", ("settled",)) if m.get("match_id") not in hot]
        return tables.MATCHES.snapshot(rows, "match_id")
    if name == "spectator_books.json":
        return tables.BOOKS.snapshot(tables.hot_books(), "match_id")
    if name == "spectator_books_archive.json":
        hot = {b.get("match_id") for b in tables.hot_books()}
        rows = [b for b in tables.BOOKS.query("status = ?", ("settled",)) if b.get("match_id") not in hot]
        return tables.BOOKS.snapshot(rows, "match_id")
    if name == "agent_lp_pools.json":
        return tables.LP_POOLS.snapshot(tables.LP_POOLS.query(), "agent_id")
    return default


def save(name: str, payload: Any) -> None:
    if name in {"matches.json", "matches_archive.json"}:
        tables.MATCHES.save_snapshot(payload)
        return
    if name in {"spectator_books.json", "spectator_books_archive.json"}:
        tables.BOOKS.save_snapshot(payload)
        return
    if name == "agent_lp_pools.json":
        tables.LP_POOLS.save_snapshot(payload)
        return
    raise RuntimeError(
        f"{name} is database-backed — write through its service (ledger.credit/debit/…)"
    )
