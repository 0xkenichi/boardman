"""Boardman House cashiers matches and cannot play."""
from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def _iso(tmp_path, monkeypatch):
    monkeypatch.setenv("BOARDMAN_AGENTIC_DATA", str(tmp_path))
    monkeypatch.setenv("BOARDMAN_AGENTIC_ONCHAIN", "0")
    monkeypatch.setenv("BOARDMAN_HOUSE_TABLES", "5")
    monkeypatch.setenv("BOARDMAN_BET_WINDOW_SEC", "0")
    monkeypatch.setenv("BOARDMAN_BOOK_CLOSE_PLIES", "24")
    monkeypatch.setattr(
        "gaming.src.stack.agentic.onchain.onchain_enabled", lambda: False
    )
    from gaming.src.stack.agentic.registry import get_registry
    from gaming.src.stack.agentic.matches import get_match_service

    get_registry.cache_clear()
    get_match_service.cache_clear()
    from gaming.src.stack.agentic import house as house_mod

    with house_mod._floor_lock:
        house_mod._workers.clear()
        if house_mod._pool is not None:
            house_mod._pool.shutdown(wait=False)
            house_mod._pool = None
    return get_registry()


def test_house_registers_and_does_not_play(tmp_path, monkeypatch):
    reg = _iso(tmp_path, monkeypatch)
    from gaming.src.stack.agentic.house import HOUSE_ID, ensure_house, get_house

    house = ensure_house()
    assert house["agent_id"] == HOUSE_ID
    assert house["role"] == "house"
    assert house["name"] == "Boardman"

    agents = {a["agent_id"]: a for a in reg.ensure_demo_agents()}
    assert HOUSE_ID in agents
    raja = agents["agent_raja_kia_alekhine"]["agent_id"]
    nero = agents["agent_nero_sicilian_french"]["agent_id"]

    rt = get_house()
    try:
        rt.open_match(agent_a_id=HOUSE_ID, agent_b_id=nero, stake_usdc=1)
        assert False, "house must not play"
    except ValueError as e:
        assert "cannot play" in str(e).lower() or "does not play" in str(e).lower()

    m = rt.open_match(agent_a_id=raja, agent_b_id=nero, stake_usdc=1)
    assert m["house_agent_id"] == HOUSE_ID
    assert m["agent_a_id"] != HOUSE_ID
    locked = rt.lock(m["match_id"])
    assert locked["status"] in {"locked", "partial_lock"}

    bet = rt.take_bet(
        m["match_id"],
        bettor_id="fan1",
        side="Raja",
        amount_usdc=Decimal("0.25"),
        funding="profile",
    )
    assert bet["side"] in {"a", "b"}
    assert bet["clerk"] == HOUSE_ID


def test_create_match_rejects_house_as_player(tmp_path, monkeypatch):
    reg = _iso(tmp_path, monkeypatch)
    from gaming.src.stack.agentic.house import HOUSE_ID, ensure_house
    from gaming.src.stack.agentic.matches import get_match_service

    ensure_house()
    agents = {a["agent_id"]: a for a in reg.ensure_demo_agents()}
    nero = agents["agent_nero_sicilian_french"]["agent_id"]
    try:
        get_match_service().create_match(
            agent_a_id=HOUSE_ID, agent_b_id=nero, stake_usdc=1
        )
        assert False
    except ValueError as e:
        assert "House" in str(e) or "play" in str(e).lower()


def _stub_contestant(reg, i: int):
    return reg.register_agent(
        agent_id=f"agent_floor_{i}",
        name=f"Floor{i}",
        owner_id=f"owner_{i}",
        strategy_id="stub",
        openings=[],
        mind={"plays_games": False},
        seed=f"boardman.floor.{i}",
        economy={"bankroll_usdc": "50", "max_stake_usdc": "5", "min_stake_usdc": "1"},
    )


