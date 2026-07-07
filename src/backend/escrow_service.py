"""
escrow_service.py
────────────────────────────────────────────────────────────────────────────────
On-chain escrow integration. Wraps blockchain_layer.py for match lifecycle.
Handles: create match → join → resolve → payout with fee deduction.
"""

# =============================================================================
# PARKED / DORMANT — 2026-06-13 ELON FOCUS (see ELON_FOCUS_PLAN.md)
# Previous on-chain gaming staking layer. Not used by current social quest product.
# Do not wire into active routes or services for quests/friends/reputation.
# =============================================================================

import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)

PLATFORM_FEE_PERCENT = float(os.getenv("PLATFORM_FEE_PERCENT", "0.03"))  # 3%
INSURANCE_POOL_ADDRESS = os.getenv("INSURANCE_POOL_ADDRESS", "")


class EscrowService:
    def __init__(self):
        self._bl = None

    @property
    def bl(self):
        if self._bl is None:
            from blockchain_layer import get_blockchain_layer
            self._bl = get_blockchain_layer()
        return self._bl

    async def create_match(self, match_id: str, stake_usd: float) -> dict:
        """Create a match on ClawEscrow contract."""
        try:
            result = await self.bl.create_match_onchain(match_id, stake_usd)
            logger.info(f"[Escrow] Match {match_id} created on-chain: {result.get('tx_hash')}")
            return {"success": True, **result}
        except Exception as e:
            logger.error(f"[Escrow] Create match failed: {e}")
            return {"success": False, "error": str(e)}

    async def join_match(self, match_id: str, player2_address: str) -> dict:
        """Player 2 joins a match (approves USDC transfer to escrow)."""
        try:
            mid = self.bl.match_id_to_bytes32(match_id)
            fn = self.bl.escrow.functions.joinMatch(mid)
            result = await __import__('asyncio').to_thread(self.bl._build_and_send, fn)
            logger.info(f"[Escrow] Match {match_id} joined: {result.get('tx_hash')}")
            return {"success": True, **result}
        except Exception as e:
            logger.error(f"[Escrow] Join match failed: {e}")
            return {"success": False, "error": str(e)}

    async def resolve_match(self, match_id: str, winner_address: str) -> dict:
        """Resolve a match — winner gets payout minus platform fee."""
        try:
            result = await self.bl.resolve_match_onchain(match_id, winner_address)
            logger.info(f"[Escrow] Match {match_id} resolved → {winner_address}: {result.get('tx_hash')}")
            return {"success": True, **result}
        except Exception as e:
            logger.error(f"[Escrow] Resolve match failed: {e}")
            return {"success": False, "error": str(e)}

    async def cancel_match(self, match_id: str) -> dict:
        """Cancel a match — both players get refunded."""
        try:
            result = await self.bl.cancel_match_onchain(match_id)
            logger.info(f"[Escrow] Match {match_id} cancelled: {result.get('tx_hash')}")
            return {"success": True, **result}
        except Exception as e:
            logger.error(f"[Escrow] Cancel match failed: {e}")
            return {"success": False, "error": str(e)}

    async def flag_dispute(self, match_id: str) -> dict:
        """Flag a match as disputed on-chain."""
        try:
            result = await self.bl.flag_dispute_onchain(match_id)
            logger.info(f"[Escrow] Match {match_id} disputed: {result.get('tx_hash')}")
            return {"success": True, **result}
        except Exception as e:
            logger.error(f"[Escrow] Flag dispute failed: {e}")
            return {"success": False, "error": str(e)}

    def get_match_onchain(self, match_id: str) -> dict:
        """Get on-chain match status."""
        try:
            return self.bl.get_match_status(match_id)
        except Exception as e:
            return {"error": str(e)}

    def calculate_payout(self, stake_usd: float) -> dict:
        """Calculate payout with platform fee deduction."""
        total_pot = stake_usd * 2
        fee = total_pot * PLATFORM_FEE_PERCENT
        payout = total_pot - fee
        return {
            "total_pot": total_pot,
            "platform_fee": fee,
            "fee_percent": PLATFORM_FEE_PERCENT * 100,
            "winner_payout": payout,
        }


_escrow_service = None

def get_escrow_service() -> EscrowService:
    global _escrow_service
    if _escrow_service is None:
        _escrow_service = EscrowService()
    return _escrow_service
