"""SpectatorPool operator — match-keyed fan deposits on Arc.

Separate from BoardmanEscrow / House cashier. The resolver key may:
  * call SpectatorPool (openBook / depositFor / close / resolve / cancel)
  * approve USDC *to SpectatorPool only* so depositFor can pull House float

It never ERC-20 transfers to an EOA. JSON is a projection written after a
confirmed tx. SPECTATOR_ONCHAIN stays off until SPECTATOR_ESCROW_ADDRESS is set
and the bet is keyed to a live agm_* match_id (never "arena").
"""
from __future__ import annotations

import logging
import os
from decimal import Decimal
from typing import Any, Optional

from gaming.src.stack.agentic.onchain import (
    ERC20_ABI,
    _account,
    _chain_config,
    _explorer,
    _send,
    _w3,
    load_resolver_key,
    match_id_hex,
    match_id_to_bytes32,
    usdc_to_raw,
)

logger = logging.getLogger(__name__)

ARENA_MATCH_IDS = frozenset({"arena", "live", ""})

SPECTATOR_ABI = [
    {
        "name": "openBook",
        "type": "function",
        "stateMutability": "nonpayable",
        "inputs": [
            {"name": "matchId", "type": "bytes32"},
            {"name": "gameId", "type": "bytes32"},
            {"name": "agentA", "type": "bytes32"},
            {"name": "agentB", "type": "bytes32"},
            {"name": "agentWalletA", "type": "address"},
            {"name": "agentWalletB", "type": "address"},
            {"name": "creatorA", "type": "address"},
            {"name": "creatorB", "type": "address"},
            {"name": "potCap", "type": "uint256"},
        ],
        "outputs": [],
    },
    {
        "name": "depositFor",
        "type": "function",
        "stateMutability": "nonpayable",
        "inputs": [
            {"name": "matchId", "type": "bytes32"},
            {"name": "user", "type": "address"},
            {"name": "amount", "type": "uint256"},
            {"name": "side", "type": "uint8"},
        ],
        "outputs": [],
    },
    {
        "name": "close",
        "type": "function",
        "stateMutability": "nonpayable",
        "inputs": [{"name": "matchId", "type": "bytes32"}],
        "outputs": [],
    },
    {
        "name": "resolve",
        "type": "function",
        "stateMutability": "nonpayable",
        "inputs": [
            {"name": "matchId", "type": "bytes32"},
            {"name": "winnerSide", "type": "int8"},
        ],
        "outputs": [],
    },
    {
        "name": "cancel",
        "type": "function",
        "stateMutability": "nonpayable",
        "inputs": [{"name": "matchId", "type": "bytes32"}],
        "outputs": [],
    },
    {
        "name": "getBook",
        "type": "function",
        "stateMutability": "view",
        "inputs": [{"name": "matchId", "type": "bytes32"}],
        "outputs": [
            {"name": "gameId", "type": "bytes32"},
            {"name": "agentA", "type": "bytes32"},
            {"name": "agentB", "type": "bytes32"},
            {"name": "agentWalletA", "type": "address"},
            {"name": "agentWalletB", "type": "address"},
            {"name": "creatorA", "type": "address"},
            {"name": "creatorB", "type": "address"},
            {"name": "seedPayerA", "type": "address"},
            {"name": "seedPayerB", "type": "address"},
            {"name": "potCap", "type": "uint256"},
            {"name": "seedA", "type": "uint256"},
            {"name": "seedB", "type": "uint256"},
            {"name": "totalA", "type": "uint256"},
            {"name": "totalB", "type": "uint256"},
            {"name": "distributable", "type": "uint256"},
            {"name": "fanWin", "type": "uint256"},
            {"name": "sideCount", "type": "uint8"},
            {"name": "winnerSide", "type": "int8"},
            {"name": "status", "type": "uint8"},
            # v2 draw book (appended — indices 0..18 unchanged)
            {"name": "seedPayerDrawA", "type": "address"},
            {"name": "seedPayerDrawB", "type": "address"},
            {"name": "seedDrawA", "type": "uint256"},
            {"name": "seedDrawB", "type": "uint256"},
            {"name": "totalDraw", "type": "uint256"},
        ],
    },
    {
        "name": "resolver",
        "type": "function",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [{"name": "", "type": "address"}],
    },
]

