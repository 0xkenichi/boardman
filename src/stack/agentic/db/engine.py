"""Storage engine: one interface, two backends.

The backend is picked from the connection URL:

* ``postgres://`` / ``postgresql://`` -> Postgres (Supabase in production) via
  psycopg 3. Real transactions, ``SELECT ... FOR UPDATE`` row locks, safe for
  several API replicas.
* ``sqlite:///path`` or unset -> SQLite (stdlib ``sqlite3``), by default
  ``<agentic data dir>/boardman.sqlite3``. Local, CI and tests.

``BOARDMAN_DATABASE_URL`` wins over ``DATABASE_URL`` so ops can point the
agentic store somewhere other than the backend's own database.

Every caller writes the same SQL for both backends: ``?`` placeholders (rewritten
to ``%s`` for psycopg), ``tx.for_update`` appended to row-locking SELECTs (empty on
SQLite, where ``BEGIN IMMEDIATE`` already holds the database write lock), and
``tx.json`` / ``tx.unjson`` for document columns (TEXT on SQLite, JSONB on
Postgres). That is the whole dialect shim.

Transactions nest: a ``transaction()`` opened while one is active on the same
thread becomes a SAVEPOINT, so a ledger call made inside a settlement step
commits (or rolls back) together with the step's journal row.
"""
from __future__ import annotations

import contextvars
import json
import logging
import math
import os
import sqlite3
import threading
import time
import weakref
from collections import OrderedDict
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Optional

logger = logging.getLogger(__name__)

DB_FILENAME = "boardman.sqlite3"
# Legacy JSON files whose presence (with no import marker in the DB) means the
# operator has not run scripts/migrate_json_to_db.py yet.
LEGACY_FILES = ("ledger.json", "matches.json", "spectator_books.json", "agent_lp_pools.json")
MAX_OPEN_DATABASES = 6


class StorageError(RuntimeError):
    """Storage misconfiguration or an operation the store refuses."""


class StorageReadOnly(StorageError):
    """A write was attempted while BOARDMAN_STORAGE=json (read-only legacy mode)."""


class StorageNotMigrated(StorageError):
    """Legacy JSON exists but was never imported into the database."""


# ── configuration ────────────────────────────────────────────────────────────


def storage_mode() -> str:
    """``db`` (default) or ``json`` (legacy files served read-only)."""
    raw = (os.getenv("BOARDMAN_STORAGE") or "db").strip().lower()
    if raw in {"db", "json"}:
        return raw
    logger.error("[storage] BOARDMAN_STORAGE=%r is not db|json — using db", raw)
    return "db"


def database_url() -> str:
    for name in ("BOARDMAN_DATABASE_URL", "DATABASE_URL"):
        v = (os.getenv(name) or "").strip()
        if v:
            return v
    return ""


def is_postgres_url(url: str) -> bool:
    return url.startswith(("postgres://", "postgresql://"))


def _data_dir() -> Path:
    from gaming.src.stack.agentic.store import data_dir

    return data_dir()


def sqlite_path_from_url(url: str) -> Path:
    """``sqlite:///abs/path`` -> /abs/path; ``sqlite:///rel`` -> data dir/rel."""
    rest = url[len("sqlite://"):]
    if rest.startswith("/"):
        rest = rest[1:] if rest.startswith("//") else rest
    if not rest or rest in {"/", ":memory:"}:
        return _data_dir() / DB_FILENAME
    p = Path(rest)
    if not p.is_absolute():
        p = _data_dir() / p
    return p


# ── dialects ─────────────────────────────────────────────────────────────────


class Dialect:
    name = "base"
    for_update = ""
    autoid = ""
    json_type = "TEXT"

    def sql(self, text: str) -> str:
        return text

    def json(self, obj: Any) -> Any:
        return dumps(obj)

    @staticmethod
    def unjson(val: Any) -> Any:
        if val is None:
            return None
        if isinstance(val, (bytes, bytearray, memoryview)):
            val = bytes(val).decode("utf-8")
        if isinstance(val, str):
            return json.loads(val)
        return val


class SQLiteDialect(Dialect):
    name = "sqlite"
    for_update = ""
    autoid = "INTEGER PRIMARY KEY AUTOINCREMENT"
    json_type = "TEXT"


