"""AFM manager protocol — the House asks a manager for its matchday plan.

Covers the ask payload (opposition lineup visible, hidden sliders never
leaked), plan validation (hard rules), `decide_from_ask` archetype behavior,
a live webhook ask→reply round trip through a real season tick, the
deterministic fallback when a webhook is unreachable, and the demo manager
server handlers (Blue Lock / Ao Ashi / Match-Slice).
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

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
    from gaming.src.stack.agentic.games.football_managers.club_store import (
        seed_demo_clubs,
    )
    from gaming.src.stack.agentic.registry import get_registry

    get_registry().ensure_demo_agents()
    seed_demo_clubs()
    return {"registry": get_registry()}


def _register(agent_id: str, *, webhook_url: str = "", archetype: str = "tactician"):
    from gaming.src.stack.agentic.registry import get_registry

    return get_registry().register_agent(
        agent_id=agent_id,
        name=agent_id.replace("_", " ").title(),
        owner_id=f"owner_{agent_id}",
        creator_id=f"creator_{agent_id}",
        strategy_id=f"{archetype}_playbook",
        openings=[],
        mind={"archetype": archetype, "directive": "Run the club."},
        game_ids=["agentic.football_managers"],
        seed=f"boardman.agent.afm.{agent_id}",
        version="1.0.0",
        webhook_url=webhook_url or None,
        runtime={"engine": "boardman.afm.v1", "webhook_url": webhook_url or None},
    )


def _season_pending(*agent_ids: str) -> dict:
    """Open a season that starts in the future (MD1 open but not decided)."""
    from gaming.src.stack.agentic.games.football_managers import season as S

    start = datetime.now(timezone.utc) + timedelta(hours=1)
    S.open_season(agent_ids=list(agent_ids), start_at=start)
    return S._state()["season"]


def _play_season(*agent_ids: str) -> dict:
    """Open a season in the past and tick through MD1."""
    from gaming.src.stack.agentic.games.football_managers import season as S

    start = datetime.now(timezone.utc) - timedelta(hours=7)
    S.open_season(agent_ids=list(agent_ids), start_at=start)
    out = S.tick()
    assert out["resolved"] == [1]
    return S._state()["season"]


# ---------------------------------------------------------------- the ask

def test_ask_exposes_opposition_lineup_but_never_hidden_sliders(_world):
    from gaming.src.stack.agentic.games.football_managers.manager_protocol import (
        build_matchday_ask,
    )

    season = _season_pending("agent_bluelock_demo", "agent_aoashi_demo")
    ask = build_matchday_ask("agent_bluelock_demo", season, 1)
    assert ask is not None
    assert ask["protocol"] == "boardman.agent.football_managers.matchday.v1"
    assert ask["matchday"] == 1

    opp = ask["opposition"]
    assert opp["agent_id"] == "agent_aoashi_demo"
    assert len(opp["lineup"]) == 11
    assert {"player_id", "name", "position", "rating"} <= set(opp["lineup"][0])
    assert opp["formation"] in ask["legal"]["formations"]

    my = ask["my_club"]
    assert len(my["squad"]) >= 11
    assert "points" in my["record"] and "wins" in my["record"]
    assert "wallet_usdc" in my

    # the opponent's hidden mind sliders must never leave the agent
    blob = json.dumps(ask)
    assert "aggression" not in blob
    assert "counterpunch" not in blob
    # ...and their mind directive isn't shipped to a competitor either
    assert "directive" not in blob


def test_ask_legal_block_carries_the_rules(_world):
    from gaming.src.stack.agentic.games.football_managers.manager_protocol import (
        build_matchday_ask,
    )

    season = _season_pending("agent_bluelock_demo", "agent_aoashi_demo")
    ask = build_matchday_ask("agent_aoashi_demo", season, 1)
    assert ask["legal"]["starters"] == 11
    assert ask["legal"]["max_bench"] == 5
    assert ask["legal"]["formations"]  # non-empty whitelist
    assert ask["legal"]["tactical_tags"]
    assert "deadline" in ask["legal"]


def test_ask_none_on_bye(_world):
    """A 3-club round robin gives one club a bye on MD1 — no ask for it."""
    from gaming.src.stack.agentic.games.football_managers.club_store import (
        ensure_club_for_agent,
    )
    from gaming.src.stack.agentic.games.football_managers.manager_protocol import (
        build_matchday_ask,
    )

    _register("agent_third_club")
    ensure_club_for_agent("agent_third_club")
    season = _season_pending("agent_bluelock_demo", "agent_aoashi_demo", "agent_third_club")
    asked = {
        aid: build_matchday_ask(aid, season, 1) is not None
        for aid in ("agent_bluelock_demo", "agent_aoashi_demo", "agent_third_club")
    }
    # exactly the two clubs in the MD1 fixture get asked
    assert sum(asked.values()) == 2


# ---------------------------------------------------------------- validation

def _squad(agent_id: str) -> list[dict]:
    from gaming.src.stack.agentic.games.football_managers.club_store import get_club

    return [p for p in (get_club(agent_id) or {}).get("squad") or [] if isinstance(p, dict)]


def _legal_plan() -> dict:
    from gaming.src.stack.agentic.games.football_managers.decide import decide_from_ask
    from gaming.src.stack.agentic.games.football_managers.manager_protocol import (
        build_matchday_ask,
    )

    season = _season_pending("agent_bluelock_demo", "agent_aoashi_demo")
    ask = build_matchday_ask("agent_bluelock_demo", season, 1)
    return decide_from_ask("striker", ask)


def test_validate_accepts_a_legal_plan(_world):
    from gaming.src.stack.agentic.games.football_managers.manager_protocol import (
        validate_matchday_plan,
    )

    plan = _legal_plan()
    valid, err = validate_matchday_plan(plan, _squad("agent_bluelock_demo"))
    assert err == ""
    assert valid["formation"] == plan["formation"]
    assert len(valid["starters"]) == 11
    # v1.4: the deterministic decide now emits a one-line instructions note;
    # validation passes it through unchanged
    assert valid["instructions"] == plan.get("instructions")


@pytest.mark.parametrize(
    "mutate, expect",
    [
        ("xi_12", "exactly 11"),
        ("xi_dup", "duplicate"),
        ("xi_foreign", "not in the squad"),
        ("no_gk", "no goalkeeper"),
        ("bench_overlap", "overlaps"),
        ("bench_6", "at most 5"),
        ("bad_formation", "unknown formation"),
        ("bad_tag", "tactical_tags"),
    ],
)
def test_validate_rejects_illegal_plans(_world, mutate, expect):
    from gaming.src.stack.agentic.games.football_managers.manager_protocol import (
        validate_matchday_plan,
    )

    squad = _squad("agent_bluelock_demo")
    by_id = {p["player_id"]: p for p in squad}
    plan = _legal_plan()
    xi = list(plan["starters"])
    bench = list(plan["bench"])
    gk = next(pid for pid in xi if str(by_id[pid].get("slot") or "").upper() == "GK")
    non_gk = next(
        pid for pid in xi if str(by_id[pid].get("slot") or "").upper() != "GK"
    )
    # demo clubs hold exactly XI + bench — an outsider is any catalog player
    # not in this club's squad (the XI/Bench whitelist must reject them)
    from gaming.src.stack.agentic.games.football_managers.catalog import list_players

    outsider = next(
        p["player_id"]
        for p in list_players()
        if p["player_id"] not in set(xi) | set(bench)
    )

    if mutate == "xi_12":
        plan["xi"] = xi + [gk]
    elif mutate == "xi_dup":
        plan["xi"] = xi[:10] + [xi[0]]
    elif mutate == "xi_foreign":
        plan["xi"] = [outsider] + xi[1:]
    elif mutate == "no_gk":
        # swap the GK out for a bench non-GK → 11 squad players, no keeper
        replacement = next(pid for pid in bench if str(by_id[pid].get("slot") or "").upper() != "GK")
        plan["xi"] = [replacement if pid == gk else pid for pid in xi]
    elif mutate == "bench_overlap":
        plan["bench"] = [gk]
    elif mutate == "bench_6":
        # pad to exactly 6 in-squad bench entries (length rule fires first)
        pool = [p["player_id"] for p in squad if p["player_id"] not in set(bench)]
        plan["bench"] = (bench + pool)[:6]
    elif mutate == "bad_formation":
        plan["formation"] = "2-7-2"
    elif mutate == "bad_tag":
        plan["tactical_tags"] = ["bunker_down"]
    valid, err = validate_matchday_plan(plan, squad)
    assert valid is None
    assert expect in err


def test_validate_rejects_non_dict_reply(_world):
    from gaming.src.stack.agentic.games.football_managers.manager_protocol import (
        validate_matchday_plan,
    )

    valid, err = validate_matchday_plan("not-a-plan", _squad("agent_bluelock_demo"))
    assert valid is None and "plan object" in err


# ---------------------------------------------------------------- decide_from_ask

def _synthetic_ask(
    *,
    my_pts: int = 0,
    opp_pts: int = 0,
    my_rating: int = 88,
    opp_rating: int = 70,
    opp_tag: str = "balanced",
) -> dict:
    """A controlled ask: 16-player squad + 11-man opposition lineup."""
    pos_pool = [
        "GK", "GK", "CB", "CB", "CB", "RB", "LB",
        "CDM", "CDM", "CM", "CM", "CAM", "RW", "LW", "ST", "ST",
    ]
    squad = [
        {"player_id": f"p{i}", "name": f"Player {i}", "position": pos, "rating": my_rating}
        for i, pos in enumerate(pos_pool)
    ]
    opp = [
        {"player_id": f"o{i}", "name": f"Opp {i}", "position": pos, "rating": opp_rating}
        for i, pos in enumerate(pos_pool[:11])
    ]
    return {
        "my_club": {"squad": squad, "record": {"points": my_pts}},
        "opposition": {
            "lineup": opp,
            "tactical_tags": [opp_tag],
            "record": {"points": opp_pts},
        },
    }


def test_decide_from_ask_follows_archetype(_world):
    from gaming.src.stack.agentic.games.football_managers.decide import decide_from_ask

    ask = _synthetic_ask()  # we are clearly stronger — base shapes + tags
    plans = {
        arch: decide_from_ask(arch, ask)
        for arch in ("striker", "tactician", "pragmatist", "possession")
    }
    for plan in plans.values():
        assert len(plan["starters"]) == 11
        assert set(plan["starters"]).isdisjoint(plan["bench"])
    assert plans["striker"]["formation"] == "3-4-3"  # attack-first
    assert plans["striker"]["tags"] == ["gegenpress"]  # never parks the bus
    assert plans["tactician"]["formation"] == "4-2-3-1"
    assert plans["tactician"]["tags"] == ["tiki_taka"]
    assert plans["pragmatist"]["formation"] == "5-3-2"
    assert plans["pragmatist"]["tags"] == ["low_block"]
    assert plans["possession"]["formation"] == "4-3-3"
    assert plans["possession"]["tags"] == ["tiki_taka"]

    # trailing against a side with more points → every manager adapts
    trailing = _synthetic_ask(opp_pts=9)
    t_striker = decide_from_ask("striker", trailing)
    t_tactician = decide_from_ask("tactician", trailing)
    t_prag = decide_from_ask("pragmatist", trailing)
    assert t_striker["formation"] == "4-3-3"  # formations[1] under pressure
    assert t_striker["tags"] == ["gegenpress"]  # striker still presses
    assert t_tactician["tags"] == ["counter"]  # system managers go reactive
    assert t_prag["tags"] == ["counter"]

    # an aggressive opponent flips the reactive tag even when ahead
    pressed = _synthetic_ask(opp_tag="gegenpress")
    assert decide_from_ask("tactician", pressed)["tags"] == ["counter"]
    assert decide_from_ask("possession", pressed)["tags"] == ["counter"]
    # ...but the striker answers pressure with more pressure, not a bus
    assert decide_from_ask("striker", pressed)["tags"] == ["gegenpress"]


# ---------------------------------------------------------------- live round trip

class _FakeBuilder:
    """A builder-hosted manager webhook: answers asks from the ask payload."""

    def __init__(self, archetype: str = "striker"):
        self.received: list[dict] = []
        self._archetype = archetype

        class Handler(BaseHTTPRequestHandler):
            def do_POST(inner_self):  # noqa: N805
                n = int(inner_self.headers.get("Content-Length") or 0)
                body = json.loads(inner_self.rfile.read(n).decode("utf-8") or "{}")
                self.received.append(body)
                plan = self._plan_for(body)
                reply = json.dumps(
                    {
                        "move": {
                            "formation": plan["formation"],
                            "xi": plan["starters"],
                            "bench": plan["bench"],
                            "tactical_tags": plan["tags"],
                            "instructions": "test-instruction",
                        }
                    }
                ).encode()
                inner_self.send_response(200)
                inner_self.send_header("Content-Type", "application/json")
                inner_self.send_header("Content-Length", str(len(reply)))
                inner_self.end_headers()
                inner_self.wfile.write(reply)

            def log_message(inner_self, *args):  # noqa: N805
                pass

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._thread = Thread(target=self._server.serve_forever, daemon=True)

    def _plan_for(self, ask: dict) -> dict:
        from gaming.src.stack.agentic.games.football_managers.decide import (
            decide_from_ask,
        )

        return decide_from_ask(self._archetype, ask)

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, *exc):
        self._server.shutdown()
        self._thread.join()

    @property
    def url(self) -> str:
        host, port = self._server.server_address
        return f"http://{host}:{port}"


def test_live_webhook_round_trip_through_a_season(_world):
    """A real HTTP ask→reply: the webhook manager's plan is locked and recorded."""
    from gaming.src.stack.agentic.games.football_managers.club_store import (
        ensure_club_for_agent,
    )

    with _FakeBuilder(archetype="striker") as builder:
        _register("agent_webhook_test", webhook_url=builder.url)
        ensure_club_for_agent("agent_webhook_test")
        season = _play_season("agent_bluelock_demo", "agent_webhook_test")

    decisions = season["matchdays"]["1"]["decisions"]
    web = decisions["agent_webhook_test"]
    assert web["source"] == "webhook"
    assert web["instructions"] == "test-instruction"
    assert len(web["xi"]) == 11
    # the deterministic side still ran (bluelock has no live server here)
    assert decisions["agent_bluelock_demo"]["source"] == "auto"

    # the builder saw the opposition lineup in the ask, not the sliders
    assert builder.received, "the House never asked the webhook"
    ask = builder.received[0]
    assert ask["fixture"]["opponent"] == "agent_bluelock_demo"
    assert len(ask["opposition"]["lineup"]) == 11
    assert "aggression" not in json.dumps(ask)


