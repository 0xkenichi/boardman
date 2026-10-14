"""Settlement journal: one row per (match_id, step), primary-keyed.

A money step writes its journal row in the *same* transaction as its ledger
change, so after a crash a step is either fully done (row present) or not at
all. A retry skips every step whose row exists and reuses its recorded detail.
Steps that call out (chain, Telegram, JSON side files) record their row right
after the call and reconcile on retry.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from gaming.src.stack.agentic.db.docs import reading
from gaming.src.stack.agentic.db.engine import Tx


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def get(tx: Tx, match_id: str, step: str) -> Optional[dict[str, Any]]:
    row = tx.one(
        "SELECT step, owner, created_at, detail FROM settlement_journal "
        "WHERE match_id = ? AND step = ?",
        (match_id, step),
    )
    if row is None:
        return None
    row["detail"] = tx.unjson(row.get("detail"))
    return row


def record(tx: Tx, match_id: str, step: str, detail: Any = None, *, owner: str = "") -> bool:
    """Insert the step row. False if it already existed (never overwrites).

    ``ON CONFLICT DO NOTHING`` rather than check-then-insert: on Postgres two
    writers can both miss the row, and the loser's plain INSERT would raise a
    unique violation that aborts its whole transaction.
    """
    return tx.rowcount(
        "INSERT INTO settlement_journal (match_id, step, owner, created_at, detail) "
        "VALUES (?, ?, ?, ?, ?) ON CONFLICT (match_id, step) DO NOTHING",
        (match_id, step, owner, _now(), tx.json(detail)),
    ) == 1


def steps(match_id: str) -> list[dict[str, Any]]:
    with reading() as tx:
        rows = tx.all(
            "SELECT step, owner, created_at, detail FROM settlement_journal "
            "WHERE match_id = ? ORDER BY created_at, step",
            (match_id,),
        )
        for r in rows:
            r["detail"] = tx.unjson(r.get("detail"))
        return rows


def done(match_id: str, step: str) -> bool:
    with reading() as tx:
        return get(tx, match_id, step) is not None
