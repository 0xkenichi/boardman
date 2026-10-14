"""Import the legacy JSON files into the database.

Used by ``scripts/migrate_json_to_db.py`` (dry run by default, ``--apply`` to
write) and by ``BOARDMAN_STORAGE=json`` (the files imported into a private,
read-only SQLite copy so every read path keeps working during a cutover).

Never modifies the JSON files. Corrupt files are reported; a truncated file
has every complete record before the damage salvaged and is reported as
``partial``.
"""
from __future__ import annotations

import json
import logging
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Optional

from gaming.src.stack.agentic.db.engine import Database, Tx, dumps
from gaming.src.stack.agentic.db.money import fmt, places, to_micro

logger = logging.getLogger(__name__)

SOURCES = {
    "ledger.json": None,
    "matches.json": "matches",
    "matches_archive.json": "matches",
    "spectator_books.json": "books",
    "spectator_books_archive.json": "books",
    "agent_lp_pools.json": "pools",
}


@dataclass
class ImportReport:
    files: dict[str, dict[str, Any]] = field(default_factory=dict)
    counts: dict[str, int] = field(default_factory=dict)
    problems: list[str] = field(default_factory=list)
    balance_sum_json: str = "0"
    balance_sum_db: str = "0"
    balance_wallets_json: int = 0
    balance_wallets_db: int = 0

    @property
    def checksum_ok(self) -> bool:
        return (
            Decimal(self.balance_sum_json) == Decimal(self.balance_sum_db)
            and self.balance_wallets_json == self.balance_wallets_db
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "files": self.files,
            "counts": self.counts,
            "problems": self.problems,
            "balances": {
                "sum_json": self.balance_sum_json,
                "sum_db": self.balance_sum_db,
                "wallets_json": self.balance_wallets_json,
                "wallets_db": self.balance_wallets_db,
                "checksum_ok": self.checksum_ok,
            },
        }


# ── reading (tolerant) ───────────────────────────────────────────────────────


def _salvage_mapping(text: str, root_key: str) -> dict[str, Any]:
    """Recover complete ``"key": {...}`` entries of ``{root_key: {...}}`` from
    a truncated or damaged file, stopping at the first unreadable record."""
    dec = json.JSONDecoder()
    marker = f'"{root_key}"'
    i = text.find(marker)
    if i < 0:
        return {}
    i = text.find("{", i + len(marker))
    if i < 0:
        return {}
    i += 1
    out: dict[str, Any] = {}
    n = len(text)
    while i < n:
        while i < n and text[i] in " \t\r\n,":
            i += 1
        if i >= n or text[i] == "}":
            break
        try:
            key, i = dec.raw_decode(text, i)
            while i < n and text[i] in " \t\r\n":
                i += 1
            if i >= n or text[i] != ":":
                break
            i += 1
            while i < n and text[i] in " \t\r\n":
                i += 1
            val, i = dec.raw_decode(text, i)
        except ValueError:
            break
        if isinstance(key, str) and isinstance(val, dict):
            out[key] = val
    return out


def read_file(path: Path, root_key: Optional[str]) -> tuple[Any, dict[str, Any]]:
    info: dict[str, Any] = {"path": str(path)}
    if not path.exists():
        info["status"] = "missing"
        return None, info
    info["bytes"] = path.stat().st_size
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        info.update(status="unreadable", error=str(exc))
        return None, info
    if not text.strip():
        info["status"] = "empty"
        return None, info
    try:
        data = json.loads(text)
        info["status"] = "ok"
        return data, info
    except ValueError as exc:
        info["error"] = str(exc)
    if root_key is None:
        info["status"] = "corrupt"
        return None, info
    salvaged = _salvage_mapping(text, root_key)
    info["status"] = "partial" if salvaged else "corrupt"
    info["salvaged_records"] = len(salvaged)
    return ({root_key: salvaged} if salvaged else None), info


def read_legacy(legacy_dir: Path, report: ImportReport) -> dict[str, Any]:
    data: dict[str, Any] = {}
    for name, root in SOURCES.items():
        payload, info = read_file(legacy_dir / name, root)
        report.files[name] = info
        if info["status"] in {"corrupt", "unreadable"}:
            report.problems.append(f"{name}: {info['status']} ({info.get('error')})")
        elif info["status"] == "partial":
            report.problems.append(
                f"{name}: damaged — salvaged {info['salvaged_records']} complete records ({info.get('error')})"
            )
        data[name] = payload
    return data


# ── writing ──────────────────────────────────────────────────────────────────


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _micro(val: Any, what: str, report: ImportReport) -> int:
    try:
        d = Decimal(str(val if val is not None else "0"))
    except InvalidOperation:
        report.problems.append(f"{what}: not a number {val!r} — imported as 0")
        return 0
    m = to_micro(d)
    if Decimal(m) / Decimal(1_000_000) != d:
        report.problems.append(f"{what}: {d} has more than 6 decimals — rounded to {fmt(m)}")
    return m


def _doc_cols(doc: dict[str, Any], settled_status: str = "settled") -> tuple[str, Any, Any, Any]:
    status = str(doc.get("status") or "")
    settled_at = doc.get("settled_at")
    if not settled_at and status == settled_status:
        settled_at = doc.get("updated_at") or doc.get("created_at")
    return status, doc.get("created_at"), doc.get("updated_at"), settled_at


def _insert_doc(tx: Tx, table: str, key_col: str, key: str, doc: dict[str, Any], default_status: str = "") -> None:
    status, created, updated, settled = _doc_cols(doc)
    tx.execute(
        f"INSERT INTO {table} ({key_col}, status, created_at, updated_at, settled_at, version, doc) "
        "VALUES (?, ?, ?, ?, ?, 1, ?)",
        (key, status or default_status, created, updated, settled, tx.json(doc)),
    )


