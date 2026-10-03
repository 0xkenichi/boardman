"""AFM P1 living layer — morale, form, development (the FM feel).

Phase 0 attributes never move; the living layer is the *state* half that
makes a season feel like Football Manager:

* a result moves the people, not just the table — winners lift, losers dent,
  and personal events (goals, assists, cards) move individuals more;
* updates are idempotent per fixture (a replayed resolve never double-applies);
* the engine consumes the lock-time snapshot — living morale overrides the
  static profile, development shifts the rating anchor — and measurably
  changes match outcomes;
* young legs grow with minutes, veterans fade;
* the matchday ask carries morale/form on a manager's OWN squad rows only
  (the opposition's rows stay clean of it — not observable);
* the season resolve actually feeds the layer (snapshot in, apply out).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from gaming.src.stack.agentic.games.football_managers import living as LV
from gaming.src.stack.agentic.games.football_managers import match_engine as M


@pytest.fixture(autouse=True)
def _isolate_store(tmp_path, monkeypatch):
    monkeypatch.setenv("BOARDMAN_AGENTIC_DATA", str(tmp_path))


@pytest.fixture(autouse=True)
def _no_demo_webhook_servers(monkeypatch):
    """Hermetic season resolves: neutralize fixed demo webhook URLs so a live
    dev-box manager server cannot decide (or slow) our season tick."""
    import gaming.src.stack.agentic.runtime.webhook as wh

    real = wh.webhook_url_for

    def neutral(agent):
        url = real(agent)
        return "" if url and ":1877" in url else url

    monkeypatch.setattr(wh, "webhook_url_for", neutral)


_XI_SLOTS = ["GK", "RB", "CB", "CB", "LB", "CDM", "CM", "CAM", "RW", "ST", "LW"]


def _squad(prefix: str, rating: float = 80.0):
    players: dict[str, dict] = {}
    xi: list[str] = []
    for i, slot in enumerate(_XI_SLOTS):
        pid = f"{prefix}_{i}"
        players[pid] = {"player_id": pid, "name": f"{prefix} {i}", "slot": slot,
                        "base_rating": rating, "form": 7.0}
        xi.append(pid)
    return xi, players


def _result(hg: int, ag: int, feed: list[dict] | None = None) -> dict:
    return {"home_goals": hg, "away_goals": ag, "feed": feed or []}


# ------------------------------------------------------- result → morale

def test_win_lifts_and_personal_events_lift_more():
    xi, _ = _squad("w")
    opp, _ = _squad("wo")
    feed = [
        {"type": "goal", "player_id": xi[9], "minute": 10, "extra": {"assist": xi[8]}},
        {"type": "goal", "player_id": xi[9], "minute": 40},
    ]
    out = LV.apply_matchday("md1_w", _result(2, 0, feed), xi, [], opp, [])
    assert out["applied"] is True

    st = LV.get_many(xi)
    # every winner lifts off the 0.72 default; the squad shares the joy
    assert all(s["morale"] > 0.72 for s in st.values())
    assert all(s["morale"] < 0.72 for s in LV.get_many(opp).values())
    # but the double scorer out-morales his assister out-morales the rest
    assert st[xi[9]]["morale"] > st[xi[8]]["morale"] > st[xi[0]]["morale"]
    # goals/assists are tallied on the career line, form trends above neutral
    assert st[xi[9]]["goals"] == 2 and st[xi[8]]["assists"] == 1
    assert st[xi[9]]["form"] > 6.5 and st[xi[0]]["form"] > 6.5


def test_loss_dents_and_a_red_dents_most():
    xi, _ = _squad("l")
    opp, _ = _squad("lo")
    feed = [{"type": "red", "player_id": xi[3], "minute": 30}]
    LV.apply_matchday("md1_l", _result(0, 2, feed), xi, [], opp, [])
    st = LV.get_many(xi)
    assert all(s["morale"] < 0.72 for s in st.values()), "a defeat dents everyone"
    worst = min(s["morale"] for k, s in st.items() if k != xi[3])
    assert st[xi[3]]["morale"] < worst, "the sent-off man suffers beyond the loss"
    assert st[xi[3]]["form"] < 6.5


def test_unused_bench_only_drifts():
    xi, _ = _squad("b")
    opp, _ = _squad("bo")
    bench = ["bench_man"]
    LV.apply_matchday("md1_b", _result(2, 0), xi, bench, opp, [])
    st = LV.get_many(xi + bench)
    # an unused sub still feels the win — but a fraction of it
    xi_morale = min(s["morale"] for pid, s in st.items() if pid != "bench_man")
    assert 0.72 < st["bench_man"]["morale"] < xi_morale
    assert st["bench_man"]["apps"] == 0


def test_apply_is_idempotent_per_fixture():
    xi, _ = _squad("i")
    opp, _ = _squad("io")
    feed = [{"type": "goal", "player_id": xi[9], "minute": 12}]
    first = LV.apply_matchday("md1_i", _result(1, 0, feed), xi, [], opp, [])
    after = LV.get_many(xi)
    replay = LV.apply_matchday("md1_i", _result(1, 0, feed), xi, [], opp, [])
    assert first["applied"] is True
    assert replay["applied"] is False
    assert LV.get_many(xi) == after, "a replayed resolve must never double-apply"


def test_snapshot_is_clamped_and_shaped():
    xi, _ = _squad("s")
    snap = LV.snapshot(xi)
    assert set(snap) == set(xi)
    for v in snap.values():
        assert set(v) == {"morale", "delta"}
        assert 0.35 <= v["morale"] <= 1.0
        assert -1.5 <= v["delta"] <= 2.5


# ------------------------------------------------------- engine consumes it

def test_engine_profiles_consume_living(monkeypatch):
    xi, players = _squad("p")
    monkeypatch.setattr(M, "get_player", lambda pid: players.get(pid))

    base = M._resolve_profiles(xi, [])
    hot = M._resolve_profiles(xi, [], living={pid: {"morale": 1.0, "delta": 1.5} for pid in xi})
    cold = M._resolve_profiles(xi, [], living={pid: {"morale": 0.35, "delta": -1.5} for pid in xi})

    # living morale overrides the static (form-derived) profile…
    assert base[xi[0]]["morale"] < 1.0
    assert hot[xi[0]]["morale"] == 1.0 and cold[xi[0]]["morale"] == 0.35
    # …and the development delta shifts the rating anchor into the attributes
    assert hot[xi[0]]["overall"] > base[xi[0]]["overall"] > cold[xi[0]]["overall"]


def test_living_changes_match_outcomes(monkeypatch):
    """Same squads, same tactics — only the living snapshot differs, and the
    results must follow the mood (FM's home 'on a run' effect)."""
    xi, players = _squad("o")
    monkeypatch.setattr(M, "get_player", lambda pid: players.get(pid))
    up = {"morale": 1.0, "delta": 0.0}
    dn = {"morale": 0.35, "delta": 0.0}

    def _home_goals(hot_home: bool, n: int = 30) -> int:
        h_liv = {p: up for p in xi} if hot_home else {p: dn for p in xi}
        a_liv = {p: dn for p in xi} if hot_home else {p: up for p in xi}
        goals = 0
        for i in range(n):
            r = M.simulate_match(
                f"living_outcome_hot_{int(hot_home)}_{i}",
                home_agent_id="home", away_agent_id="away",
                home_xi=xi, away_xi=xi, home_bench=[], away_bench=[],
                home_tactics={"formation": "4-3-3", "tags": ["balanced"]},
                away_tactics={"formation": "4-3-3", "tags": ["balanced"]},
                home_living=h_liv, away_living=a_liv,
            )
            goals += r.home_goals
        return goals

    hot = _home_goals(True)
    cold = _home_goals(False)
    assert hot > cold, "morale must move results, not just vibes"


# ------------------------------------------------------- development

def _pid_in_stage(stage: str, tries: int = 500) -> str:
    for i in range(tries):
        pid = f"dev_{stage}_{i}"
        if LV.stage(pid)[0] == stage:
            return pid
    raise AssertionError(f"no {stage} pid found in {tries} tries")


def test_development_young_grows_veterans_fade_minutes_scaled():
    young = _pid_in_stage("young")
    vet = _pid_in_stage("veteran")
    assert young != vet

    # both play the full 90 in winning fixtures
    LV.apply_matchday(
        "dev_full",
        _result(1, 0, [{"type": "goal", "player_id": young, "minute": 5}]),
        [young], [], [vet], [],
    )
    dy_full = LV.get(young)["delta"]
    dv_full = LV.get(vet)["delta"]
    assert dy_full > 0, "young legs with minutes grow"
    assert dv_full < 0, "veterans fade"

    # a 45-minute shift (past the 30' development gate) grows about half
    # as much as the full 90 — development scales with minutes on pitch
    LV.reset_all()
    LV.apply_matchday(
        "dev_cameo",
        _result(1, 0, [{"type": "substitution", "in": young, "off": "mate", "minute": 45}]),
        [young, "mate"], [], [], [],
    )
    dy_cameo = LV.get(young)["delta"]
    assert 0 < dy_cameo < dy_full / 1.8, "development scales with minutes on pitch"
    # the replaced starter is credited only his actual minutes
    assert LV.get("mate")["minutes"] == 45


def test_career_line_tallies_apps_minutes():
    xi, _ = _squad("c")
    opp, _ = _squad("co")
    feed = [{"type": "substitution", "in": "sub_on", "off": xi[7], "minute": 60}]
    LV.apply_matchday("md1_c", _result(1, 1, feed), xi, ["sub_on"], opp, ["co_sub"])
    started = LV.get(xi[7])
    came_on = LV.get("sub_on")
    rode_it_out = LV.get(xi[0])
    assert started["apps"] == 1 and started["minutes"] == 60
    assert came_on["apps"] == 1 and came_on["minutes"] == 30
    assert rode_it_out["apps"] == 1 and rode_it_out["minutes"] == 90


# ------------------------------------------------------- surfaces

def test_morale_form_map_defaults_and_known_pids():
    xi, _ = _squad("m")
    opp, _ = _squad("mo")
    LV.apply_matchday("md1_m", _result(1, 0), xi, [], opp, [])
    out = LV.morale_form_map(xi + ["stranger"])
    assert set(out) == set(xi) | {"stranger"}
    for v in out.values():
        assert set(v) == {"morale", "form"}
        assert 0.35 <= v["morale"] <= 1.0 and 4.0 <= v["form"] <= 9.5


def test_squad_view_carries_living_columns():
    from gaming.src.stack.agentic.games.football_managers import club_store as C
    from gaming.src.stack.agentic.registry import get_registry

    get_registry().ensure_demo_agents()
    clubs = C.seed_demo_clubs()
    rows = C.squad_view(clubs[0]["agent_id"])
    assert rows
    for r in rows:
        assert 0.35 <= r["morale"] <= 1.0
        assert 4.0 <= r["form"] <= 9.5
        career = r["career"]
        assert career["stage"] in ("young", "prime", "veteran")
        assert 18 <= career["age"] <= 40
        assert career["apps"] >= 0 and career["goals"] >= 0


def test_matchday_ask_carries_own_morale_form_only():
    from gaming.src.stack.agentic.games.football_managers.manager_protocol import (
        build_matchday_ask,
    )
    from gaming.src.stack.agentic.games.football_managers.club_store import seed_demo_clubs
    from gaming.src.stack.agentic.games.football_managers import season as S
    from gaming.src.stack.agentic.registry import get_registry

    get_registry().ensure_demo_agents()
    seed_demo_clubs()
    start = datetime.now(timezone.utc) + timedelta(hours=1)
    S.open_season(agent_ids=["agent_bluelock_demo", "agent_aoashi_demo"], start_at=start)
    season = S._state()["season"]

    ask = build_matchday_ask("agent_bluelock_demo", season, 1)
    assert ask is not None
    mine = ask["my_club"]["squad"]
    assert mine
    assert all({"morale", "form"} <= set(r) for r in mine)
    assert all(0.35 <= r["morale"] <= 1.0 and 4.0 <= r["form"] <= 9.5 for r in mine)
    # the opposition's rows stay clean — their mood is not observable
    assert all("morale" not in r and "form" not in r for r in ask["opposition"]["lineup"])


def test_season_resolve_feeds_the_living_layer():
    from gaming.src.stack.agentic.games.football_managers import season as S
    from gaming.src.stack.agentic.games.football_managers.club_store import seed_demo_clubs
    from gaming.src.stack.agentic.registry import get_registry
    from gaming.src.stack.agentic.store import load_json

    get_registry().ensure_demo_agents()
    seed_demo_clubs()
    start = datetime.now(timezone.utc) - timedelta(hours=7)
    S.open_season(agent_ids=["agent_bluelock_demo", "agent_aoashi_demo"], start_at=start)
    out = S.tick()
    assert out["resolved"] == [1]

    data = load_json("afm_living.json", {"players": {}, "applied": {}})
    assert data["applied"], "the resolved fixture must be recorded in the living store"
    states = [e["state"] for e in data["players"].values() if isinstance(e, dict) and "state" in e]
    assert states, "players who took part must now have living state"
    assert any(st["apps"] >= 1 for st in states), "match minutes must be tallied"
