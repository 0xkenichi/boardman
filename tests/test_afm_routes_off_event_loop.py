"""Slow AFM season work must not stall the rest of the API.

GET /football/season parses a ~20MB state file and POST /football/season/tick
resolves whole matchdays (manager webhooks, LLM brains). As `async def`
routes they ran on the event loop and every other request queued behind
them — the live season endpoint took up to 52s. They are plain `def` now,
so FastAPI runs them in its threadpool.
"""
from __future__ import annotations

import asyncio
import time

import pytest

MASTER = "sk_master_test"
SLOW = 0.6


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.setenv("BOARDMAN_AGENTIC_DATA", str(tmp_path))
    for name in ("REMATCH_API_KEY", "STACK_API_KEY", "BOARDMAN_STACK_API_KEYS_FILE", "BOARDMAN_STACK_ALLOW_OPEN"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("BOARDMAN_API_KEY", MASTER)


def _app():
    from fastapi import FastAPI

    from gaming.src.stack.agentic import api as api_mod

    app = FastAPI()
    app.include_router(api_mod.router)

    @app.get("/ping")
    async def ping():
        return {"ok": True}

    return app, api_mod


def _fast_request_waits_for(method: str, path: str) -> float:
    """Seconds until a /ping sent 0.1s after `path` came back."""
    import httpx

    app, _ = _app()
    prefix = "/api/stack/agentic"

    async def run() -> float:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
            t0 = time.perf_counter()
            slow = asyncio.create_task(
                c.request(method, prefix + path, headers={"X-Boardman-Key": MASTER})
            )
            await asyncio.sleep(0.1)  # let the slow handler start
            r = await c.get("/ping")
            took = time.perf_counter() - t0  # ~0.1s, or ~SLOW when the loop was blocked
            assert r.status_code == 200
            res = await slow
            assert res.status_code == 200, res.text
            return took

    return asyncio.run(run())


def test_season_read_runs_off_the_event_loop(monkeypatch):
    from gaming.src.stack.agentic.games.football_managers import season as S

    def slow_get_season():
        time.sleep(SLOW)
        return None

    monkeypatch.setattr(S, "get_season", slow_get_season)
    assert _fast_request_waits_for("GET", "/football/season") < SLOW * 0.75


def test_season_tick_runs_off_the_event_loop(monkeypatch):
    from gaming.src.stack.agentic.games.football_managers import season as S

    def slow_tick(now=None):
        time.sleep(SLOW)
        return {"action": "idle"}

    monkeypatch.setattr(S, "tick", slow_tick)
    assert _fast_request_waits_for("POST", "/football/season/tick") < SLOW * 0.75


def test_heavy_football_routes_are_threadpool_routes():
    import inspect

    _, api_mod = _app()
    for name in (
        "football_season", "football_season_tick", "football_season_open", "football_season_replay",
        "football_season_prematch", "football_match_report", "football_owner_dashboard",
        "football_clubs", "football_club", "football_cup", "football_cup_tick", "football_cup_replay",
    ):
        assert not inspect.iscoroutinefunction(getattr(api_mod, name)), name
