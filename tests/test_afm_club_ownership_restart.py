"""A deploy (process restart, manifest bump, re-seed) never costs a human
owner their club, squad, lineup or tactics.

Catalog ``owner_agent_id`` lives in memory: after a restart every rostered
player looked like a free agent until something re-claimed him, and nothing
did — so another club could sign a player already in someone's squad.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest


@pytest.fixture(autouse=True)
def _isolate_store(tmp_path, monkeypatch):
    monkeypatch.setenv("BOARDMAN_AGENTIC_DATA", str(tmp_path))
    yield
    from gaming.src.stack.agentic.games.football_managers import catalog as cat

    for p in cat.seed_catalog():
        cat.set_owner(p["player_id"], None)


def _restart():
    """What a fresh process sees: persisted clubs, an ownerless catalog."""
    from gaming.src.stack.agentic.games.football_managers import catalog as cat

    for p in cat.seed_catalog():
        cat.set_owner(p["player_id"], None)


@pytest.fixture()
def _world():
    from gaming.src.stack.agentic.games.football_managers.club_store import seed_demo_clubs
    from gaming.src.stack.agentic.registry import get_registry

    get_registry().ensure_demo_agents()
    seed_demo_clubs()


def test_reseed_after_restart_reclaims_every_rostered_player(_world):
    from gaming.src.stack.agentic.games.football_managers import catalog as cat
    from gaming.src.stack.agentic.games.football_managers import club_store as CS

    club = "agent_bluelock_demo"
    squad = CS.roster_ids(club)
    _restart()
    assert cat.get_player(squad[0])["owner_agent_id"] is None  # the bug's precondition
    CS.seed_demo_clubs()
    assert all(cat.get_player(pid)["owner_agent_id"] == club for pid in squad)
    free = {p["player_id"] for p in cat.list_players(free_only=True)}
    assert not free & set(squad)


def test_another_club_cannot_sign_a_rostered_player_after_restart(_world):
    from gaming.src.stack.agentic.games.football_managers import club_store as CS
    from gaming.src.stack.agentic.games.football_managers import market as M
    from gaming.src.stack.agentic.games.football_managers import season as S

    S.open_season(
        agent_ids=["agent_bluelock_demo", "agent_aoashi_demo"],
        start_at=datetime.now(timezone.utc) + timedelta(hours=2),
    )
    M.open_window(1, "mid", closes_at="soon")
    victim, raider = "agent_bluelock_demo", "agent_aoashi_demo"
    CS.adjust_budget(raider, Decimal("200.00"))
    target = CS.roster_ids(victim)[0]
    _restart()  # no re-seed: the season runner can act before any API call

    with pytest.raises(M.MarketError) as err:
        M.buy_free_agent(raider, target)
    assert "player_not_free" in str(err.value)
    with pytest.raises(ValueError):
        CS.move_player(target, from_agent=None, to_agent=raider)
    assert target in CS.roster_ids(victim) and target not in CS.roster_ids(raider)
    # the window's free-agent list does not offer him either
    tw = M.window_ask_payload(raider)
    assert target not in {p["player_id"] for p in tw["free_agents"]}


def test_human_lineup_tactics_and_club_survive_a_deploy(_world, monkeypatch):
    from gaming.src.stack.agentic import ledger as L
    from gaming.src.stack.agentic.games.football_managers import club_store as CS
    from gaming.src.stack.agentic.games.football_managers.agent_market import (
        list_market_agents,
        purchase_manager_agent,
    )
    from gaming.src.stack.agentic.registry import get_registry
    import gaming.src.stack.agentic.agents as agents_pkg

    aid = "agent_bluelock_demo"
    list_market_agents()
    L.credit("owner:alice", Decimal("25.00"), reason="test_deposit")
    purchase_manager_agent(agent_id=aid, buyer_id="alice")
    club = CS.get_club(aid)
    squad = [p["player_id"] for p in club["squad"]]
    starters = list(reversed(squad[:11]))
    CS.set_lineup(aid, formation="4-4-2", starters=starters, bench=squad[11:14], tactical_tags=["high_press"], set_by="alice")
    before = CS._state()["clubs"][aid]

    # deploy: new manifest version, fresh process, re-seed
    real = agents_pkg.load_demo_manifests
    monkeypatch.setattr(
        agents_pkg,
        "load_demo_manifests",
        lambda: [{**m, "version": "9.9.9"} if m["agent_id"] == aid else m for m in real()],
    )
    _restart()
    get_registry().ensure_demo_agents()
    CS.seed_demo_clubs()

    after = CS._state()["clubs"][aid]
    assert CS.club_owner_id(aid) == "alice"
    for key in ("club_name", "formation", "tactical_tags", "starters", "bench", "roster", "budget_usdc"):
        assert after[key] == before[key], key