class PostgresDialect(Dialect):
    name = "postgres"
    for_update = " FOR UPDATE"
    autoid = "BIGSERIAL PRIMARY KEY"
    json_type = "JSONB"

    def __init__(self) -> None:
        self._cache: dict[str, str] = {}

    def sql(self, text: str) -> str:
        hit = self._cache.get(text)
        if hit is None:
            # Our SQL never embeds '?' or '%' in literals (values are params).
            hit = text.replace("%", "%%").replace("?", "%s")
            self._cache[text] = hit
        return hit

    def json(self, obj: Any) -> Any:
        from psycopg.types.json import Jsonb  # type: ignore

        return Jsonb(_pg_safe(obj), dumps=dumps)


def _pg_safe(obj: Any) -> Any:
    """JSONB has no NaN/Infinity — map them to null (JSON text allowed them)."""
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    if isinstance(obj, dict):
        return {k: _pg_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_pg_safe(v) for v in obj]
    return obj


def dumps(obj: Any) -> str:
    return json.dumps(obj, separators=(",", ":"), default=str)


# ── transactions ─────────────────────────────────────────────────────────────


class Tx:
    """A live transaction (or savepoint) on one connection."""

    def __init__(self, db: "Database", conn: Any, *, readonly: bool) -> None:
        self.db = db
        self.conn = conn
        self.dialect: Dialect = db.dialect
        self.readonly = readonly
        self.thread_id = threading.get_ident()
        self._sp = 0

    @property
    def for_update(self) -> str:
        return self.dialect.for_update

    def json(self, obj: Any) -> Any:
        return self.dialect.json(obj)

    def unjson(self, val: Any) -> Any:
        return self.dialect.unjson(val)

    def execute(self, sql: str, params: tuple | list = ()) -> Any:
        if self.db.readonly and not self._is_read(sql):
            raise StorageReadOnly(
                "BOARDMAN_STORAGE=json serves the legacy files read-only — "
                "run scripts/migrate_json_to_db.py and switch to BOARDMAN_STORAGE=db"
            )
        return self.db.run(self.conn, self.dialect.sql(sql), tuple(params))

    @staticmethod
    def _is_read(sql: str) -> bool:
        head = sql.lstrip().split(None, 1)[0].upper() if sql.strip() else ""
        return head in {"SELECT", "WITH", "SAVEPOINT", "RELEASE", "ROLLBACK"}

    def one(self, sql: str, params: tuple | list = ()) -> Optional[dict[str, Any]]:
        cur = self.execute(sql, params)
        row = cur.fetchone()
        return self.db.row(cur, row) if row is not None else None

    def all(self, sql: str, params: tuple | list = ()) -> list[dict[str, Any]]:
        cur = self.execute(sql, params)
        return [self.db.row(cur, r) for r in cur.fetchall()]

    def scalar(self, sql: str, params: tuple | list = ()) -> Any:
        cur = self.execute(sql, params)
        row = cur.fetchone()
        if row is None:
            return None
        if isinstance(row, dict):
            return next(iter(row.values()))
        return row[0]

    def rowcount(self, sql: str, params: tuple | list = ()) -> int:
        cur = self.execute(sql, params)
        return int(cur.rowcount or 0)


_CURRENT: contextvars.ContextVar[Optional[Tx]] = contextvars.ContextVar(
    "boardman_current_tx", default=None
)


def current_tx(db: Optional["Database"] = None) -> Optional[Tx]:
    tx = _CURRENT.get()
    if tx is None or tx.thread_id != threading.get_ident():
        # A context copied into another thread (asyncio.to_thread) must never
        # reuse this thread's connection.
        return None
    if db is not None and tx.db is not db:
        return None
    return tx


# ── database ─────────────────────────────────────────────────────────────────


class _ConnHolder:
    """One thread's connection; closed when the thread (and its locals) go away.

    Short-lived threads (payout DMs, book-close txs) would otherwise leave a
    connection open per thread for the life of the process.
    """

    __slots__ = ("conn", "closed", "pid", "__weakref__")

    def __init__(self, conn: Any) -> None:
        self.conn = conn
        self.closed = False
        self.pid = os.getpid()

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        if self.pid != os.getpid():
            return  # inherited across fork: not ours to close
        try:
            self.conn.close()
        except Exception:
            pass

    def __del__(self) -> None:  # pragma: no cover - GC timing
        self.close()



