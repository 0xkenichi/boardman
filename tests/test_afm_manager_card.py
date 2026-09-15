"""AFM manager detail card — playbook + ability radars and the season record.

Covers: playbook axes derived from the live strategy table (formation slot
shares, tag press, pick style), squad-ability axes from real derived
attributes (with the empty-squad fallback), and the per-matchday record
series folded from stored season results (outcomes, goals, xG, form string).
"""
from __future__ import annotations

import pytest

@pytest.fixture(autouse=True)
def _isolate_store(tmp_path, monkeypatch):
    monkeypatch.setenv("BOARDMAN_AGENTIC_DATA", str(tmp_path))
    yield
    from gaming.src.stack.agentic.games.football_managers import catalog as cat

    for p in cat.seed_catalog():
        cat.set_owner(p["player_id"], None)


def test_playbook_axes_reflect_the_strategy_table():
    from gaming.src.stack.agentic.games.football_managers.decide import STRATEGIES
    from gaming.src.stack.agentic.games.football_managers.manager_card import (
        PLAYBOOK_AXES,
        playbook_axes,
    )

    striker = playbook_axes("striker")
    prag = playbook_axes("pragmatist")
    tactician = playbook_axes("tactician")

    # all six axes present, all bounded 0-100
    for axes in (striker, prag, tactician):
        assert set(axes) == set(PLAYBOOK_AXES)
        assert all(0.0 <= v <= 100.0 for v in axes.values())

    # 3-4-3 has 4 of 10 outfield slots forward vs 5-3-2's 2 — attack must rank them
    assert striker["attack"] > prag["attack"]
    # 5-3-2 has 5 of 10 slots defensive vs 3-4-3's 3 — defence must rank them
    assert prag["defence"] > striker["defence"]
    # striker presses (gegenpress base) far harder than the low block
    assert striker["press"] > prag["press"]
    # striker picks by rating (stars over system); tactician by shape
    assert striker["stars"] > tactician["stars"]
    assert tactician["system"] > striker["system"]
    # pragmatist's reactive tag is a counter; striker's is a second press tag
    assert prag["counter"] > striker["counter"]


def test_playbook_axes_match_what_the_decide_loop_runs():
    """The radar is computed from decide.STRATEGIES itself, so it can never
    drift from the manager's real matchday behaviour."""
    from gaming.src.stack.agentic.games.football_managers.decide import STRATEGIES
    from gaming.src.stack.agentic.games.football_managers.manager_card import (
        playbook_axes,
        playbook_summary,
    )

    for arch, strat in STRATEGIES.items():
        summ = playbook_summary(arch)
        assert summ["formation"] == strat["formations"][0]
        assert summ["pick"] == strat["pick"]
        assert summ["base_tag"] == strat["tags"][0]
        axes = playbook_axes(arch)
        if strat["pick"] == "rating":
            assert axes["stars"] > axes["system"]
        else:
            assert axes["system"] > axes["stars"]


def test_ability_axes_average_real_squad_attributes():
    from gaming.src.stack.agentic.games.football_managers.agent_market import (
        create_manager_agent,
    )
    from gaming.src.stack.agentic.games.football_managers.attributes import derive_profile
    from gaming.src.stack.agentic.games.football_managers.club_store import get_club
    from gaming.src.stack.agentic.games.football_managers.manager_card import (
        ABILITY_AXES,
        ability_axes,
    )

    out = create_manager_agent(
        manager_name="Card City",
        archetype="tactician",
        owner_id="owner_card",
    )
    agent_id = out["agent"]["agent_id"]

    axes = ability_axes(agent_id)
    assert axes is not None
    assert set(axes) == set(ABILITY_AXES)
    assert all(0.0 <= v <= 100.0 for v in axes.values())

    # cross-check one axis against a hand-computed squad average: keeper axis
    # is the mean of every squad player's derived `gk` attribute (outfielders
    # sit at 20, the keeper near their base rating) — it must be well below a
    # pure-GK squad's, and the defence axis must beat the keeper axis for a
    # normal squad.
    club = get_club(agent_id) or {}
    squad = club.get("squad") or []
    assert squad, "created club should have a seeded squad"
    gk_mean = sum(derive_profile(p)["gk"] for p in squad) / len(squad)
    expected_keeper = round(max(0.0, min(100.0, gk_mean)), 1)
    assert axes["keeper"] == expected_keeper
    assert axes["defence"] > axes["keeper"]


