"""AFM seasons roll over on the house clock, unattended.

Season open/tick/reset are platform-admin routes, so the keeper's tick is
the only thing that starts the next season. Production has sat on a
finished season 1 since 2026-10-05: tick() tried the roll-over before it had
saved the finished season, so open_season() read "season already open" from
disk and refused; the error was swallowed and an idle tick never retried.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

DERBY = ["agent_bluelock_demo", "agent_aoashi_demo"]


@pytest.fixture(autouse=True)
def _isolate_store(tmp_path, monkeypatch):
    monkeypatch.setenv("BOARDMAN_AGENTIC_DATA", str(tmp_path))
    monkeypatch.delenv("AFM_AUTO_NEXT_SEASON", raising=False)
    monkeypatch.delenv("AFM_SEASON_BREAK_HOURS", raising=False)
    from gaming.src.stack.agentic.games.football_managers import season as S

    S._auto_open_failures.clear()
    yield
    S._auto_open_failures.clear()
    from gaming.src.stack.agentic.games.football_managers import catalog as cat

    for p in cat.seed_catalog():
        cat.set_owner(p["player_id"], None)


@pytest.fixture()
def _world():
    from gaming.src.stack.agentic.registry import get_registry
    from gaming.src.stack.agentic.games.football_managers.club_store import seed_demo_clubs

    reg = get_registry()
    reg.ensure_demo_agents()
    seed_demo_clubs()
    return reg


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _finish_a_derby_season():
    from gaming.src.stack.agentic.games.football_managers import season as S

    S.open_season(agent_ids=DERBY, start_at=_now() - timedelta(days=31))
    out = S.tick()
    assert out["season_status"] == "finished"
    return S


@pytest.mark.slow
def test_finished_season_waits_out_the_break_then_rolls_over(_world):
    S = _finish_a_derby_season()
    champion = S.get_season()["champion"]

    # inside the break: the final table stays up, nothing opens
    assert S.tick(now=_now() + timedelta(hours=1))["action"] == "idle"
    assert S.get_season()["status"] == "finished"

    out = S.tick(now=_now() + timedelta(hours=13))
    assert out["action"] == "auto_open"
    snap = S.get_season()
    assert snap["season_no"] == 2 and snap["status"] == "open"
    assert len(snap["division"]) >= 2
    # the finished season is kept as a compact record
    from gaming.src.stack.agentic.games.football_managers.season import _state_view

    hist = _state_view().get("history") or []
    assert [h["season_no"] for h in hist] == [1]
    assert hist[0]["champion"] == champion
    assert hist[0]["standings"][0]["agent_id"] == champion
    # and the new season then plays on the same clock
    assert S.tick(now=_now() + timedelta(hours=13))["season_no"] == 2


@pytest.mark.slow
def test_rollover_in_the_finishing_tick_is_not_overwritten(_world, monkeypatch):
    """With no break, the tick that crowns the champion opens the next season
    (the old code tried this and silently failed) — and it sticks."""
    monkeypatch.setenv("AFM_SEASON_BREAK_HOURS", "0")
    from gaming.src.stack.agentic.games.football_managers import season as S

    S.open_season(agent_ids=DERBY, start_at=_now() - timedelta(days=31))
    out = S.tick()
    assert out["season_status"] == "finished"
    assert out["next_season"]["action"] == "auto_open"
    snap = S.get_season()
    assert snap["season_no"] == 2
    assert snap["status"] == "open"


@pytest.mark.slow
def test_auto_next_season_can_be_switched_off(_world, monkeypatch):
    monkeypatch.setenv("AFM_AUTO_NEXT_SEASON", "0")
    S = _finish_a_derby_season()
    assert S.tick(now=_now() + timedelta(days=3))["action"] == "idle"
    assert S.get_season()["season_no"] == 1


def test_failed_open_hands_the_entries_back(_world, monkeypatch):
    """Too few payers: the entries already collected go back to the clubs
    instead of being stranded in a pot no season will ever pay out."""
    import gaming.src.stack.agentic.ledger as L
    from gaming.src.stack.agentic.games.football_managers import season as S

    monkeypatch.setenv("BOARDMAN_DEMO_FAUCET", "0")
    payer = S._wallet(DERBY[0])
    L.credit(payer, Decimal("100"), reason="test_fund", ref="t")
    before = L.balance(payer)
    with pytest.raises(ValueError, match="fewer than two clubs"):
        S.open_season(agent_ids=DERBY, start_at=_now() + timedelta(hours=1))
    assert L.balance(payer) == before
    assert L.balance(S._pot_wallet(1)) == 0
    assert S.get_season() is None


@pytest.mark.slow
def test_failed_rollover_is_retried_hourly_not_every_tick(_world, monkeypatch):
    S = _finish_a_derby_season()
    calls = []

    def boom(*a, **kw):
        calls.append(1)
        raise ValueError("fewer than two clubs could pay the season entry")

    monkeypatch.setattr(S, "open_season", boom)
    t0 = _now() + timedelta(hours=13)
    out = S.tick(now=t0)
    assert out["action"] == "auto_open_failed"
    assert "fewer than two clubs" in out["auto_open_error"]
    assert S.tick(now=t0 + timedelta(minutes=5))["action"] == "idle"
    assert len(calls) == 1
    assert S.tick(now=t0 + timedelta(minutes=61))["action"] == "auto_open_failed"
    assert len(calls) == 2
    assert S.get_season()["status"] == "finished"
