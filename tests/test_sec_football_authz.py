"""Football / marketplace API authz: key required, identity from the caller,
never the body; admin routes only for the platform itself; ownership checks
on adopt, lineup, wallet binding and betting."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

MASTER = "sk_master_test"
BUILDER = "sk_builder_alice"
ADDR = "0x" + "ab" * 20
ADDR2 = "0x" + "cd" * 20


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.setenv("BOARDMAN_AGENTIC_DATA", str(tmp_path))
    for name in ("REMATCH_API_KEY", "STACK_API_KEY", "BOARDMAN_STACK_API_KEYS_FILE", "BOARDMAN_STACK_ALLOW_OPEN"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("BOARDMAN_API_KEY", MASTER)
    monkeypatch.setenv("BOARDMAN_STACK_API_KEYS", f"{BUILDER}:alice_lab")
    yield
    from gaming.src.stack.agentic.games.football_managers import catalog as cat

    for p in cat.seed_catalog():
        cat.set_owner(p["player_id"], None)


@pytest.fixture()
def client():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from gaming.src.stack.agentic import api as api_mod
    from gaming.src.stack.agentic.games.football_managers.club_store import seed_demo_clubs
    from gaming.src.stack.agentic.registry import get_registry

    get_registry().ensure_demo_agents()
    seed_demo_clubs()
    app = FastAPI()
    app.include_router(api_mod.router)
    return TestClient(app)


def _as(caller: str | None = None, key: str = MASTER) -> dict[str, str]:
    h = {"X-Boardman-Key": key}
    if caller:
        h["X-Boardman-Caller"] = caller
    return h


BASE = "/api/stack/agentic"


# ---------------------------------------------------------------- key required

@pytest.mark.parametrize(
    "method,path,body",
    [
        ("get", "/football/catalog", None),
        ("get", "/football/clubs", None),
        ("get", "/football/season", None),
        ("get", "/football/agents", None),
        ("get", "/admin/metrics-detail", None),
        ("post", "/football/season/tick", None),
        ("post", "/football/season/reset", None),
        ("post", "/football/agents/purchase", {"agent_id": "agent_bluelock_demo", "buyer_id": "x"}),
        ("post", "/football/agents/wallet/bind", {"party_id": "x", "address": ADDR, "wallet_id": "w"}),
        ("post", "/football/betting/bet", {"better": "x", "matchday": 1, "home": "a", "away": "b", "side": "home", "amount": 1}),
        ("put", "/football/clubs/agent_bluelock_demo/lineup", {"formation": "4-3-3"}),
    ],
)
def test_football_routes_need_a_key(client, method, path, body):
    kw = {"json": body} if body is not None else {}
    res = getattr(client, method)(BASE + path, **kw)
    assert res.status_code == 401
    res = getattr(client, method)(BASE + path, headers={"X-Boardman-Key": "wrong"}, **kw)
    assert res.status_code == 401


def test_every_route_but_health_and_public_metrics_is_gated():
    from gaming.src.stack.agentic import api as api_mod

    open_routes = []
    for route in api_mod.router.routes:
        deps = {getattr(d.call, "__name__", "") for d in route.dependant.dependencies}
        if not deps & {"require_stack_api_key", "require_stack_caller", "require_platform_admin"}:
            open_routes.append(route.path)
    assert sorted(open_routes) == [f"{BASE}/health", f"{BASE}/public/metrics"]


# ---------------------------------------------------------------- admin only

@pytest.mark.parametrize(
    "path,body",
    [
        ("/football/season/tick", None),
        ("/football/season/reset", None),
        ("/football/season/open", {}),
        ("/football/cup/reset", None),
        ("/football/cup/tick", None),
        ("/football/betting/settle", {"season_no": 1, "matchday": 1}),
    ],
)
def test_admin_routes_refuse_users_and_builders(client, path, body):
    kw = {"json": body} if body is not None else {}
    # a signed-in user proxied by the BFF (master key + caller) is not admin
    assert client.post(BASE + path, headers=_as("profile_123"), **kw).status_code == 403
    # a builder key is never admin
    assert client.post(BASE + path, headers=_as(key=BUILDER), **kw).status_code == 403


def test_admin_route_open_to_platform(client):
    assert client.post(BASE + "/football/season/reset", headers=_as()).status_code == 200
    assert client.get(BASE + "/admin/metrics-detail", headers=_as("profile_123")).status_code == 403
    assert client.get(BASE + "/admin/metrics-detail", headers=_as(key=BUILDER)).status_code == 403


# ---------------------------------------------------------------- identity

def test_body_id_must_match_the_caller(client):
    res = client.post(
        BASE + "/football/agents/purchase",
        headers=_as("profile_bob"),
        json={"agent_id": "agent_bluelock_demo", "buyer_id": "profile_alice"},
    )
    assert res.status_code == 403


def test_builder_key_cannot_claim_another_caller(client):
    res = client.post(
        BASE + "/football/agents/acquire",
        headers=_as("profile_victim", key=BUILDER),
        json={"agent_id": "agent_bluelock_demo"},
    )
    assert res.status_code == 403
    res = client.post(
        BASE + "/football/agents/acquire",
        headers=_as(key=BUILDER),
        json={"agent_id": "agent_bluelock_demo", "owner_id": "profile_victim"},
    )
    assert res.status_code == 403


def test_builder_key_acts_as_itself(client):
    res = client.post(
        BASE + "/football/agents/acquire",
        headers=_as(key=BUILDER),
        json={"agent_id": "agent_bluelock_demo"},
    )
    assert res.status_code == 200, res.text
    assert res.json()["agent"]["owner_id"] == "alice_lab"


def test_caller_fills_omitted_body_ids(client):
    res = client.post(
        BASE + "/football/agents/create",
        headers=_as("profile_alice"),
        json={"manager_name": "Alice Athletic"},
    )
    assert res.status_code == 200, res.text
    assert res.json()["agent"]["owner_id"] == "profile_alice"


# ---------------------------------------------------------------- ownership

def test_acquire_cannot_take_someone_elses_manager(client):
    ok = client.post(BASE + "/football/agents/acquire", headers=_as("profile_alice"), json={"agent_id": "agent_bluelock_demo"})
    assert ok.status_code == 200, ok.text
    stolen = client.post(BASE + "/football/agents/acquire", headers=_as("profile_bob"), json={"agent_id": "agent_bluelock_demo"})
    assert stolen.status_code == 403
    from gaming.src.stack.agentic.registry import get_registry

    assert get_registry().get_agent("agent_bluelock_demo")["owner_id"] == "profile_alice"


def test_acquire_cannot_take_a_person_built_manager(client):
    made = client.post(BASE + "/football/agents/create", headers=_as("profile_alice"), json={"manager_name": "Alice Rovers"})
    aid = made.json()["agent"]["agent_id"]
    res = client.post(BASE + "/football/agents/acquire", headers=_as("profile_bob"), json={"agent_id": aid})
    assert res.status_code == 403


def test_lineup_owner_only(client):
    from gaming.src.stack.agentic.games.football_managers.club_store import get_club

    client.post(BASE + "/football/agents/acquire", headers=_as("profile_alice"), json={"agent_id": "agent_bluelock_demo"})
    club = get_club("agent_bluelock_demo")
    body = {"formation": club["formation"], "tactical_tags": ["counter"]}
    path = BASE + "/football/clubs/agent_bluelock_demo/lineup"
    assert client.put(path, headers=_as("profile_bob"), json=body).status_code == 403
    assert client.put(path, headers=_as(key=BUILDER), json=body).status_code == 403
    res = client.put(path, headers=_as("profile_alice"), json=body)
    assert res.status_code == 200, res.text


def test_set_lineup_library_guard():
    from gaming.src.stack.agentic.games.football_managers.club_store import (
        NotOwnerError,
        seed_demo_clubs,
        set_lineup,
    )
    from gaming.src.stack.agentic.registry import get_registry

    get_registry().ensure_demo_agents()
    seed_demo_clubs()
    with pytest.raises(NotOwnerError):
        set_lineup("agent_bluelock_demo", tactical_tags=["counter"], set_by="profile_mallory")
    with pytest.raises(NotOwnerError):
        set_lineup("agent_bluelock_demo", tactical_tags=["counter"], set_by="")
    set_lineup("agent_bluelock_demo", tactical_tags=["counter"])  # House path untouched


def test_season_join_owner_only(client):
    res = client.post(BASE + "/football/season/join", headers=_as("profile_bob"), json={"agent_id": "agent_bluelock_demo"})
    assert res.status_code == 403


# ---------------------------------------------------------------- wallets

def test_wallet_bind_only_your_own_party(client):
    res = client.post(
        BASE + "/football/agents/wallet/bind",
        headers=_as("profile_bob"),
        json={"party_id": "profile_alice", "address": ADDR},
    )
    assert res.status_code == 403
    res = client.post(BASE + "/football/agents/wallet/bind", headers=_as("profile_bob"), json={"address": ADDR})
    assert res.status_code == 200, res.text
    assert res.json()["wallet"]["party_id"] == "profile_bob"
    assert res.json()["wallet"]["can_send"] is False


def test_wallet_bind_rejects_unverified_circle_wallet(client):
    res = client.post(
        BASE + "/football/agents/wallet/bind",
        headers=_as("profile_bob"),
        json={"address": ADDR, "wallet_id": "victims_circle_wallet"},
    )
    assert res.status_code == 403
    from gaming.src.stack.agentic.games.football_managers.agent_market import get_party_wallet

    assert get_party_wallet("profile_bob") is None


def test_wallet_bind_accepts_verified_circle_wallet(client, monkeypatch):
    from gaming.src.stack.agentic.games.football_managers import agent_market as M

    monkeypatch.setattr(
        M,
        "circle_wallet_owned_by",
        lambda party, wid, addr: (party, wid, addr) == ("profile_bob", "bobs_wallet", ADDR),
    )
    res = client.post(
        BASE + "/football/agents/wallet/bind",
        headers=_as("profile_bob"),
        json={"address": ADDR, "wallet_id": "bobs_wallet"},
    )
    assert res.status_code == 200, res.text
    assert res.json()["wallet"]["can_send"] is True
    # same wallet id, different address than the profile holds → refused
    res = client.post(
        BASE + "/football/agents/wallet/bind",
        headers=_as("profile_bob"),
        json={"address": ADDR2, "wallet_id": "bobs_wallet"},
    )
    assert res.status_code == 403


def test_wallet_unbind_only_your_own(client):
    from gaming.src.stack.agentic.games.football_managers.agent_market import bind_party_wallet

    bind_party_wallet(party_id="profile_alice", address=ADDR)
    res = client.post(BASE + "/football/agents/wallet/unbind", headers=_as("profile_bob"), json={"party_id": "profile_alice"})
    assert res.status_code == 403
    res = client.post(BASE + "/football/agents/wallet/unbind", headers=_as("profile_alice"), json={})
    assert res.status_code == 200 and res.json()["removed"] is True


def test_circle_wallet_verification_fails_closed():
    from gaming.src.stack.agentic.games.football_managers.agent_market import circle_wallet_owned_by

    # no Supabase in tests → unverifiable → False
    assert circle_wallet_owned_by("profile_bob", "w", ADDR) is False


# ---------------------------------------------------------------- betting

@pytest.fixture()
def open_season(client):
    from gaming.src.stack.agentic.games.football_managers import season as S
    from gaming.src.stack.agentic.games.football_managers.league import schedule_season

    S.open_season(
        agent_ids=["agent_bluelock_demo", "agent_aoashi_demo", "agent_matchslice_demo"],
        start_at=datetime.now(timezone.utc) - timedelta(hours=1),
    )
    season = S._state()["season"]
    fx = schedule_season(season["division"])[0][0]
    return int(season["season_no"]), fx.home_agent_id, fx.away_agent_id


def test_bet_debits_the_caller_not_the_body(client, open_season):
    from gaming.src.stack.agentic import ledger as L

    sn, home, away = open_season
    L.ensure_funded("profile_victim", Decimal("100"))
    L.ensure_funded("profile_bob", Decimal("100"))
    bet = {"matchday": 1, "home": home, "away": away, "side": "home", "amount": 5, "season_no": sn}
    res = client.post(BASE + "/football/betting/bet", headers=_as("profile_bob"), json={**bet, "better": "profile_victim"})
    assert res.status_code == 403
    res = client.post(BASE + "/football/betting/bet", headers=_as("profile_bob"), json=bet)
    assert res.status_code == 200, res.text
    assert L.balance("profile_victim") == Decimal("100")
    assert L.balance("owner:profile_bob") == Decimal("95")  # one football wallet per person (B9)


def test_bet_never_debits_a_system_wallet(open_season):
    from gaming.src.stack.agentic.games.football_managers.betting import place_bet

    sn, home, away = open_season
    for wallet in ("owner:creator_bluelock_demo", f"afm_fixture_s{sn}_md1_{home}_{away}", "agent_bluelock_demo", "house"):
        with pytest.raises(ValueError, match="system wallet"):
            place_bet(wallet, sn, 1, home, away, "home", "5")


def test_my_bets_are_the_callers(client, open_season):
    res = client.get(BASE + "/football/betting/my", headers=_as("profile_bob"), params={"better": "profile_victim"})
    assert res.status_code == 403
    res = client.get(BASE + "/football/betting/my", headers=_as("profile_bob"))
    assert res.status_code == 200