BOOK_STATUS = {0: "None", 1: "Open", 2: "Closed", 3: "Resolved", 4: "Cancelled"}
POOL_LABELS = frozenset({"openBook", "depositFor", "close", "resolve", "cancel", "approve"})


class SpectatorOnchainError(RuntimeError):
    pass


def spectator_pool_address() -> str:
    env = (os.getenv("SPECTATOR_ESCROW_ADDRESS") or "").strip()
    if env:
        return env
    try:
        from gaming.src.backend.services.chains import get_chain

        c = get_chain("arc") or {}
        return str(c.get("spectator_pool_address") or "").strip()
    except Exception:
        return ""


def spectator_onchain_enabled() -> bool:
    v = os.getenv("SPECTATOR_ONCHAIN", "").strip().lower()
    return v in {"1", "true", "yes", "on"} and bool(spectator_pool_address())


def assert_live_match_id(match_id: str) -> str:
    """Refuse the commingled sha256('arena') book."""
    mid = (match_id or "").strip()
    if mid.lower() in ARENA_MATCH_IDS:
        raise SpectatorOnchainError(
            "spectator on-chain requires a live match_id, not 'arena'"
        )
    if not mid.startswith("agm_"):
        raise SpectatorOnchainError(
            f"spectator on-chain match_id must be a Boardman match (got {mid!r})"
        )
    return mid


def side_to_idx(side: str) -> int:
    s = (side or "").strip().lower()
    if s in {"a", "0"}:
        return 0
    if s in {"b", "1"}:
        return 1
    if s in {"draw", "d", "tie", "2"}:
        return 2
    raise SpectatorOnchainError("side must be a, b, or draw")


def _pool_cfg(chain_id: str = "arc") -> dict[str, Any]:
    cfg = dict(_chain_config(chain_id))
    pool = spectator_pool_address()
    if not pool:
        raise SpectatorOnchainError("SPECTATOR_ESCROW_ADDRESS not configured")
    cfg["pool"] = pool
    return cfg


def _contracts(w3, cfg: dict[str, Any]):
    usdc = w3.eth.contract(address=w3.to_checksum_address(cfg["usdc"]), abi=ERC20_ABI)
    pool = w3.eth.contract(address=w3.to_checksum_address(cfg["pool"]), abi=SPECTATOR_ABI)
    return usdc, pool


def _assert_pool_tx(tx: dict[str, Any], cfg: dict[str, Any], label: str) -> None:
    if label not in POOL_LABELS:
        raise SpectatorOnchainError(f"spectator operator cannot broadcast {label}")
    to = str(tx.get("to") or "").lower()
    pool = str(cfg["pool"]).lower()
    usdc = str(cfg["usdc"]).lower()
    if label == "approve":
        if to != usdc:
            raise SpectatorOnchainError(f"approve must target USDC ({usdc}), not {to}")
        return
    if to != pool:
        raise SpectatorOnchainError(
            f"spectator operator may only call SpectatorPool ({pool}), not {to}"
        )


def _send_pool(w3, acct, tx: dict[str, Any], cfg: dict[str, Any], label: str) -> str:
    _assert_pool_tx(tx, cfg, label)
    return _send(w3, acct, tx, label)


def _ensure_allowance(w3, usdc, acct, spender: str, raw: int, cfg: dict[str, Any]) -> Optional[str]:
    current = usdc.functions.allowance(acct.address, w3.to_checksum_address(spender)).call()
    if current >= raw:
        return None
    tx = usdc.functions.approve(w3.to_checksum_address(spender), raw).build_transaction(
        {"from": acct.address}
    )
    return _send_pool(w3, acct, tx, cfg, "approve")


def read_book(match_id: str, chain_id: str = "arc") -> dict[str, Any]:
    cfg = _pool_cfg(chain_id)
    w3 = _w3(cfg)
    _, pool = _contracts(w3, cfg)
    mid = match_id_to_bytes32(match_id)
    raw = pool.functions.getBook(mid).call()
    status = int(raw[18])
    return {
        "match_id": match_id,
        "match_id_bytes32": match_id_hex(match_id),
        "pot_cap_raw": int(raw[9]),
        "seed_a": int(raw[10]),
        "seed_b": int(raw[11]),
        "total_a": int(raw[12]),
        "total_b": int(raw[13]),
        "distributable": int(raw[14]),
        "fan_win": int(raw[15]),
        "winner_side": int(raw[17]),
        "status": status,
        "status_name": BOOK_STATUS.get(status, str(status)),
        # v2 draw book
        "seed_draw_a": int(raw[21]),
        "seed_draw_b": int(raw[22]),
        "total_draw": int(raw[23]),
        "pool": cfg["pool"],
        "chain_id": chain_id,
    }