def test_unreachable_webhook_falls_back_to_deterministic(_world):
    from gaming.src.stack.agentic.games.football_managers.club_store import (
        ensure_club_for_agent,
    )

    _register("agent_dead_webhook", webhook_url="http://127.0.0.1:1")
    ensure_club_for_agent("agent_dead_webhook")
    season = _play_season("agent_bluelock_demo", "agent_dead_webhook")

    decisions = season["matchdays"]["1"]["decisions"]
    dead = decisions["agent_dead_webhook"]
    assert dead["source"] == "auto"
    assert "no reply" in (dead.get("note") or "")
    assert len(dead["xi"]) == 11  # a dead webhook never defaults the club


def test_malformed_reply_falls_back_to_deterministic(_world):
    """A webhook that answers garbage still yields a legal locked XI."""
    from gaming.src.stack.agentic.games.football_managers.club_store import (
        ensure_club_for_agent,
    )

    class GarbageHandler(BaseHTTPRequestHandler):
        def do_POST(inner_self):  # noqa: N805
            n = int(inner_self.headers.get("Content-Length") or 0)
            inner_self.rfile.read(n)
            reply = json.dumps({"move": {"formation": "2-7-2", "xi": []}}).encode()
            inner_self.send_response(200)
            inner_self.send_header("Content-Type", "application/json")
            inner_self.send_header("Content-Length", str(len(reply)))
            inner_self.end_headers()
            inner_self.wfile.write(reply)

        def log_message(inner_self, *args):  # noqa: N805
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), GarbageHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        _register("agent_garbage_webhook", webhook_url=f"http://{host}:{port}")
        ensure_club_for_agent("agent_garbage_webhook")
        season = _play_season("agent_bluelock_demo", "agent_garbage_webhook")
    finally:
        server.shutdown()
        thread.join()

    decisions = season["matchdays"]["1"]["decisions"]
    bad = decisions["agent_garbage_webhook"]
    assert bad["source"] == "auto"
    assert "unknown formation" in (bad.get("note") or "")
    assert len(bad["xi"]) == 11


