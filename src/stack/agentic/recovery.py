"""Crash recovery for house tables: no table stays stuck after a kill -9.

A worker that dies (redeploy, OOM, kill -9) leaves its table mid-flight:
``open``/``locking`` (stakes being locked), ``locked`` (bet window),
``playing``, ``settling``, ``aborting``, or ``error`` with the stakes still
locked. Its match lease stops being renewed and expires
(``BOARDMAN_LEASE_TTL_SEC``, default 90s). This module finds those tables and
finishes them, exactly once:

* ``settling``  -> resume settlement from its journal (``run_match``).
* ``locked`` / ``playing`` whose game can be rebuilt exactly — chess moves
  that all replay legally from the stored list, or any game with no move yet —
  -> resume it on a table worker; it settles through the journal.
* everything else (lock never completed, game not resumable, escrow not
  locked, a failed ``error`` table, a refund already under way)
  -> ``house.abort_table(reason="interrupted")``: journaled full refund of
  both stakes, the spectator book and the agents' seeds.

The rule for touching a table at all: no live lease (missing, or expired),
not driven by a thread of this process, and — when there is no lease row at
all — quiet for a grace period, because a few legitimate steps (a manual
open -> lock through the API) run without one. A fresh lease is never taken
over; the workers re-acquire the lease atomically, so two processes running
recovery at once still give one driver per table, and the settlement / abort
journals make every money step happen once.

Runs at house-session start, every ``BOARDMAN_RECOVERY_INTERVAL_SEC`` from a
background thread, from the floor view, and on demand from
``scripts/recover_interrupted_tables.py``.
"""
from __future__ import annotations

import logging
import os
import threading
from concurrent.futures import Future
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable, Optional

logger = logging.getLogger(__name__)

# Tables a dead worker can leave behind without a result.
CANDIDATE_STATUSES = ("open", "locking", "partial_lock", "locked", "playing", "settling", "aborting", "error")
CHESS = "agentic.chess_standard"

DEFAULT_GRACE_SEC = 120.0
DEFAULT_OPEN_GRACE_SEC = 900.0
DEFAULT_INTERVAL_SEC = 30.0
DEFAULT_RETRY_BASE_SEC = 2.0
DEFAULT_RETRY_CAP_SEC = 120.0


def _env_float(name: str, default: float, lo: float, hi: float) -> float:
    try:
        v = float(os.getenv(name) or default)
    except ValueError:
        v = default
    return max(lo, min(v, hi))


def grace_sec() -> float:
    """How long a lease-less table must sit untouched before it is an orphan."""
    return _env_float("BOARDMAN_RECOVERY_GRACE_SEC", DEFAULT_GRACE_SEC, 0.0, 86400.0)


def open_grace_sec() -> float:
    """Same for ``open`` tables: the API's open -> lock may be minutes apart."""
    return _env_float("BOARDMAN_RECOVERY_OPEN_GRACE_SEC", DEFAULT_OPEN_GRACE_SEC, 0.0, 86400.0)


def interval_sec() -> float:
    return _env_float("BOARDMAN_RECOVERY_INTERVAL_SEC", DEFAULT_INTERVAL_SEC, 1.0, 3600.0)


def retry_delay(failures: int, *, base: Optional[float] = None, cap: Optional[float] = None) -> float:
    """Exponential backoff for the house session's failed-open loop.

    ``failures`` counts consecutive failures (1 = the first): base, 2*base,
    4*base, ... capped. Defaults 2s doubling to a 120s cap
    (``BOARDMAN_HOUSE_RETRY_BASE_SEC`` / ``BOARDMAN_HOUSE_RETRY_CAP_SEC``).
    """
    b = base if base is not None else _env_float("BOARDMAN_HOUSE_RETRY_BASE_SEC", DEFAULT_RETRY_BASE_SEC, 0.1, 600.0)
    c = cap if cap is not None else _env_float("BOARDMAN_HOUSE_RETRY_CAP_SEC", DEFAULT_RETRY_CAP_SEC, 1.0, 3600.0)
    n = max(1, int(failures))
    return float(min(c, b * (2 ** min(n - 1, 30))))


