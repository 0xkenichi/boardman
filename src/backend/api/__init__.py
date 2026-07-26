"""
gaming/src/backend/api — FastAPI routers for the ClawStation backend.
"""

from gaming.src.backend.api.deposit import router as deposit_router
from gaming.src.backend.api.health import router as health_router
from gaming.src.backend.api.settlement import router as settlement_router
from gaming.src.backend.api.webhooks import router as webhooks_router
from gaming.src.backend.api.rematch import router as rematch_router

__all__ = [
    "deposit_router",
    "health_router",
    "settlement_router",
    "webhooks_router",
    "rematch_router",
]