def open_book_onchain(match: dict[str, Any], *, chain_id: str = "arc") -> dict[str, Any]:
    """Resolver openBook. Idempotent if the book is already Open."""
    match_id = assert_live_match_id(str(match.get("match_id") or ""))
    existing = read_book(match_id, chain_id=chain_id)
    if existing["status"] == 1:
        return {**existing, "success": True, "already_open": True, "tx_hash": None}
    if existing["status"] != 0:
        raise SpectatorOnchainError(
            f"SpectatorPool book {match_id} is {existing['status_name']}"
        )

    cfg = _pool_cfg(chain_id)
    w3 = _w3(cfg)
    _, pool = _contracts(w3, cfg)
    acct = _account(load_resolver_key())

    wallet_a = match.get("agent_a_wallet") or ""
    wallet_b = match.get("agent_b_wallet") or ""
    if not wallet_a or not wallet_b:
        raise SpectatorOnchainError("openBook needs both agent wallets")

    eco = match.get("economy") or {}
    try:
        cap = Decimal(str(eco.get("pot_cap_usdc") or "20"))
    except Exception:
        cap = Decimal("20")
    if cap <= 0:
        cap = Decimal("20")

    zero = "0x0000000000000000000000000000000000000000"
    # creatorA/creatorB = the agent wallets: the pool pays them the 2%
    # creator pool on resolve (winner-weighted 75/25 in v2), so the agents
    # earn a slice of every fan market on their own match.
    tx = pool.functions.openBook(
        match_id_to_bytes32(match_id),
        match_id_to_bytes32(str(match.get("game_id") or "agentic.chess_standard")),
        match_id_to_bytes32(str(match.get("agent_a_id") or "")),
        match_id_to_bytes32(str(match.get("agent_b_id") or "")),
        w3.to_checksum_address(wallet_a),
        w3.to_checksum_address(wallet_b),
        w3.to_checksum_address(wallet_a),
        w3.to_checksum_address(wallet_b),
        usdc_to_raw(cap),
    ).build_transaction({"from": acct.address})
    h = _send_pool(w3, acct, tx, cfg, "openBook")
    logger.info("[spectator.onchain] openBook match=%s tx=%s", match_id, h)
    return {
        "success": True,
        "tx_hash": h,
        "explorer": _explorer(cfg, h),
        "match_id": match_id,
        "match_id_bytes32": match_id_hex(match_id),
        "pool": cfg["pool"],
        "chain_id": chain_id,
        "step": "openBook",
    }


