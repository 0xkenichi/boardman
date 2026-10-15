"""Slow AFM season work must not stall the rest of the API.

GET /football/season parses a ~20MB state file and POST /football/season/tick
resolves whole matchdays (manager webhooks, LLM brains). As `async def`
routes they ran on the event loop and every other request queued behind
them — the live season endpoint took up to 52s. They are plain `def` now,
so FastAPI runs them in its threadpool.
"""
from __future__ import annotations

import asyncio
import threading

import pytest

MASTER = "sk_master_test"
SAFETY = 10.0  # only bounds a broken run; the assertions use events, not timings


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


class _Gate:
    """A slow handler that holds until released, so the test needs no timings."""

    def __init__(self) -> None:
        self.started = threading.Event()
        self.release = threading.Event()

    def hold(self) -> None:
        self.started.set()
        self.release.wait(SAFETY)


def _ping_answers_while_held(method: str, path: str, gate: _Gate) -> bool:
    """True when /ping answers while `path` is still held in its handler.

    If the slow route ran on the event loop, the loop could not serve /ping
    until the gate's safety timeout let the handler finish, so the slow
    request would already be done by the time /ping returns.
    """
    import httpx

    app, _ = _app()
    prefix = "/api/stack/agentic"

    async def run() -> bool:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
            slow = asyncio.create_task(
                c.request(method, prefix + path, headers={"X-Boardman-Key": MASTER})
            )
            await asyncio.to_thread(gate.started.wait, SAFETY)
            r = await c.get("/ping")
            answered_while_held = r.status_code == 200 and not slow.done()
            gate.release.set()
            res = await slow
            assert res.status_code == 200, res.text
            return answered_while_held

    return asyncio.run(run())


def test_season_read_runs_off_the_event_loop(monkeypatch):
    from gaming.src.stack.agentic.games.football_managers import season as S

    gate = _Gate()

    def slow_get_season():
        gate.hold()
        return None

    monkeypatch.setattr(S, "get_season", slow_get_season)
    assert _ping_answers_while_held("GET", "/football/season", gate)


def test_season_tick_runs_off_the_event_loop(monkeypatch):
    from gaming.src.stack.agentic.games.football_managers import season as S

    gate = _Gate()

    def slow_tick(now=None):
        gate.hold()
        return {"action": "idle"}

    monkeypatch.setattr(S, "tick", slow_tick)
    assert _ping_answers_while_held("POST", "/football/season/tick", gate)


def test_heavy_football_routes_are_threadpool_routes():
    import inspect

    _, api_mod = _app()
    for name in (
        "football_season", "football_season_tick", "football_season_open", "football_season_replay",
        "football_season_prematch", "football_match_report", "football_owner_dashboard",
        "football_clubs", "football_club", "football_cup", "football_cup_tick", "football_cup_replay",
    ):
        assert not inspect.iscoroutinefunction(getattr(api_mod, name)), name
