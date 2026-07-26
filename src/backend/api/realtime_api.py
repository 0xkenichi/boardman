"""
Main API - sideQuest Real-time & Notifications System
Integrates WebSocket, Notifications, Presence, and Gaming APIs.
"""

import os
import logging
from datetime import datetime, timezone
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware

# ─── Logging ─────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s"
)
logger = logging.getLogger(__name__)

# ─── Lifespan ────────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("[API] Starting sideQuest API with realtime & notifications...")
    yield
    logger.info("[API] Shutting down sideQuest API...")

# ─── FastAPI App ─────────────────────────────────────────────────────────────────

app = FastAPI(
    title="sideQuest API",
    version="1.1.0",  # Bumped for realtime features
    lifespan=lifespan
)

# ─── CORS ────────────────────────────────────────────────────────────────────────
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "https://playingsidequest.fun,https://staging.playingsidequest.fun,https://app.playingsidequest.fun,http://localhost:3000,http://localhost,capacitor://localhost,ionic://localhost,null").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)

# ─── Health Check ────────────────────────────────────────────────────────────────

@app.get("/health")
async def health_check():
    return {
        "status": "ok",
        "service": "sidequest-api",
        "version": "1.1.0",
        "features": ["realtime", "notifications", "presence", "websocket"],
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

# ─── API Routers ─────────────────────────────────────────────────────────────────

# Existing routes
from .webhooks import router as circle_webhook_router
app.include_router(circle_webhook_router, prefix="/webhook", tags=["webhooks"])

# New notifications routes
from .notifications import router as notifications_router
app.include_router(notifications_router)

# Presence routes
from .presence import router as presence_router
app.include_router(presence_router)

# Chat routes
from .chat import router as chat_router
app.include_router(chat_router)

# ─── Run Server ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)