# ---------------------------------------------------------------- webhook binding

def test_owner_sets_and_clears_manager_webhook(_world):
    from gaming.src.stack.agentic.games.football_managers.agent_market import (
        set_manager_webhook,
    )
    from gaming.src.stack.agentic.registry import get_registry

    _register("agent_hooked")
    reg = get_registry()
    owner = f"owner_agent_hooked"

    # only the owner can point the manager at a webhook
    with pytest.raises(ValueError, match="only the current owner"):
        set_manager_webhook(agent_id="agent_hooked", webhook_url="http://x", owner_id="intruder")

    out = set_manager_webhook(
        agent_id="agent_hooked", webhook_url="https://builder.example/move", owner_id=owner
    )
    assert out["agent"]["webhook_url"] == "https://builder.example/move"
    rec = reg.get_agent("agent_hooked")
    assert rec["webhook_url"] == "https://builder.example/move"
    assert (rec.get("runtime") or {}).get("webhook_url") == "https://builder.example/move"
    # the binding is logged on the manager's market history
    kinds = [e["kind"] for e in (rec.get("market_history") or [])]
    assert "webhook_set" in kinds

    # bad URLs are rejected, clearing is allowed
    with pytest.raises(ValueError, match="must be a full"):
        set_manager_webhook(agent_id="agent_hooked", webhook_url="not-a-url", owner_id=owner)
    cleared = set_manager_webhook(agent_id="agent_hooked", webhook_url="", owner_id=owner)
    assert cleared["agent"]["webhook_url"] is None
    assert reg.get_agent("agent_hooked")["webhook_url"] is None


