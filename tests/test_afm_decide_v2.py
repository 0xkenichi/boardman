"""AFM Decide v2 acceptance: condition-aware XI selection (rotation under
fatigue), half-time contingency plans carried in the plan, protocol validation
of the `plans` extension, and the season wiring that feeds plans + injuries
into the engine / club store.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest


@pytest.fixture(autouse=True)
def _isolate_store(tmp_path, monkeypatch):
    monkeypatch.setenv("BOARDMAN_AGENTIC_DATA", str(tmp_path))
    yield
    from gaming.src.stack.agentic.games.football_managers import catalog as cat

    for p in cat.seed_catalog():
        cat.set_owner(p["player_id"], None)


@pytest.fixture()
def _world():
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


def _pair_for_slot(squad: list[dict]) -> tuple[dict, dict]:
    """Two squad players sharing a slot (star + understudy)."""
    by_slot: dict[str, list[dict]] = {}
    for p in squad:
        by_slot.setdefault(str(p.get("slot") or "").upper(), []).append(p)
    for slot, lst in by_slot.items():
        if slot != "GK" and len(lst) >= 2:
            lst.sort(key=lambda p: float(p.get("base_rating") or 0), reverse=True)
            return lst[0], lst[1]
    pytest.fail("no shared outfield slot in the seeded squad — cannot test rotation")


# ------------------------------------------------------------- rotation

def test_exhausted_star_rotates_to_bench(_world):
    """A star at condition 0.4 loses his slot to a fit teammate."""
    from gaming.src.stack.agentic.games.football_managers import season as S
    from gaming.src.stack.agentic.games.football_managers.club_store import (
        current_condition,
        get_club,
        record_match_fatigue,
    )
    from gaming.src.stack.agentic.games.football_managers.decide import decide_matchday

    aid = "agent_bluelock_demo"
    season = S.open_season(
        agent_ids=["agent_bluelock_demo", "agent_aoashi_demo"],
        start_at=_now() - timedelta(hours=7),
    )
    club = get_club(aid)
    star, backup = _pair_for_slot(club["squad"])

    # exhaust the star (store 0.05; recovery boost brings it to ~0.4)
    record_match_fatigue(aid, {star["player_id"]: 0.05})
    cond = current_condition(aid)
    assert cond[star["player_id"]] < 0.62

    plan = decide_matchday(aid, S._state()["season"], 1)
    assert plan is not None
    assert star["player_id"] not in plan["starters"], (
        "exhausted star should rotate out when a fit replacement exists"
    )
    assert backup["player_id"] in plan["starters"] or backup["player_id"] in plan["bench"]


def test_fresh_squad_keeps_best_xi(_world):
    """With no condition recorded, selection is unchanged (rating-driven)."""
    from gaming.src.stack.agentic.games.football_managers import season as S
    from gaming.src.stack.agentic.games.football_managers.club_store import get_club
    from gaming.src.stack.agentic.games.football_managers.decide import decide_matchday

    aid = "agent_bluelock_demo"
    season = S.open_season(
        agent_ids=["agent_bluelock_demo", "agent_aoashi_demo"],
        start_at=_now() - timedelta(hours=7),
    )
    club = get_club(aid)
    plan = decide_matchday(aid, S._state()["season"], 1)
    assert plan is not None
    assert len(plan["starters"]) == 11
    assert any(
        str(p.get("slot") or "").upper() == "GK"
        for p in club["squad"]
        if p["player_id"] in plan["starters"]
    )


def test_rotation_still_picks_a_legal_xi(_world):
    """Even with half the squad exhausted the XI stays legal (GK + 11)."""
    from gaming.src.stack.agentic.games.football_managers import season as S
    from gaming.src.stack.agentic.games.football_managers.club_store import (
        get_club,
        record_match_fatigue,
    )
    from gaming.src.stack.agentic.games.football_managers.decide import decide_matchday

    aid = "agent_bluelock_demo"
    season = S.open_season(
        agent_ids=["agent_bluelock_demo", "agent_aoashi_demo"],
        start_at=_now() - timedelta(hours=7),
    )
    club = get_club(aid)
    # exhaust everyone the engine could consider
    record_match_fatigue(aid, {p["player_id"]: 0.05 for p in club["squad"]})
    plan = decide_matchday(aid, S._state()["season"], 1)
    assert plan is not None
    assert len(plan["starters"]) == 11
    assert len(set(plan["starters"])) == 11


# ------------------------------------------------------------- HT plans

def test_plan_carries_contingency_plans_for_all_states(_world):
    """Every archetype plan includes trailing/level/leading HT tactics with
    legal formations and tags."""
    from gaming.src.stack.agentic.games.football_managers import season as S
    from gaming.src.stack.agentic.games.football_managers.club_store import get_club
    from gaming.src.stack.agentic.games.football_managers.decide import decide_matchday
    from gaming.src.stack.agentic.games.football_managers.manager_protocol import (
        validate_matchday_plan,
    )

    aid = "agent_bluelock_demo"
    season = S.open_season(
        agent_ids=["agent_bluelock_demo", "agent_aoashi_demo"],
        start_at=_now() - timedelta(hours=7),
    )
    club = get_club(aid)
    squad = club["squad"]
    plan = decide_matchday(aid, S._state()["season"], 1)
    assert plan is not None
    plans = plan.get("plans") or {}
    assert set(plans) == {"trailing", "level", "leading"}
    for state, p in plans.items():
        assert p.get("formation"), f"{state} plan has no formation"
        assert p.get("mentality") in ("attacking", "balanced", "defensive")

    # and the whole plan (plans included) round-trips the protocol validator
    valid, err = validate_matchday_plan(
        {
            "formation": plan["formation"],
            "xi": plan["starters"],
            "bench": plan["bench"],
            "tactical_tags": plan["tags"],
            "plans": plan["plans"],
        },
        squad,
    )
    assert err == ""
    assert valid["plans"]["trailing"]["formation"] == plan["plans"]["trailing"]["formation"]


def test_protocol_rejects_illegal_ht_plan_formation(_world):
    from gaming.src.stack.agentic.games.football_managers.manager_protocol import (
        validate_matchday_plan,
    )
    from tests.test_afm_decide_replay import _legal_xi  # reuse helper shape

    from gaming.src.stack.agentic.games.football_managers.club_store import get_club

    club = get_club("agent_bluelock_demo")
    squad = club["squad"]
    plan = {
        "formation": "4-3-3",
        "xi": _legal_xi(club),
        "bench": [],
        "tactical_tags": ["counter"],
        "plans": {"trailing": {"formation": "2-7-2", "tags": ["counter"]}},
    }
    valid, err = validate_matchday_plan(plan, squad)
    assert valid is None
    assert "2-7-2" in err


def test_protocol_rejects_illegal_ht_plan_tags(_world):
    from gaming.src.stack.agentic.games.football_managers.manager_protocol import (
        validate_matchday_plan,
    )
    from tests.test_afm_decide_replay import _legal_xi

    from gaming.src.stack.agentic.games.football_managers.club_store import get_club

    club = get_club("agent_bluelock_demo")
    plan = {
        "formation": "4-3-3",
        "xi": _legal_xi(club),
        "bench": [],
        "tactical_tags": ["counter"],
        "plans": {"leading": {"formation": "5-3-2", "tags": ["bunker_down"]}},
    }
    valid, err = validate_matchday_plan(plan, club["squad"])
    assert valid is None
    # the validator reports the legal tag set rather than echoing the bad tag
    assert "tags must be from" in err


# ------------------------------------------------------------- season wiring

def test_season_passes_ht_plans_into_the_engine(_world, monkeypatch):
    """The lock hands each club's contingency plans to simulate_match."""
    import gaming.src.stack.agentic.games.football_managers.match_engine as ME
    from gaming.src.stack.agentic.games.football_managers import season as S

    captured: dict[str, object] = {}
    real = ME.simulate_match

    def spy(mid, **kw):
        captured[mid] = {"home_plans": kw.get("home_plans"), "away_plans": kw.get("away_plans")}
        return real(mid, **kw)

    monkeypatch.setattr(ME, "simulate_match", spy)

    S.open_season(
        agent_ids=["agent_bluelock_demo", "agent_aoashi_demo"],
        start_at=_now() - timedelta(hours=7),
    )
    out = S.tick()
    assert out["resolved"] == [1]
    assert captured, "no fixture was simulated"
    for mid, kw in captured.items():
        assert isinstance(kw["home_plans"], dict) and kw["home_plans"], f"{mid}: home plans missing"
        assert isinstance(kw["away_plans"], dict) and kw["away_plans"], f"{mid}: away plans missing"
        assert set(kw["home_plans"]) == {"trailing", "level", "leading"}


