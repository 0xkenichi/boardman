"""AFM clubs + tactics: agent-owned clubs, legal-lineup enforcement, engine bias."""
from __future__ import annotations

import os

import pytest


@pytest.fixture(autouse=True)
def _isolate_store(tmp_path, monkeypatch):
    monkeypatch.setenv("BOARDMAN_AGENTIC_DATA", str(tmp_path))
    yield
    # reset per-process catalog ownership between tests (in-memory only)
    from gaming.src.stack.agentic.games.football_managers import catalog as cat

    for p in cat.seed_catalog():
        cat.set_owner(p["player_id"], None)


def _seed():
    from gaming.src.stack.agentic.games.football_managers.club_store import (
        list_clubs,
        seed_demo_clubs,
    )

    seed_demo_clubs()
    return list_clubs()


def _club(clubs: list[dict], key: str) -> dict:
    return next(c for c in clubs if c["agent_id"].find(key) >= 0)


def test_seed_creates_budgeted_clubs_with_legal_xis():
    clubs = _seed()
    # demo AFM manager agents (Blue Lock + Ao Ashi + Match-Slice) each own a club
    assert len(clubs) >= 3
    # Raja/Nero are the chess duo — they never own AFM clubs or players
    for club in clubs:
        assert "raja" not in club["agent_id"] and "nero" not in club["agent_id"]
    owners: set[str] = set()
    for club in clubs:
        assert club["formation"] in {"4-3-3", "4-2-3-1", "3-5-2"}
        assert len(club["starters"]) == 11
        assert len(club["bench"]) <= 5
        slots = [str(p.get("slot") or "") for p in club["starters"]]
        assert sum(1 for s in slots if s == "GK") == 1, club["club_name"]
        # unique ownership across the whole universe
        for p in club["starters"] + club["bench"]:
            assert p["player_id"] not in owners
            owners.add(p["player_id"])
        # spend respects budget (+ 3-matchday wage runway)
        spend = float(club["spend_usdc"])
        assert spend <= float(club["budget_usdc"]) + 1e-6


def test_set_lineup_enforces_rules():
    clubs = _seed()
    bluelock = _club(clubs, "bluelock")
    roster = [p["player_id"] for p in bluelock["squad"]]
    from gaming.src.stack.agentic.games.football_managers.club_store import set_lineup

    # legal roundtrip
    out = set_lineup(
        bluelock["agent_id"],
        formation="4-4-2",
        starters=roster[:11],
        bench=roster[11:16],
        tactical_tags=["high_press"],
    )
    assert out["formation"] == "4-4-2"
    assert out["tactical_tags"] == ["high_press"]
    assert len(out["starters"]) == 11

    with pytest.raises(ValueError):
        set_lineup(bluelock["agent_id"], starters=roster[:10])  # not 11
    with pytest.raises(ValueError):
        set_lineup(bluelock["agent_id"], starters=roster[:11], bench=roster[11:16], formation="2-7-2")
    with pytest.raises(ValueError):
        set_lineup(bluelock["agent_id"], tactical_tags=["false_nine_wizard"])
    # no GK in the XI → refused
    gk_idx = next(i for i, p in enumerate(bluelock["starters"]) if p["slot"] == "GK")
    bad = list(roster[:11])
    swap = next(p["player_id"] for p in bluelock["squad"] if p["slot"] != "GK" and p["player_id"] not in bad)
    bad[gk_idx] = swap
    with pytest.raises(ValueError):
        set_lineup(bluelock["agent_id"], starters=bad)
    # stealing another club's player is refused
    aoashi = _club(clubs, "aoashi")
    stolen = aoashi["starters"][0]["player_id"]
    with pytest.raises(ValueError):
        set_lineup(bluelock["agent_id"], starters=[stolen] + list(roster[1:11]))


def test_engine_tactics_deterministic_and_biasing():
    from gaming.src.stack.agentic.games.football_managers.club_store import seed_demo_clubs
    from gaming.src.stack.agentic.games.football_managers.match_engine import simulate_match

    clubs = seed_demo_clubs()
    bluelock = _club(clubs, "bluelock")
    aoashi = _club(clubs, "aoashi")
    h = [p["player_id"] for p in bluelock["starters"]]
    a = [p["player_id"] for p in aoashi["starters"]]

    def run(home_tags: list[str], seed: str) -> dict:
        r = simulate_match(
            seed,
            home_agent_id="H",
            away_agent_id="A",
            home_xi=h,
            away_xi=a,
            home_tactics={"formation": bluelock["formation"], "tags": home_tags},
            away_tactics={"formation": aoashi["formation"], "tags": ["park_bus"]},
        )
        return r.to_dict()

    assert run(["balanced"], "afm_test_tactics") == run(["balanced"], "afm_test_tactics")

    # aggregate expected goals across many seeded matches: more aggressive
    # instructions must out-score defensive ones (same two XIs otherwise)
    def total_goals(tags: list[str]) -> int:
        return sum(int(run(tags, f"afm_agg_{tags[0]}_{i}")["home_goals"]) for i in range(50))

    press_goals = total_goals(["gegenpress"])
    bus_goals = total_goals(["park_bus"])
    assert press_goals > bus_goals, f"expected gegenpress ({press_goals}) > park_bus ({bus_goals})"
