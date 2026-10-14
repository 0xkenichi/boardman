"""Hot-path fixes: off-loop handlers, uncapped house metrics, schedule truth,
and the admin balance TTL."""
from __future__ import annotations

import inspect
import threading
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from gaming.src.stack.agentic import api as api_mod
from gaming.src.stack.agentic.json_cache import get_cache
from gaming.src.stack.agentic.store import save_json

KEY = "test-perf-key"
RAJA = "agent_raja_kia_alekhine"
NERO = "agent_nero_sicilian_french"


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("BOARDMAN_API_KEY", KEY)
    app = FastAPI()
    app.include_router(api_mod.router)
    with TestClient(app, headers={"X-Boardman-Key": KEY}) as c:
        yield c


def _match(mid: str, *, settled_at: datetime, stake: str = "1", status: str = "settled", a=RAJA, b=NERO):
    return {
        "match_id": mid,
        "status": status,
        "stake_usdc": stake,
        "agent_a_id": a,
        "agent_b_id": b,
        "white_agent_id": a,
        "black_agent_id": b,
        "winner_agent_id": a,
        "result": "1-0",
        "created_at": settled_at.isoformat(),
        "settled_at": settled_at.isoformat(),
        "moves": [{"san": "e4"}] * 50,
        "spectator_book": {"totals": {"a": "2", "b": "1"}, "bets": [{"amount": "2", "user_id": "u1"}]},
    }


def _seed_hot_and_archive(now: datetime, *, hot_n: int = 3, arch_n: int = 15):
    hot = {f"h{i}": _match(f"h{i}", settled_at=now - timedelta(minutes=i + 1)) for i in range(hot_n)}
    hot["live1"] = _match("live1", settled_at=now, status="playing")
    hot["live1"]["settled_at"] = None
    arch = {f"a{i}": _match(f"a{i}", settled_at=now - timedelta(hours=1, minutes=i)) for i in range(arch_n)}
    arch["old"] = _match("old", settled_at=now - timedelta(days=3))
    save_json("matches.json", {"matches": hot}, compact=True)
    save_json("matches_archive.json", {"matches": arch}, compact=True)


# ------------------------------------------------------------ metrics source

def test_metrics_count_the_archive_not_just_the_hot_file():
    from gaming.src.stack.agentic.metrics import build_public_metrics, house_activity

    now = datetime.now(timezone.utc)
    _seed_hot_and_archive(now)
    out = build_public_metrics(limit=5)
    vol = out["volume"]
    assert vol["matches_settled"] == 3 + 15 + 1
    assert Decimal(vol["skill_volume_usdc"]) == Decimal(2 * 19)
    assert len(out["matches"]) == 5  # the page is still capped; the counts are not
    act = house_activity(now=now)
    assert act["games_24h"] == 18  # > 10: no longer derived from a 10-row page
    assert act["games_live"] == 1
    assert act["last_settled"]["match_id"] == "h0"


def test_archive_projection_drops_move_lists():
    from gaming.src.stack.agentic.metrics import metric_matches

    _seed_hot_and_archive(datetime.now(timezone.utc))
    ms = metric_matches()["matches"]
    assert "moves" not in ms["a0"]
    assert "moves" in ms["h0"]  # hot records are passed through untouched


def test_big_archive_is_refreshed_in_the_background():
    cache = get_cache()
    save_json("swr_probe.json", {"v": 1})
    assert cache.view_swr("swr_probe.json", {}, sync_below_bytes=0)["v"] == 1
    time.sleep(0.01)
    save_json("swr_probe.json", {"v": 2})
    # stale version served immediately, fresh one after the background parse
    assert cache.view_swr("swr_probe.json", {}, sync_below_bytes=0)["v"] in (1, 2)
    deadline = time.time() + 5
    while cache.view_swr("swr_probe.json", {}, sync_below_bytes=0)["v"] != 2:
        assert time.time() < deadline
        time.sleep(0.01)


# ------------------------------------------------------------ schedule truth

