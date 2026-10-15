"""Is a profile empty enough to merge into another one?

Empty means: no money on any rail, no matches, no top-ups. Every check fails
closed: if we cannot prove a profile is empty, it is not (CHANNELS_DESIGN §2.3).
"""
from __future__ import annotations

import asyncio
import logging
from decimal import Decimal

from gaming.src.channels.core.identity.repo import get_repo

logger = logging.getLogger(__name__)

_DUST = Decimal("0.01")


async def profile_is_empty(profile_id: str) -> tuple[bool, list[str]]:
    reasons: list[str] = []

    try:
        from gaming.src.backend.services.clawstation_circle import get_balance_summary

        s = await get_balance_summary(profile_id)
        for k in ("spendable_usdc", "other_usdc", "ledger_usdc"):
            if Decimal(str(s.get(k) or 0)) >= _DUST:
                reasons.append(f"balance:{k}")
        if s.get("balance_error"):
            reasons.append("balance:unknown")
    except Exception:
        logger.warning("[channels] emptiness: balance lookup failed", exc_info=True)
        reasons.append("balance:unknown")

    def _db_checks() -> list[str]:
        out: list[str] = []
        try:
            prof = get_repo().get_profile(profile_id) or {}
        except Exception:
            return ["profile:unknown"]
        if not prof:
            return ["profile:missing"]
        if Decimal(str(prof.get("wallet_balance_usdc") or 0)) >= _DUST:
            out.append("balance:legacy")
        if any(int(prof.get(k) or 0) for k in ("gaming_wins", "gaming_losses", "gaming_draws")):
            out.append("matches:played")
        if prof.get("linked_wallet"):
            out.append("wallet:linked")
        try:
            from backend.supabase_client import get_supabase

            ch = get_supabase().schema("gaming").table("challenges")
            for col in ("creator_id", "opponent_id"):
                r = ch.select("id").eq(col, profile_id).limit(1).execute()
                if getattr(r, "data", None):
                    out.append("matches:challenges")
                    break
        except Exception:
            out.append("matches:unknown")
        try:
            from gaming.src.backend.services.fiat_topup import _load_all

            if any(str(t.get("profile_id")) == str(profile_id) for t in _load_all()):
                out.append("topups")
        except Exception:
            out.append("topups:unknown")
        return out

    reasons += await asyncio.to_thread(_db_checks)
    return (not reasons), reasons
