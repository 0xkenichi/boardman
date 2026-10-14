"""
Strict (fail-closed) geo-fence for money routes, the canonical blocked list, and
the trusted forwarded-country header for master-key BFF traffic.

See COMPLIANCE.md ("Geo-fence") and config/compliance/geo_fence.json.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

_REPO_ROOT = Path(__file__).resolve().parents[1]
for _p in (str(_REPO_ROOT), str(_REPO_ROOT.parent)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from gaming.src.backend.middleware import BlockedRegionError, check_region  # noqa: E402
from gaming.src.backend.middleware import geo_fence as gf  # noqa: E402

MASTER = "test-master-key-not-a-secret"
BUILDER = "test-builder-key-not-a-secret"

_ENV_TO_CLEAR = (
    "BLOCKED_REGIONS_FILE", "GEO_FENCE_POLICY_FILE", "GEO_FENCE_STRICT", "GEO_FENCE_DISABLED",
    "BOARDMAN_ENV", "APP_ENV", "ENVIRONMENT", "NETWORK", "CLAW_DEFAULT_CHAIN",
    "BOARDMAN_SETTLEMENT_RAIL", "REMATCH_API_KEY", "STACK_API_KEY", "BOARDMAN_STACK_API_KEYS_FILE",
)


class _Url:
    def __init__(self, path):
        self.path = path


class _Req:
    def __init__(self, method="GET", path="/", headers=None, client_host=None):
        self.method = method
        self.url = _Url(path)
        self.headers = {k.lower(): v for k, v in (headers or {}).items()}
        self.client = type("C", (), {"host": client_host})() if client_host else None


@pytest.fixture(autouse=True)
def _env(tmp_path, monkeypatch):
    for name in _ENV_TO_CLEAR:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("MAXMIND_DB_PATH", str(tmp_path / "no-such-db.mmdb"))
    monkeypatch.setenv("BOARDMAN_API_KEY", MASTER)
    monkeypatch.setenv("BOARDMAN_STACK_API_KEYS", f"{BUILDER}:acme_lab")
    gf.reset_blocked_cache()
    yield
    gf.reset_blocked_cache()


def _strict(monkeypatch, on=True):
    monkeypatch.setenv("GEO_FENCE_STRICT", "1" if on else "0")


# ── Canonical blocked list ───────────────────────────────────────────────────
class TestCanonicalBlockedList:
    def test_default_path_is_tracked_config_file(self):
        assert gf.DEFAULT_BLOCKED_FILE == _REPO_ROOT / "config" / "blocked_regions.json"
        assert gf.DEFAULT_POLICY_FILE == _REPO_ROOT / "config" / "compliance" / "geo_fence.json"

    def test_loads_without_env_var(self):
        blocked = gf._load_blocked_regions()
        assert gf.blocked_list_loaded()
        data = json.loads(gf.DEFAULT_BLOCKED_FILE.read_text())
        assert blocked == {c.upper() for c in data["blocked"]}
        assert "US" in blocked and "GB" in blocked
        assert "NG" not in blocked  # unblocked 2026-08-13 (commit cf035e4)

    def test_relative_env_path_resolves_from_repo_root(self, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("BLOCKED_REGIONS_FILE", "config/blocked_regions.json")
        assert "US" in gf._load_blocked_regions()

    @pytest.mark.skipif(shutil.which("git") is None or not (_REPO_ROOT / ".git").exists(),
                        reason="needs a git checkout")
    def test_config_files_are_tracked_not_ignored(self):
        for rel in ("config/blocked_regions.json", "config/compliance/geo_fence.json"):
            ignored = subprocess.run(["git", "check-ignore", "-q", rel], cwd=_REPO_ROOT)
            assert ignored.returncode == 1, f"{rel} must not be gitignored"

    def test_missing_list_reports_not_loaded(self, monkeypatch, tmp_path):
        monkeypatch.setenv("BLOCKED_REGIONS_FILE", str(tmp_path / "missing.json"))
        assert gf._load_blocked_regions() == set()
        assert not gf.blocked_list_loaded()


# ── Money-route classification ───────────────────────────────────────────────
class TestMoneyRoutes:
    @pytest.mark.parametrize("method,path,kind", [
        ("GET", "/api/deposit/address", "deposit"),
        ("POST", "/api/rematch/web/spectator/bet", "spectator_bet"),
        ("POST", "/api/rematch/web/spectator/lp", "spectator_lp"),
        ("POST", "/api/rematch/web/spectator/lp/withdraw", "withdraw"),
        ("POST", "/api/rematch/web/spectator/payout", "spectator_payout"),
        ("POST", "/api/stack/v1/matches", "stake_create"),
        ("POST", "/api/stack/v1/matches/", "stake_create"),
        ("POST", "/api/stack/v1/matches/by-tag", "stake_create"),
        ("POST", "/api/stack/v1/matches/abc/accept", "stake_accept"),
        ("POST", "/api/stack/v1/matches/abc/lock", "stake_lock"),
        ("POST", "/api/stack/agentic/matches/m1/lock", "stake_lock"),
        ("POST", "/api/stack/agentic/matches/m1/spectator/bet", "spectator_bet"),
        ("POST", "/api/stack/agentic/house/matches/m1/bets", "spectator_bet"),
        ("POST", "/api/stack/agentic/football/agents/purchase", "buy"),
        ("POST", "/api/stack/agentic/football/agents/offer/accept", "buy"),
        ("POST", "/api/stack/agentic/football/season/join", "entry_fee"),
        ("POST", "/api/stack/agentic/football/betting/bet", "spectator_bet"),
    ])
    def test_money_routes(self, method, path, kind):
        assert gf.money_route_kind(method, path) == kind

    @pytest.mark.parametrize("method,path", [
        ("GET", "/api/rematch/web/spectator/bet"),       # approval poll
        ("GET", "/api/stack/v1/matches/abc"),
        ("POST", "/api/stack/v1/matches/abc/report"),
        ("POST", "/api/stack/agentic/football/agents/offer/reject"),
        ("GET", "/api/healthz"),
        ("POST", "/webhooks/circle"),
    ])
    def test_non_money_routes(self, method, path):
        assert gf.money_route_kind(method, path) is None

    def test_missing_policy_falls_back_to_all_mutating_api_calls(self, monkeypatch, tmp_path):
        monkeypatch.setenv("GEO_FENCE_POLICY_FILE", str(tmp_path / "nope.json"))
        assert gf.money_route_kind("POST", "/api/anything/new") == "unknown"
        assert gf.money_route_kind("GET", "/api/anything/new") is None


# ── Strict-mode switch ───────────────────────────────────────────────────────
class TestStrictMode:
    def test_off_by_default_on_testnet(self):
        assert gf.strict_mode() is False

    @pytest.mark.parametrize("name,value", [
        ("BOARDMAN_ENV", "production"), ("APP_ENV", "prod"), ("ENVIRONMENT", "mainnet"),
        ("NETWORK", "mainnet"), ("CLAW_DEFAULT_CHAIN", "arc_mainnet"),
        ("BOARDMAN_SETTLEMENT_RAIL", "arc_mainnet"),
    ])
    def test_on_in_production(self, monkeypatch, name, value):
        monkeypatch.setenv(name, value)
        assert gf.strict_mode() is True

    def test_explicit_flag_wins(self, monkeypatch):
        monkeypatch.setenv("NETWORK", "mainnet")
        monkeypatch.setenv("GEO_FENCE_STRICT", "0")
        assert gf.strict_mode() is False
        monkeypatch.delenv("NETWORK")
        monkeypatch.setenv("GEO_FENCE_STRICT", "1")
        assert gf.strict_mode() is True


# ── evaluate_request ─────────────────────────────────────────────────────────
BET = ("POST", "/api/rematch/web/spectator/bet")
LOCK = ("POST", "/api/stack/v1/matches/abc/lock")


class TestEvaluateRequest:
    def test_health_exempt_even_strict(self, monkeypatch):
        _strict(monkeypatch)
        d = gf.evaluate_request(_Req("GET", "/api/healthz"))
        assert d.allowed and d.reason == "exempt"

    def test_strict_money_route_unknown_country_refused(self, monkeypatch):
        _strict(monkeypatch)
        d = gf.evaluate_request(_Req(*BET))
        assert not d.allowed and d.reason == "country_unknown"
        assert d.status_code == 451 and d.body()["error"] == "region_unverified"

    def test_strict_money_route_allowed_country(self, monkeypatch):
        _strict(monkeypatch)
        d = gf.evaluate_request(_Req(*BET, headers={"cf-ipcountry": "BR"}))
        assert d.allowed and d.country == "BR" and d.money_kind == "spectator_bet"

    def test_blocked_country_refused(self, monkeypatch):
        d = gf.evaluate_request(_Req(*BET, headers={"x-vercel-ip-country": "US"}))
        assert not d.allowed and d.reason == "blocked"
        assert d.body() == {"error": "service_unavailable_in_region"}

    def test_lenient_mode_allows_unknown_country(self):
        d = gf.evaluate_request(_Req(*BET))
        assert d.allowed and d.country is None

    def test_strict_non_money_route_unknown_country_allowed(self, monkeypatch):
        _strict(monkeypatch)
        assert gf.evaluate_request(_Req("GET", "/api/stack/agentic/matches")).allowed

    def test_master_key_with_trusted_header(self, monkeypatch):
        _strict(monkeypatch)
        ok = gf.evaluate_request(_Req(*LOCK, headers={
            "x-rematch-key": MASTER, "x-boardman-client-country": "ke"}))
        assert ok.allowed and ok.country == "KE" and ok.source == "forwarded"
        bad = gf.evaluate_request(_Req(*LOCK, headers={
            "x-rematch-key": MASTER, "x-boardman-client-country": "GB"}))
        assert not bad.allowed and bad.reason == "blocked"

    def test_master_key_without_forwarded_country_refused_in_strict(self, monkeypatch):
        _strict(monkeypatch)
        d = gf.evaluate_request(_Req(*LOCK, headers={"x-rematch-key": MASTER}))
        assert not d.allowed and d.reason == "country_unknown"

    def test_master_key_ignores_edge_headers(self, monkeypatch):
        # cf-ipcountry on the Vercel -> API hop describes Vercel, not the user.
        _strict(monkeypatch)
        d = gf.evaluate_request(_Req(*LOCK, headers={"x-rematch-key": MASTER, "cf-ipcountry": "BR"}))
        assert not d.allowed and d.reason == "country_unknown"

    def test_master_key_non_money_route_passes(self, monkeypatch):
        _strict(monkeypatch)
        d = gf.evaluate_request(_Req("GET", "/api/stack/v1/games", headers={"x-rematch-key": MASTER}))
        assert d.allowed and d.reason == "api_key_non_money"

    def test_builder_key_cannot_use_trusted_header(self, monkeypatch):
        _strict(monkeypatch)
        d = gf.evaluate_request(_Req(*LOCK, headers={
            "authorization": f"Bearer {BUILDER}", "x-boardman-client-country": "KE"}))
        assert not d.allowed and d.reason == "country_unknown"

    def test_builder_key_judged_by_edge_country(self, monkeypatch):
        _strict(monkeypatch)
        d = gf.evaluate_request(_Req(*LOCK, headers={"x-boardman-key": BUILDER, "cf-ipcountry": "KE"}))
        assert d.allowed and d.country == "KE"

    def test_unkeyed_trusted_header_ignored(self, monkeypatch):
        _strict(monkeypatch)
        d = gf.evaluate_request(_Req(*BET, headers={"x-boardman-client-country": "KE"}))
        assert not d.allowed

    def test_wrong_key_is_unkeyed(self, monkeypatch):
        _strict(monkeypatch)
        d = gf.evaluate_request(_Req(*LOCK, headers={
            "x-rematch-key": "wrong", "x-boardman-client-country": "KE"}))
        assert not d.allowed

    def test_disabled_flag_ignored_for_strict_money_routes(self, monkeypatch):
        monkeypatch.setenv("GEO_FENCE_DISABLED", "1")
        assert gf.evaluate_request(_Req(*BET)).allowed  # lenient: disabled wins
        _strict(monkeypatch)
        assert not gf.evaluate_request(_Req(*BET)).allowed
        assert gf.evaluate_request(_Req("GET", "/", headers={"cf-ipcountry": "US"})).allowed

    def test_unreadable_blocklist_fails_closed_in_strict(self, monkeypatch, tmp_path):
        bad = tmp_path / "blocked.json"
        bad.write_text("{not json")
        monkeypatch.setenv("BLOCKED_REGIONS_FILE", str(bad))
        assert gf.evaluate_request(_Req(*BET, headers={"cf-ipcountry": "KE"})).allowed
        _strict(monkeypatch)
        gf.reset_blocked_cache()
        d = gf.evaluate_request(_Req(*BET, headers={"cf-ipcountry": "KE"}))
        assert not d.allowed and d.status_code == 503
        assert d.body() == {"error": "geo_fence_unavailable"}

    def test_sentinel_and_garbage_country_values_are_unknown(self, monkeypatch):
        _strict(monkeypatch)
        for value in ("XX", "T1", "", "USA", "1"):
            d = gf.evaluate_request(_Req(*BET, headers={"cf-ipcountry": value}))
            assert not d.allowed, value


# ── check_region (legacy entry point used by main.py and the bot) ────────────
class TestCheckRegionStrict:
    def test_raises_unverified_for_strict_money_route(self, monkeypatch):
        _strict(monkeypatch)
        with pytest.raises(gf.RegionUnverifiedError) as exc:
            check_region(_Req("GET", "/api/deposit/address"))
        assert isinstance(exc.value, BlockedRegionError)  # main.py's except still catches it
        assert exc.value.reason == "country_unknown"

    def test_webhooks_exempt_even_from_blocked_country(self):
        assert check_region(_Req("POST", "/webhooks/circle", headers={"cf-ipcountry": "US"})) is None

    def test_plain_request_without_path_unchanged(self, monkeypatch):
        _strict(monkeypatch)
        req = type("R", (), {"headers": {}, "client": None})()
        assert check_region(req) is None


# ── Intended middleware wiring ───────────────────────────────────────────────
def _wired_app() -> FastAPI:
    app = FastAPI()

    @app.middleware("http")
    async def _geo(request, call_next):
        decision = gf.evaluate_request(request)
        if not decision.allowed:
            return JSONResponse(status_code=decision.status_code, content=decision.body())
        return await call_next(request)

    @app.get("/api/healthz")
    async def _health():
        return {"ok": True}

    @app.post("/api/rematch/web/spectator/bet")
    async def _bet():
        return {"ok": True}

    return app


class TestWiredMiddleware:
    def test_end_to_end(self, monkeypatch):
        _strict(monkeypatch)
        c = TestClient(_wired_app())
        assert c.get("/api/healthz").status_code == 200
        assert c.post("/api/rematch/web/spectator/bet").status_code == 451
        assert c.post("/api/rematch/web/spectator/bet",
                      headers={"X-Rematch-Key": MASTER, "X-Boardman-Client-Country": "KE"}).status_code == 200
        assert c.post("/api/rematch/web/spectator/bet",
                      headers={"X-Rematch-Key": MASTER, "X-Boardman-Client-Country": "US"}).status_code == 451


@pytest.mark.xfail(strict=True, reason=(
    "main.py still returns early for /api/stack/, /api/rematch/web and any valid API key, "
    "so strict mode never reaches money routes. Replace that block with evaluate_request "
    "(COMPLIANCE.md, 'Wiring'), then delete this marker."))
def test_real_app_fences_stack_money_route_in_strict_mode(monkeypatch):
    _strict(monkeypatch)
    from gaming.src.backend.main import app

    resp = TestClient(app).post("/api/stack/v1/matches/abc/lock")
    assert resp.status_code == 451