def test_one_agent_one_live_table(tmp_path, monkeypatch):
    reg = _iso(tmp_path, monkeypatch)
    monkeypatch.setenv("BOARDMAN_HOUSE_TABLES", "5")
    from gaming.src.stack.agentic.house import get_house

    a = _stub_contestant(reg, 1)
    b = _stub_contestant(reg, 2)
    c = _stub_contestant(reg, 3)
    rt = get_house()
    rt.open_match(agent_a_id=a["agent_id"], agent_b_id=b["agent_id"], stake_usdc=1)
    try:
        rt.open_match(agent_a_id=a["agent_id"], agent_b_id=c["agent_id"], stake_usdc=1)
        assert False, "same agent cannot sit two tables"
    except ValueError as e:
        assert "already live" in str(e)


def test_sixth_table_queues(tmp_path, monkeypatch):
    reg = _iso(tmp_path, monkeypatch)
    from gaming.src.stack.agentic.house import _set_status, get_house

    agents = [_stub_contestant(reg, i) for i in range(12)]
    rt = get_house()
    ids = []
    for i in range(6):
        m = rt.open_match(
            agent_a_id=agents[i * 2]["agent_id"],
            agent_b_id=agents[i * 2 + 1]["agent_id"],
            stake_usdc=1,
        )
        ids.append(m["match_id"])

    for mid in ids[:5]:
        _set_status(mid, "playing")
    sixth = rt.start(ids[5])
    assert sixth["seated"] is False
    assert sixth["status"] == "queued"
    floor = rt.floor()
    assert floor["cap"] == 5
    assert floor["playing"] == 5
    assert floor["queued"] == 1

    bet = rt.take_bet(ids[0], bettor_id="fan", side="a", amount_usdc=Decimal("0.25"), funding="profile")
    assert bet["side"] == "a"


