"""
api_blockchain_additions.py
────────────────────────────────────────────────────────────────────────────────
Additions to paste into api.py:
  1. Lifespan handler that starts TransactionManager on startup
  2. /health/blockchain endpoint
  3. /wallet/link endpoint for linking crypto wallet
  4. /admin/blockchain endpoints

Paste the relevant sections into your existing api.py.
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI, APIRouter, HTTPException, Depends
from pydantic import BaseModel
import logging
from utils.auth import get_current_user, get_current_admin_user

logger = logging.getLogger(__name__)


# ─── 1. Lifespan (replace your existing @app on startup) ─────────────────────
# Replace your FastAPI() instantiation with this:

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("[API] Starting sideQuest backend...")
    try:
        from transaction_manager import get_tx_manager
        tx_manager = get_tx_manager()
        await tx_manager.start()
        logger.info("[API] TransactionManager started ✅")
    except Exception as e:
        logger.error(f"[API] TransactionManager failed to start: {e}")
        # Don't crash the whole app — blockchain may not be configured yet

    yield

    # Shutdown
    try:
        from transaction_manager import get_tx_manager
        await get_tx_manager().stop()
    except Exception:
        pass
    logger.info("[API] Shutdown complete")


# app = FastAPI(title="sideQuest API", lifespan=lifespan)


# ─── 2. Blockchain Health Endpoint ────────────────────────────────────────────

router = APIRouter(prefix="/api/v1/health", tags=["Health"])

@router.get("/blockchain")
async def blockchain_health():
    """Returns on-chain connectivity status and admin wallet info."""
    try:
        from blockchain_layer import get_blockchain_layer
        bl = get_blockchain_layer()
        info = bl.get_network_info()
        return {
            "status": "ok" if info["connected"] else "degraded",
            **info,
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "hint": "Check CSC_ADDRESS and ADMIN_PRIVATE_KEY in .env",
        }


# ─── 3. Wallet Link Endpoint ──────────────────────────────────────────────────

wallet_router = APIRouter(prefix="/api/v1/wallet", tags=["Wallet"])

class LinkWalletRequest(BaseModel):
    wallet_address: str  # 0x...
    user_id: str

@wallet_router.post("/link")
async def link_wallet(
    req: LinkWalletRequest,
    current_user: str = Depends(get_current_user),
):
    """Link a crypto wallet address to a user's sideQuest profile."""
    if current_user != req.user_id:
        raise HTTPException(status_code=403, detail="Can only link wallet to your own profile")

    from web3 import Web3
    if not Web3.is_address(req.wallet_address):
        raise HTTPException(status_code=400, detail="Invalid Ethereum address")

    from db_layer_blockchain import link_wallet_address, get_blockchain_layer
    bl = get_blockchain_layer()

    checksum = Web3.to_checksum_address(req.wallet_address)
    await link_wallet_address(req.user_id, checksum)

    return {
        "success": True,
        "wallet": checksum,
        "deposit_address": bl.get_deposit_address(),
        "network": bl.network_key,
        "usdc_address": bl.network["usdc_address"],
        "message": (
            f"Send USDC to {bl.get_deposit_address()} on {bl.network['name']} "
            f"from your wallet {checksum}. Your balance will be credited automatically."
        ),
    }


@wallet_router.get("/deposit-info")
async def deposit_info():
    """Returns the deposit address and network info for crypto top-ups."""
    from blockchain_layer import get_blockchain_layer
    bl = get_blockchain_layer()
    return {
        "deposit_address": bl.get_deposit_address(),
        "network":         bl.network["name"],
        "chain_id":        bl.network["chain_id"],
        "usdc_address":    bl.network["usdc_address"],
        "explorer":        bl.network["explorer"],
        "minimum_deposit": 1.0,
        "note": (
            "Send USDC only. Other tokens will not be credited. "
            "Deposits typically confirm within 30 seconds."
        ),
    }


# ─── 4. Admin Endpoints ───────────────────────────────────────────────────────

admin_router = APIRouter(prefix="/api/v1/admin", tags=["Admin"])

class ResolveMatchRequest(BaseModel):
    match_id: str
    winner_user_id: str
    winner_wallet: str
    loser_user_id: str
    stake_usd: float

class CancelMatchRequest(BaseModel):
    match_id: str
    player1_user_id: str
    player2_user_id: str = None
    stake_usd: float

@admin_router.post("/resolve-match")
async def admin_resolve_match(
    req: ResolveMatchRequest,
    admin: str = Depends(get_current_admin_user),
):
    """Manually resolve a match (admin-only). Used for AI mediator results."""
    from betting_engine_onchain import resolve_match_and_payout
    result = await resolve_match_and_payout(
        match_id=req.match_id,
        winner_user_id=req.winner_user_id,
        winner_wallet=req.winner_wallet,
        loser_user_id=req.loser_user_id,
        stake_usd=req.stake_usd,
    )
    return {"success": True, **result}

@admin_router.post("/cancel-match")
async def admin_cancel_match(
    req: CancelMatchRequest,
    admin: str = Depends(get_current_admin_user),
):
    """Cancel a match and refund players."""
    from betting_engine_onchain import cancel_match_and_refund
    result = await cancel_match_and_refund(
        match_id=req.match_id,
        player1_user_id=req.player1_user_id,
        player2_user_id=req.player2_user_id,
        stake_usd=req.stake_usd,
    )
    return {"success": True, **result}

@admin_router.get("/escrow-balance")
async def escrow_balance(
    admin: str = Depends(get_current_admin_user),
):
    """Returns total USDC locked in the escrow contract."""
    from blockchain_layer import get_blockchain_layer
    bl = get_blockchain_layer()
    return {
        "contract_usdc_balance": bl.get_contract_usdc_balance(),
        "admin_eth_balance":     bl.get_admin_balance(),
        "network":               bl.network_key,
    }
