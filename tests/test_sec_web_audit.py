"""2026-10 web/API audit (docs/security/AUDIT_2026-10_web.md): regression
tests for the backend findings.

* WEB-01: a builder key could act as ANY player on /api/stack/v1 (create,
  accept, lock = move custodial USDC, report, proof, settle).
* WEB-02: any builder key could drive the House (schedule, open / lock /
  play / rematch, demo seeding) and lock other builders' agents in matches.
* WEB-05: the first PRESENT edge country header decides; Tor (T1) can no
  longer pick a country with a self-typed x-vercel-ip-country.
* WEB-07: no public route map, no exception text on public health routes.
* WEB-10: ilike wildcards in tag lookups; screenshot refs cannot steer
  settlement at other hosts or local files; RPC URLs are not echoed.
"""
from __future__ import annotations

import asyncio

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

MASTER = "sk_master_audit_test"
BUILDER = "sk_builder_audit_test"
OTHER_BUILDER = "sk_other_audit_test"


@pytest.fixture(autouse=True)
def _keys(monkeypatch):
    for name in ("REMATCH_API_KEY", "STACK_API_KEY", "BOARDMAN_STACK_API_KEYS_FILE", "BOARDMAN_STACK_ALLOW_OPEN"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("BOARDMAN_API_KEY", MASTER)
    monkeypatch.setenv("BOARDMAN_STACK_API_KEYS", f"{BUILDER}:alice_lab,{OTHER_BUILDER}:mallory_lab")


def _never(*_a, **_k):
    raise AssertionError("auth should have refused before touching the match store")


# ---------------------------------------------------------------- WEB-01 v1

@pytest.fixture()
def v1(monkeypatch):
    from gaming.src.stack import api_v1

    monkeypatch.setattr(api_v1, "_load_challenge", _never)
    monkeypatch.setattr(api_v1, "_sb", _never)
    app = FastAPI()
    app.include_router(api_v1.router)
    return TestClient(app), api_v1


VICTIM = "11111111-1111-4111-8111-111111111111"
ATTACKER = "22222222-2222-4222-8222-222222222222"

V1_WRITES = [
    ("/api/stack/v1/matches", {"creator_id": VICTIM, "opponent_id": ATTACKER, "amount_usdc": 25, "game_id": "EAFC"}),
    ("/api/stack/v1/matches/by-tag", {"creator_id": VICTIM, "opponent_tag": "attacker", "amount_usdc": 25}),
    ("/api/stack/v1/matches/ABC123/accept", {"opponent_id": ATTACKER}),
    ("/api/stack/v1/matches/ABC123/lock", {"profile_id": VICTIM}),
    ("/api/stack/v1/matches/ABC123/report", {"profile_id": VICTIM, "score": "L"}),
    ("/api/stack/v1/matches/ABC123/settle", None),
]


@pytest.mark.parametrize("path,body", V1_WRITES)
def test_builder_key_cannot_act_for_a_player(v1, path, body):
    client, _ = v1
    r = client.post(path, json=body, headers={"X-Boardman-Key": BUILDER})
    assert r.status_code == 403, r.text


def test_builder_key_cannot_upload_proof_as_a_player(v1):
    client, _ = v1
    r = client.post(
        "/api/stack/v1/matches/ABC123/proof",
        data={"profile_id": VICTIM, "score": "0-3"},
        files={"file": ("p.jpg", b"\xff\xd8\xff", "image/jpeg")},
        headers={"X-Boardman-Key": BUILDER},
    )
    assert r.status_code == 403


def test_builder_key_can_still_read(v1, monkeypatch):
    client, api_v1 = v1
    monkeypatch.setattr(api_v1, "_load_challenge", lambda ref: None)
    r = client.get("/api/stack/v1/matches/ABC123", headers={"X-Boardman-Key": BUILDER})
    assert r.status_code == 404  # past auth: read routes stay open to builders


@pytest.mark.parametrize(
    "path,body",
    [
        ("/api/stack/v1/matches", {"creator_id": ATTACKER, "amount_usdc": 5, "game_id": "EAFC"}),
        ("/api/stack/v1/matches/ABC123/accept", {"opponent_id": ATTACKER}),
        ("/api/stack/v1/matches/ABC123/lock", {"profile_id": ATTACKER}),
        ("/api/stack/v1/matches/ABC123/report", {"profile_id": ATTACKER, "score": "W"}),
    ],
)
def test_master_key_body_id_must_be_the_vouched_caller(v1, path, body):
    client, _ = v1
    h = {"X-Rematch-Key": MASTER, "X-Boardman-Caller": VICTIM}
    assert client.post(path, json=body, headers=h).status_code == 403


def test_master_key_platform_passes_auth(v1, monkeypatch):
    client, api_v1 = v1
    monkeypatch.setattr(api_v1, "_load_challenge", lambda ref: None)
    r = client.post("/api/stack/v1/matches/ABC123/lock", json={"profile_id": VICTIM}, headers={"X-Rematch-Key": MASTER})
    assert r.status_code == 404  # reached the store


@pytest.mark.parametrize("tag", ["%", "a%", "_", "*", "x_y%"])
def test_by_tag_refuses_wildcards(v1, tag):
    client, _ = v1
    r = client.post(
        "/api/stack/v1/matches/by-tag",
        json={"creator_id": VICTIM, "opponent_tag": tag, "amount_usdc": 1},
        headers={"X-Rematch-Key": MASTER, "X-Boardman-Caller": VICTIM},
    )
    assert r.status_code == 400


def test_escape_like_neutralises_wildcards():
    from gaming.src.stack.api_v1 import _escape_like

    assert _escape_like("big_boss") == "big\\_boss"
    assert _escape_like("a%b\\") == "a\\%b\\\\"


# ---------------------------------------------------------------- WEB-02 agentic

class _FakeRegistry:
    AGENTS = {
        "agent_alice": {"agent_id": "agent_alice", "registered_by": "alice_lab"},
        "agent_mallory": {"agent_id": "agent_mallory", "registered_by": "mallory_lab"},
        "agent_raja_kia_alekhine": {"agent_id": "agent_raja_kia_alekhine"},  # platform agent
    }

    def get_agent(self, aid):
        return self.AGENTS.get(aid)


class _FakeMatches:
    def __init__(self):
        self.created = []

    def create_match(self, **kw):
        self.created.append(kw)
        return {"match_id": "agm_x", **kw}

    def get(self, mid):
        return {"match_id": mid, "agent_a_id": "agent_mallory", "agent_b_id": "agent_raja_kia_alekhine"}

    def lock_both(self, mid):
        return {"match_id": mid, "status": "locked"}

    def run_match(self, mid, **kw):
        return {"match_id": mid, "status": "settled"}


@pytest.fixture()
def agentic(monkeypatch):
    from gaming.src.stack.agentic import api as A
    from gaming.src.stack.agentic import matches as M
    from gaming.src.stack.agentic import registry as R

    fake = _FakeMatches()
    monkeypatch.setattr(R, "get_registry", lambda: _FakeRegistry())
    monkeypatch.setattr(M, "get_match_service", lambda: fake)
    app = FastAPI()
    app.include_router(A.router)
    return TestClient(app), fake


HOUSE_OPS = [
    ("POST", "/api/stack/agentic/house/schedule", {"enabled": False}),
    ("POST", "/api/stack/agentic/house/matches", {"agent_a_id": "a", "agent_b_id": "b"}),
    ("POST", "/api/stack/agentic/house/matches/agm_x/lock", None),
    ("POST", "/api/stack/agentic/house/matches/agm_x/play", {}),
    ("POST", "/api/stack/agentic/house/rematch", {}),
    ("POST", "/api/stack/agentic/agents/demo/seed", None),
    ("POST", "/api/stack/agentic/demo/chess", {}),
    ("POST", "/api/stack/agentic/demo/game", {}),
    ("GET", "/api/stack/agentic/house/status", None),
]


@pytest.mark.parametrize("method,path,body", HOUSE_OPS)
def test_builder_key_cannot_drive_the_house(agentic, method, path, body):
    client, _ = agentic
    r = client.request(method, path, json=body, headers={"X-Boardman-Key": BUILDER})
    assert r.status_code == 403, r.text


def test_house_schedule_still_works_for_the_platform(agentic):
    client, _ = agentic
    r = client.post("/api/stack/agentic/house/schedule", json={"cadence_sec": 600}, headers={"X-Rematch-Key": MASTER})
    assert r.status_code == 200, r.text
    # a caller header means "a signed-in player", never the platform
    r = client.post(
        "/api/stack/agentic/house/schedule",
        json={"cadence_sec": 600},
        headers={"X-Rematch-Key": MASTER, "X-Boardman-Caller": VICTIM},
    )
    assert r.status_code == 403


def test_builder_cannot_seat_another_builders_agent(agentic):
    client, fake = agentic
    r = client.post(
        "/api/stack/agentic/matches",
        json={"agent_a_id": "agent_alice", "agent_b_id": "agent_mallory", "stake_usdc": 25},
        headers={"X-Boardman-Key": BUILDER},
    )
    assert r.status_code == 403 and not fake.created


def test_builder_cannot_seat_only_platform_agents(agentic):
    client, fake = agentic
    r = client.post(
        "/api/stack/agentic/matches",
        json={"agent_a_id": "agent_raja_kia_alekhine", "agent_b_id": "agent_raja_kia_alekhine"},
        headers={"X-Boardman-Key": BUILDER},
    )
    assert r.status_code == 403 and not fake.created


def test_builder_may_challenge_a_platform_agent_with_its_own(agentic):
    client, fake = agentic
    r = client.post(
        "/api/stack/agentic/matches",
        json={"agent_a_id": "agent_alice", "agent_b_id": "agent_raja_kia_alekhine"},
        headers={"X-Boardman-Key": BUILDER},
    )
    assert r.status_code == 200 and fake.created


@pytest.mark.parametrize("suffix", ["lock", "play"])
def test_builder_cannot_lock_or_play_someone_elses_match(agentic, suffix):
    client, _ = agentic
    r = client.post(f"/api/stack/agentic/matches/agm_x/{suffix}", json={}, headers={"X-Boardman-Key": BUILDER})
    assert r.status_code == 403
    r = client.post(f"/api/stack/agentic/matches/agm_x/{suffix}", json={}, headers={"X-Boardman-Key": OTHER_BUILDER})
    assert r.status_code == 200


def test_safe_err_strips_rpc_urls():
    from gaming.src.stack.agentic.api import _clamp_days, _safe_err

    msg = _safe_err(RuntimeError("RPC not connected: https://arc.example/v2/SECRETKEY123 (timeout)"))
    assert "SECRETKEY123" not in msg and "<url>" in msg
    assert _clamp_days(100000) == 90 and _clamp_days(0) == 1 and _clamp_days(None) is None


# ---------------------------------------------------------------- WEB-05 geo

class _Url:
    def __init__(self, path):
        self.path = path


class _Req:
    def __init__(self, method, path, headers):
        self.method = method
        self.url = _Url(path)
        self.headers = {k.lower(): v for k, v in headers.items()}
        self.client = None


@pytest.fixture()
def geo(monkeypatch, tmp_path):
    from gaming.src.backend.middleware import geo_fence as gf

    for name in ("BLOCKED_REGIONS_FILE", "GEO_FENCE_POLICY_FILE", "GEO_FENCE_DISABLED"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("MAXMIND_DB_PATH", str(tmp_path / "none.mmdb"))
    monkeypatch.setenv("GEO_FENCE_STRICT", "1")
    gf.reset_blocked_cache()
    yield gf
    gf.reset_blocked_cache()


@pytest.mark.parametrize("sentinel", ["T1", "XX", "garbage"])
def test_unknown_cloudflare_country_is_not_overridden_by_vercel_header(geo, sentinel):
    req = _Req("POST", "/api/stack/v1/matches/abc/lock", {"cf-ipcountry": sentinel, "x-vercel-ip-country": "GB"})
    d = geo.evaluate_request(req)
    assert not d.allowed and d.reason == "country_unknown"


def test_cloudflare_country_still_wins(geo):
    req = _Req("POST", "/api/stack/v1/matches/abc/lock", {"cf-ipcountry": "GB", "x-vercel-ip-country": "US"})
    assert geo.evaluate_request(req).country == "GB"


# ---------------------------------------------------------------- WEB-07 info leaks

def test_api_docs_off_by_default(monkeypatch):
    from gaming.src.backend import main

    monkeypatch.delenv("BOARDMAN_API_DOCS", raising=False)
    app = main.create_app()
    client = TestClient(app)
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert client.get(path).status_code == 404, path
    assert "docs" not in client.get("/").json()

    monkeypatch.setenv("BOARDMAN_API_DOCS", "1")
    assert TestClient(main.create_app()).get("/openapi.json").status_code == 200


def test_healthz_does_not_echo_backend_errors(monkeypatch):
    from gaming.src.backend.api import health

    class Boom(Exception):
        pass

    def bad():
        raise Boom("connect to db.secret-host.supabase.co:5432 failed for role service_role")

    monkeypatch.setattr(health, "get_supabase", bad)
    app = FastAPI()
    app.include_router(health.router, prefix="/api")
    r = TestClient(app).get("/api/healthz")
    assert r.status_code == 503
    assert "secret-host" not in r.text and "Boom" in r.text


# ---------------------------------------------------------------- WEB-10 screenshot refs

@pytest.mark.parametrize(
    "ref",
    [
        "http://169.254.169.254/latest/meta-data/",
        "https://attacker.example/x.jpg",
        "http://api.telegram.org/file/botX/y.jpg",  # plain http
        "/etc/passwd",
        "../../.env",
        "data/agentic/keystore.json",
    ],
)
def test_settlement_refuses_untrusted_screenshot_refs(ref):
    from gaming.src.backend.services.clawstation_settlement import _resolve_screenshot_source

    assert asyncio.run(_resolve_screenshot_source(ref)) == ""


def test_long_base64_with_slashes_becomes_a_data_url():
    from gaming.src.backend.services.clawstation_settlement import _resolve_screenshot_source

    ref = "/" * 250 + "etc/passwd"
    out = asyncio.run(_resolve_screenshot_source(ref))
    assert out.startswith("data:image/jpeg;base64,")


@pytest.mark.parametrize("route", ["wallet", "sales"])
def test_party_wallet_and_sales_are_the_callers_own(route):
    """WEB-11: a party's bound wallet address and earnings were readable by id."""
    from gaming.src.stack.agentic import api as A

    app = FastAPI()
    app.include_router(A.router)
    client = TestClient(app)
    path = f"/api/stack/agentic/football/agents/{route}"
    # a builder key reads only itself
    assert client.get(path, params={"party_id": VICTIM}, headers={"X-Boardman-Key": BUILDER}).status_code == 403
    # a signed-in player (BFF) reads only themself
    h = {"X-Rematch-Key": MASTER, "X-Boardman-Caller": ATTACKER}
    assert client.get(path, params={"party_id": VICTIM}, headers=h).status_code == 403
    r = client.get(path, headers=h)
    assert r.status_code == 200 and r.json()[route]["party_id"] == ATTACKER


def test_telegram_file_url_is_kept():
    from gaming.src.backend.services.clawstation_settlement import _resolve_screenshot_source

    url = "https://api.telegram.org/file/bot123:abc/photos/file_1.jpg"
    assert asyncio.run(_resolve_screenshot_source(url)) == url
