"""AFM season service: entries, daily tick, fixture resolution, pot payout."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest


@pytest.fixture(autouse=True)
def _isolate_store(tmp_path, monkeypatch):
    monkeypatch.setenv("BOARDMAN_AGENTIC_DATA", str(tmp_path))
    yield
    # reset per-process catalog ownership between tests (in-memory only)
    from gaming.src.stack.agentic.games.football_managers import catalog as cat

    for p in cat.seed_catalog():
        cat.set_owner(p["player_id"], None)


@pytest.fixture()
def _world():
    """Registered AFM demo managers + their clubs, all under the tmp store."""
    from gaming.src.stack.agentic.registry import get_registry

    reg = get_registry()
    reg.ensure_demo_agents()

    from gaming.src.stack.agentic.games.football_managers.club_store import (
        seed_demo_clubs,
    )

    seed_demo_clubs()
    return reg


def _now() -> datetime:
    return datetime.now(timezone.utc)


def test_open_season_collects_entries_and_builds_schedule(_world):
    import gaming.src.stack.agentic.ledger as L
    from gaming.src.stack.agentic.games.football_managers import season as S

    # a two-club derby season — the demo default now includes 3 clubs
    S.open_season(
        agent_ids=["agent_bluelock_demo", "agent_aoashi_demo"],
        start_at=_now() + timedelta(hours=2),
    )
    snap = S.get_season()
    assert snap is not None
    assert snap["status"] == "open"
    assert len(snap["division"]) == 2
    assert snap["matchdays_total"] == 30  # derby division, home/away alternating
    assert snap["current_matchday"] == 1
    # both entries landed in the season pot: 2 × $25
    assert float(snap["pot_usdc"]) == 50.0
    assert all(e["paid"] for e in snap["entries"].values())
    # zeroed standings
    for row in snap["standings"]:
        assert row["played"] == 0 and row["points"] == 0


def test_open_season_guards_against_double_open(_world):
    from gaming.src.stack.agentic.games.football_managers import season as S

    S.open_season(start_at=_now() + timedelta(hours=2))
    with pytest.raises(ValueError):
        S.open_season(start_at=_now() + timedelta(hours=3))


def test_tick_resolves_due_matchday(_world):
    import gaming.src.stack.agentic.ledger as L
    from gaming.src.stack.agentic.games.football_managers import season as S

    # matchday 1 opened 7h ago → deadline (lock_hours=6) already passed
    S.open_season(
        agent_ids=["agent_bluelock_demo", "agent_aoashi_demo"],
        start_at=_now() - timedelta(hours=7),
    )
    out = S.tick()
    assert out["opened"] == [1]
    assert out["resolved"] == [1]

    snap = S.get_season()
    assert snap["current_matchday"] == 2
    assert len(snap["recent"]) == 1
    assert all(r["played"] == 1 for r in snap["standings"])
    # 3/1/0 — exactly one winner (or a draw: both 1)
    assert sum(r["points"] for r in snap["standings"]) in (3, 1)

    # the matchday escrow actually settled through the ledger
    fx = snap["recent"][0]
    esc = L.get_escrow(fx["match_id"])
    assert esc is not None and esc["status"] == "settled"
    # pot untouched by matchday play (still the two entries)
    assert float(snap["pot_usdc"]) == 50.0


def test_full_season_crowns_champion_and_pays_pot(_world):
    import gaming.src.stack.agentic.ledger as L
    from gaming.src.stack.agentic.games.football_managers import season as S

    # start the season 31 days ago → all 30 matchdays are due at first tick
    S.open_season(
        agent_ids=["agent_bluelock_demo", "agent_aoashi_demo"],
        start_at=_now() - timedelta(days=31),
    )
    out = S.tick()
    assert out["season_status"] == "finished"

    snap = S.get_season()
    assert snap["status"] == "finished"
    assert snap["champion"] is not None
    assert len(snap["recent"]) == 12
    for row in snap["standings"]:
        assert row["played"] == 30
    # champion is rank 1 by the same ordering that got the payout
    assert snap["standings"][0]["agent_id"] == snap["champion"]

    # the whole pot (2 × $25) was paid out — pot balance is zero
    assert float(snap["pot_usdc"]) == 0.0


def test_tick_is_idempotent_never_double_counts(_world):
    """Keeper, API and humans can all tick — a played matchday never re-resolves."""
    from gaming.src.stack.agentic.games.football_managers import season as S

    S.open_season(
        agent_ids=["agent_bluelock_demo", "agent_aoashi_demo"],
        start_at=_now() - timedelta(hours=7),
    )
    first = S.tick()
    assert first["resolved"] == [1]

    S.tick()  # second (or third) caller
    S.tick()
    snap = S.get_season()
    rows = {r["agent_id"]: r for r in snap["standings"]}
    assert sum(r["played"] for r in rows.values()) == 2  # 2 clubs × 1 matchday
    assert sum(r["points"] for r in rows.values()) in (3, 1)  # 3/1/0, never doubled
    assert len(snap["recent"]) == 1


def test_join_season_queues_for_next_season(_world):
    from gaming.src.stack.agentic.games.football_managers import season as S

    S.open_season(
        agent_ids=["agent_bluelock_demo", "agent_aoashi_demo"],
        start_at=_now() - timedelta(days=31),
    )
    S.tick()
    assert S.get_season()["status"] == "finished"

    S.join_season("agent_bluelock_demo")
    snap = S.open_season(start_at=_now() + timedelta(hours=1))
    # the queued joiner is in the new season's division
    assert "agent_bluelock_demo" in [d["agent_id"] for d in snap["division"]]
    assert snap["season_no"] == 2