"""
Avalanche funding-rail helper.

Full ERC-20 Transfer indexing needs a reliable indexer or archive RPC.
For now we provide:
  - ops deposit address + expected ref matching (manual / screenshot)
  - optional lightweight "recent txs" note for admins
  - status used by /rails_status

Auto-detect of USDC transfers can be enabled later with:
  AVALANCHE_USDC_ADDRESS + BOARDMAN_OPS_USDC_AVALANCHE + a websockets/log poller.
"""
from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


def avalanche_ops_address() -> str:
    from gaming.src.backend.services.funding_rails import ops_deposit_address

    return ops_deposit_address("avalanche")


def avalanche_configured() -> bool:
    return bool(avalanche_ops_address())


def avalanche_status() -> dict[str, Any]:
    addr = avalanche_ops_address() or ""
    return {
        "configured": bool(addr),
        "ops_address": addr or None,
        "mode": "manual_ref",  # until log poller ships
        "network": os.getenv("AVALANCHE_NETWORK", "fuji"),
        "usdc": os.getenv(
            "AVALANCHE_USDC_ADDRESS",
            "0x5425890298aed601595a70AB815c96711a31Bc65",  # Fuji USDC
        ),
        "notes": (
            "Players send USDC with top-up ref. Ops credits Arc play wallet "
            "then /credit_topup. Auto Transfer watcher = next."
        ),
    }


async def watch_avalanche_deposits() -> dict[str, Any]:
    """Placeholder job — no-op until log indexer is configured."""
    if os.getenv("AVALANCHE_WATCH_ENABLED", "0").lower() not in ("1", "true", "yes"):
        return {"skipped": True, "reason": "manual_mode"}
    # Future: eth_getLogs for Transfer(to=ops)
    logger.debug("[AvaxWatch] auto watch not implemented; manual ref flow active")
    return {"skipped": True, "reason": "not_implemented"}
