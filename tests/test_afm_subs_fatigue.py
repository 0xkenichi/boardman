"""AFM P-0 acceptance: substitution realism + persistent fatigue.

Covers the two remaining engine Musts from the roadmap:

* **Sub-choice realism** — the known bug ("engine subbed a star off for a GK
  while winning 2-0") is fixed: a keeper never replaces an outfielder, and
  the match state drives the substitution (chasing → attackers on,
  protecting → fresh legs in defence/midfield). Every sub event carries
  `kind` (tactical/injury) and `match_type` (chasing/protecting/level).
* **Fatigue carries between fixtures (G4)** — `simulate_match` accepts
  `home_fatigue` / `away_fatigue` (condition 0..1 per player), starts those
  players at the carried condition instead of fresh legs, and returns the
  final condition of every involved player in `MatchResult.fatigue`. The
  season stores it per club (`record_match_fatigue`), feeds it into the next
  matchday (`current_condition`) and surfaces it to the manager in the
  matchday ask + squad screen.
"""
from __future__ import annotations

import pytest

from gaming.src.stack.agentic.games.football_managers import match_engine as M

_SLOTS = ["GK", "RB", "CB", "CB", "LB", "CDM", "CM", "CAM", "RW", "ST", "LW"]


def _squad(side: str, rating: float, bench_slots: list[str]) -> tuple[list[str], list[str], dict]:
    players: dict[str, dict] = {}
    xi: list[str] = []
    for i, slot in enumerate(_SLOTS):
        pid = f"{side}_xi_{i + 1}"
        players[pid] = {"player_id": pid, "name": f"{side} {i + 1}", "slot": slot,
                        "base_rating": rating, "form": 7.0}
        xi.append(pid)
    bench: list[str] = []
    for i, slot in enumerate(bench_slots):
        pid = f"{side}_bn_{i + 1}"
        players[pid] = {"player_id": pid, "name": f"{side} bench {i + 1}", "slot": slot,
                        "base_rating": rating, "form": 7.0}
        bench.append(pid)
    return xi, bench, players


# benches built to make the match-type assertion crisp: the strong home side
# can only send on defenders/mids, the weak away side only forwards.
_DEF_MID_BENCH = ["CB", "CM", "CDM", "LB", "RB"]
_FWD_BENCH = ["ST", "RW", "LW", "ST", "RW"]
_HOME_XI, _HOME_BN, _HOME_PL = _squad("h", 92.0, _DEF_MID_BENCH)
_AWAY_XI, _AWAY_BN, _AWAY_PL = _squad("a", 62.0, _FWD_BENCH)
_ALL_FAKE = {**_HOME_PL, **_AWAY_PL}


@pytest.fixture()
def _fake_players(monkeypatch):
    monkeypatch.setattr(M, "get_player", lambda pid: _ALL_FAKE.get(pid))


def _run(match_id: str, **kw) -> M.MatchResult:
    params = dict(
        home_xi=_HOME_XI, away_xi=_AWAY_XI,
        home_bench=_HOME_BN, away_bench=_AWAY_BN,
    )
    params.update(kw)
    return M.simulate_match(match_id, home_agent_id="home", away_agent_id="away", **params)


def _slot_of(pid: str) -> str:
    return str((_ALL_FAKE.get(pid) or {}).get("slot") or "").upper()


# --------------------------------------------------------------- subs


def test_keeper_never_replaces_an_outfielder(_fake_players):
    """The Mbappé-for-GK bug: no GK ever comes ON for an outfield player."""
    for i in range(25):
        d = _run(f"sub_gk_invariant_{i}").to_dict()
        for ev in d["feed"]:
            if ev.get("type") != "substitution":
                continue
            off, on = ev.get("off"), ev.get("on")
            assert off and on
            if _slot_of(on) == "GK":
                assert _slot_of(off) == "GK", (
                    f"seed {i}: GK {on} replaced outfielder {off} — the known sub bug"
                )