def deposit_for(
    match_id: str,
    user_address: str,
    amount_usdc: Decimal,
    side: str,
    *,
    chain_id: str = "arc",
    match: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """House custodial deposit: ledger already debited; resolver pulls USDC into the pool."""
    mid = assert_live_match_id(match_id)
    if amount_usdc <= 0:
        raise SpectatorOnchainError("amount must be positive")
    user = (user_address or "").strip()
    if not user.startswith("0x") or len(user) != 42:
        raise SpectatorOnchainError("user address required for depositFor")
    side_idx = side_to_idx(side)

    book = read_book(mid, chain_id=chain_id)
    if book["status"] == 0:
        if not match:
            raise SpectatorOnchainError(f"SpectatorPool book not open for {mid}")
        open_book_onchain(match, chain_id=chain_id)
        book = read_book(mid, chain_id=chain_id)
    if book["status"] != 1:
        raise SpectatorOnchainError(
            f"SpectatorPool book {mid} is {book['status_name']} — not accepting deposits"
        )

    cfg = _pool_cfg(chain_id)
    w3 = _w3(cfg)
    usdc, pool = _contracts(w3, cfg)
    acct = _account(load_resolver_key())
    raw = usdc_to_raw(Decimal(str(amount_usdc)))
    bal = usdc.functions.balanceOf(acct.address).call()
    if bal < raw:
        raise SpectatorOnchainError(
            f"House float {acct.address} has {bal / 1e6} USDC, need {amount_usdc}"
        )
    approve_h = _ensure_allowance(w3, usdc, acct, cfg["pool"], raw, cfg)
    tx = pool.functions.depositFor(
        match_id_to_bytes32(mid),
        w3.to_checksum_address(user),
        raw,
        side_idx,
    ).build_transaction({"from": acct.address})
    h = _send_pool(w3, acct, tx, cfg, "depositFor")
    logger.info("[spectator.onchain] depositFor match=%s user=%s tx=%s", mid, user, h)
    side_label = {0: "a", 1: "b", 2: "draw"}.get(side_idx, str(side_idx))
    return {
        "success": True,
        "tx_hash": h,
        "explorer": _explorer(cfg, h),
        "approve_tx_hash": approve_h,
        "match_id": mid,
        "match_id_bytes32": match_id_hex(mid),
        "user": user,
        "side": side_label,
        "side_idx": side_idx,
        "amount_usdc": str(amount_usdc),
        "pool": cfg["pool"],
        "chain_id": chain_id,
        "step": "depositFor",
    }


def refund_float_to_user(
    user_address: str,
    amount_usdc: Decimal,
    *,
    chain_id: str = "arc",
) -> dict[str, Any]:
    """Return USDC from the House float (resolver key) to a user wallet.

    Used when a pulled bet deposit fails — never leave user money stranded.
    """
    if amount_usdc <= 0:
        raise SpectatorOnchainError("refund amount must be positive")
    user = (user_address or "").strip()
    if not user.startswith("0x") or len(user) != 42:
        raise SpectatorOnchainError("user address required for refund")
    cfg = _pool_cfg(chain_id)
    w3 = _w3(cfg)
    usdc, _ = _contracts(w3, cfg)
    acct = _account(load_resolver_key())
    raw = usdc_to_raw(amount_usdc)
    bal = usdc.functions.balanceOf(acct.address).call()
    if bal < raw:
        raise SpectatorOnchainError(
            f"House float {acct.address} has {bal / 1e6} USDC, need {amount_usdc}"
        )
    tx = usdc.functions.transfer(
        w3.to_checksum_address(user), raw
    ).build_transaction({"from": acct.address})
    h = _send(w3, acct, tx, "refund_float")
    logger.info("[spectator.onchain] refund_float user=%s amt=%s tx=%s", user, amount_usdc, h)
    return {
        "success": True,
        "tx_hash": h,
        "explorer": _explorer(cfg, h),
        "amount_usdc": str(amount_usdc),
        "user": user,
    }


def resolve_book(
    match_id: str,
    winner_side: Optional[str],
    *,
    chain_id: str = "arc",
) -> dict[str, Any]:
    """Resolver resolve(0|1) or cancel() for a draw / empty pot."""
    mid = assert_live_match_id(match_id)
    book = read_book(mid, chain_id=chain_id)
    if book["status"] in {3, 4}:
        return {
            "success": True,
            "already_settled": True,
            "tx_hash": None,
            "match_id": mid,
            "status_name": book["status_name"],
        }
    if book["status"] == 0:
        raise SpectatorOnchainError(f"no SpectatorPool book for {mid}")

    cfg = _pool_cfg(chain_id)
    w3 = _w3(cfg)
    _, pool = _contracts(w3, cfg)
    acct = _account(load_resolver_key())
    mid_b = match_id_to_bytes32(mid)
    if winner_side is None:
        # Draw is a real outcome in v2: draw tickets win the whole pot.
        # The contract refunds when there are no draw fans (fanWin == 0).
        tx = pool.functions.resolve(mid_b, -2).build_transaction({"from": acct.address})
        label = "resolve"
        idx = -2
    else:
        idx = side_to_idx(winner_side)
        tx = pool.functions.resolve(mid_b, idx).build_transaction({"from": acct.address})
        label = "resolve"
    h = _send_pool(w3, acct, tx, cfg, label)
    logger.info("[spectator.onchain] %s match=%s side=%s tx=%s", label, mid, winner_side, h)
    return {
        "success": True,
        "tx_hash": h,
        "explorer": _explorer(cfg, h),
        "match_id": mid,
        "winner_side": winner_side,
        "winner_idx": idx,
        "pool": cfg["pool"],
        "chain_id": chain_id,
        "step": label,
    }
