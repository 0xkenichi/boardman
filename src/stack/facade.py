"""
RematchStack façade — single entry point for apps and the Stack HTTP API.

Wraps live ClawStation/Rematch services without re-implementing money rails.
"""
from __future__ import annotations

import logging
import os
from decimal import Decimal
from functools import lru_cache
from typing import Any, Optional

from gaming.src.stack.types import ChainInfo, StackCapabilities, StackHealth

logger = logging.getLogger(__name__)


class RematchStack:
    """Platform façade for Rematch Stack v0."""

    def __init__(self) -> None:
        self.version = "0.1.0"

    # ── Discovery ──────────────────────────────────────────────────────────

    def capabilities(self) -> StackCapabilities:
        from gaming.src.backend.services.chains import list_chains

        live = [c["id"] for c in list_chains(include_disabled=False)]
        nxt = [
            c["id"]
            for c in list_chains(include_disabled=True)
            if not c.get("enabled") and c.get("status") == "next"
        ]
        from gaming.src.backend.services.game_catalog import list_games

        game_ids = [g["game_id"] for g in list_games(enabled_only=True)]
        return StackCapabilities(
            version=self.version,
            default_chain=os.getenv("CLAW_DEFAULT_CHAIN", "arc"),
            network=os.getenv("NETWORK", "testnet"),
            live_chains=live or ["arc"],
            next_chains=nxt or ["avalanche"],
            games=game_ids or ["EAFC", "imessage.8_ball"],
            experiences=["telegram:rematch", "api:stack_v1"],
        )

    def list_games(self, category: Optional[str] = None) -> list[dict[str, Any]]:
        from gaming.src.backend.services.game_catalog import list_games

        return list_games(category=category, enabled_only=True)

    def list_chains(self, *, include_disabled: bool = False) -> list[ChainInfo]:
        """Default: live chains only (Arc). Ops can pass include_disabled."""
        from gaming.src.backend.services.chains import list_chains

        out: list[ChainInfo] = []
        for c in list_chains(include_disabled=include_disabled):
            escrow_ok = False
            try:
                from gaming.src.backend.services.chains import get_escrow_address

                get_escrow_address(c["id"])
                escrow_ok = True
            except Exception:
                escrow_ok = bool(c.get("escrow_address"))
            out.append(
                ChainInfo(
                    id=c["id"],
                    label=c.get("label") or c["id"],
                    recommended=bool(c.get("recommended")),
                    enabled=bool(c.get("enabled", True)),
                    status=str(c.get("status") or ("live" if c.get("enabled") else "disabled")),
                    chain_id=c.get("chain_id"),
                    explorer_tx=c.get("explorer_tx") or "",
                    gas_token=c.get("gas_token") or "",
                    escrow_configured=escrow_ok,
                    notes=c.get("notes") or "",
                )
            )
        return out

    def health(self) -> StackHealth:
        checks: dict[str, str] = {"stack": "ok"}
        # Supabase
        try:
            from backend.supabase_client import get_supabase

            get_supabase().table("profiles").select("id").limit(1).execute()
            checks["supabase"] = "ok"
        except Exception as exc:
            logger.warning("[Stack] supabase health: %s", exc)
            checks["supabase"] = "unhealthy"
        # Circle keys present (not a live API call — cheap)
        if os.getenv("CIRCLE_API_KEY") and os.getenv("CIRCLE_ENTITY_SECRET"):
            checks["circle_config"] = "ok"
        else:
            checks["circle_config"] = "missing_keys"
        status = "ok" if checks.get("supabase") == "ok" else "degraded"
        return StackHealth(status=status, version=self.version, checks=checks)

    # ── Public data (same as Rematch board) ────────────────────────────────

    def public_board(self, leaderboard_limit: int = 25, open_limit: int = 30) -> dict[str, Any]:
        from gaming.src.backend.services.rematch_public import (
            get_chain_metrics,
            get_leaderboard,
            get_open_public_challenges,
        )

        return {
            "success": True,
            "leaderboard": get_leaderboard(leaderboard_limit),
            "open_challenges": get_open_public_challenges(open_limit),
            "metrics": get_chain_metrics(),
        }

    # ── Wallets (async wrappers) ───────────────────────────────────────────

    async def ensure_wallet(self, user_id: str, chain_id: Optional[str] = None) -> dict[str, Any]:
        from gaming.src.backend.services.clawstation_circle import ensure_user_wallet

        return await ensure_user_wallet(user_id, chain_id=chain_id)

    async def get_usdc_balance(self, user_id: str, chain_id: Optional[str] = None) -> Decimal:
        from gaming.src.backend.services.clawstation_circle import get_usdc_balance

        return await get_usdc_balance(user_id, chain_id=chain_id)

    # ── Settlement (operator) ──────────────────────────────────────────────

    async def settle_challenge(self, challenge_id: str) -> dict[str, Any]:
        from gaming.src.backend.services.clawstation_settlement import settle_challenge

        return await settle_challenge(challenge_id)


@lru_cache(maxsize=1)
def get_stack() -> RematchStack:
    return RematchStack()
