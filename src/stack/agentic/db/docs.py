"""JSON documents with atomic read-modify-write.

Matches, spectator books and LP pools keep their existing JSON shape (the API
and the frontend depend on it) but live one row per record, keyed and indexed,
instead of one ever-growing file. Every change is ``update(key, fn)``: the row is
read *inside* the write transaction (``FOR UPDATE`` on Postgres, the database
write lock on SQLite), ``fn`` edits it, and it is written back in the same
transaction — no stale copy is ever saved over a newer one.

``snapshot`` / ``save_snapshot`` keep the old whole-file ``_load()`` / ``_save()``
call pattern working for code outside the ledger package: a snapshot remembers
every record as loaded, and saving it writes back only the top-level keys the
caller actually changed, merged onto the current row (a three-way merge per
record). Two writers that touched different fields no longer erase each other.
"""
from __future__ import annotations

import json
import logging
from contextlib import contextmanager
from typing import Any, Callable, Iterable, Iterator, Optional

from gaming.src.stack.agentic.db.engine import Tx, current_tx, dumps, get_db, transaction

logger = logging.getLogger(__name__)

Guard = Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]]


@contextmanager
def reading() -> Iterator[Tx]:
    """Join the caller's transaction, or open a short read-only one."""
    tx = current_tx(get_db())
    if tx is not None:
        yield tx
        return
    with transaction(readonly=True) as tx:
        yield tx


class DocSnapshot(dict):
    """Root dict returned by ``DocTable.snapshot`` (``{"matches": {...}}``)."""

    orig: dict[str, str]
    root_key: str


