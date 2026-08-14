"""
Request Arc Testnet USDC via Circle's faucet drips API when the account allows it.

Circle docs: POST /v1/faucet/drips
  { address, blockchain: "ARC-TESTNET", usdc: true }

Notes:
- Public faucet.circle.com always needs human reCAPTCHA — we cannot auto-submit that.
- API drip often requires a mainnet-upgraded Circle developer account.
- On failure, the bot falls back to the web fund helper with the address prefilled.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)

CIRCLE_FAUCET_URL = "https://faucet.circle.com/"
ARC_BLOCKCHAIN = "ARC-TESTNET"


async def request_arc_usdc(address: str) -> dict[str, Any]:
    """
    Try to drip Arc testnet USDC to ``address``.

    Returns:
      { ok: bool, method: "api"|"none", message: str, status?: int }
    """
    addr = (address or "").strip()
    if not addr.startswith("0x") or len(addr) < 20:
        return {"ok": False, "method": "none", "message": "Invalid address"}

    api_key = (os.getenv("CIRCLE_API_KEY") or "").strip()
    if not api_key:
        return {
            "ok": False,
            "method": "none",
            "message": "No CIRCLE_API_KEY — use web faucet",
        }

    # Prefer production host; sandbox rejects TEST keys for this route differently
    bases = [
        os.getenv("CIRCLE_API_BASE", "https://api.circle.com").rstrip("/").removesuffix("/v1"),
        "https://api.circle.com",
    ]
    # de-dupe
    seen = set()
    unique_bases = []
    for b in bases:
        if b not in seen:
            seen.add(b)
            unique_bases.append(b)

    last_err = "Faucet unavailable"
    async with httpx.AsyncClient(timeout=25.0) as client:
        for base in unique_bases:
            url = f"{base}/v1/faucet/drips"
            try:
                r = await client.post(
                    url,
                    json={
                        "address": addr,
                        "blockchain": ARC_BLOCKCHAIN,
                        "usdc": True,
                        "native": False,
                    },
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                        "Accept": "application/json",
                    },
                )
            except Exception as exc:
                logger.warning("[CircleFaucet] request error: %s", exc)
                last_err = str(exc)
                continue

            if r.status_code in (200, 201, 202, 204):
                return {
                    "ok": True,
                    "method": "api",
                    "message": "USDC requested — wait ~30s then refresh Wallet",
                    "status": r.status_code,
                }

            # 403 often = sandbox key / account not upgraded for faucet API
            try:
                body = r.json()
                last_err = body.get("message") or body.get("error") or r.text[:200]
            except Exception:
                last_err = r.text[:200] or f"HTTP {r.status_code}"
            logger.info(
                "[CircleFaucet] drip failed base=%s status=%s msg=%s",
                base,
                r.status_code,
                last_err,
            )
            # Don't hammer other bases if clearly forbidden
            if r.status_code in (401, 403):
                break

    return {
        "ok": False,
        "method": "none",
        "message": last_err,
        "status": None,
    }


def fund_helper_url(address: str, site: Optional[str] = None) -> str:
    """Our site page with address prefilled for one-tap copy + faucet open."""
    try:
        from gaming.src.bot.brand_assets import boardman_site_url

        root = (site or boardman_site_url()).rstrip("/")
    except Exception:
        root = (site or os.getenv("BOARDMAN_URL") or os.getenv("REMATCH_WEB_URL") or "https://boardman.playingsidequest.fun").rstrip("/")
    if root.endswith("/rematch"):
        root = root[: -len("/rematch")]
    addr = (address or "").strip()
    if addr:
        return f"{root}/get-usdc?address={addr}"
    return f"{root}/get-usdc"
