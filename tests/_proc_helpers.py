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


def proc_credit(data_dir: str, wallet: str, n: int) -> None:
    _install_aliases()
    os.environ["BOARDMAN_AGENTIC_DATA"] = data_dir
    from gaming.src.stack.agentic import ledger as L

    for _ in range(n):
        L.credit(wallet, Decimal("0.5"), reason="proc")
        try:
            L.debit(wallet, Decimal("0.25"), reason="proc")
        except ValueError:
            pass


def bump(data_dir: str, n: int) -> None:
    _install_aliases()
    os.environ["BOARDMAN_AGENTIC_DATA"] = data_dir
    from gaming.src.stack.agentic import store as s

    for _ in range(n):
        s.update_json("counter.json", lambda cur: {"n": int((cur or {}).get("n", 0)) + 1}, {})