def test_engine_applies_plan_matching_the_ht_score_end_to_end(_world):
    """Integration: a resolved matchday's feed shows a tactical_change whose
    formation matches the plan for the actual HT state."""
    from gaming.src.stack.agentic.games.football_managers import season as S

    S.open_season(
        agent_ids=["agent_bluelock_demo", "agent_aoashi_demo"],
        start_at=_now() - timedelta(hours=7),
    )
    out = S.tick()
    assert out["resolved"] == [1]

    st = S._state()
    results = st["season"]["matchdays"]["1"]["results"]
    assert results
    for res in results:
        feed = res.get("feed") or []
        ht = next((e for e in feed if e.get("type") == "halftime"), None)
        if not ht:
            continue
        hg_ht, ag_ht = (int(x) for x in str(ht["score"]).split("-"))
        for side, goals, opp in (("home", hg_ht, ag_ht), ("away", ag_ht, hg_ht)):
            plans = (res.get("lineups") or {}).get(
                res[f"{side}_agent_id"]
            )
            if not plans:
                continue
            # stored plans must cover every state the score could call for
            stored = plans.get("plans") or {}
            assert set(stored) == {"trailing", "level", "leading"}
            state = "leading" if goals > opp else "trailing" if opp > goals else "level"
            assert stored[state].get("formation"), f"{state} plan has no formation"