# ── classification ──────────────────────────────────────────────────────────


@dataclass
class Plan:
    match_id: str
    status: str
    action: str  # skip | resume | resume_settlement | abort
    why: str
    agents: tuple[str, str] = ("", "")
    game_id: str = CHESS
    moves: int = 0
    lease: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["agents"] = list(self.agents)
        return d


def _parse_ts(raw: Any) -> Optional[datetime]:
    s = str(raw or "").strip()
    if not s:
        return None
    try:
        t = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def _age_sec(m: dict[str, Any], now: datetime) -> Optional[float]:
    t = _parse_ts(m.get("updated_at")) or _parse_ts(m.get("created_at"))
    return None if t is None else (now - t).total_seconds()


def replayable(m: dict[str, Any]) -> tuple[bool, str]:
    """Can this table's game be rebuilt exactly from what was stored?"""
    game_id = str(m.get("game_id") or CHESS)
    moves = list(m.get("moves") or [])
    if not moves:
        return True, "no move played yet — the game starts from the beginning"
    if game_id != CHESS:
        return False, f"{game_id} cannot resume mid-game ({len(moves)} moves stored)"
    from gaming.src.stack.agentic.chess.arena import _replay_prior

    _board, _game, _node, events = _replay_prior(moves)
    if len(events) != len(moves):
        return False, f"stored moves do not replay ({len(events)}/{len(moves)} legal)"
    return True, f"position rebuilt from {len(moves)} stored moves"


def _local_ids() -> set[str]:
    from gaming.src.stack.agentic import house
    from gaming.src.stack.agentic.matches import _RUNNING, _RUNNING_LOCK

    with house._floor_lock:
        ids = set(house._workers)
    with _RUNNING_LOCK:
        ids |= set(_RUNNING)
    return ids


def plan_table(m: dict[str, Any], *, now: Optional[datetime] = None, local: Optional[set[str]] = None) -> Plan:
    """Decide what recovery does with one table (no side effects)."""
    from gaming.src.stack.agentic import ledger
    from gaming.src.stack.agentic.db import leases
    from gaming.src.stack.agentic.db.engine import now_ms

    now = now or datetime.now(timezone.utc)
    mid = str(m.get("match_id") or "")
    st = str(m.get("status") or "")
    plan = Plan(
        match_id=mid,
        status=st,
        action="skip",
        why="",
        agents=(str(m.get("agent_a_id") or ""), str(m.get("agent_b_id") or "")),
        game_id=str(m.get("game_id") or CHESS),
        moves=len(m.get("moves") or []),
    )
    if st not in CANDIDATE_STATUSES:
        plan.why = f"status {st} is not recoverable"
        return plan
    if m.get("result"):
        plan.why = "has a result"
        return plan
    local = _local_ids() if local is None else local
    if mid in local or leases.held_here(mid):
        plan.why = "driven by this process"
        return plan
    row = leases.state(mid)
    if row is not None:
        left = int(row["expires_at_ms"]) - now_ms()
        if left > 0:
            plan.why = f"lease held by {row['owner']} ({left // 1000}s left)"
            plan.lease = str(row["owner"])
            return plan
        plan.lease = f"{row['owner']} (expired {-left // 1000}s ago)"
    else:
        age = _age_sec(m, now)
        g = open_grace_sec() if st == "open" else grace_sec()
        if age is not None and age < g:
            plan.why = f"no lease, touched {age:.0f}s ago (< {g:.0f}s grace)"
            return plan
        plan.lease = "none"

    if st == "settling":
        plan.action, plan.why = "resume_settlement", "settlement resumes from its journal"
        return plan
    if st == "aborting":
        plan.action, plan.why = "abort", "refund resumes from its journal"
        return plan
    if st in {"open", "locking", "partial_lock"}:
        plan.action, plan.why = "abort", "stakes never finished locking"
        return plan
    esc = ledger.get_escrow(mid) or {}
    if st == "error":
        if esc.get("status") == "locked":
            plan.action, plan.why = "abort", "worker failed with the stakes still locked"
        else:
            plan.why = "error table with nothing locked"
        return plan
    # locked / playing
    if esc.get("status") != "locked":
        plan.action, plan.why = "abort", f"escrow is {esc.get('status') or 'missing'}, not locked"
        return plan
    ok, why = replayable(m)
    plan.action, plan.why = ("resume" if ok else "abort"), why
    return plan


