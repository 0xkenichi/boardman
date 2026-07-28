"""
gaming/src/backend/main.py — FastAPI entrypoint for the ClawStation gaming backend.

Registers the geo-fence middleware so any request whose origin country is in the
configured block list is rejected with HTTP 451 and a structured JSON error.

This app is intentionally separate from the social app (``backend/``). Do not import
from ``backend/`` here — the two packages share infrastructure (Supabase, Circle) but
no Python modules.
"""
from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from gaming.src.backend.api import (
    deposit_router,
    health_router,
    settlement_router,
    webhooks_router,
    rematch_router,
)
from gaming.src.backend.middleware import BlockedRegionError, check_region
from gaming.src.backend.services.clawstation_circle import start_deposit_expiry_task

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    """Build the ClawStation / Rematch Stack FastAPI application."""
    app = FastAPI(
        title="Rematch Stack API",
        version="0.1.0",
        description="Rematch product API + Rematch Stack (builder platform) surface",
    )

    @app.middleware("http")
    async def geo_fence_middleware(request: Request, call_next):
        try:
            check_region(request)
        except BlockedRegionError as exc:
            logger.info(
                "geo-fence blocked request country=%s path=%s",
                exc.country_code,
                request.url.path,
            )
            return JSONResponse(
                status_code=451,
                content={"error": "service_unavailable_in_region"},
            )
        return await call_next(request)

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

    # Rematch Stack — builder platform surface
    from gaming.src.stack.api import router as stack_router

    app.include_router(stack_router)

    return app


# Module-level app for ``uvicorn gaming.src.backend.main:app``
app = create_app()


@app.on_event("startup")
async def _startup():
    """Start background jobs on server startup."""
    start_deposit_expiry_task(interval_seconds=3600.0)
    logger.info("[Startup] ClawStation API started, expiry task scheduled")