def _merge_records(data: dict[str, Any], hot: str, archive: str, root: str) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for name in (archive, hot):  # hot wins
        for k, v in ((data.get(name) or {}).get(root) or {}).items():
            if isinstance(v, dict):
                out[str(k)] = v
    return out


def import_into(tx: Tx, data: dict[str, Any], report: ImportReport) -> None:
    """Write everything in one transaction (caller commits or rolls back)."""
    # ledger
    ledger = data.get("ledger.json") or {}
    balances = ledger.get("balances") or {}
    for wallet, raw in balances.items():
        m = _micro(raw, f"balance {wallet}", report)
        if m < 0:
            report.problems.append(f"balance {wallet} is negative ({raw}) — imported as 0, needs review")
            m = 0
        tx.execute(
            "INSERT INTO ledger_balances (wallet, balance_micro, scale, updated_at) VALUES (?, ?, ?, ?)",
            (str(wallet).lower(), m, places(raw), _now()),
        )
    report.balance_wallets_json = len(balances)
    report.balance_sum_json = fmt(
        sum(_micro(v, "", ImportReport()) for v in balances.values())
    )
    escs = ledger.get("escrows") or {}
    for mid, esc in escs.items():
        if not isinstance(esc, dict):
            report.problems.append(f"escrow {mid}: not an object — skipped")
            continue
        tx.execute(
            "INSERT INTO ledger_escrows (match_id, status, stake_micro, agent_a_wallet, agent_b_wallet, "
            "result, created_at, settled_at, doc) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                str(mid),
                str(esc.get("status") or "open"),
                max(0, _micro(esc.get("stake_usdc"), f"escrow {mid} stake", report)),
                str(esc.get("agent_a_wallet") or "").lower(),
                str(esc.get("agent_b_wallet") or "").lower(),
                esc.get("result"),
                esc.get("created_at") or _now(),
                esc.get("settled_at"),
                tx.json(esc),
            ),
        )
    txs = ledger.get("txs") or []
    for t in txs:
        if not isinstance(t, dict):
            continue
        amt = t.get("amount")
        bal_after = t.get("balance_after")
        tx.execute(
            "INSERT INTO ledger_txs (ts, type, wallet, ref, reason, amount_micro, balance_after_micro, doc) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                t.get("ts") or "",
                str(t.get("type") or ""),
                t.get("wallet"),
                t.get("ref"),
                t.get("reason"),
                to_micro(amt) if amt not in (None, "") else None,
                to_micro(bal_after) if bal_after not in (None, "") else None,
                tx.json(t),
            ),
        )
    report.counts.update(ledger_wallets=len(balances), ledger_escrows=len(escs), ledger_txs=len(txs))

    matches = _merge_records(data, "matches.json", "matches_archive.json", "matches")
    for mid, m in matches.items():
        m.setdefault("match_id", mid)
        _insert_doc(tx, "agentic_matches", "match_id", mid, m)
    books = _merge_records(data, "spectator_books.json", "spectator_books_archive.json", "books")
    for mid, b in books.items():
        b.setdefault("match_id", mid)
        _insert_doc(tx, "spectator_books", "match_id", mid, b)
    pools = ((data.get("agent_lp_pools.json") or {}).get("pools") or {})
    for aid, p in pools.items():
        if isinstance(p, dict):
            _insert_doc(tx, "lp_pools", "agent_id", str(aid), p, default_status="active")
    report.counts.update(matches=len(matches), spectator_books=len(books), lp_pools=len(pools))

    row = tx.one("SELECT COUNT(*) AS n, COALESCE(SUM(balance_micro), 0) AS s FROM ledger_balances", ())
    report.balance_wallets_db = int(row["n"])
    report.balance_sum_db = fmt(row["s"])


def mark_imported(tx: Tx, report: ImportReport) -> None:
    summary = dumps({"at": _now(), **report.to_dict()})
    tx.execute(
        "INSERT INTO storage_meta (key, value, updated_at) VALUES (?, ?, ?) "
        "ON CONFLICT (key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at",
        ("legacy_import", summary, _now()),
    )


def db_is_empty(tx: Tx) -> bool:
    for t in ("ledger_balances", "ledger_escrows", "agentic_matches", "spectator_books", "lp_pools"):
        if tx.scalar(f"SELECT COUNT(*) AS n FROM {t}", ()):
            return False
    return True


# ── BOARDMAN_STORAGE=json ────────────────────────────────────────────────────


def open_readonly_legacy(key: str, legacy_dir: Path) -> Database:
    """Import the legacy files into a private SQLite file, then open it read-only."""
    tmpdir = Path(tempfile.mkdtemp(prefix="boardman-legacy-"))
    path = tmpdir / "legacy.sqlite3"
    writer = Database(f"{key}:build", sqlite_path=path, check_migrated=False)
    report = ImportReport()
    data = read_legacy(legacy_dir, report)
    # The import marker keeps the "never migrated" guard quiet for this copy.
    with writer.transaction() as tx:
        import_into(tx, data, report)
        mark_imported(tx, report)
    writer.close_all()
    for p in report.problems:
        logger.error("[storage] legacy read-only mode: %s", p)
    logger.warning(
        "[storage] BOARDMAN_STORAGE=json — serving %s read-only (%s)", legacy_dir, report.counts
    )
    db = Database(key, sqlite_path=path, readonly=True)
    db._schema_ready = True
    return db
