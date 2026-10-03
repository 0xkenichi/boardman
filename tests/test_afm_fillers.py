"""AI filler clubs — divisions bootstrap to a full league, never a derby."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest


@pytest.fixture(autouse=True)
def _isolate_store(tmp_path, monkeypatch):
    monkeypatch.setenv("BOARDMAN_AGENTIC_DATA", str(tmp_path))
    monkeypatch.setenv("AFM_FILLER_CLUBS", "1")
    monkeypatch.setenv("AFM_FILLER_TARGET", "10")
    yield
    from gaming.src.stack.agentic.games.football_managers import catalog as cat

    for p in cat.seed_catalog():
        cat.set_owner(p["player_id"], None)


@pytest.fixture()
def _world():
    from gaming.src.stack.agentic.registry import get_registry
    from gaming.src.stack.agentic.games.football_managers.club_store import (
        seed_demo_clubs,
    )

    reg = get_registry()
    reg.ensure_demo_agents()
    seed_demo_clubs()
    return reg


def _now() -> datetime:
    return datetime.now(timezone.utc)


def test_auto_season_bootstraps_to_a_full_league(_world):
    import gaming.src.stack.agentic.ledger as L
    from gaming.src.stack.agentic.games.football_managers import season as S
    from gaming.src.stack.agentic.games.football_managers.league import (
        schedule_season,
    )

    S.open_season(start_at=_now() + timedelta(hours=2))
    snap = S.get_season()
    div = snap["division"]
    fillers = [d["agent_id"] for d in div if d.get("is_filler")]
    reals = [d["agent_id"] for d in div if not d.get("is_filler")]
    # 7 real clubs + fillers to the target of 10 — never a two-club derby
    assert len(reals) == 7
    assert len(fillers) == 3
    assert len(div) == 10
    # even division → double round robin, no byes: 18 matchdays × 5 fixtures
    assert snap["matchdays_total"] == 18
    rounds = schedule_season([d["agent_id"] for d in div])
    assert len(rounds) == 18
    assert all(len(r) == 5 for r in rounds)
    pairs = [
        tuple(sorted((f.home_agent_id, f.away_agent_id))) for r in rounds for f in r
    ]
    assert len(pairs) == 90 and len(set(pairs)) == 45  # every pair exactly twice
    # fillers paid their entry into the pot like everyone else (10 × $25)
    assert float(snap["pot_usdc"]) == 250.0
    for fid in fillers:
        assert snap["entries"][fid]["paid"] is True
        assert snap["entries"][fid]["ai_filler"] is True
        assert L.balance(f"afm_wallet_{fid}") == 575.00  # 600 faucet − 25 entry
    # the snapshot flags AI clubs so a dashboard can badge them
    assert all(d["is_filler"] is True for d in div if d["agent_id"] in fillers)


def test_real_joins_shrink_the_filler_count(_world):
    from gaming.src.stack.agentic.games.football_managers import season as S
    from gaming.src.stack.agentic.games.football_managers.club_store import (
        ensure_club_for_agent,
    )
    from gaming.src.stack.agentic.games.football_managers.agent_market import (
        create_manager_agent,
    )

    S.open_season(start_at=_now() + timedelta(hours=2))
    n_fill_1 = sum(1 for d in S.get_season()["division"] if d.get("is_filler"))

    # a brand-new real manager registers, queues, and takes a league slot
    S.reset_season()
    created = create_manager_agent(
        manager_name="Newcomer Manager", club_name="Newcomer FC"
    )
    S.join_season(created["agent"]["agent_id"])
    S.open_season(start_at=_now() + timedelta(hours=2))
    div = S.get_season()["division"]
    n_fill_2 = sum(1 for d in div if d.get("is_filler"))
    assert len(div) == 10
    assert n_fill_2 == n_fill_1 - 1
    assert created["agent"]["agent_id"] in [d["agent_id"] for d in div]


def test_explicit_ids_keep_exact_control(_world):
    from gaming.src.stack.agentic.games.football_managers import season as S

    S.open_season(
        agent_ids=["agent_bluelock_demo", "agent_aoashi_demo"],
        start_at=_now() + timedelta(hours=2),
    )
    snap = S.get_season()
    assert len(snap["division"]) == 2
    assert snap["matchdays_total"] == 30  # the derby path is untouched
    assert not any(d.get("is_filler") for d in snap["division"])


def test_fillers_play_and_are_auto_picked(_world):
    from gaming.src.stack.agentic.games.football_managers import club_store as CS
    from gaming.src.stack.agentic.games.football_managers import season as S

    # matchday 1 opens 7h before the tick, so it resolves on the first tick
    S.open_season(start_at=_now() - timedelta(hours=7))
    snap = S.get_season()
    assert len(snap["division"]) == 10  # 7 real + 3 fillers
    out = S.tick()
    assert out["resolved"] == [1]
    snap = S.get_season()
    assert snap["current_matchday"] == 2
    assert len(snap["recent"]) == 5  # 10 clubs → five fixtures per matchday
    # every filler fielded a legal locked XI: 11 men, exactly one keeper
    for d in snap["division"]:
        if not d.get("is_filler"):
            continue
        club = CS.get_club(d["agent_id"])
        assert len(club["starters"]) == 11
        assert sum(1 for p in club["starters"] if p["slot"] == "GK") == 1


def test_filler_squads_are_legal_solvent_and_deterministic(_world):
    from gaming.src.stack.agentic.games.football_managers import club_store as CS
    from gaming.src.stack.agentic.games.football_managers import fillers as F

    ids = F.top_up(3)
    assert len(ids) == 3
    for aid in ids:
        club = CS.get_club(aid)
        assert club["is_filler"] is True
        assert club["roster_size"] == 16
        assert [p["slot"] for p in club["squad"]].count("GK") == 2
        assert len(club["starters"]) == 11
        assert sum(1 for p in club["starters"] if p["slot"] == "GK") == 1
        # budget authority left after the committed squad — they can trade
        assert CS.transfer_balance(aid) > 0
        assert F.synthetic_wallet(aid).startswith("afm_wallet_ai_filler")
    # minting is idempotent: the same filler ids come back, same squads
    again = F.top_up(3)
    assert again == ids
    for a, b in zip(ids, again):
        assert CS.roster_ids(a) == CS.roster_ids(b)