def test_house_snapshot_has_escrow_guardrails(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from gaming.src.stack.agentic.house import get_house

    snap = get_house().snapshot()
    assert snap["role"] == "house"
    assert snap["can_erc20_transfer"] is False
    assert snap["guardrails"]["can_pick_recipient"] is False


def test_rematch_async_returns_without_blocking(tmp_path, monkeypatch):
    reg = _iso(tmp_path, monkeypatch)
    from gaming.src.stack.agentic import house as house_mod

    monkeypatch.setattr(house_mod, "_lock_and_run", lambda *a, **k: None)
    monkeypatch.setattr(house_mod, "ensure_builder_webhooks", lambda: None)
    from gaming.src.stack.agentic.house import get_house

    agents = {a["agent_id"]: a for a in reg.ensure_demo_agents()}
    rt = get_house()
    out = rt.rematch(
        agent_a_id=agents["agent_raja_kia_alekhine"]["agent_id"],
        agent_b_id=agents["agent_nero_sicilian_french"]["agent_id"],
        stake_usdc=1,
        wait=False,
    )
    assert out["status"] == "locking"
    assert out["match_id"]


def test_abort_never_started_frees_pair(tmp_path, monkeypatch):
    reg = _iso(tmp_path, monkeypatch)
    from gaming.src.stack.agentic.house import get_house
    from gaming.src.stack.agentic.matches import get_match_service

    agents = {a["agent_id"]: a for a in reg.ensure_demo_agents()}
    raja = agents["agent_raja_kia_alekhine"]["agent_id"]
    nero = agents["agent_nero_sicilian_french"]["agent_id"]
    rt = get_house()
    m = rt.open_match(agent_a_id=raja, agent_b_id=nero, stake_usdc=1)
    rt.lock(m["match_id"])
    try:
        rt.open_match(agent_a_id=raja, agent_b_id=nero, stake_usdc=1)
        assert False, "pair still live"
    except ValueError:
        pass
    aborted = rt.abort_never_started(m["match_id"])
    assert aborted["status"] == "cancelled"
    m2 = rt.open_match(agent_a_id=raja, agent_b_id=nero, stake_usdc=1)
    assert m2["match_id"] != m["match_id"]
    assert get_match_service().get(m["match_id"])["status"] == "cancelled"


@pytest.mark.slow
def test_house_play_settles_only_with_disbursement(tmp_path, monkeypatch):
    """Happy path: lock → play → settle records a contract trigger, never a random payee."""
    reg = _iso(tmp_path, monkeypatch)
    from gaming.src.stack.agentic.house import HOUSE_ID, get_house

    agents = {a["agent_id"]: a for a in reg.ensure_demo_agents()}
    rt = get_house()
    m = rt.open_match(
        agent_a_id=agents["agent_raja_kia_alekhine"]["agent_id"],
        agent_b_id=agents["agent_nero_sicilian_french"]["agent_id"],
        stake_usdc=1,
        game_id="agentic.chess_standard",
    )
    locked = rt.lock(m["match_id"])
    assert locked["status"] == "locked"
    out = rt.play(m["match_id"], move_delay_sec=0, wait=True, seed=1)
    assert out["status"] == "settled"
    auth = out.get("disbursement") or {}
    assert auth.get("trigger") in {"MATCH_RESOLVE_WIN", "MATCH_RESOLVE_DRAW"}
    assert auth.get("match_id") == m["match_id"]


def test_book_closes_after_plies(tmp_path, monkeypatch):
    reg = _iso(tmp_path, monkeypatch)
    monkeypatch.setenv("BOARDMAN_BOOK_CLOSE_PLIES", "4")
    from gaming.src.stack.agentic.house import get_house
    from gaming.src.stack.agentic.store import load_json, save_json

    agents = {a["agent_id"]: a for a in reg.ensure_demo_agents()}
    rt = get_house()
    m = rt.open_match(
        agent_a_id=agents["agent_raja_kia_alekhine"]["agent_id"],
        agent_b_id=agents["agent_nero_sicilian_french"]["agent_id"],
        stake_usdc=1,
    )
    rt.lock(m["match_id"])
    store = load_json("matches.json", {"matches": {}})
    rec = store["matches"][m["match_id"]]
    rec["moves"] = [{"ply": i, "uci": "e2e4", "san": "e4"} for i in range(1, 5)]
    store["matches"][m["match_id"]] = rec
    save_json("matches.json", store)
    try:
        rt.take_bet(m["match_id"], bettor_id="fan", side="a", amount_usdc=Decimal("0.25"), funding="profile")
        assert False, "book should be closed"
    except ValueError as e:
        assert "closed" in str(e).lower()


def test_book_closes_on_the_clock_before_the_ply_limit(tmp_path, monkeypatch):
    """Friendlies: betting closes N seconds after kickoff, even on move 2."""
    from datetime import datetime, timedelta, timezone

    reg = _iso(tmp_path, monkeypatch)
    monkeypatch.setenv("BOARDMAN_BOOK_CLOSE_SEC", "30")
    from gaming.src.stack.agentic.house import get_house
    from gaming.src.stack.agentic.store import load_json, save_json

    agents = {a["agent_id"]: a for a in reg.ensure_demo_agents()}
    rt = get_house()
    m = rt.open_match(
        agent_a_id=agents["agent_raja_kia_alekhine"]["agent_id"],
        agent_b_id=agents["agent_nero_sicilian_french"]["agent_id"],
        stake_usdc=1,
    )
    rt.lock(m["match_id"])
    store = load_json("matches.json", {"matches": {}})
    rec = store["matches"][m["match_id"]]
    rec["moves"] = [{"ply": i, "uci": "e2e4", "san": "e4"} for i in range(1, 3)]
    rec["play_started_at"] = (datetime.now(timezone.utc) - timedelta(seconds=10)).isoformat()
    store["matches"][m["match_id"]] = rec
    save_json("matches.json", store)
    # 10s in: still open.
    rt.take_bet(m["match_id"], bettor_id="fan", side="a", amount_usdc=Decimal("0.25"), funding="profile")

    store = load_json("matches.json", {"matches": {}})
    rec = store["matches"][m["match_id"]]
    rec["play_started_at"] = (datetime.now(timezone.utc) - timedelta(seconds=31)).isoformat()
    store["matches"][m["match_id"]] = rec
    save_json("matches.json", store)
    with pytest.raises(ValueError, match="closed"):
        rt.take_bet(m["match_id"], bettor_id="fan2", side="b", amount_usdc=Decimal("0.25"), funding="profile")


def test_book_close_reason_clock_is_off_by_default(monkeypatch):
    from datetime import datetime, timedelta, timezone

    from gaming.src.stack.agentic.economy.spectator import book_close_reason

    monkeypatch.delenv("BOARDMAN_BOOK_CLOSE_SEC", raising=False)
    monkeypatch.setenv("BOARDMAN_BOOK_CLOSE_PLIES", "24")
    old = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    assert book_close_reason({"moves": [{}] * 3, "play_started_at": old}) is None
    assert book_close_reason({"moves": [{}] * 24}) == "ply_24"
    monkeypatch.setenv("BOARDMAN_BOOK_CLOSE_SEC", "30")
    assert book_close_reason({"moves": [{}] * 3, "play_started_at": old}) == "clock_30s"
    assert book_close_reason({"moves": [{}] * 3}) is None  # not kicked off yet


def test_bet_window_zero_is_instant(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from gaming.src.stack.agentic.house import _wait_bet_window, bet_window_sec, get_house

    assert bet_window_sec() == 0
    agents = {a["agent_id"]: a for a in __import__(
        "gaming.src.stack.agentic.registry", fromlist=["get_registry"]
    ).get_registry().ensure_demo_agents()}
    rt = get_house()
    m = rt.open_match(
        agent_a_id=agents["agent_raja_kia_alekhine"]["agent_id"],
        agent_b_id=agents["agent_nero_sicilian_french"]["agent_id"],
        stake_usdc=1,
    )
    rt.lock(m["match_id"])
    assert _wait_bet_window(m["match_id"]) is True


def test_overlay_serves_live_bets(tmp_path, monkeypatch):
    reg = _iso(tmp_path, monkeypatch)
    from gaming.src.stack.agentic.house import get_house
    from gaming.src.stack.agentic.matches import get_match_service

    agents = {a["agent_id"]: a for a in reg.ensure_demo_agents()}
    rt = get_house()
    m = rt.open_match(
        agent_a_id=agents["agent_raja_kia_alekhine"]["agent_id"],
        agent_b_id=agents["agent_nero_sicilian_french"]["agent_id"],
        stake_usdc=1,
    )
    rt.lock(m["match_id"])
    rt.take_bet(m["match_id"], bettor_id="fan-ken", side="a", amount_usdc=Decimal("1.25"), funding="profile")
    got = get_match_service().get(m["match_id"])
    bets = (got.get("spectator_book") or {}).get("bets") or []
    assert any(b.get("bettor_id") == "fan-ken" for b in bets)


def test_play_match_resumes_prior_moves():
    from gaming.src.stack.agentic.chess.arena import _replay_prior

    prior = [
        {"uci": "e2e4", "san": "e4", "side": "white", "ply": 1},
        {"uci": "e7e5", "san": "e5", "side": "black", "ply": 2},
    ]
    board, _game, _node, events = _replay_prior(prior)
    assert len(events) == 2
    assert board.ply() == 2
    assert "4p3" in board.fen()


def test_rematch_attaches_to_locked_pair(tmp_path, monkeypatch):
    reg = _iso(tmp_path, monkeypatch)
    from gaming.src.stack.agentic import house as house_mod
    from gaming.src.stack.agentic.house import get_house

    monkeypatch.setattr(house_mod, "ensure_builder_webhooks", lambda: None)
    monkeypatch.setattr(house_mod, "rescue_orphans", lambda: [])
    agents = {a["agent_id"]: a for a in reg.ensure_demo_agents()}
    raja = agents["agent_raja_kia_alekhine"]["agent_id"]
    nero = agents["agent_nero_sicilian_french"]["agent_id"]
    from gaming.src.stack.agentic.db import leases

    rt = get_house()
    m = rt.open_match(agent_a_id=raja, agent_b_id=nero, stake_usdc=1)
    rt.lock(m["match_id"])
    # Nobody drives it (no lease, no worker): never handed back as "live".
    with pytest.raises(ValueError, match="no live worker"):
        rt.rematch(agent_a_id=raja, agent_b_id=nero, stake_usdc=1, wait=False)
    # Another process drives it under a fresh lease: attach.
    monkeypatch.setattr(leases, "process_owner", lambda: "other-process")
    assert leases.try_acquire(m["match_id"]) is not None
    monkeypatch.setattr(leases, "process_owner", lambda: "this-process")
    out = rt.rematch(agent_a_id=raja, agent_b_id=nero, stake_usdc=1, wait=False)
    assert out.get("attached") is True
    assert out.get("match_id") == m["match_id"]


def _fake_popen(monkeypatch):
    import subprocess

    spawned: list[list[str]] = []

    class _FakePopen:
        def __init__(self, args, **_kw):
            spawned.append(list(args))

    monkeypatch.setattr(subprocess, "Popen", _FakePopen)
    return spawned


@pytest.mark.builder_webhooks
def test_supervised_webhooks_are_not_spawned(monkeypatch):
    from gaming.src.stack.agentic import house as house_mod

    spawned = _fake_popen(monkeypatch)
    monkeypatch.setenv("BOARDMAN_WEBHOOKS_SUPERVISED", "1")
    house_mod.ensure_builder_webhooks()
    assert spawned == []


@pytest.mark.builder_webhooks
def test_unsupervised_webhooks_still_spawn_when_ports_are_free(monkeypatch):
    from gaming.src.stack.agentic import house as house_mod

    spawned = _fake_popen(monkeypatch)
    monkeypatch.delenv("BOARDMAN_WEBHOOKS_SUPERVISED", raising=False)
    house_mod.ensure_builder_webhooks()  # port probes are refused by the test net guard
    mods = [args[-1] for args in spawned]
    assert "gaming.src.stack.agentic.agents.raja.serve" in mods
    assert "gaming.src.stack.agentic.agents.nero.serve" in mods


def test_table_pool_threads_are_daemon_and_run_work():
    import threading

    from gaming.src.stack.agentic.house import _DaemonTablePool

    pool = _DaemonTablePool(max_workers=2, thread_name_prefix="t")
    gate = threading.Event()
    blocked = pool.submit(gate.wait, 30)
    quick = pool.submit(lambda x: x * 2, 21)
    assert quick.result(timeout=5) == 42
    assert pool._threads and all(t.daemon for t in pool._threads)
    gate.set()
    assert blocked.result(timeout=5) is True
    pool.shutdown(wait=True)


def test_process_exits_with_a_table_still_playing():
    """A table mid-game must not keep the interpreter alive (pytest used to hang)."""
    import subprocess

    code = (
        "import sys, types, time\n"
        f"root = {str(_REPO_ROOT)!r}\n"
        "sys.path.insert(0, root)\n"
        "m = types.ModuleType('gaming'); m.__path__ = [root]\n"
        "sys.modules.setdefault('gaming', m)\n"
        "from gaming.src.stack.agentic import house\n"
        "house._executor().submit(time.sleep, 600)\n"
        "print('submitted', flush=True)\n"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, timeout=60
    )
    assert proc.returncode == 0, proc.stderr[-2000:]
    assert "submitted" in proc.stdout