class Database:
    """One configured store. Connections are per thread."""

    def __init__(self, key: str, *, url: str = "", sqlite_path: Optional[Path] = None,
                 readonly: bool = False, check_migrated: bool = True) -> None:
        self.key = key
        self.check_migrated = check_migrated
        self.url = url
        self.sqlite_path = sqlite_path
        self.readonly = readonly
        self.dialect: Dialect = PostgresDialect() if is_postgres_url(url) else SQLiteDialect()
        self._local = threading.local()
        self._holders: "weakref.WeakSet[_ConnHolder]" = weakref.WeakSet()
        self._conns_lock = threading.Lock()
        self._schema_lock = threading.Lock()
        self._schema_ready = False
        self._pid = os.getpid()
        self.closed = False

    # -- connections --

    @property
    def is_postgres(self) -> bool:
        return self.dialect.name == "postgres"

    def _new_connection(self) -> Any:
        if self.is_postgres:
            try:
                import psycopg  # type: ignore
                from psycopg.rows import dict_row  # type: ignore
            except ImportError as exc:  # pragma: no cover - env specific
                raise StorageError(
                    "DATABASE_URL is Postgres but psycopg is not installed — "
                    "pip install 'psycopg[binary]' (see src/backend/requirements.txt)"
                ) from exc
            # prepare_threshold=None: no server-side prepared statements, so a
            # Supabase pooler URL (pgbouncer, transaction mode) works too.
            conn = psycopg.connect(
                self.url, autocommit=True, row_factory=dict_row, prepare_threshold=None
            )
            return conn
        assert self.sqlite_path is not None
        self.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(
            str(self.sqlite_path),
            timeout=30.0,
            isolation_level=None,  # we issue BEGIN/COMMIT ourselves
            check_same_thread=False,
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout=30000")
        if not self.readonly:
            try:
                conn.execute("PRAGMA journal_mode=WAL")
            except sqlite3.OperationalError:
                pass
            conn.execute("PRAGMA synchronous=NORMAL")
        else:
            conn.execute("PRAGMA query_only=ON")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def connection(self) -> Any:
        if self.closed:
            raise StorageError("database handle closed")
        if self._pid != os.getpid():
            # Forked child: never touch the parent's connections (SQLite and
            # libpq handles are not fork-safe). Abandon them without closing
            # (each holder only closes in the process that opened it).
            self._local = threading.local()
            with self._conns_lock:
                self._holders = weakref.WeakSet()
            self._pid = os.getpid()
        holder = getattr(self._local, "holder", None)
        if holder is None or holder.closed:
            holder = _ConnHolder(self._new_connection())
            self._local.holder = holder
            with self._conns_lock:
                self._holders.add(holder)
        if not self._schema_ready:
            # Re-checked on every call until it passes: a refused start (e.g.
            # never migrated) must keep refusing, not slip through on retry.
            self._ensure_schema(holder.conn)
        return holder.conn

    def _ensure_schema(self, conn: Any) -> None:
        if self._schema_ready:
            return
        with self._schema_lock:
            if self._schema_ready:
                return
            if not self.readonly:
                from gaming.src.stack.agentic.db.schema import ensure_schema

                ensure_schema(self, conn)
                if self.check_migrated:
                    self._check_migrated(conn)
            self._schema_ready = True

    def _check_migrated(self, conn: Any) -> None:
        """Fail closed when legacy JSON sits next to a never-imported database.

        Deploying this code before running scripts/migrate_json_to_db.py would
        otherwise start every wallet at zero. Override (for a deliberate fresh
        start) with BOARDMAN_STORAGE_ALLOW_UNMIGRATED=1.
        """
        if (os.getenv("BOARDMAN_STORAGE_ALLOW_UNMIGRATED") or "").strip() == "1":
            return
        try:
            legacy_dir = _data_dir()
        except Exception:
            return
        present = [
            n for n in LEGACY_FILES
            if (legacy_dir / n).is_file() and (legacy_dir / n).stat().st_size > 2
        ]
        if not present:
            return
        sql = self.dialect.sql("SELECT value FROM storage_meta WHERE key = ?")
        row = conn.execute(sql, ("legacy_import",)).fetchone()
        if row is not None:
            return
        raise StorageNotMigrated(
            f"legacy JSON {present} in {legacy_dir} was never imported into the "
            "database. Stop the API and house session, run "
            "`python scripts/migrate_json_to_db.py --apply`, then restart "
            "(or set BOARDMAN_STORAGE=json for read-only legacy mode)."
        )

    def close_all(self) -> None:
        self.closed = True
        with self._conns_lock:
            holders = list(self._holders)
            self._holders = weakref.WeakSet()
        for h in holders:
            h.close()

    # -- execution helpers --

    def run(self, conn: Any, sql: str, params: tuple) -> Any:
        if self.is_postgres:
            return conn.execute(sql, params)
        return conn.execute(sql, params)

    @staticmethod
    def row(cur: Any, row: Any) -> dict[str, Any]:
        if isinstance(row, dict):
            return row
        if isinstance(row, sqlite3.Row):
            return {k: row[k] for k in row.keys()}
        cols = [d[0] for d in (cur.description or [])]
        return dict(zip(cols, row))

    def _begin(self, conn: Any, readonly: bool) -> None:
        if self.is_postgres:
            conn.execute("BEGIN")
        elif readonly:
            conn.execute("BEGIN")
        else:
            # Take the write lock up front: read-modify-write inside the
            # transaction is then serialized across threads AND processes.
            conn.execute("BEGIN IMMEDIATE")

    @contextmanager
    def transaction(self, *, readonly: bool = False) -> Iterator[Tx]:
        outer = current_tx(self)
        if outer is not None:
            outer._sp += 1
            name = f"sp_{outer._sp}"
            outer.conn.execute(f"SAVEPOINT {name}")
            try:
                yield outer
            except BaseException:
                try:
                    outer.conn.execute(f"ROLLBACK TO SAVEPOINT {name}")
                    outer.conn.execute(f"RELEASE SAVEPOINT {name}")
                except Exception:
                    logger.debug("[storage] savepoint rollback failed", exc_info=True)
                raise
            else:
                outer.conn.execute(f"RELEASE SAVEPOINT {name}")
            return

        conn = self.connection()
        ro = readonly or self.readonly
        self._begin(conn, ro)
        tx = Tx(self, conn, readonly=ro)
        token = _CURRENT.set(tx)
        try:
            yield tx
        except BaseException:
            try:
                conn.execute("ROLLBACK")
            except Exception:
                logger.debug("[storage] rollback failed", exc_info=True)
            raise
        else:
            conn.execute("COMMIT")
        finally:
            _CURRENT.reset(token)


# ── registry of open databases ───────────────────────────────────────────────

_DBS: "OrderedDict[str, Database]" = OrderedDict()
_DBS_LOCK = threading.Lock()


def _resolve() -> tuple[str, dict[str, Any]]:
    mode = storage_mode()
    if mode == "json":
        legacy_dir = _data_dir()
        return f"json:{legacy_dir}", {"legacy_dir": legacy_dir}
    url = database_url()
    if is_postgres_url(url):
        return f"pg:{url}", {"url": url}
    if url and not url.startswith("sqlite:"):
        raise StorageError(
            "DATABASE_URL must be postgres://, postgresql:// or sqlite:/// "
            "(set BOARDMAN_DATABASE_URL to override for the agentic store)"
        )
    path = sqlite_path_from_url(url) if url else _data_dir() / DB_FILENAME
    return f"sqlite:{path}", {"sqlite_path": path}


def get_db() -> Database:
    key, spec = _resolve()
    with _DBS_LOCK:
        db = _DBS.get(key)
        if db is not None and not db.closed:
            _DBS.move_to_end(key)
            return db
    if "legacy_dir" in spec:
        from gaming.src.stack.agentic.db.legacy import open_readonly_legacy

        db = open_readonly_legacy(key, spec["legacy_dir"])
    elif "url" in spec:
        db = Database(key, url=spec["url"])
    else:
        db = Database(key, sqlite_path=spec["sqlite_path"])
    with _DBS_LOCK:
        existing = _DBS.get(key)
        if existing is not None and not existing.closed:
            return existing
        _DBS[key] = db
        while len(_DBS) > MAX_OPEN_DATABASES:
            _, old = _DBS.popitem(last=False)
            old.close_all()
    return db


def reset_databases() -> None:
    """Close every cached handle (tests, ops scripts)."""
    with _DBS_LOCK:
        dbs = list(_DBS.values())
        _DBS.clear()
    for db in dbs:
        db.close_all()


@contextmanager
def transaction(*, readonly: bool = False) -> Iterator[Tx]:
    db = get_db()
    outer = current_tx()
    if outer is not None and outer.db is not db:
        # Store switched underneath an open transaction (a test changed the
        # data dir): keep using the open one rather than splitting the work.
        db = outer.db
    with db.transaction(readonly=readonly) as tx:
        yield tx


def now_ms() -> int:
    return int(time.time() * 1000)
