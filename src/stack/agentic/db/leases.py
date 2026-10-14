"""Per-match leases: exactly one process plays or settles a table.

A lease row ``(match_id, owner, epoch, expires_at_ms)`` lives in the shared
database, so the API process, the house session and any extra replica all see
it. The holder renews it from a heartbeat thread; another process may take it
over only once it has expired (the holder crashed or hung). Every settlement
step re-checks the lease *inside* its own transaction (``assert_held``), so a
worker that lost its lease mid-game cannot move money.

The owner id is per process (host:pid:random). Inside one process the match
service's ``_RUNNING`` set still stops two threads driving one table; leases are
reference-counted so nested ``hold()`` calls (house worker -> run_match ->
settle) share one lease.
"""
from __future__ import annotations

import logging
import os
import socket
import threading
import uuid
from contextlib import contextmanager
from typing import Any, Iterator, Optional

from gaming.src.stack.agentic.db.engine import Tx, get_db, now_ms, transaction

logger = logging.getLogger(__name__)

DEFAULT_TTL_SEC = 90.0


class LeaseBusy(RuntimeError):
    """Another live owner holds this match."""


class LeaseLost(RuntimeError):
    """This process no longer holds the lease it was working under."""


_owner_lock = threading.Lock()
_owner: tuple[int, str] = (0, "")


def process_owner() -> str:
    """Stable for the life of this process; regenerated after fork."""
    global _owner
    pid = os.getpid()
    with _owner_lock:
        if _owner[0] != pid:
            _owner = (pid, f"{socket.gethostname()}:{pid}:{uuid.uuid4().hex[:8]}")
        return _owner[1]


def lease_ttl_ms() -> int:
    try:
        sec = float(os.getenv("BOARDMAN_LEASE_TTL_SEC") or DEFAULT_TTL_SEC)
    except ValueError:
        sec = DEFAULT_TTL_SEC
    return int(max(5.0, min(sec, 3600.0)) * 1000)


# (db key, match_id) -> refcount held by this process
_held: dict[tuple[str, str], int] = {}
_held_lock = threading.RLock()
_hb_thread: Optional[threading.Thread] = None
_hb_stop = threading.Event()


def _row(tx: Tx, match_id: str) -> Optional[dict[str, Any]]:
    return tx.one(
        "SELECT match_id, owner, epoch, acquired_at_ms, heartbeat_at_ms, expires_at_ms "
        f"FROM match_leases WHERE match_id = ?{tx.for_update}",
        (match_id,),
    )


def _insert_new(tx: Tx, match_id: str, owner: str, now: int, ttl: int) -> bool:
    """Create the lease row unless one appeared meanwhile.

    ``FOR UPDATE`` cannot lock a missing row, so two processes can both miss
    it; ``ON CONFLICT DO NOTHING`` makes the loser wait for the winner's
    commit and then see 0 rows instead of aborting on a unique violation.
    """
    return tx.rowcount(
        "INSERT INTO match_leases (match_id, owner, epoch, acquired_at_ms, "
        "heartbeat_at_ms, expires_at_ms) VALUES (?, ?, 1, ?, ?, ?) "
        "ON CONFLICT (match_id) DO NOTHING",
        (match_id, owner, now, now, now + ttl),
    ) == 1


def try_acquire(match_id: str, *, owner: Optional[str] = None) -> Optional[dict[str, Any]]:
    """Take or renew the lease. Returns the lease row, or None if someone else holds it."""
    me = owner or process_owner()
    ttl = lease_ttl_ms()
    with transaction() as tx:
        now = now_ms()
        row = _row(tx, match_id)
        if row is None:
            if _insert_new(tx, match_id, me, now, ttl):
                return {"match_id": match_id, "owner": me, "epoch": 1, "expires_at_ms": now + ttl, "taken_over": False}
            row = _row(tx, match_id)  # a concurrent creator won: judge its row
            if row is None:  # created and already released again
                return None
        if row["owner"] == me:
            tx.execute(
                "UPDATE match_leases SET heartbeat_at_ms = ?, expires_at_ms = ? WHERE match_id = ?",
                (now, now + ttl, match_id),
            )
            row.update(heartbeat_at_ms=now, expires_at_ms=now + ttl, taken_over=False)
            return row
        if int(row["expires_at_ms"]) > now:
            return None
        epoch = int(row["epoch"]) + 1
        tx.execute(
            "UPDATE match_leases SET owner = ?, epoch = ?, acquired_at_ms = ?, "
            "heartbeat_at_ms = ?, expires_at_ms = ? WHERE match_id = ?",
            (me, epoch, now, now, now + ttl, match_id),
        )
        logger.warning(
            "[lease] %s taken over from %s (expired %dms ago), epoch %d",
            match_id, row["owner"], now - int(row["expires_at_ms"]), epoch,
        )
        return {"match_id": match_id, "owner": me, "epoch": epoch, "expires_at_ms": now + ttl, "taken_over": True}


