"""Worker functions for the cross-process storage tests.

They run in *spawned* interpreters, not forked ones: forking pytest while its
background threads hold locks can deadlock the child (and multiprocessing's
exit hook then waits on it forever). Spawned children start clean, which is
also what production looks like — the API and the house session are separate
programs. conftest.py does not run in the child, so this module installs the
same `gaming` / `backend` import aliases before touching app code.
"""
from __future__ import annotations

import os
import sys
import types
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _install_aliases() -> None:
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    for name, target in (("gaming", ROOT), ("backend", ROOT / "src" / "backend")):
        if (ROOT / name).exists() or name in sys.modules:
            continue
        alias = types.ModuleType(name)
        alias.__path__ = [str(target)]  # type: ignore[attr-defined]
        alias.__file__ = str(target / "__init__.py")
        sys.modules[name] = alias


def _use_store(data_dir: str) -> None:
    """The parent test's store for ``data_dir``: its SQLite file, or its
    Postgres schema when BOARDMAN_TEST_DATABASE_URL is on (tests/_pgtest.py)."""
    _install_aliases()
    os.environ["BOARDMAN_AGENTIC_DATA"] = data_dir
    from tests._pgtest import use_in_child

    use_in_child(data_dir)


def proc_credit(data_dir: str, wallet: str, n: int) -> None:
    _use_store(data_dir)
    from gaming.src.stack.agentic import ledger as L

    for _ in range(n):
        L.credit(wallet, Decimal("0.5"), reason="proc")
        try:
            L.debit(wallet, Decimal("0.25"), reason="proc")
        except ValueError:
            pass


def bump(data_dir: str, n: int) -> None:
    _use_store(data_dir)
    from gaming.src.stack.agentic import store as s

    for _ in range(n):
        s.update_json("counter.json", lambda cur: {"n": int((cur or {}).get("n", 0)) + 1}, {})


def _die_now() -> None:
    """kill -9 ourselves: no finally blocks, no atexit, no lease release."""
    import signal

    os.kill(os.getpid(), signal.SIGKILL)


def proc_lock_then_die(data_dir: str, match_id: str) -> None:
    """The house session locks a table and is killed during its bet window."""
    _use_store(data_dir)
    from gaming.src.stack.agentic.db import leases
    from gaming.src.stack.agentic.house import get_house

    leases.acquire(match_id)  # what rematch(wait=True) holds across the window
    get_house().lock(match_id)
    _die_now()


def proc_settle_then_die(data_dir: str, match_id: str, result: dict, crash_step: str) -> None:
    """Settle a table and get killed right after one journaled step commits."""
    _use_store(data_dir)
    from gaming.src.stack.agentic import matches

    matches._notify_spectator_outcomes = lambda *a, **k: None
    matches._SETTLE_STEP_HOOK = lambda step: _die_now() if step == crash_step else None
    matches.get_match_service().settle_result(match_id, result)
    raise SystemExit(3)  # never reached when crash_step is a real step
