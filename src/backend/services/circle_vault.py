"""
services/circle_vault.py — The Single Source of Truth
Fetches live USDC balances from Circle Programmable Wallets API.
"""
import os
import httpx
import logging
from typing import Optional

logger = logging.getLogger(__name__)

CIRCLE_API_KEY = os.getenv("CIRCLE_API_KEY")
BASE_URL = "https://api.circle.com/v1/w3s"

async def get_live_balance(wallet_id: str) -> Optional[float]:
    """
    Fetch the real-time USDC balance from Circle for a given wallet_id.
    Returns balance in USDC (float), or None on failure.
    """
    if not CIRCLE_API_KEY:
        raise ValueError("CIRCLE_API_KEY not set")

    headers = {
        "Authorization": f"Bearer {CIRCLE_API_KEY}",
        "Content-Type": "application/json"
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(f"{BASE_URL}/wallets/{wallet_id}/balances", headers=headers)
            logger.info(f"[Circle] Balance API {resp.status_code} for wallet {wallet_id}")
            resp.raise_for_status()
            data = resp.json()
            logger.info(f"[Circle] Balance response: {str(data)[:300]}")
    except Exception as e:
        logger.error(f"[Circle] Balance fetch error: {e}")
        return None

    # Extract USDC balance from tokenBalances array
    for token in data.get("data", {}).get("tokenBalances", []):
        if token.get("token", {}).get("symbol") == "USDC":
            amount = token.get("amount")
            return float(amount) if amount is not None else 0.0

    return 0.0
