"""Guards for the hermetic harness in conftest.py.

Named ``test_zz_*`` so it runs last in a full run: the final test checks that
nothing earlier in the session wrote to the repo's ``data/`` directory.
"""
from __future__ import annotations

import ast
import os
import socket
from pathlib import Path

import pytest


def _inside(path: Path, parent: Path) -> bool:
    try:
        Path(os.path.realpath(path)).relative_to(os.path.realpath(parent))
        return True
    except ValueError:
        return False


def test_agentic_store_points_at_sandbox(hermetic):
    from gaming.src.stack.agentic.store import data_dir

    d = data_dir()
    assert not _inside(d, hermetic.root), d
    for protected in hermetic.protected_dirs:
        assert not _inside(d, protected), d


def test_import_time_paths_point_at_sandbox(hermetic):
    from gaming.src.backend.services import (
        fiat_topup,
        partners,
        stellar_watcher,
        tournament,
        wallet_activity,
    )

    paths = {
        "partners attributions": partners._ATTR_PATH,
        "partners ledger": partners._LEDGER_PATH,
        "tournaments": tournament._STORE_PATH,
        "wallet watch": wallet_activity._SNAPSHOT_PATH,
        "fiat top-ups": fiat_topup._store_path(),
        "stellar watch": stellar_watcher._state_path(),
    }
    for label, p in paths.items():
        assert _inside(p, hermetic.sandbox), f"{label} -> {p}"


def test_live_flags_are_off():
    from gaming.src.stack.agentic.onchain import onchain_enabled
    from gaming.src.stack.agentic.spectator_onchain import spectator_onchain_enabled

    assert onchain_enabled() is False
    assert spectator_onchain_enabled() is False


def test_dotenv_is_inert(tmp_path, monkeypatch):
    import dotenv

    env = tmp_path / ".env"
    env.write_text("HERMETIC_DOTENV_PROBE=leaked\n")
    monkeypatch.chdir(tmp_path)
    dotenv.load_dotenv(env)
    dotenv.load_dotenv()
    assert "HERMETIC_DOTENV_PROBE" not in os.environ


@pytest.mark.parametrize(
    "rel",
    [
        "src/backend/psn_layer.py",
        "src/backend/notification_services.py",
        "src/backend/xbox_game_reader.py",
        "src/backend/bot_monitor.py",
    ],
)
def test_no_import_time_load_dotenv(hermetic, rel):
    """These modules must not load .env as a side effect of being imported."""
    tree = ast.parse((hermetic.root / rel).read_text(encoding="utf-8"))
    for node in tree.body:  # module level only; functions / __main__ may load it
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            fn = node.value.func
            name = getattr(fn, "id", None) or getattr(fn, "attr", None)
            assert name != "load_dotenv", f"{rel}:{node.lineno} calls load_dotenv() at import"


def test_write_to_repo_data_is_refused(hermetic):
    probe = hermetic.protected_dirs[0] / "hermetic_probe.json"
    before = len(hermetic.data_write_violations)
    with pytest.raises(PermissionError):
        with open(probe, "w") as fh:
            fh.write("{}")
    assert not probe.exists()
    # expected violation — don't let it fail the session check
    del hermetic.data_write_violations[before:]


def test_network_guard(hermetic):
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    port = srv.getsockname()[1]
    try:
        # our own loopback server is reachable
        with socket.create_connection(("127.0.0.1", port), timeout=2):
            pass
        # a loopback port this process didn't bind (e.g. a live builder) is not
        with pytest.raises(hermetic.NetworkBlocked):
            socket.create_connection(("127.0.0.1", 18761), timeout=1)
        # nor is anything off-box
        with pytest.raises(OSError):
            socket.create_connection(("example.com", 443), timeout=1)
    finally:
        srv.close()


def test_repo_data_dir_untouched(hermetic):
    """Nothing in this session wrote to the repo's data/ (keep this test last)."""
    assert hermetic.data_write_violations == []
    if not hermetic.ignore_data_mtime:
        changed = hermetic.data_dir_changes()
        assert changed == [], (
            "repo data/ changed during the test run (if a live hub is writing "
            "there, rerun with HERMETIC_IGNORE_DATA_MTIME=1):\n" + "\n".join(changed[:20])
        )
