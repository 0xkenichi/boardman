"""JSON -> database migration, cutover guard, and read-only legacy mode."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from decimal import Decimal
from pathlib import Path

import pytest

from gaming.src.stack.agentic.db import engine

ROOT = Path(__file__).resolve().parents[1]


def _script():
    spec = importlib.util.spec_from_file_location("migrate_json_to_db", ROOT / "scripts" / "migrate_json_to_db.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _match(mid: str, status: str, settled_at: str = "") -> dict:
    return {
        "match_id": mid,
        "status": status,
        "agent_a_id": "agent_raja_kia_alekhine",
        "agent_b_id": "agent_nero_sicilian_french",
        "stake_usdc": "5",
        "created_at": "2026-10-01T00:00:00+00:00",
        "updated_at": settled_at or "2026-10-01T00:00:00+00:00",
        "settled_at": settled_at or None,
        "moves": [{"ply": 1, "san": "e4"}],
    }


def _legacy(dirpath: Path) -> dict[str, str]:
    """A small legacy store: hot + archive overlap, txs of every shape."""
    dirpath.mkdir(parents=True, exist_ok=True)
    ledger = {
        "balances": {"0xaa": "58.600000", "0xbb": "40", "creator:raja": "2.00", "fan1": "0.000001"},
        "escrows": {
            "agm_old1": {"match_id": "agm_old1", "status": "settled", "stake_usdc": "5", "agent_a_wallet": "0xaa",
                         "agent_b_wallet": "0xbb", "result": "win", "created_at": "2026-10-01T00:00:00+00:00"},
        },
        "txs": [
            {"ts": "t1", "type": "credit", "wallet": "0xaa", "amount": "50", "reason": "fund", "ref": "", "balance_after": "50"},
            {"ts": "t2", "type": "escrow_open", "ref": "agm_old1", "stake": "5"},
            {"ts": "t3", "type": "escrow_settle", "ref": "agm_old1", "winner": "0xaa", "payout": "9.3", "fee": "0.7"},
        ],
    }
    files = {
        "ledger.json": ledger,
        "matches.json": {"matches": {"agm_live": _match("agm_live", "playing"),
                                     "agm_old1": _match("agm_old1", "settled", "2026-10-02T00:00:00+00:00")}},
        "matches_archive.json": {"matches": {"agm_arch": _match("agm_arch", "settled", "2026-09-01T00:00:00+00:00"),
                                             "agm_old1": _match("agm_old1", "error")}},
        "spectator_books.json": {"books": {"agm_live": {"match_id": "agm_live", "status": "open", "bets": [],
                                                        "totals": {"a": "1", "b": "0", "draw": "0"}}}},
        "spectator_books_archive.json": {"books": {"agm_arch": {"match_id": "agm_arch", "status": "settled",
                                                                "settled_at": "2026-09-01", "bets": []}}},
        "agent_lp_pools.json": {"pools": {"agent_raja_kia_alekhine": {"agent_id": "agent_raja_kia_alekhine",
                                                                      "total_lp_usdc": "20", "positions": {}, "history": []}}},
    }
    hashes = {}
    for name, payload in files.items():
        p = dirpath / name
        p.write_text(json.dumps(payload))
        hashes[name] = hashlib.sha256(p.read_bytes()).hexdigest()
    return hashes


def _isolate(monkeypatch, data: Path) -> None:
    # run() writes these into os.environ; registering them here restores them.
    for k, v in (("BOARDMAN_AGENTIC_DATA", str(data)), ("BOARDMAN_STORAGE", "db"),
                 ("BOARDMAN_STORAGE_ALLOW_UNMIGRATED", "0")):
        monkeypatch.setenv(k, v)
    engine.reset_databases()


@pytest.fixture(autouse=True)
def _reset():
    engine.reset_databases()
    yield
    engine.reset_databases()


def test_dry_run_reports_counts_and_checksum_and_writes_nothing(tmp_path, monkeypatch):
    data = tmp_path / "agentic"
    before = _legacy(data)
    _isolate(monkeypatch, data)
    code, out = _script().run(data, apply=False)
    assert code == 0
    assert out["counts"]["matches"] == 3  # hot + archive, hot wins on overlap
    assert out["counts"]["spectator_books"] == 2
    assert out["counts"]["ledger_txs"] == 3
    assert out["balances"]["checksum_ok"] and out["balances"]["sum_json"] == "100.600001"
    assert not (data / engine.DB_FILENAME).exists()
    assert before == {n: hashlib.sha256((data / n).read_bytes()).hexdigest() for n in before}


def test_apply_imports_everything_and_keeps_json_untouched(tmp_path, monkeypatch):
    data = tmp_path / "agentic"
    before = _legacy(data)
    _isolate(monkeypatch, data)
    code, out = _script().run(data, apply=True)
    assert code == 0, out
    monkeypatch.setenv("BOARDMAN_STORAGE_ALLOW_UNMIGRATED", "0")
    engine.reset_databases()

    from gaming.src.stack.agentic import ledger
    from gaming.src.stack.agentic.economy.lp import AgentLPPool
    from gaming.src.stack.agentic.economy.spectator import SpectatorBook
    from gaming.src.stack.agentic.matches import AgentMatchService

    assert ledger.balance("0xaa") == Decimal("58.6")
    assert str(ledger.balance("creator:raja")) == "2.00"  # display scale kept
    assert ledger.get_escrow("agm_old1")["result"] == "win"
    svc = AgentMatchService()
    assert svc.get("agm_old1")["status"] == "settled"  # hot copy won
    assert svc.get("agm_arch")["moves"][0]["san"] == "e4"  # archived = indexed lookup
    assert SpectatorBook().get("agm_arch")["status"] == "settled"
    assert AgentLPPool().get_pool("agent_raja_kia_alekhine")["total_lp_usdc"] == "20"
    assert [m["match_id"] for m in svc.list_matches() if m["status"] == "playing"] == ["agm_live"]
    assert before == {n: hashlib.sha256((data / n).read_bytes()).hexdigest() for n in before}

    # A second import into a non-empty database is refused.
    code, out = _script().run(data, apply=True)
    assert code == 3 and "refused" in out


def test_corrupt_and_truncated_files_are_reported_and_block_apply(tmp_path, monkeypatch):
    data = tmp_path / "agentic"
    _legacy(data)
    (data / "agent_lp_pools.json").write_text("{not json")
    full = json.dumps({"matches": {"agm_a": _match("agm_a", "settled", "2026-09-01"),
                                   "agm_b": _match("agm_b", "settled", "2026-09-02")}})
    (data / "matches_archive.json").write_text(full[: full.index('"agm_b"') + 30])  # cut mid-record
    _isolate(monkeypatch, data)
    script = _script()
    code, out = script.run(data, apply=False)
    assert code == 2
    assert out["files"]["agent_lp_pools.json"]["status"] == "corrupt"
    assert out["files"]["matches_archive.json"]["status"] == "partial"
    assert out["files"]["matches_archive.json"]["salvaged_records"] == 1
    assert any("damaged" in p for p in out["problems"])

    assert script.main(["--data-dir", str(data), "--apply"]) == 2
    engine.reset_databases()
    monkeypatch.setenv("BOARDMAN_STORAGE_ALLOW_UNMIGRATED", "1")
    from gaming.src.stack.agentic import ledger

    assert ledger.balances() == {}  # rolled back: nothing imported

    code, out = script.run(data, apply=True, accept_problems=True)
    assert code == 0 and out["counts"]["matches"] == 3  # agm_live, agm_old1, salvaged agm_a


def test_unmigrated_store_refuses_to_start(tmp_path, monkeypatch):
    data = tmp_path / "agentic"
    _legacy(data)
    _isolate(monkeypatch, data)
    from gaming.src.stack.agentic import ledger

    with pytest.raises(engine.StorageNotMigrated, match="migrate_json_to_db"):
        ledger.balance("0xaa")
    engine.reset_databases()
    code, _ = _script().run(data, apply=True)
    assert code == 0
    monkeypatch.setenv("BOARDMAN_STORAGE_ALLOW_UNMIGRATED", "0")
    engine.reset_databases()
    assert ledger.balance("0xaa") == Decimal("58.6")


def test_json_mode_serves_legacy_files_read_only(tmp_path, monkeypatch):
    data = tmp_path / "agentic"
    _legacy(data)
    _isolate(monkeypatch, data)
    monkeypatch.setenv("BOARDMAN_STORAGE", "json")
    engine.reset_databases()
    from gaming.src.stack.agentic import ledger
    from gaming.src.stack.agentic.matches import AgentMatchService

    assert ledger.balance("0xbb") == Decimal("40")
    assert AgentMatchService().get("agm_arch")["status"] == "settled"
    with pytest.raises(engine.StorageReadOnly):
        ledger.credit("0xbb", Decimal("1"), reason="nope")
    assert not (data / engine.DB_FILENAME).exists()