class DocTable:
    def __init__(
        self,
        table: str,
        key_col: str,
        *,
        root_key: str,
        default_status: str = "",
        settled_status: str = "settled",
        guard: Optional[Guard] = None,
    ) -> None:
        self.table = table
        self.key_col = key_col
        self.root_key = root_key
        self.default_status = default_status
        self.settled_status = settled_status
        self.guard = guard

    # ── row <-> doc ──

    def _columns(self, doc: dict[str, Any]) -> tuple[str, Any, Any, Any]:
        status = str(doc.get("status") or self.default_status or "")
        settled_at = doc.get("settled_at")
        if not settled_at and status == self.settled_status:
            settled_at = doc.get("updated_at") or doc.get("created_at")
        return status, doc.get("created_at"), doc.get("updated_at"), settled_at

    @staticmethod
    def _load(tx: Tx, raw: Any) -> dict[str, Any]:
        doc = tx.unjson(raw)
        return doc if isinstance(doc, dict) else {}

    # ── reads ──

    def get(self, key: str) -> Optional[dict[str, Any]]:
        if not key:
            return None
        with reading() as tx:
            row = tx.one(f"SELECT doc FROM {self.table} WHERE {self.key_col} = ?", (key,))
            return self._load(tx, row["doc"]) if row else None

    def get_locked(self, tx: Tx, key: str) -> Optional[dict[str, Any]]:
        row = tx.one(
            f"SELECT doc FROM {self.table} WHERE {self.key_col} = ?{tx.for_update}", (key,)
        )
        return self._load(tx, row["doc"]) if row else None

    def _get_for_write(self, tx: Tx, key: str) -> Optional[dict[str, Any]]:
        """``get_locked`` for a write that may create the row.

        A miss takes a per-key lock and reads again, so two creators of the
        same key queue up instead of both inserting (see ``Tx.lock_key``).
        """
        cur = self.get_locked(tx, key)
        if cur is None:
            tx.lock_key(self.table, key)
            cur = self.get_locked(tx, key)
        return cur

    def exists(self, key: str) -> bool:
        with reading() as tx:
            return tx.one(f"SELECT 1 AS x FROM {self.table} WHERE {self.key_col} = ?", (key,)) is not None

    def query(
        self,
        where: str = "",
        params: Iterable[Any] = (),
        *,
        order_by: str = "",
        limit: Optional[int] = None,
    ) -> list[dict[str, Any]]:
        sql = f"SELECT doc FROM {self.table}"
        if where:
            sql += f" WHERE {where}"
        if order_by:
            sql += f" ORDER BY {order_by}"
        args = list(params)
        if limit is not None:
            sql += " LIMIT ?"
            args.append(int(limit))
        with reading() as tx:
            return [self._load(tx, r["doc"]) for r in tx.all(sql, args)]

    def keys(self, where: str = "", params: Iterable[Any] = ()) -> list[str]:
        sql = f"SELECT {self.key_col} AS k FROM {self.table}"
        if where:
            sql += f" WHERE {where}"
        with reading() as tx:
            return [str(r["k"]) for r in tx.all(sql, list(params))]

    def count(self, where: str = "", params: Iterable[Any] = ()) -> int:
        sql = f"SELECT COUNT(*) AS n FROM {self.table}"
        if where:
            sql += f" WHERE {where}"
        with reading() as tx:
            return int(tx.scalar(sql, list(params)) or 0)

    def hot(self, keep_settled: int, *, settled_order: str) -> list[dict[str, Any]]:
        """Every non-settled record plus the newest ``keep_settled`` settled ones.

        Same set the old hot JSON file held, now an indexed query.
        """
        with reading() as tx:
            live = tx.all(
                f"SELECT doc FROM {self.table} WHERE status <> ?", (self.settled_status,)
            )
            recent = tx.all(
                f"SELECT doc FROM {self.table} WHERE status = ? ORDER BY {settled_order} LIMIT ?",
                (self.settled_status, int(keep_settled)),
            )
            return [self._load(tx, r["doc"]) for r in live + recent]

    # ── writes ──

    def _insert(self, tx: Tx, key: str, doc: dict[str, Any]) -> None:
        status, created, updated, settled = self._columns(doc)
        tx.execute(
            f"INSERT INTO {self.table} ({self.key_col}, status, created_at, updated_at, "
            "settled_at, version, doc) VALUES (?, ?, ?, ?, ?, 1, ?)",
            (key, status, created, updated, settled, tx.json(doc)),
        )

    def _write(self, tx: Tx, key: str, doc: dict[str, Any]) -> None:
        status, created, updated, settled = self._columns(doc)
        tx.execute(
            f"UPDATE {self.table} SET status = ?, created_at = ?, updated_at = ?, "
            f"settled_at = ?, version = version + 1, doc = ? WHERE {self.key_col} = ?",
            (status, created, updated, settled, tx.json(doc), key),
        )

    def insert_if_absent(self, key: str, doc: dict[str, Any]) -> tuple[dict[str, Any], bool]:
        """Atomic create. Returns (stored doc, created?)."""
        with transaction() as tx:
            cur = self._get_for_write(tx, key)
            if cur is not None:
                return cur, False
            self._insert(tx, key, doc)
            return doc, True

    def put(self, key: str, doc: dict[str, Any]) -> dict[str, Any]:
        """Upsert the whole document (imports, new records)."""
        with transaction() as tx:
            if self._get_for_write(tx, key) is None:
                self._insert(tx, key, doc)
            else:
                self._write(tx, key, doc)
        return doc

    def upsert_with(
        self, key: str, fn: Callable[[Optional[dict[str, Any]]], Optional[dict[str, Any]]]
    ) -> Optional[dict[str, Any]]:
        """``fn(current or None) -> new doc`` (None = leave as is), atomically."""
        with transaction() as tx:
            cur = self._get_for_write(tx, key)
            new = fn(json.loads(dumps(cur)) if cur is not None else None)
            if new is None:
                return cur
            if cur is None:
                self._insert(tx, key, new)
            else:
                self._write(tx, key, new)
            return new

    def update(self, key: str, fn: Callable[[dict[str, Any]], Any]) -> Optional[dict[str, Any]]:
        """Mutate an existing record in place, atomically. None if missing.

        ``fn`` edits the dict it is given; raising inside ``fn`` rolls back;
        returning ``False`` means "nothing to write".
        """
        with transaction() as tx:
            cur = self.get_locked(tx, key)
            if cur is None:
                return None
            if fn(cur) is False:
                return cur
            self._write(tx, key, cur)
            return cur

    def delete(self, key: str) -> None:
        with transaction() as tx:
            tx.execute(f"DELETE FROM {self.table} WHERE {self.key_col} = ?", (key,))

    # ── whole-file compatibility ──

    def snapshot(self, docs: list[dict[str, Any]], key_field: str) -> DocSnapshot:
        records = {str(d.get(key_field) or ""): d for d in docs if d.get(key_field)}
        snap = DocSnapshot({self.root_key: records})
        snap.orig = {k: dumps(v) for k, v in records.items()}
        snap.root_key = self.root_key
        return snap

    def save_snapshot(self, data: dict[str, Any]) -> int:
        """Write back what the caller changed in a snapshot. Returns rows written."""
        records = (data or {}).get(self.root_key) or {}
        orig: Optional[dict[str, str]] = getattr(data, "orig", None)
        written = 0
        for key, rec in list(records.items()):
            if not key or not isinstance(rec, dict):
                continue
            new_json = dumps(rec)
            before = orig.get(key) if orig is not None else None
            if before is not None and before == new_json:
                continue
            new = json.loads(new_json)
            base = json.loads(before) if before is not None else None

            def _apply(cur: Optional[dict[str, Any]], new=new, base=base) -> dict[str, Any]:
                if cur is None:
                    return new
                merged = dict(cur)
                if base is None:
                    merged.update(new)
                else:
                    for k, v in new.items():
                        if k not in base or base[k] != v:
                            merged[k] = v
                    for k in base:
                        if k not in new:
                            merged.pop(k, None)
                if self.guard is not None:
                    merged = self.guard(cur, merged)
                return merged

            self.upsert_with(key, _apply)
            written += 1
            if orig is not None:
                orig[key] = new_json
        return written