def test_sub_events_carry_kind_and_match_type(_fake_players):
    seen = {"kind": set(), "match_type": set()}
    found = 0
    for i in range(25):
        d = _run(f"sub_meta_{i}").to_dict()
        for ev in d["feed"]:
            if ev.get("type") == "substitution":
                found += 1
                assert ev.get("kind") in ("tactical", "injury")
                assert ev.get("match_type") in ("chasing", "protecting", "level")
                seen["kind"].add(ev["kind"])
                seen["match_type"].add(ev["match_type"])
    assert found > 0, "benches were provided but no substitutions happened"


def test_protecting_side_sends_on_defenders_not_attackers(_fake_players):
    """The strong home side leads most matches; when protecting, its bench
    (defenders/mids only) must be what comes on — never an attacker unless
    the bench is empty of everything else (it isn't, here)."""
    protecting_subs = 0
    for i in range(25):
        d = _run(f"sub_protect_{i}").to_dict()
        for ev in d["feed"]:
            if ev.get("type") != "substitution" or ev.get("side") != "home":
                continue
            if ev.get("match_type") == "protecting":
                protecting_subs += 1
                on_slot = _slot_of(ev["on"])
                assert on_slot in ("CB", "CM", "CDM", "LB", "RB"), (
                    f"seed {i}: protecting sub brought on an attacker ({on_slot})"
                )
    assert protecting_subs > 0, "home never made a protecting sub across 25 seeds"


def test_chasing_side_sends_on_attackers(_fake_players):
    """The weak away side trails most matches; when chasing, its bench
    (forwards only) must be what comes on."""
    chasing_subs = 0
    for i in range(25):
        d = _run(f"sub_chase_{i}").to_dict()
        for ev in d["feed"]:
            if ev.get("type") != "substitution" or ev.get("side") != "away":
                continue
            if ev.get("match_type") == "chasing":
                chasing_subs += 1
                on_slot = _slot_of(ev["on"])
                assert on_slot in ("ST", "RW", "LW"), (
                    f"seed {i}: chasing sub brought on a non-attacker ({on_slot})"
                )
    assert chasing_subs > 0, "away never made a chasing sub across 25 seeds"


# ------------------------------------------------------------- fatigue


def test_fatigue_kwarg_starts_players_tired_and_result_carries_final_condition(_fake_players):
    carried = {pid: 0.5 for pid in _HOME_XI}
    res = _run("fatigue_basic", home_fatigue=carried, away_fatigue={pid: 1.0 for pid in _AWAY_XI})
    d = res.to_dict()
    # every XI player ends the match below fresh: they started at 0.5 and drained
    final_home = d["fatigue"]["home"]
    for pid in _HOME_XI:
        assert pid in final_home
        assert final_home[pid] < 0.5, "a player starting at 0.5 cannot finish fresh"
    # a fresh side finishes below 1.0 too (fitness drains through the match)
    for pid in _AWAY_XI:
        assert d["fatigue"]["away"][pid] < 1.0


def test_fatigue_is_deterministic_per_match_id(_fake_players):
    carried = {pid: 0.7 for pid in _HOME_XI}
    a = _run("fatigue_det", home_fatigue=carried).to_dict()["fatigue"]
    b = _run("fatigue_det", home_fatigue=carried).to_dict()["fatigue"]
    assert a == b


def test_fatigued_side_scores_less_than_a_fresh_equal_side(_fake_players):
    """Tired legs must measurably hurt: an identical squad at condition 0.4
    scores fewer goals than a fresh one across seeds (home/away swapped to
    cancel home advantage)."""
    tired = {pid: 0.4 for pid in _HOME_XI}
    fresh = {pid: 1.0 for pid in _HOME_XI}

    def goals_sum(fatigue: dict) -> int:
        total = 0
        for i in range(30):
            if i % 2 == 0:
                d = _run(f"fatigue_goals_{fatigue['h_xi_1']}_{i}", home_fatigue=fatigue,
                         away_fatigue={pid: 1.0 for pid in _AWAY_XI}).to_dict()
                total += d["home_goals"]
            else:
                d = _run(f"fatigue_goals_{fatigue['h_xi_1']}_{i}", away_fatigue=fatigue,
                         home_fatigue={pid: 1.0 for pid in _AWAY_XI}).to_dict()
                total += d["away_goals"]
        return total

    assert goals_sum(tired) < goals_sum(fresh), "carried fatigue did not change outcomes"