def test_next_table_on_the_hour_with_zero_cadence_is_hourly():
    now = datetime(2026, 10, 3, 12, 43, 21, tzinfo=timezone.utc)
    at, sec = api_mod._next_table({"enabled": True, "cadence_sec": 0, "cadence_mode": "on_the_hour"}, now)
    assert at is not None and 960 <= sec <= 1004  # → 13:00, the session's 3600 fallback
    # after_game: last settle + cadence; continuous has no countdown
    sched = {"enabled": True, "cadence_sec": 600, "cadence_mode": "after_game",
             "last_settled_at": (now - timedelta(seconds=100)).isoformat()}
    assert api_mod._next_table(sched, now)[1] == 500
    assert api_mod._next_table({**sched, "cadence_sec": 0}, now) == (None, None)
    assert api_mod._next_table({**sched, "enabled": False}, now) == (None, None)


def test_status_and_schedule_agree_in_on_the_hour_mode(client):
    now = datetime.now(timezone.utc)
    _seed_hot_and_archive(now)
    r = client.post("/api/stack/agentic/house/schedule", json={"cadence_sec": 0, "cadence_mode": "on_the_hour"})
    assert r.status_code == 200, r.text
    assert r.json()["schedule"]["cadence_mode"] == "on_the_hour"
    sched = client.get("/api/stack/agentic/house/schedule").json()
    status = client.get("/api/stack/agentic/house/status").json()
    assert sched["next_in_sec"] is not None and 0 < sched["next_in_sec"] <= 3602
    assert status["next_in_sec"] is not None
    assert abs(status["next_in_sec"] - sched["next_in_sec"]) <= 2
    assert status["games_24h"] == 18
    assert status["last_settled"]["match_id"] == "h0"
    bad = client.post("/api/stack/agentic/house/schedule", json={"cadence_mode": "sometimes"})
    assert bad.status_code == 422


# ------------------------------------------------------------ admin balances

def test_metrics_detail_caches_wallet_balances(client, monkeypatch):
    from gaming.src.stack.agentic import onchain

    save_json("agents.json", {"agents": {
        RAJA: {"agent_id": RAJA, "name": "Raja", "wallet_address": "0x" + "1" * 40},
        NERO: {"agent_id": NERO, "name": "Nero", "wallet_address": "0x" + "2" * 40},
    }})
    _seed_hot_and_archive(datetime.now(timezone.utc))
    calls = {"n": 0}

    def fake_balance(wallet, chain_id="arc"):
        calls["n"] += 1
        return Decimal("7")

    monkeypatch.setattr(onchain, "usdc_balance", fake_balance)
    monkeypatch.setattr(api_mod, "_wallet_balance_cache", {})
    for _ in range(3):
        r = client.get("/api/stack/agentic/admin/metrics-detail")
        assert r.status_code == 200, r.text
    assert calls["n"] == 2  # one RPC per wallet per TTL, not per request
    j = r.json()
    assert j["wallet_balances"][RAJA]["balance_usdc"] == "7"
    # agent-vs-agent games are classified from raw records (hot + archive)
    assert j["human_vs_agent"]["agent"]["matches"] == 19


# ------------------------------------------------------------ off the loop

BLOCKING_HANDLERS = (
    "play_match", "house_play", "lock_match", "house_lock", "create_match",
    "house_open_match", "house_rematch", "agents_onchain_volume",
    "agent_onchain_volume", "get_agent", "get_agent_wallet", "house_status",
    "admin_metrics_detail", "demo_chess", "demo_any_game", "public_metrics",
)


@pytest.mark.parametrize("name", BLOCKING_HANDLERS)
def test_blocking_handlers_run_in_the_threadpool(name):
    assert not inspect.iscoroutinefunction(getattr(api_mod, name))


def test_a_long_play_does_not_freeze_other_requests(client, monkeypatch):
    from gaming.src.stack.agentic import matches as matches_mod

    class SlowService:
        def run_match(self, match_id, **kw):
            time.sleep(0.8)  # a full game with think delays
            return {"match_id": match_id, "status": "settled"}

    monkeypatch.setattr(matches_mod, "get_match_service", lambda: SlowService())
    done = {}

    def play():
        done["r"] = client.post("/api/stack/agentic/matches/m1/play", json={})

    t = threading.Thread(target=play)
    t.start()
    time.sleep(0.15)
    t0 = time.perf_counter()
    h = client.get("/api/stack/agentic/health")
    elapsed = time.perf_counter() - t0
    t.join()
    assert h.status_code == 200
    assert done["r"].status_code == 200
    assert elapsed < 0.5, f"health waited {elapsed:.2f}s behind the game"