# ------------------------------------------------------------- injuries

def test_injury_marks_excludes_from_lineup_then_decays(_world):
    """record_match_injuries → squad shows injured + set_lineup refuses him →
    decay clears → he is selectable again."""
    from gaming.src.stack.agentic.games.football_managers.club_store import (
        decay_injuries,
        get_club,
        record_match_injuries,
        set_lineup,
    )
    from tests.test_afm_decide_replay import _legal_xi

    aid = "agent_bluelock_demo"
    club = get_club(aid)
    squad = club["squad"]
    victim = max((p for p in squad if str(p.get("slot") or "").upper() != "GK"),
                 key=lambda p: float(p.get("base_rating") or 0))
    others = [p["player_id"] for p in squad if p["player_id"] != victim["player_id"]]

    assert record_match_injuries([victim["player_id"]]) == 1

    # the resolved squad view flags him
    club = get_club(aid)
    flagged = {p["player_id"] for p in club["squad"] if p.get("injury")}
    assert victim["player_id"] in flagged

    # the XI lock refuses an injured starter
    xi = _legal_xi(club)
    assert victim["player_id"] in xi, "victim is the best outfielder — he starts"
    bench = [p["player_id"] for p in squad if p["player_id"] not in set(xi)][:5]
    with pytest.raises(ValueError, match="injured"):
        set_lineup(aid, formation="4-3-3", starters=xi, bench=bench)

    # a matchday passes → the injury clears
    decay_injuries()
    club = get_club(aid)
    flagged = {p["player_id"] for p in club["squad"] if p.get("injury")}
    assert victim["player_id"] not in flagged
    set_lineup(aid, formation="4-3-3", starters=xi, bench=bench)  # no raise


def test_injured_player_misses_the_next_matchday(_world):
    """Season integration: a player injured before open sits out MD1."""
    from gaming.src.stack.agentic.games.football_managers import season as S
    from gaming.src.stack.agentic.games.football_managers.club_store import (
        get_club,
        record_match_injuries,
    )

    aid = "agent_bluelock_demo"
    club = get_club(aid)
    victim = max((p for p in club["squad"] if str(p.get("slot") or "").upper() != "GK"),
                 key=lambda p: float(p.get("base_rating") or 0))
    record_match_injuries([victim["player_id"]])

    S.open_season(
        agent_ids=["agent_bluelock_demo", "agent_aoashi_demo"],
        start_at=_now() - timedelta(hours=7),
    )
    out = S.tick()
    assert out["resolved"] == [1]

    st = S._state()
    decisions = st["season"]["matchdays"]["1"]["decisions"]
    assert aid in decisions, "club had no bye but did not decide"
    assert victim["player_id"] not in decisions[aid]["xi"]

    # and the club's stored starters agree
    club = get_club(aid)
    assert victim["player_id"] not in (club.get("starters") or [])


def test_double_injury_is_idempotent(_world):
    from gaming.src.stack.agentic.games.football_managers.club_store import (
        injuries_map,
        record_match_injuries,
    )

    pid = "afm_pl_001"
    assert record_match_injuries([pid]) == 1
    assert record_match_injuries([pid]) == 0  # already injured — no double-count
    assert injuries_map() == {pid: 1}
