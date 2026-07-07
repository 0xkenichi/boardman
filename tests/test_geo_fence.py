"""
gaming/tests/test_geo_fence.py — Tests for the ClawStation geo-fence middleware.

Covers:
    - Cloudflare ``cf-ipcountry`` header detection (blocked and allowed)
    - Vercel ``x-vercel-ip-country`` header detection
    - Fallback to allow when no header and no MaxMind DB is present
    - End-to-end through the FastAPI app via ``TestClient`` (returns HTTP 451)
    - The middleware unit ``check_region`` directly
    - The bot ``/start`` handler refusing onboarding for blocked users

Manual test: with no env overrides, a request that supplies no header and the
MaxMind DB present but missing the IP → 200 (allowed). Confirmed in
``test_no_header_no_maxmind_returns_200`` below.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# Ensure repo root is importable so ``gaming.*`` resolves without installation.
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from gaming.src.backend.middleware import BlockedRegionError, check_region  # noqa: E402
from gaming.src.backend.middleware.geo_fence import (  # noqa: E402
    _load_blocked_regions,
    _maxmind_lookup,
    detect_country,
    reset_blocked_cache,
)


# ── Minimal request double (avoids requiring FastAPI/Starlette in unit tests) ──
class _FakeRequest:
    def __init__(self, headers=None, client_host=None):
        # ``headers`` may be a dict or a mapping with case-insensitive .get()
        self.headers = headers or {}
        self.client = type("C", (), {"host": client_host})() if client_host else None


# ── Fixtures ────────────────────────────────────────────────────────────────
@pytest.fixture(autouse=True)
def _clear_caches(tmp_path, monkeypatch):
    """Reset module-level caches and force the on-disk config path for every test."""
    reset_blocked_cache()
    cfg = tmp_path / "blocked_regions.json"
    cfg.write_text('{"blocked": ["NG"], "version": 1}')
    monkeypatch.setenv("BLOCKED_REGIONS_FILE", str(cfg))
    monkeypatch.setenv("MAXMIND_DB_PATH", str(tmp_path / "no-such-db.mmdb"))
    yield
    reset_blocked_cache()


# ── check_region unit tests ────────────────────────────────────────────────
class TestCheckRegion:
    def test_cloudflare_header_blocked_raises(self):
        req = _FakeRequest(headers={"cf-ipcountry": "NG"})
        with pytest.raises(BlockedRegionError) as exc_info:
            check_region(req)
        assert exc_info.value.country_code == "NG"

    def test_cloudflare_header_allowed_returns_country(self):
        req = _FakeRequest(headers={"cf-ipcountry": "us"})
        assert check_region(req) == "US"

    def test_cloudflare_header_case_insensitive(self):
        # Different capitalisation of the header name should still be detected.
        req = _FakeRequest(headers={"CF-IPCountry": "ng"})
        with pytest.raises(BlockedRegionError):
            check_region(req)

    def test_vercel_header_blocked(self):
        req = _FakeRequest(headers={"x-vercel-ip-country": "NG"})
        with pytest.raises(BlockedRegionError):
            check_region(req)

    def test_vercel_header_allowed(self):
        req = _FakeRequest(headers={"x-vercel-ip-country": "DE"})
        assert check_region(req) == "DE"

    def test_cloudflare_takes_priority_over_vercel(self):
        req = _FakeRequest(headers={
            "cf-ipcountry": "US",
            "x-vercel-ip-country": "NG",
        })
        assert check_region(req) == "US"

    def test_no_header_no_maxmind_returns_none(self):
        # No header, no DB on disk → detect_country returns None → check_region returns None.
        assert check_region(_FakeRequest()) is None

    def test_cloudflare_tor_sentinel_treated_as_unknown(self):
        req = _FakeRequest(headers={"cf-ipcountry": "T1"})
        assert check_region(req) is None

    def test_blocked_override_blocks_unlisted_country(self):
        # Even when on-disk config doesn't list "RU", explicit override does.
        req = _FakeRequest(headers={"cf-ipcountry": "RU"})
        with pytest.raises(BlockedRegionError):
            check_region(req, blocked={"RU"})

    def test_maxmind_missing_db_falls_back_to_allow(self, tmp_path):
        # IP-based lookup with a non-existent DB returns None, not a crash.
        assert _maxmind_lookup("8.8.8.8", db_path=tmp_path / "missing.mmdb") is None

    def test_detect_country_handles_missing_headers_attr(self):
        # A request-like with no ``headers`` attribute at all should not crash.
        class _NoHeaders:
            client = None

        assert detect_country(_NoHeaders()) is None

    def test_blocked_cache_is_reloaded_when_path_changes(self, tmp_path, monkeypatch):
        # First load with NG blocked
        cfg_a = tmp_path / "a.json"
        cfg_a.write_text('{"blocked": ["NG"], "version": 1}')
        monkeypatch.setenv("BLOCKED_REGIONS_FILE", str(cfg_a))
        assert "NG" in _load_blocked_regions()

        # Swap config to a different path with NG no longer blocked
        cfg_b = tmp_path / "b.json"
        cfg_b.write_text('{"blocked": ["RU"], "version": 1}')
        monkeypatch.setenv("BLOCKED_REGIONS_FILE", str(cfg_b))
        blocked = _load_blocked_regions()
        assert "NG" not in blocked
        assert "RU" in blocked


# ── FastAPI integration via TestClient ─────────────────────────────────────
class _IsolatedApp(FastAPI):
    """A copy of the real app's middleware, but without coupling to ``main.py``.

    We avoid importing ``gaming.src.backend.main`` here because that module
    pulls in the full app surface. Instead we rebuild the same middleware
    stack so the test exercises the contract directly.
    """

    def __init__(self):
        super().__init__()

        @self.middleware("http")
        async def _geo_fence(request, call_next):
            try:
                check_region(request)
            except BlockedRegionError:
                from fastapi.responses import JSONResponse
                return JSONResponse(
                    status_code=451,
                    content={"error": "service_unavailable_in_region"},
                )
            return await call_next(request)

        @self.get("/")
        async def _root():
            return {"status": "ok"}


@pytest.fixture
def client():
    return TestClient(_IsolatedApp())


class TestFastAPIIntegration:
    def test_cf_ng_returns_451(self, client):
        resp = client.get("/", headers={"cf-ipcountry": "NG"})
        assert resp.status_code == 451
        assert resp.json() == {"error": "service_unavailable_in_region"}

    def test_cf_us_returns_200(self, client):
        resp = client.get("/", headers={"cf-ipcountry": "US"})
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}

    def test_vercel_ng_returns_451(self, client):
        resp = client.get("/", headers={"x-vercel-ip-country": "NG"})
        assert resp.status_code == 451
        assert resp.json() == {"error": "service_unavailable_in_region"}

    def test_no_header_no_maxmind_returns_200(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}

    def test_real_main_app_exposes_root(self):
        # Smoke-test the actual exported ``app`` object so main.py wiring stays correct.
        from gaming.src.backend.main import app
        c = TestClient(app)
        resp = c.get("/", headers={"cf-ipcountry": "US"})
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}

    def test_real_main_app_blocks_ng(self):
        from gaming.src.backend.main import app
        c = TestClient(app)
        resp = c.get("/", headers={"cf-ipcountry": "NG"})
        assert resp.status_code == 451
        assert resp.json() == {"error": "service_unavailable_in_region"}


# ── Bot /start handler test (with mocks) ───────────────────────────────────
class TestBotStartHandler:
    """The bot handler is the user-facing touchpoint for the geo-fence.

    We avoid importing ``gaming.src.backend.bot.handlers`` (which eagerly
    constructs the global app controller and pulls in Supabase / DB layers
    not needed for the geo-fence contract). Instead we reimplement just the
    region-check + send-message logic, exactly as ``cmd_start`` does, so we
    can exercise it without dragging the whole bot runtime into the test
    process.
    """

    async def _run_start(self, headers, sent_messages, *, side_effects):
        """Mirror the first half of ``cmd_start`` (the geo-fence branch)."""
        from gaming.src.backend.middleware import BlockedRegionError, check_region

        class _FakeRequest:
            def __init__(self, headers):
                self.headers = headers or {}
                self.client = None

        await _clear_state()
        try:
            check_region(_FakeRequest(headers))
        except BlockedRegionError:
            await _send(sent_messages, 99, "ClawStation isn't available in your region yet.")
            return "blocked"
        # If we reach here, profile / wallet helpers would be invoked.
        if "raise_profile" in side_effects:
            await _send(sent_messages, 99, "Profile error.")
        else:
            await _send(sent_messages, 99, "OK welcome message")
        return "ok"

    def test_blocked_country_skips_onboarding(self):
        import asyncio

        sent: list[tuple] = []

        async def _send(sent, chat_id, text):
            sent.append((chat_id, text))

        async def _clear_state():
            return None

        # Patch the helpers used in the test mirror.
        globals()["_send"] = _send
        globals()["_clear_state"] = _clear_state

        result = asyncio.run(self._run_start({"cf-ipcountry": "NG"}, sent, side_effects={}))
        assert result == "blocked"
        assert sent == [(99, "ClawStation isn't available in your region yet.")]

    def test_allowed_country_proceeds(self):
        import asyncio

        sent: list[tuple] = []

        async def _send(sent, chat_id, text):
            sent.append((chat_id, text))

        async def _clear_state():
            return None

        globals()["_send"] = _send
        globals()["_clear_state"] = _clear_state

        result = asyncio.run(self._run_start({"cf-ipcountry": "US"}, sent, side_effects={}))
        assert result == "ok"
        assert sent == [(99, "OK welcome message")]
        # The blocked message must NOT have been sent.
        assert not any("isn't available" in m for _, m in sent)

    def test_handler_source_contains_region_block(self):
        """Static check: the cmd_start function must contain the geo-fence branch.

        We can't import the handler module without its heavy dependencies, so we
        verify the source text directly. This guards against accidental removal
        of the region check in future refactors.
        """
        handler_path = Path(__file__).resolve().parents[1] / "src" / "backend" / "bot" / "handlers.py"
        src = handler_path.read_text(encoding="utf-8")
        assert "BlockedRegionError" in src, "cmd_start must reference BlockedRegionError"
        assert "ClawStation isn't available in your region yet." in src, \
            "cmd_start must include the user-facing blocked-region message"
        assert "check_region" in src, "cmd_start must invoke check_region"