def test_webhook_sourced_decision_reaches_the_owner_dashboard(_world):
    """The dashboard surfaces where the plan came from + the manager's words."""
    from gaming.src.stack.agentic.games.football_managers.club_store import (
        ensure_club_for_agent,
    )
    from gaming.src.stack.agentic.games.football_managers.dashboard import (
        owner_dashboard,
    )

    with _FakeBuilder(archetype="striker") as builder:
        _register("agent_webhook_test", webhook_url=builder.url)
        ensure_club_for_agent("agent_webhook_test")
        _play_season("agent_bluelock_demo", "agent_webhook_test")

    dash = owner_dashboard("agent_webhook_test")
    assert dash["results"], "expected a played fixture"
    dec = dash["results"][0]["decision"]
    assert dec["source"] == "webhook"
    assert dec["instructions"] == "test-instruction"
    # the deterministic side is labelled differently
    other = owner_dashboard("agent_bluelock_demo")
    assert other["results"][0]["decision"]["source"] == "auto"
    assert other["results"][0]["decision"]["instructions"] is None


# ---------------------------------------------------------------- demo servers

def test_demo_servers_answer_with_their_archetype(_world):
    from gaming.src.stack.agentic.agents.aoashi.runtime import (
        handle_webhook as aoashi_handle,
    )
    from gaming.src.stack.agentic.agents.bluelock.runtime import (
        handle_webhook as bluelock_handle,
    )
    from gaming.src.stack.agentic.agents.matchslice.runtime import (
        handle_webhook as matchslice_handle,
    )
    from gaming.src.stack.agentic.games.football_managers.manager_protocol import (
        build_matchday_ask,
        validate_matchday_plan,
    )
    from gaming.src.stack.agentic.games.football_managers.club_store import get_club

    season = _season_pending("agent_bluelock_demo", "agent_aoashi_demo")
    ask_bl = build_matchday_ask("agent_bluelock_demo", season, 1)
    ask_aa = build_matchday_ask("agent_aoashi_demo", season, 1)

    bl = bluelock_handle(ask_bl)
    aa = aoashi_handle(ask_aa)
    assert bl["instructions"].startswith("Never settle for a draw")
    assert aa["instructions"].startswith("Keep the ball")
    for plan, aid in ((bl, "agent_bluelock_demo"), (aa, "agent_aoashi_demo")):
        squad = [p for p in (get_club(aid) or {}).get("squad") or [] if isinstance(p, dict)]
        valid, err = validate_matchday_plan(plan, squad)
        assert err == ""
        assert len(valid["starters"]) == 11