# --------------------------------------------------- season integration


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
    from gaming.src.stack.agentic.games.football_managers.club_store import seed_demo_clubs

    seed_demo_clubs()
    return reg


def _now():
    from datetime import datetime, timezone

    return datetime.now(timezone.utc)


def test_season_carries_fatigue_into_next_matchday(_world, monkeypatch):
    """G4 end-to-end: MD1 stores each club's final condition; MD2's engine
    call receives it; the squad screen surfaces it."""
    from datetime import timedelta

    from gaming.src.stack.agentic.games.football_managers import season as S
    from gaming.src.stack.agentic.games.football_managers import match_engine as M
    from gaming.src.stack.agentic.games.football_managers import club_store as CS
    from gaming.src.stack.agentic.games.football_managers.club_store import (
        get_club,
        squad_view,
    )

    # freeze recovery so MD2 sees exactly what MD1's squads finished with
    monkeypatch.setattr(CS, "FATIGUE_RECOVERY", 0.0)

    real_sim = M.simulate_match
    seen_fatigue: list[dict] = []

    def spy_sim(mid, **kw):
        seen_fatigue.append({
            "home_fatigue": kw.get("home_fatigue"),
            "away_fatigue": kw.get("away_fatigue"),
        })
        return real_sim(mid, **kw)

    monkeypatch.setattr(M, "simulate_match", spy_sim)
    # two-club derby — no byes, so both clubs play every matchday
    S.open_season(
        agent_ids=["agent_bluelock_demo", "agent_aoashi_demo"],
        start_at=_now() - timedelta(hours=31),
    )
    S.tick()  # resolves MD1 + MD2 (both due)
    assert len(seen_fatigue) >= 2

    # MD1 ran fresh (no stored condition yet)
    assert seen_fatigue[0]["home_fatigue"] in (None, {})

    # MD2 ran with the condition stored from MD1: values in band, and at
    # least one player on the pitch below fresh (they played and drained)
    md2 = seen_fatigue[1]
    assert md2["home_fatigue"], "MD2 was not fed MD1's stored condition"
    assert all(0.05 <= v <= 1.0 for v in md2["home_fatigue"].values())
    assert any(v < 1.0 for v in md2["home_fatigue"].values())

    # the club store holds it and the squad screen exposes it
    bl = next(c for c in [get_club(a) for a in ("agent_bluelock_demo",)] if c)
    aid = bl["agent_id"]
    rows = squad_view(aid)
    played = [r for r in rows if r.get("condition") is not None]
    assert played, "squad view shows no carried condition"
    assert all(0.05 <= r["condition"] <= 1.0 for r in played)
    # a starter who played MD1 is tired (get_club rows are dicts)
    starter_ids = {
        (s["player_id"] if isinstance(s, dict) else str(s)) for s in (bl.get("starters") or [])
    }
    tired_starters = [r for r in played if r["player_id"] in starter_ids and r["condition"] < 1.0]
    assert tired_starters, "no starter carries a drained condition"


def test_condition_recovers_between_matchdays(_world):
    from gaming.src.stack.agentic.games.football_managers.club_store import (
        FATIGUE_RECOVERY,
        current_condition,
        record_match_fatigue,
    )

    aid = "agent_bluelock_demo"
    record_match_fatigue(aid, {"player_a": 0.4})
    cond = current_condition(aid)
    assert cond["player_a"] == pytest.approx(min(1.0, 0.4 + FATIGUE_RECOVERY))
    # unknown players come back fresh (absent from the map)
    assert "player_never_seen" not in cond
