"""
gaming/src/backend/main.py — FastAPI entrypoint for the ClawStation gaming backend.

Registers the geo-fence middleware so any request whose origin country is in the
configured block list is rejected with HTTP 451 and a structured JSON error.

This app is intentionally separate from the social app (``backend/``). Do not import
from ``backend/`` here — the two packages share infrastructure (Supabase, Circle) but
no Python modules.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from gaming.src.backend.api import (
    deposit_router,
    health_router,
    settlement_router,
    webhooks_router,
    rematch_router,
)
from gaming.src.backend.api.rematch_web import router as rematch_web_router
from gaming.src.backend.middleware.geo_fence import evaluate_request
from gaming.src.backend.services.clawstation_circle import start_deposit_expiry_task

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    """Build the ClawStation / Rematch Stack FastAPI application."""
    app = FastAPI(
        title="Boardman API",
        version="0.1.0",
        description="Boardman product API + builder platform surface",
    )

    @app.middleware("http")
    async def geo_fence_middleware(request: Request, call_next):
        # One policy for every route (config/compliance/geo_fence.json):
        # health/docs/webhooks exempt, keyed non-money traffic allowed,
        # money routes judged by the user's country (forwarded by the BFF
        # alongside the master key) and refused in strict mode when unknown.
        decision = evaluate_request(request)
        if not decision.allowed:
            logger.info(
                "geo-fence denied reason=%s country=%s kind=%s path=%s",
                decision.reason,
                decision.country,
                decision.money_kind,
                request.url.path,
            )
            return JSONResponse(status_code=decision.status_code, content=decision.body())
        # Spectator-betting allowlist reads the same country (KYC_AML_PLAN §6.2).
        from gaming.src.backend.services.spectator_policy import set_request_country

        set_request_country(decision.country)
        return await call_next(request)

    from gaming.src.backend.services.spectator_policy import SpectatorBettingUnavailable

    @app.exception_handler(SpectatorBettingUnavailable)
    async def _spectator_betting_unavailable(request: Request, exc: SpectatorBettingUnavailable):
        # §6.4 bodies exactly: {"error": "spectator_betting_disabled"} (403) or
        # {"error": "spectator_betting_unavailable_in_region", "reason": ...} (451).
        return JSONResponse(status_code=exc.status_code, content=exc.body)

    @app.get("/")
    async def root():
        return {
            "status": "ok",
            "product": "rematch",
            "stack": "/api/stack/v0",
            "docs": "/docs",
        }

    app.include_router(deposit_router, prefix="/api")
    app.include_router(health_router, prefix="/api")
    app.include_router(settlement_router, prefix="/api")
    app.include_router(webhooks_router)
    app.include_router(rematch_router)
    app.include_router(rematch_web_router)

    # Rematch Stack — builder platform surface
    from gaming.src.stack.api import router as stack_router
    from gaming.src.stack.api_v1 import router as stack_v1_router
    from gaming.src.stack.agentic.api import router as agentic_router

    app.include_router(stack_router)
    app.include_router(stack_v1_router)
    app.include_router(agentic_router)

    @app.get("/api/health/deep")
    async def health_deep():
        """Readiness for operators and uptime monitors (no auth, no secrets).

        503 when the data dir is not writable, the event loop is stalling, or
        the house session's heartbeat is stale. /api/healthz stays the cheap
        liveness probe the platform health check uses.
        """
        body, ok = await _deep_health()
        return JSONResponse(status_code=200 if ok else 503, content=body)

    return app


# ── deep health ─────────────────────────────────────────────────────────────

_BOOT_AT = time.time()
_LOOP_TICK_SEC = 1.0
_loop_state: dict[str, float] = {"last_tick": 0.0, "max_lag": 0.0, "max_lag_at": 0.0}


async def _loop_lag_monitor() -> None:
    """Tick every second; record how late each tick fires (event-loop lag)."""
    loop = asyncio.get_running_loop()
    while True:
        t0 = loop.time()
        await asyncio.sleep(_LOOP_TICK_SEC)
        lag = max(0.0, loop.time() - t0 - _LOOP_TICK_SEC)
        now = time.time()
        if lag >= _loop_state["max_lag"] or now - _loop_state["max_lag_at"] > 60:
            _loop_state["max_lag"] = lag
            _loop_state["max_lag_at"] = now
        _loop_state["last_tick"] = now


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name) or default)
    except ValueError:
        return default


def _probe_data_dir() -> dict[str, Any]:
    from gaming.src.stack.agentic.store import data_dir

    d = data_dir()
    probe = d / f".health-probe-{os.getpid()}"
    probe.write_text(str(time.time()), encoding="utf-8")
    probe.unlink()
    marker = (d / ".boardman-data-volume").exists()
    return {"ok": True, "marker": marker}


def _read_house_heartbeat() -> Optional[dict[str, Any]]:
    from gaming.src.stack.agentic.store import load_json

    hb = load_json("house_heartbeat.json", None)
    return hb if isinstance(hb, dict) else None


def _read_supervisors() -> list[dict[str, Any]]:
    from gaming.src.stack.agentic.store import data_dir

    out: list[dict[str, Any]] = []
    rt = data_dir() / ".runtime"
    if not rt.is_dir():
        return out
    for p in rt.glob("supervisor-*.json"):
        try:
            doc = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        if time.time() - float(doc.get("ts") or 0) <= 120:
            out.append(doc)
    return out


async def _deep_health() -> tuple[dict[str, Any], bool]:
    checks: dict[str, Any] = {}
    ok = True
    degraded = False
    now = time.time()
    uptime = now - _BOOT_AT

    # 1. event loop: the monitor keeps ticking and recent lag stays small.
    lag_fail = _env_float("BOARDMAN_HEALTH_LOOP_LAG_FAIL_SEC", 5.0)
    since_tick = now - _loop_state["last_tick"] if _loop_state["last_tick"] else None
    recent_lag = _loop_state["max_lag"] if now - _loop_state["max_lag_at"] <= 60 else 0.0
    if since_tick is None and not _loop_state.get("started"):
        # Startup hook did not run (e.g. TestClient without lifespan): start now.
        _loop_state["started"] = 1.0
        asyncio.get_running_loop().create_task(_loop_lag_monitor())
    loop_ok = since_tick is None or since_tick < 3 * _LOOP_TICK_SEC + lag_fail
    checks["event_loop"] = {
        "ok": loop_ok,
        "max_lag_60s_ms": round(recent_lag * 1000),
        "since_tick_ms": None if since_tick is None else round(since_tick * 1000),
    }
    if not loop_ok:
        ok = False
    elif recent_lag >= lag_fail:
        degraded = True
        checks["event_loop"]["warn"] = "loop stalled recently"

    # 2. data dir writable (off-loop with a timeout so a hung volume can't hang us)
    try:
        checks["data_dir"] = await asyncio.wait_for(asyncio.to_thread(_probe_data_dir), 3.0)
        if os.getenv("REQUIRE_PERSISTENT_DATA", "").strip() == "1" and not checks["data_dir"]["marker"]:
            checks["data_dir"]["ok"] = False
            ok = False
    except Exception as exc:
        checks["data_dir"] = {"ok": False, "error": exc.__class__.__name__}
        ok = False

    # 3. house session heartbeat
    house_on = (os.getenv("BOARDMAN_HOUSE_SESSION") or "1").strip().lower() not in {
        "0", "false", "no", "off",
    }
    if not house_on:
        checks["house_session"] = {"ok": True, "state": "disabled"}
    else:
        max_age = _env_float("BOARDMAN_HOUSE_HEARTBEAT_MAX_AGE_SEC", 120.0)
        max_phase = _env_float("BOARDMAN_HOUSE_PHASE_MAX_SEC", 2700.0)
        try:
            hb = await asyncio.wait_for(asyncio.to_thread(_read_house_heartbeat), 3.0)
        except Exception:
            hb = None
        if not hb:
            starting = uptime < max_age
            checks["house_session"] = {
                "ok": starting,
                "state": "starting" if starting else "no_heartbeat",
            }
            ok = ok and starting
        else:
            age = now - float(hb.get("ts") or 0)
            phase_age = now - float(hb.get("phase_at") or now)
            fresh = age <= max_age
            info = {
                "ok": fresh,
                "age_sec": round(age),
                "phase": hb.get("phase"),
                "phase_age_sec": round(phase_age),
                "games": hb.get("games"),
            }
            # Waiting for funds or paused by the admin desk can legitimately
            # last for hours; only an active phase stuck this long is suspect.
            if fresh and phase_age > max_phase and hb.get("phase") not in {
                "no_funds", "schedule_paused", "cadence",
            }:
                info["warn"] = "phase unchanged for too long"
                degraded = True
            checks["house_session"] = info
            ok = ok and fresh

    # 4. supervised processes (informational; restarts flag degradation)
    try:
        sups = await asyncio.wait_for(asyncio.to_thread(_read_supervisors), 3.0)
    except Exception:
        sups = []
    if sups:
        procs: dict[str, Any] = {}
        for s in sups:
            for name, st in (s.get("children") or {}).items():
                procs[name] = {
                    "running": bool(st.get("running") or st.get("adopted")),
                    "restarts": st.get("restarts", 0),
                }
                if not procs[name]["running"]:
                    degraded = True
        checks["processes"] = procs

    status = "ok" if ok and not degraded else ("degraded" if ok else "fail")
    return (
        {
            "status": status,
            "uptime_sec": round(uptime),
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "checks": checks,
        },
        ok,
    )


# Module-level app for ``uvicorn gaming.src.backend.main:app``
app = create_app()


@app.on_event("startup")
async def _startup():
    """Start background jobs on server startup."""
    start_deposit_expiry_task(interval_seconds=3600.0)
    _loop_state["started"] = 1.0
    app.state.loop_lag_monitor = asyncio.create_task(_loop_lag_monitor())
    logger.info("[Startup] ClawStation API started, expiry task scheduled")