def test_ability_axes_none_without_a_squad():
    from gaming.src.stack.agentic.games.football_managers.manager_card import (
        ability_axes,
    )

    assert ability_axes("agent_nobody_home") is None


def _seed_finished_matchday(agent_id: str, opponent_id: str, *, md: int = 1) -> None:
    """Store one resolved matchday result for the pair (engine-shaped result row)."""
    from gaming.src.stack.agentic.games.football_managers import season as S
    from gaming.src.stack.agentic.games.football_managers.league import schedule_season

    st = S._state()
    season = st.get("season")
    if season is None:
        S.open_season([agent_id, opponent_id], start_at=S._now())
        st = S._state()
        season = st["season"]
    sched = schedule_season(season["division"])
    fixtures = sched[md - 1]
    fx = next(f for f in fixtures if {f.home_agent_id, f.away_agent_id} == {agent_id, opponent_id})
    info = season["matchdays"].setdefault(str(md), {"status": "resolved", "results": []})
    info["results"].append(
        {
            "match_id": f"afm_season_{season['season_no']}_md{md}_{fx.home_agent_id}_{fx.away_agent_id}",
            "home_agent_id": fx.home_agent_id,
            "away_agent_id": fx.away_agent_id,
            "home_goals": 2,
            "away_goals": 1,
            "outcome": "home_win",
            "score": "2-1",
            "home_club": fx.home_agent_id,
            "away_club": fx.away_agent_id,
            "stats": {
                "shots_xg_home": 1.4,
                "shots_xg_away": 0.9,
            },
        }
    )
    st["season"] = season
    S._save(st)


def test_record_series_folds_stored_results():
    from gaming.src.stack.agentic.games.football_managers.agent_market import (
        create_manager_agent,
    )
    from gaming.src.stack.agentic.games.football_managers.manager_card import (
        record_series,
    )

    me = create_manager_agent(manager_name="Chart FC", archetype="striker", owner_id="owner_chart")["agent"]["agent_id"]
    opp = create_manager_agent(manager_name="Chart Rivals", archetype="tactician", owner_id="owner_chart2")["agent"]["agent_id"]

    _seed_finished_matchday(me, opp, md=1)

    rec = record_series(me)
    assert rec["totals"]["played"] == 1
    assert rec["totals"]["wins"] == 1
    assert rec["totals"]["points"] == 3
    assert rec["form"] == "W"
    m = rec["matches"][0]
    assert m["matchday"] == 1
    assert m["opponent_id"] == opp
    assert (m["gf"], m["ga"]) == (2, 1)
    # xG is read from the stored per-shot fold (home side had 1.4)
    assert m["xg_for"] == 1.4 and m["xg_against"] == 0.9

    # the loser's card mirrors it from the same stored result
    rec_opp = record_series(opp)
    assert rec_opp["totals"]["losses"] == 1
    assert rec_opp["form"] == "L"
    assert (rec_opp["matches"][0]["xg_for"], rec_opp["matches"][0]["xg_against"]) == (0.9, 1.4)


def test_record_series_empty_for_a_fresh_manager():
    from gaming.src.stack.agentic.games.football_managers.agent_market import (
        create_manager_agent,
    )
    from gaming.src.stack.agentic.games.football_managers.manager_card import (
        record_series,
    )

    fresh = create_manager_agent(manager_name="No Games FC", owner_id="owner_fresh")["agent"]["agent_id"]
    rec = record_series(fresh)
    assert rec["matches"] == []
    assert rec["totals"]["played"] == 0
    assert rec["form"] == ""


def test_market_row_embeds_the_card(_isolate_store):
    from gaming.src.stack.agentic.games.football_managers.agent_market import (
        create_manager_agent,
    )

    out = create_manager_agent(manager_name="Carded United", archetype="pragmatist", owner_id="owner_carded")
    card = out["agent"]["card"]
    assert card["playbook"]["summary"]["formation"] == "5-3-2"
    assert set(card["playbook"]["axes"]) == {"attack", "press", "defence", "counter", "system", "stars"}
    assert card["record"]["totals"]["played"] == 0
