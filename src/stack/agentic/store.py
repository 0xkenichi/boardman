"""Agentic file store under data/agentic/ + the bridge to the database.

Money state (ledger, matches, spectator books, LP pools) lives in the agentic
database (see ``gaming.src.stack.agentic.db``). Code that still calls
``load_json("matches.json")`` / ``save_json("matches.json", ...)`` is routed
there transparently: a load returns the same shape the hot file had, and a save
writes back only the records (and top-level fields) the caller changed.

Everything else (agents, schedule, AFM state, caches) stays a JSON file. For
those this module now:

* never hands back the default for a *corrupt* file without first copying the
  bad file aside (``<name>.corrupt-<ts>``) — a parse error used to turn into an
  empty dict and the next save wiped the data;
* removes its temp file when a write fails (no more orphaned ``*.tmp``) and
  sweeps stale ones (``cleanup_orphan_tmp``);
* offers ``update_json(name, fn)``: read-modify-write under an exclusive
  cross-process file lock, so the API and the house session cannot lose each
  other's writes.
"""
from __future__ import annotations

import contextlib
import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Any, Callable, Iterator

logger = logging.getLogger(__name__)

_lock = threading.RLock()

# Legacy file name -> handled by the database.
DB_BACKED = frozenset(
    {
        "ledger.json",
        "matches.json",
        "matches_archive.json",
        "spectator_books.json",
        "spectator_books_archive.json",
        "agent_lp_pools.json",
    }
)
TMP_MAX_AGE_SEC = 3600


def data_dir() -> Path:
    env = os.getenv("BOARDMAN_AGENTIC_DATA")
    if env:
        p = Path(env)
    else:
        # repo_root/data/agentic — works from monorepo or gaming/ layout
        here = Path(__file__).resolve()
        # .../src/stack/agentic/store.py → repo root is parents[3]
        root = here.parents[3]
        p = root / "data" / "agentic"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _path(name: str) -> Path:
    return data_dir() / name


def _db_backed(name: str) -> bool:
    return name in DB_BACKED


# ── corrupt-file handling ────────────────────────────────────────────────────


def _quarantine(path: Path, exc: Exception) -> None:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    dest = path.with_name(f"{path.name}.corrupt-{stamp}")
    try:
        if not dest.exists():
            dest.write_bytes(path.read_bytes())
        logger.error("[store] %s is unreadable (%s) — copied to %s", path.name, exc, dest.name)
    except OSError:
        logger.error("[store] %s is unreadable (%s) and could not be copied aside", path.name, exc)


def _read(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        logger.error("[store] cannot read %s: %s", path.name, exc)
        return default
    if not text.strip():
        return default
    try:
        return json.loads(text)
    except ValueError as exc:
        _quarantine(path, exc)
        return default


def load_json(name: str, default: Any) -> Any:
    if _db_backed(name):
        from gaming.src.stack.agentic import store_compat

        return store_compat.load(name, default)
    with _lock:
        return _read(_path(name), default)


def _write(path: Path, payload: Any, *, compact: bool) -> None:
    if compact:
        text = json.dumps(payload, separators=(",", ":"), default=str)
    else:
        text = json.dumps(payload, indent=2, default=str) + "\n"
    # A tmp name unique to this process+thread: two writers sharing one tmp
    # race each other's atomic replace. Removed on any failure.
    tmp = path.with_name(f"{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    try:
        tmp.write_text(text, encoding="utf-8")
        tmp.replace(path)
    finally:
        with contextlib.suppress(FileNotFoundError):
            tmp.unlink()


def save_json(name: str, payload: Any, *, compact: bool = False) -> None:
    if _db_backed(name):
        from gaming.src.stack.agentic import store_compat

        store_compat.save(name, payload)
        return
    path = _path(name)
    with _lock:
        _write(path, payload, compact=compact)


@contextlib.contextmanager
def _file_lock(name: str) -> Iterator[None]:
    """Exclusive lock shared by every process using this data dir."""
    lock_path = _path(f".{name}.lock")
    with _lock:
        fh = open(lock_path, "a+")
        try:
            try:
                import fcntl

                fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
            except ImportError:  # pragma: no cover - non-POSIX
                pass
            yield
        finally:
            fh.close()  # releases the flock


def update_json(name: str, fn: Callable[[Any], Any], default: Any, *, compact: bool = False) -> Any:
    """Atomic read-modify-write of a JSON file across processes.

    ``fn(current)`` returns the new payload (or mutates and returns it).
    """
    if _db_backed(name):
        raise ValueError(f"{name} is database-backed; use its service API")
    path = _path(name)
    with _file_lock(name):
        cur = _read(path, default)
        new = fn(cur)
        if new is None:
            new = cur
        _write(path, new, compact=compact)
        return new


def cleanup_orphan_tmp(max_age_sec: float = TMP_MAX_AGE_SEC) -> list[str]:
    """Delete ``*.tmp`` leftovers from crashed writers older than ``max_age_sec``."""
    removed: list[str] = []
    cutoff = time.time() - max_age_sec
    for p in data_dir().glob("*.tmp"):
        try:
            if p.stat().st_mtime < cutoff:
                p.unlink()
                removed.append(p.name)
        except OSError:
            continue
    if removed:
        logger.info("[store] removed %d orphaned tmp files", len(removed))
    return removed