def candidates() -> list[dict[str, Any]]:
    """Full records of every table in a recoverable status (indexed query)."""
    from gaming.src.stack.agentic.db.tables import MATCHES

    marks = ",".join("?" for _ in CANDIDATE_STATUSES)
    return MATCHES.query(f"status IN ({marks})", CANDIDATE_STATUSES, order_by="updated_at")


def scan(*, agents: Optional[Iterable[str]] = None) -> list[Plan]:
    want = set(agents or ())
    now = datetime.now(timezone.utc)
    local = _local_ids()
    plans = []
    for m in candidates():
        if want and not want & {m.get("agent_a_id"), m.get("agent_b_id")}:
            continue
        try:
            plans.append(plan_table(m, now=now, local=local))
        except Exception as exc:
            logger.warning("[recovery] could not classify %s: %s", m.get("match_id"), exc, exc_info=True)
    return plans


# ── execution ───────────────────────────────────────────────────────────────


def _abort_worker(match_id: str) -> dict[str, Any]:
    from gaming.src.stack.agentic import house

    try:
        return house.abort_table(match_id, reason="interrupted")
    finally:
        with house._floor_lock:
            house._workers.pop(match_id, None)


def _seat(plan: Plan, *, inline: bool) -> dict[str, Any]:
    """Resume a table on a worker under a freshly taken lease."""
    from gaming.src.stack.agentic import house
    from gaming.src.stack.agentic.db.tables import MATCHES

    mid = plan.match_id
    out = {**plan.to_dict(), "submitted": False}
    with house._floor_lock:
        if mid in house._workers:
            return {**out, "why": "already driven by this process"}
        if not house._claim_table(mid):
            return {**out, "why": "lease taken by another worker meanwhile"}
        cur = MATCHES.get(mid) or {}
        if cur.get("status") != plan.status or cur.get("result"):
            house._release_table(mid)
            return {**out, "why": f"status moved to {cur.get('status')} meanwhile"}
        fn = house._run_table if plan.status in {"playing", "settling"} else house._lock_and_run
        delay = float(cur.get("play_delay_sec") or 0.05)
        seed = cur.get("play_seed")
        if inline:
            # Placeholder so no other thread here seats it while it runs.
            house._workers[mid] = Future()
        else:
            house._workers[mid] = house._executor().submit(fn, mid, delay, seed, True)
    logger.warning("[recovery] resuming %s (%s): %s", mid, plan.status, plan.why)
    if inline:
        fn(mid, delay, seed, True)  # pops _workers and releases the lease itself
        final = MATCHES.get(mid) or {}
        return {**out, "submitted": True, "final_status": final.get("status")}
    return {**out, "submitted": True}


def _abort(plan: Plan, *, inline: bool) -> dict[str, Any]:
    from gaming.src.stack.agentic import house

    mid = plan.match_id
    out = {**plan.to_dict(), "submitted": False}
    with house._floor_lock:
        if mid in house._workers:
            return {**out, "why": "already driven by this process"}
        if not inline:
            house._workers[mid] = house._executor().submit(_abort_worker, mid)
            return {**out, "submitted": True}
        house._workers[mid] = Future()
    logger.warning("[recovery] refunding %s (%s): %s", mid, plan.status, plan.why)
    res = _abort_worker(mid)
    return {**out, "submitted": True, "final_status": res.get("status")}


