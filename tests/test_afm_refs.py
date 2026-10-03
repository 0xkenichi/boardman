"""AFM referee & unexpected-events layer (arc L3) — the game is not fully predictable.

Covers:

* **Referee catalogue & assignment** — twelve named officials across six
  personas (steady / lenient / strict / lets-it-flow / no-nonsense /
  eases-off), assigned deterministically per fixture so the official can be
  announced pre-match without stored state;
* **Persona curves** — lets-it-flow tightens late, no-nonsense is strict
  early then eases, steady stays flat;
* **Hidden temperament** — a personality attribute (never in a profile or an
  ask) that decides who collects the cards;
* **Engine behavior** — a strict ref books far more than a lenient one on
  identical squads, volatile squads collect more cards than cold ones, the
  mean-preserving scales keep the league-wide rate calibrated, and the same
  seed is still byte-identical (referee included);
* **Surprise events** — rare, deterministic per (fixture, player) pre-match
  events absorbed by the living layer as morale dents, idempotent per
  fixture;
* **Season wiring** — the resolve names the official, applies surprises to
  the lock-time snapshot, records them in the matchday news, and flags a
  star-man injury.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from gaming.src.stack.agentic.games.football_managers import living as LV
from gaming.src.stack.agentic.games.football_managers import match_engine as M
from gaming.src.stack.agentic.games.football_managers import refs as R


@pytest.fixture(autouse=True)
def _isolate_store(tmp_path, monkeypatch):
    monkeypatch.setenv("BOARDMAN_AGENTIC_DATA", str(tmp_path))


_XI_SLOTS = ["GK", "RB", "CB", "CB", "LB", "CDM", "CM", "CAM", "RW", "ST", "LW"]
_STRICT = {"ref_id": "ref_x", "name": "Test Strict", "persona": "strict", "base": 0.5}
_LENIENT = {"ref_id": "ref_y", "name": "Test Lenient", "persona": "lenient", "base": 0.5}


def _squad(prefix: str, rating: float = 80.0, pids: list[str] | None = None):
    players: dict[str, dict] = {}
    xi: list[str] = []
    for i, slot in enumerate(_XI_SLOTS):
        pid = pids[i] if pids else f"{prefix}_{i}"
        players[pid] = {"player_id": pid, "name": pid, "slot": slot,
                        "base_rating": rating, "form": 7.0}
        xi.append(pid)
    return xi, players


def _run(match_id: str, home_xi, away_xi, players: dict, **kw) -> dict:
    orig = M.get_player
    M.get_player = lambda pid: players.get(pid)
    try:
        return M.simulate_match(
            match_id, home_agent_id="home", away_agent_id="away",
            home_xi=home_xi, away_xi=away_xi,
            home_tactics={"formation": "4-3-3", "tags": ["balanced"]},
            away_tactics={"formation": "4-3-3", "tags": ["balanced"]},
            **kw,
        ).to_dict()
    finally:
        M.get_player = orig


# ------------------------------------------------------- catalogue & assignment

def test_referee_assignment_is_deterministic_and_varied():
    a = R.referee_for("afm_season_1_md1_a_b")
    b = R.referee_for("afm_season_1_md1_a_b")
    assert a == b, "same fixture → same official (replays stay honest)"
    assert {"ref_id", "name", "persona", "base"} <= set(a)
    assert a["persona"] in R.PERSONAS

    names = {R.referee_for(f"ref_variety_{i}")["name"] for i in range(60)}
    assert len(names) >= 5, "a league of fixtures must see several officials"
    assert len(R.all_referees()) >= 10, "a real officiating roster"


def test_persona_curves_bend_the_right_way():
    ref = {"ref_id": "t", "name": "t", "persona": "steady", "base": 0.5}
    flow = {"ref_id": "t", "name": "t", "persona": "lets_it_flow", "base": 0.5}
    nonsense = {"ref_id": "t", "name": "t", "persona": "no_nonsense", "base": 0.5}

    # lets it flow: lenient early, tightens late
    assert R.strictness_at(flow, 80) > R.strictness_at(flow, 10) + 0.1
    # no nonsense: strict from minute one, eases off as the game settles
    assert R.strictness_at(nonsense, 10) > R.strictness_at(nonsense, 80) + 0.1
    # the extremes hold across the whole match; steady stays mid
    for m in (5, 30, 60, 85):
        assert R.strictness_at(_STRICT, m) > R.strictness_at(_LENIENT, m) + 0.3
        assert 0.3 < R.strictness_at(ref, m) < 0.7
    # tension (a tight late finish) only sharpens an official
    assert R.strictness_at(ref, 85, tension=True) > R.strictness_at(ref, 85)
    # everything clamped
    for m in range(0, 91, 5):
        for r in (ref, flow, nonsense):
            assert 0.05 <= R.strictness_at(r, m) <= 0.95


def test_card_scales_are_mean_preserving_and_personality_shaped():
    avg = {"ref_id": "t", "name": "t", "persona": "steady", "base": 0.5}
    y, r, fk = R.card_scales(avg, 45, False, 0.5)
    assert (y, r, fk) == (1.0, 1.0, 1.0), "average ref + average temper = today's calibration"

    y_len, _, _ = R.card_scales(_LENIENT, 45, False, 0.2)
    y_str, _, _ = R.card_scales(_STRICT, 45, False, 0.9)
    assert y_str > 1.4 and y_len < 0.65, "personality spreads the card rate around the mean"
    assert y_str < 2.0 and y_len > 0.3, "bounded so no XI gets stamped out of a game"


# ------------------------------------------------------- hidden temperament

def test_temperament_is_hidden_and_deterministic():
    from gaming.src.stack.agentic.games.football_managers.attributes import (
        derive_profile,
        temperament,
        temperament_label,
    )

    a = temperament("afm_pl_001")
    assert a == temperament("afm_pl_001"), "personality does not drift"
    assert 0.0 <= a <= 1.0
    assert temperament_label(a) in ("ice-cold", "composed", "competitive", "volatile")
    # hidden: never rides a derived profile or a squad row
    prof = derive_profile({"player_id": "afm_pl_001", "slot": "CM", "base_rating": 70})
    assert "temperament" not in prof


# ------------------------------------------------------- engine behavior

def _cards(d: dict) -> int:
    return sum(1 for e in d["feed"] if e["type"] in ("yellow", "red"))


def test_strict_ref_books_far_more_than_lenient_ref():
    xi, players = _squad("ref")
    opp, opp_players = _squad("refopp")
    all_p = {**players, **opp_players}
    strict = sum(_cards(_run(f"ref_strict_{i}", xi, opp, all_p, referee=_STRICT)) for i in range(25))
    lenient = sum(_cards(_run(f"ref_lenient_{i}", xi, opp, all_p, referee=_LENIENT)) for i in range(25))
    assert strict > lenient * 1.5, f"the whistle must follow the official: strict {strict} vs lenient {lenient}"
    assert 0 < lenient / 25 <= 6 and strict / 25 <= 12, "both extremes stay sane"
    # mean-preserving check: default referees keep today's league-wide rate
    default_cards = sum(_cards(_run(f"ref_default_rate_{i}", xi, opp, all_p)) for i in range(25))
    assert 2.0 <= default_cards / 25 <= 7.0, "average officials stay near the old calibration"


def test_referee_rides_the_result_and_replays_stay_identical():
    xi, players = _squad("ride")
    opp, opp_players = _squad("rideopp")
    all_p = {**players, **opp_players}
    d = _run("ref_ride_1", xi, opp, all_p, referee=_STRICT)
    assert d["referee"]["name"] == "Test Strict"
    # default path: the official is derived from the match id, deterministically
    a = _run("ref_default_1", xi, opp, all_p)
    b = _run("ref_default_1", xi, opp, all_p)
    assert a["referee"] == b["referee"] and a["feed"] == b["feed"]
    assert a["referee"]["persona"] in R.PERSONAS


def test_volatile_players_collect_more_cards_than_cold_ones():
    cold: list[str] = []
    hot: list[str] = []
    for i in range(400):
        pid = f"temp_{i}"
        t = __import__(
            "gaming.src.stack.agentic.games.football_managers.attributes",
            fromlist=["temperament"],
        ).temperament(pid)
        if t < 0.15 and len(cold) < 11:
            cold.append(pid)
        if t > 0.85 and len(hot) < 11:
            hot.append(pid)
        if len(cold) == 11 and len(hot) == 11:
            break
    assert len(cold) == 11 and len(hot) == 11, "extreme temperaments must exist on the roster"

    xi_cold, players_cold = _squad("c", pids=cold)
    xi_hot, players_hot = _squad("h", pids=hot)
    opp, opp_players = _squad("topp")
    hot_cards = sum(
        _cards(_run(f"temper_hot_{i}", xi_hot, opp, {**players_hot, **opp_players}, referee=_STRICT))
        for i in range(25)
    )
    cold_cards = sum(
        _cards(_run(f"temper_cold_{i}", xi_cold, opp, {**players_cold, **opp_players}, referee=_STRICT))
        for i in range(25)
    )
    # sent-off men stop fouling, which compresses the gap — it must still show
    assert hot_cards > cold_cards * 1.15, f"volatility must show: hot {hot_cards} vs cold {cold_cards}"


def test_second_yellow_still_sends_off():
    xi, players = _squad("disc")
    opp, opp_players = _squad("discopp")
    all_p = {**players, **opp_players}
    reds = []
    for i in range(25):
        d = _run(f"discipline_{i}", xi, opp, all_p, referee=_STRICT)
        yellows: dict[str, int] = {}
        match_reds: list[tuple[str, bool]] = []
        for e in d["feed"]:
            if e["type"] == "yellow" and e.get("player_id"):
                yellows[e["player_id"]] = yellows.get(e["player_id"], 0) + 1
            if e["type"] == "red" and e.get("player_id"):
                match_reds.append((e["player_id"], "second yellow" in e.get("text", "")))
        # a second-yellow red must follow two bookings of the same man —
        # checked against THIS match's bookings (reds accumulate across seeds)
        for pid, is_second in match_reds:
            if is_second:
                assert yellows.get(pid, 0) >= 2, "second-yellow reds only after two bookings"
        reds.extend(match_reds)
    assert reds, "a strict referee produces sendings-off across seeds"


# ------------------------------------------------------- surprise events

def test_surprise_events_are_rare_and_deterministic():
    a = R.surprise_for("md1", "afm_pl_001")
    assert a == R.surprise_for("md1", "afm_pl_001"), "same fixture, same player → same week"
    for mid, pid in (("md1", "afm_pl_001"), ("md2", "afm_pl_001")):
        ev = R.surprise_for(mid, pid)
        if ev:
            assert ev["kind"] in {e["kind"] for e in R.SURPRISE_TABLE}
            assert ev["label"] and isinstance(ev["dent"], (int, float))

    hits = sum(1 for i in range(500) if R.surprise_for(f"rate_{i}", "afm_pl_001"))
    assert 0.002 <= hits / 500 <= 0.06, "surprises stay rare — a drip, not a storm"
    # dent is a signed morale delta: bad weeks dent (negative), family joy lifts
    kinds = {e["kind"]: e["dent"] for e in R.SURPRISE_TABLE}
    assert kinds["family"] > 0 > kinds["personal"]


def test_living_absorbs_surprises_idempotently():
    events = {
        "p_bad": {"kind": "personal", "dent": -0.07, "label": "a personal matter"},
        "p_ill": {"kind": "illness", "dent": -0.06, "label": "a bug"},
        "p_joy": {"kind": "family", "dent": 0.04, "label": "a first child"},
    }
    out = LV.apply_surprises("md_sur_1", events)
    assert out["applied"] is True and out["players"] == 3
    st = LV.get_many(list(events))
    assert st["p_bad"]["morale"] < 0.72 and st["p_ill"]["morale"] < 0.72
    assert st["p_joy"]["morale"] > 0.72, "family joy lifts a man"
    replay = LV.apply_surprises("md_sur_1", events)
    assert replay["applied"] is False, "a replayed resolve never double-applies"
    assert LV.get_many(list(events)) == st


def test_season_resolve_names_the_referee_and_applies_surprises(monkeypatch):
    from gaming.src.stack.agentic.games.football_managers import season as S
    from gaming.src.stack.agentic.games.football_managers import refs as R
    from gaming.src.stack.agentic.games.football_managers.club_store import seed_demo_clubs
    from gaming.src.stack.agentic.registry import get_registry
    from gaming.src.stack.agentic.store import load_json

    # neutralize demo webhooks so the resolve is hermetic
    import gaming.src.stack.agentic.runtime.webhook as wh

    real = wh.webhook_url_for
    monkeypatch.setattr(
        wh, "webhook_url_for",
        lambda a: ("" if (u := real(a)) and ":1877" in u else u),
    )

    get_registry().ensure_demo_agents()
    seed_demo_clubs()

    # force the unexpected: everyone gets "a personal matter" this matchday
    forced = {"kind": "personal", "dent": -0.07, "label": "a personal matter kept him from training"}
    monkeypatch.setattr(R, "surprise_for", lambda mid, pid: dict(forced))

    start = datetime.now(timezone.utc) - timedelta(hours=7)
    S.open_season(agent_ids=["agent_bluelock_demo", "agent_aoashi_demo"], start_at=start)
    out = S.tick()
    assert out["resolved"] == [1]

    season = S._state()["season"]
    info = season["matchdays"]["1"]
    news = info.get("match_news") or []
    assert any(n["kind"] == "referee" for n in news), "the official is announced"
    assert sum(1 for n in news if n["kind"] == "personal") >= 11, "both XIs felt the week"

    # the persisted living state carries the dent past the fixture
    lv = load_json("afm_living.json", {"players": {}})["players"]
    dented = [
        st["state"]["morale"]
        for st in lv.values()
        if isinstance(st, dict) and st.get("state", {}).get("morale", 0.72) < 0.71
    ]
    assert dented, "the surprise dent lands in the living layer"
    assert info["results"][0]["referee"]["persona"] in R.PERSONAS

    # the news desk surfaces it
    items = S.matchday_news_items(1)
    assert any(i.get("kind") == "referee" for i in items)
    assert any(i.get("kind") == "personal" for i in items)


def test_star_injury_is_flagged_in_the_news(monkeypatch):
    from gaming.src.stack.agentic.games.football_managers import match_engine as ME
    from gaming.src.stack.agentic.games.football_managers import season as S
    from gaming.src.stack.agentic.games.football_managers.club_store import (
        get_club,
        get_player,
        seed_demo_clubs,
    )
    from gaming.src.stack.agentic.registry import get_registry

    import gaming.src.stack.agentic.runtime.webhook as wh

    real = wh.webhook_url_for
    monkeypatch.setattr(
        wh, "webhook_url_for",
        lambda a: ("" if (u := real(a)) and ":1877" in u else u),
    )

    get_registry().ensure_demo_agents()
    seed_demo_clubs()
    bl = next(c for c in [get_club(a) for a in ["agent_bluelock_demo"]] if c)
    # starters come back as full player dicts — work in ids
    star = max(
        (str(p["player_id"]) for p in bl["starters"]),
        key=lambda pid: float((get_player(pid) or {}).get("base_rating") or 0),
    )
    star_name = (get_player(star) or {}).get("name") or star

    real_sim = ME.simulate_match

    def star_down(mid, **kw):
        res = real_sim(mid, **kw).to_dict()
        side = "home" if kw.get("home_agent_id") == bl["agent_id"] else "away"
        res["feed"].append({
            "minute": 34, "type": "injury", "side": side, "player_id": star,
            "text": f"34' · injury: {star_name} needs treatment",
        })
        res["feed"].append({
            "minute": 34, "type": "substitution", "side": side,
            "off": star, "on": (kw.get("home_bench") or ["x"])[0], "kind": "injury",
            "text": "34' · forced change",
        })
        return type("R", (), {"to_dict": lambda self: res})()

    monkeypatch.setattr(ME, "simulate_match", star_down)

    start = datetime.now(timezone.utc) - timedelta(hours=7)
    S.open_season(agent_ids=["agent_bluelock_demo", "agent_aoashi_demo"], start_at=start)
    S.tick()

    items = S.matchday_news_items(1)
    blows = [i for i in items if i.get("kind") == "star_injury"]
    assert blows and star_name in blows[0]["answer"], "the star going down is a story"