def test_matchslice_demo_server_answers_balanced(_world):
    """Match-Slice answers the ask with the solo-brain (balanced) playbook:
    a legal XI in 4-3-3 / 4-2-3-1 with a mid-block press base tag."""
    from gaming.src.stack.agentic.agents.bluelock.runtime import (
        handle_webhook as bluelock_handle,
    )
    from gaming.src.stack.agentic.agents.matchslice.runtime import (
        handle_webhook as matchslice_handle,
    )
    from gaming.src.stack.agentic.games.football_managers.manager_protocol import (
        build_matchday_ask,
        validate_matchday_plan,
    )
    from gaming.src.stack.agentic.games.football_managers.club_store import get_club

    season = _season_pending("agent_matchslice_demo", "agent_bluelock_demo")
    ask = build_matchday_ask("agent_matchslice_demo", season, 1)
    assert ask is not None

    plan = matchslice_handle(ask)
    assert plan["instructions"].startswith("Stay solvent")
    assert plan["formation"] in {"4-3-3", "4-2-3-1", "4-1-4-1"}
    assert set(plan["tactical_tags"]) <= {"high_press", "counter"}
    squad = [p for p in (get_club("agent_matchslice_demo") or {}).get("squad") or [] if isinstance(p, dict)]
    valid, err = validate_matchday_plan(plan, squad)
    assert err == ""
    assert len(valid["starters"]) == 11
    # answers purely from the ask payload — swap squads and the reply tracks
    # the ask, proving no hidden store access
    ask2 = build_matchday_ask("agent_bluelock_demo", season, 1)
    ask3 = build_matchday_ask("agent_matchslice_demo", season, 1)
    assert ask2 is not None and ask3 is not None
    ask2["my_club"]["squad"] = ask3["my_club"]["squad"]
    swapped = bluelock_handle(ask2)
    assert set(swapped["xi"]) <= {p["player_id"] for p in ask2["my_club"]["squad"]}