def recover_table(
    match_id: str,
    *,
    resume_inline: bool = False,
    abort_inline: bool = True,
    force_abort: bool = False,
    plan: Optional[Plan] = None,
) -> dict[str, Any]:
    """Recover one table if the expired-lease rule allows it.

    ``force_abort`` refunds instead of resuming a resumable game (ops choice);
    it never overrides the lease rule.
    """
    from gaming.src.stack.agentic.db.tables import MATCHES

    if plan is None:
        m = MATCHES.get(match_id)
        if not m:
            raise ValueError("match not found")
        plan = plan_table(m)
    if plan.action == "skip":
        return {**plan.to_dict(), "submitted": False}
    if force_abort and plan.action == "resume":
        plan.action, plan.why = "abort", f"ops chose refund over resume ({plan.why})"
    if plan.action in {"resume", "resume_settlement"}:
        return _seat(plan, inline=resume_inline)
    return _abort(plan, inline=abort_inline)


def recover_interrupted(
    *,
    agents: Optional[Iterable[str]] = None,
    resume_inline: bool = False,
    abort_inline: bool = True,
    dry_run: bool = False,
) -> list[dict[str, Any]]:
    """Find every interrupted table (optionally only those of ``agents``) and recover it.

    Resumed games run on the table pool unless ``resume_inline``; refunds run
    inline unless ``abort_inline`` is False (the floor view must not block on
    an on-chain cancel). ``dry_run`` only returns the plans, skips included.
    One table failing never stops the others.
    """
    from gaming.src.stack.agentic import house

    plans = scan(agents=agents)
    if dry_run:
        return [p.to_dict() for p in plans]
    out: list[dict[str, Any]] = []
    for p in plans:
        if p.action == "skip":
            continue
        try:
            out.append(recover_table(p.match_id, plan=p, resume_inline=resume_inline, abort_inline=abort_inline))
        except Exception as exc:
            logger.warning("[recovery] %s %s failed: %s", p.action, p.match_id, exc, exc_info=True)
            out.append({**p.to_dict(), "submitted": False, "error": f"{exc.__class__.__name__}: {exc}"})
    try:
        house._pump_queue()  # a restart leaves queued tables nobody would seat
    except Exception:
        logger.warning("[recovery] queue pump failed", exc_info=True)
    return out


# ── periodic sweep ──────────────────────────────────────────────────────────

_thread: Optional[threading.Thread] = None
_thread_lock = threading.Lock()
_stop = threading.Event()


def _loop(every: float) -> None:
    while not _stop.wait(every):
        try:
            done = recover_interrupted(abort_inline=True, resume_inline=False)
            for r in done:
                logger.warning("[recovery] %s %s -> %s", r.get("action"), r.get("match_id"),
                               r.get("error") or r.get("final_status") or ("submitted" if r.get("submitted") else r.get("why")))
        except Exception:
            logger.warning("[recovery] periodic sweep failed", exc_info=True)


def start_recovery_thread(every: Optional[float] = None) -> threading.Thread:
    """Start (once per process) the background sweep. Daemon: never pins exit."""
    global _thread
    with _thread_lock:
        if _thread is not None and _thread.is_alive():
            return _thread
        _stop.clear()
        _thread = threading.Thread(
            target=_loop, args=(every if every is not None else interval_sec(),),
            name="house-recovery", daemon=True,
        )
        _thread.start()
        return _thread


def stop_recovery_thread(timeout: float = 5.0) -> None:
    global _thread
    with _thread_lock:
        t = _thread
        _stop.set()
    if t is not None:
        t.join(timeout)
    with _thread_lock:
        _thread = None