def acquire(match_id: str) -> dict[str, Any]:
    """Reference-counted acquire for this process. Raises LeaseBusy."""
    db = get_db()
    k = (db.key, match_id)
    row = try_acquire(match_id)
    if row is None:
        holder = state(match_id) or {}
        raise LeaseBusy(f"match {match_id} is leased by {holder.get('owner')}")
    with _held_lock:
        _held[k] = _held.get(k, 0) + 1
    _ensure_heartbeat()
    return row


def release(match_id: str) -> None:
    db = get_db()
    k = (db.key, match_id)
    with _held_lock:
        n = _held.get(k, 0) - 1
        if n > 0:
            _held[k] = n
            return
        _held.pop(k, None)
    try:
        with transaction() as tx:
            tx.execute(
                "DELETE FROM match_leases WHERE match_id = ? AND owner = ?",
                (match_id, process_owner()),
            )
    except Exception:
        logger.warning("[lease] release %s failed (expires on its own)", match_id, exc_info=True)


@contextmanager
def hold(match_id: str) -> Iterator[dict[str, Any]]:
    row = acquire(match_id)
    try:
        yield row
    finally:
        release(match_id)


def held_here(match_id: str) -> bool:
    try:
        k = (get_db().key, match_id)
    except Exception:
        return False
    with _held_lock:
        return _held.get(k, 0) > 0


def state(match_id: str) -> Optional[dict[str, Any]]:
    with transaction(readonly=True) as tx:
        return tx.one(
            "SELECT match_id, owner, epoch, acquired_at_ms, heartbeat_at_ms, expires_at_ms "
            "FROM match_leases WHERE match_id = ?",
            (match_id,),
        )


def active_holder(match_id: str) -> Optional[str]:
    """Owner of an unexpired lease on this match, or None if it is free/expired."""
    row = state(match_id)
    if row is None or int(row["expires_at_ms"]) <= now_ms():
        return None
    return str(row["owner"])


def assert_held(tx: Tx, match_id: str) -> None:
    """Fencing check for a money step, inside the step's own transaction.

    Locks the lease row (Postgres) so a takeover cannot interleave with the
    step; a step whose lease went to another owner refuses to run.
    """
    row = _row(tx, match_id)
    me = process_owner()
    if row is None:
        # Released or never taken (direct ops call): claim it for this step.
        if _insert_new(tx, match_id, me, now_ms(), lease_ttl_ms()):
            return
        row = _row(tx, match_id)
        if row is None:
            raise LeaseLost(f"match {match_id} lease changed hands mid-step; retry")
    if row["owner"] != me:
        if int(row["expires_at_ms"]) > now_ms():
            raise LeaseLost(f"match {match_id} lease belongs to {row['owner']}")
        # Expired foreign lease: take it within this transaction.
        now = now_ms()
        tx.execute(
            "UPDATE match_leases SET owner = ?, epoch = epoch + 1, acquired_at_ms = ?, "
            "heartbeat_at_ms = ?, expires_at_ms = ? WHERE match_id = ?",
            (me, now, now, now + lease_ttl_ms(), match_id),
        )


def renew_held() -> list[str]:
    """Heartbeat: renew every lease this process holds. Returns any it lost."""
    with _held_lock:
        items = list(_held.keys())
    lost: list[str] = []
    current = None
    try:
        current = get_db().key
    except Exception:
        return lost
    for db_key, match_id in items:
        if db_key != current:
            continue  # store switched (tests); that lease is not ours to touch
        try:
            if try_acquire(match_id) is None:
                lost.append(match_id)
        except Exception:
            logger.warning("[lease] heartbeat %s failed", match_id, exc_info=True)
    for mid in lost:
        logger.error("[lease] lost %s to another owner", mid)
    return lost


def _heartbeat_loop() -> None:
    while not _hb_stop.wait(max(1.0, lease_ttl_ms() / 3000.0)):
        try:
            renew_held()
        except Exception:
            logger.warning("[lease] heartbeat loop error", exc_info=True)


def _ensure_heartbeat() -> None:
    global _hb_thread
    with _held_lock:
        if _hb_thread is not None and _hb_thread.is_alive():
            return
        _hb_stop.clear()
        _hb_thread = threading.Thread(target=_heartbeat_loop, name="lease-heartbeat", daemon=True)
        _hb_thread.start()


def forget_local_state() -> None:
    """Drop this process's in-memory lease bookkeeping (tests simulating a crash)."""
    with _held_lock:
        _held.clear()
