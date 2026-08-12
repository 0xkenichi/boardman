"""
On-chain dual-lock for agent matches on Arc (BoardmanEscrow V1).

Uses each agent's deterministic private key (data/agentic/secrets_*.json)
to approve USDC + createMatch / joinMatch. Resolver key settles the winner.

Mode selection:
  BOARDMAN_AGENTIC_ONCHAIN=1  → attempt live Arc txs
  Missing keys / funds / RPC  → raise; caller falls back to demo ledger

Env:
  BOARDMAN_AGENTIC_ONCHAIN=1
  BOARDMAN_RESOLVER_KEY=0x...   # must be BoardmanEscrow.resolver (or owner)
  ARC_RPC_URL / from chains.yaml
  CLAW_ESCROW_ADDRESS_ARC / BOARDMAN_ESCROW_ADDRESS_ARC
"""
from __future__ import annotations

import hashlib
import logging
import os
import time
from decimal import Decimal
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

USDC_DECIMALS = 6

ERC20_ABI = [
    {
        "name": "approve",
        "type": "function",
        "stateMutability": "nonpayable",
        "inputs": [
            {"name": "spender", "type": "address"},
            {"name": "amount", "type": "uint256"},
        ],
        "outputs": [{"name": "", "type": "bool"}],
    },
    {
        "name": "allowance",
        "type": "function",
        "stateMutability": "view",
        "inputs": [
            {"name": "owner", "type": "address"},
            {"name": "spender", "type": "address"},
        ],
        "outputs": [{"name": "", "type": "uint256"}],
    },
    {
        "name": "balanceOf",
        "type": "function",
        "stateMutability": "view",
        "inputs": [{"name": "account", "type": "address"}],
        "outputs": [{"name": "", "type": "uint256"}],
    },
    {
        "name": "transfer",
        "type": "function",
        "stateMutability": "nonpayable",
        "inputs": [
            {"name": "to", "type": "address"},
            {"name": "amount", "type": "uint256"},
        ],
        "outputs": [{"name": "", "type": "bool"}],
    },
    {
        "name": "decimals",
        "type": "function",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [{"name": "", "type": "uint8"}],
    },
]

ESCROW_ABI = [
    {
        "name": "createMatch",
        "type": "function",
        "stateMutability": "nonpayable",
        "inputs": [
            {"name": "matchId", "type": "bytes32"},
            {"name": "stake", "type": "uint256"},
        ],
        "outputs": [],
    },
    {
        "name": "joinMatch",
        "type": "function",
        "stateMutability": "nonpayable",
        "inputs": [{"name": "matchId", "type": "bytes32"}],
        "outputs": [],
    },
    {
        "name": "resolveMatch",
        "type": "function",
        "stateMutability": "nonpayable",
        "inputs": [
            {"name": "matchId", "type": "bytes32"},
            {"name": "winner", "type": "address"},
        ],
        "outputs": [],
    },
    {
        "name": "cancelMatch",
        "type": "function",
        "stateMutability": "nonpayable",
        "inputs": [{"name": "matchId", "type": "bytes32"}],
        "outputs": [],
    },
    {
        "name": "matches",
        "type": "function",
        "stateMutability": "view",
        "inputs": [{"name": "", "type": "bytes32"}],
        "outputs": [
            {"name": "player1", "type": "address"},
            {"name": "player2", "type": "address"},
            {"name": "stakePerPlayer", "type": "uint256"},
            {"name": "status", "type": "uint8"},
            {"name": "createdAt", "type": "uint256"},
            {"name": "lockedAt", "type": "uint256"},
        ],
    },
    {
        "name": "FEE_BPS",
        "type": "function",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [{"name": "", "type": "uint256"}],
    },
]


def onchain_enabled() -> bool:
    return os.getenv("BOARDMAN_AGENTIC_ONCHAIN", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _chain_config(chain_id: str = "arc") -> dict[str, Any]:
    try:
        from gaming.src.backend.services.chains import get_chain, get_escrow_address, get_usdc_address, get_rpc_url, get_explorer_tx

        c = get_chain(chain_id) or {}
        return {
            "chain_id": chain_id,
            "rpc_url": os.getenv("ARC_RPC_URL") or get_rpc_url(chain_id) or c.get("rpc_url"),
            "usdc": os.getenv("ARC_USDC_ADDRESS") or get_usdc_address(chain_id) or c.get("usdc_address"),
            "escrow": (
                os.getenv("BOARDMAN_ESCROW_ADDRESS_ARC")
                or os.getenv("CLAW_ESCROW_ADDRESS_ARC")
                or get_escrow_address(chain_id)
                or c.get("escrow_address")
            ),
            "explorer_tx": c.get("explorer_tx") or "https://testnet.arcscan.app/tx/",
            "evm_chain_id": int(c.get("chain_id") or 5042002),
            "get_explorer_tx": get_explorer_tx,
        }
    except Exception as exc:
        logger.warning("[agentic.onchain] chains config: %s", exc)
        return {
            "chain_id": "arc",
            "rpc_url": os.getenv("ARC_RPC_URL", "https://rpc.testnet.arc.network"),
            "usdc": os.getenv("ARC_USDC_ADDRESS", "0x3600000000000000000000000000000000000000"),
            "escrow": os.getenv(
                "BOARDMAN_ESCROW_ADDRESS_ARC",
                "0x3cD57447490c81598Bd8CaCBe3843b24E5735A77",
            ),
            "explorer_tx": "https://testnet.arcscan.app/tx/",
            "evm_chain_id": 5042002,
            "get_explorer_tx": None,
        }


def match_id_to_bytes32(match_id: str) -> bytes:
    return hashlib.sha256(match_id.encode("utf-8")).digest()


def match_id_hex(match_id: str) -> str:
    return "0x" + match_id_to_bytes32(match_id).hex()


def usdc_to_raw(amount: Decimal) -> int:
    return int(amount * Decimal(10**USDC_DECIMALS))


def load_agent_private_key(agent_id: str) -> str:
    from gaming.src.stack.agentic.store import data_dir, load_json
    from gaming.src.stack.agentic.wallets import seed_to_private_key

    secrets = load_json(f"secrets_{agent_id}.json", {})
    pk = secrets.get("private_key")
    if pk:
        return pk if str(pk).startswith("0x") else "0x" + str(pk)
    # Re-derive from seed (same as registry)
    from gaming.src.stack.agentic.chess.personas import get_persona

    p = get_persona(agent_id) or {}
    seed = p.get("seed") or agent_id
    return seed_to_private_key(seed)


def _w3(cfg: dict[str, Any]):
    from web3 import Web3

    w3 = Web3(Web3.HTTPProvider(cfg["rpc_url"], request_kwargs={"timeout": 60}))
    if not w3.is_connected():
        raise RuntimeError(f"RPC not connected: {cfg['rpc_url']}")
    return w3


def _account(pk: str):
    from eth_account import Account

    return Account.from_key(pk)


def _contracts(w3, cfg: dict[str, Any]):
    usdc = w3.eth.contract(
        address=w3.to_checksum_address(cfg["usdc"]), abi=ERC20_ABI
    )
    escrow = w3.eth.contract(
        address=w3.to_checksum_address(cfg["escrow"]), abi=ESCROW_ABI
    )
    return usdc, escrow


def _explorer(cfg: dict[str, Any], tx_hash: str) -> str:
    fn = cfg.get("get_explorer_tx")
    if callable(fn):
        try:
            return fn(cfg["chain_id"], tx_hash)
        except Exception:
            pass
    base = cfg.get("explorer_tx") or ""
    return f"{base}{tx_hash}" if tx_hash else ""


def _send(w3, acct, tx: dict[str, Any], label: str) -> str:
    """Sign + send + wait. Returns tx hash hex."""
    from web3 import Web3

    nonce = w3.eth.get_transaction_count(acct.address)
    tx = dict(tx)
    tx.setdefault("from", acct.address)
    tx.setdefault("nonce", nonce)
    tx.setdefault("chainId", int(w3.eth.chain_id))

    # Gas
    try:
        gas = w3.eth.estimate_gas(tx)
        tx["gas"] = int(gas * 1.25)
    except Exception as exc:
        logger.warning("[agentic.onchain] estimate_gas %s: %s — using 400000", label, exc)
        tx["gas"] = 400_000

    # Fee fields — EIP-1559 if supported, else legacy
    try:
        latest = w3.eth.get_block("latest")
        base = latest.get("baseFeePerGas")
        if base is not None:
            tip = w3.to_wei(1, "gwei")
            tx["maxPriorityFeePerGas"] = tip
            tx["maxFeePerGas"] = int(base * 2) + tip
        else:
            tx["gasPrice"] = w3.eth.gas_price
    except Exception:
        tx.setdefault("gasPrice", w3.to_wei(2, "gwei"))

    signed = acct.sign_transaction(tx)
    raw = getattr(signed, "rawTransaction", None) or getattr(signed, "raw_transaction", None)
    tx_hash = w3.eth.send_raw_transaction(raw)
    h = tx_hash.hex() if hasattr(tx_hash, "hex") else Web3.to_hex(tx_hash)
    logger.info("[agentic.onchain] %s sent %s", label, h)
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=180)
    if receipt.status != 1:
        raise RuntimeError(f"{label} reverted tx={h}")
    return h if h.startswith("0x") else "0x" + h


def usdc_balance(address: str, chain_id: str = "arc") -> Decimal:
    cfg = _chain_config(chain_id)
    w3 = _w3(cfg)
    usdc, _ = _contracts(w3, cfg)
    raw = usdc.functions.balanceOf(w3.to_checksum_address(address)).call()
    return Decimal(raw) / Decimal(10**USDC_DECIMALS)


def dual_lock_onchain(
    match_id: str,
    *,
    agent_a_id: str,
    agent_b_id: str,
    agent_a_wallet: str,
    agent_b_wallet: str,
    stake_usdc: Decimal,
    chain_id: str = "arc",
    player1_is_a: bool = True,
) -> dict[str, Any]:
    """
    Player1 (createMatch) + Player2 (joinMatch) with USDC approve.
    player1_is_a: if True agent_a is creator; else agent_b creates.
    """
    cfg = _chain_config(chain_id)
    w3 = _w3(cfg)
    usdc, escrow = _contracts(w3, cfg)
    stake_raw = usdc_to_raw(stake_usdc)
    mid = match_id_to_bytes32(match_id)
    mid_hex = match_id_hex(match_id)

    if player1_is_a:
        p1_id, p2_id = agent_a_id, agent_b_id
        p1_addr, p2_addr = agent_a_wallet, agent_b_wallet
    else:
        p1_id, p2_id = agent_b_id, agent_a_id
        p1_addr, p2_addr = agent_b_wallet, agent_a_wallet

    pk1 = load_agent_private_key(p1_id)
    pk2 = load_agent_private_key(p2_id)
    acct1 = _account(pk1)
    acct2 = _account(pk2)

    # Sanity: derived addresses match registry wallets
    if acct1.address.lower() != p1_addr.lower():
        logger.warning(
            "[agentic.onchain] p1 key address %s != registry %s — using key address",
            acct1.address,
            p1_addr,
        )
        p1_addr = acct1.address
    if acct2.address.lower() != p2_addr.lower():
        logger.warning(
            "[agentic.onchain] p2 key address %s != registry %s — using key address",
            acct2.address,
            p2_addr,
        )
        p2_addr = acct2.address

    bal1 = usdc.functions.balanceOf(w3.to_checksum_address(p1_addr)).call()
    bal2 = usdc.functions.balanceOf(w3.to_checksum_address(p2_addr)).call()
    if bal1 < stake_raw:
        raise RuntimeError(
            f"Agent {p1_id} USDC too low: have {bal1 / 1e6}, need {stake_usdc}. "
            "Fund agent wallets on Arc testnet (see scripts/fund_agent_wallets.py)."
        )
    if bal2 < stake_raw:
        raise RuntimeError(
            f"Agent {p2_id} USDC too low: have {bal2 / 1e6}, need {stake_usdc}."
        )

    # Existing match?
    try:
        existing = escrow.functions.matches(mid).call()
        p1_ex = existing[0]
        zero = "0x0000000000000000000000000000000000000000"
        if str(p1_ex).lower() not in {zero, "0x0", ""}:
            status = int(existing[3])
            if status >= 1:  # LOCKED or beyond
                return {
                    "success": True,
                    "mode": "onchain",
                    "already_locked": True,
                    "match_id": match_id,
                    "match_id_bytes32": mid_hex,
                    "chain_id": chain_id,
                    "escrow": cfg["escrow"],
                    "status": status,
                    "player1": p1_ex,
                    "player2": existing[1],
                    "stake_usdc": str(stake_usdc),
                }
    except Exception:
        pass

    txs: list[dict[str, str]] = []

    # Approve p1
    tx = usdc.functions.approve(
        w3.to_checksum_address(cfg["escrow"]), stake_raw
    ).build_transaction({"from": acct1.address})
    h = _send(w3, acct1, tx, "p1_approve")
    txs.append({"step": "p1_approve", "tx_hash": h, "explorer": _explorer(cfg, h)})

    # createMatch
    tx = escrow.functions.createMatch(mid, stake_raw).build_transaction(
        {"from": acct1.address}
    )
    h = _send(w3, acct1, tx, "createMatch")
    txs.append({"step": "createMatch", "tx_hash": h, "explorer": _explorer(cfg, h)})
    create_tx = h

    # Approve p2
    tx = usdc.functions.approve(
        w3.to_checksum_address(cfg["escrow"]), stake_raw
    ).build_transaction({"from": acct2.address})
    h = _send(w3, acct2, tx, "p2_approve")
    txs.append({"step": "p2_approve", "tx_hash": h, "explorer": _explorer(cfg, h)})

    # joinMatch
    tx = escrow.functions.joinMatch(mid).build_transaction({"from": acct2.address})
    h = _send(w3, acct2, tx, "joinMatch")
    txs.append({"step": "joinMatch", "tx_hash": h, "explorer": _explorer(cfg, h)})
    join_tx = h

    return {
        "success": True,
        "mode": "onchain",
        "match_id": match_id,
        "match_id_bytes32": mid_hex,
        "chain_id": chain_id,
        "escrow": cfg["escrow"],
        "stake_usdc": str(stake_usdc),
        "player1": p1_addr,
        "player2": p2_addr,
        "create_tx_hash": create_tx,
        "join_tx_hash": join_tx,
        "txs": txs,
        "status": "locked",
        "explorer_create": _explorer(cfg, create_tx),
        "explorer_join": _explorer(cfg, join_tx),
    }


def resolve_onchain(
    match_id: str,
    winner_address: str,
    *,
    chain_id: str = "arc",
    draw: bool = False,
) -> dict[str, Any]:
    """Resolver settles winner (or cancelMatch for draw)."""
    cfg = _chain_config(chain_id)
    resolver_pk = (
        os.getenv("BOARDMAN_RESOLVER_KEY")
        or os.getenv("CLAW_RESOLVER_PRIVATE_KEY")
        or os.getenv("RESOLVER_PRIVATE_KEY")
        or ""
    ).strip()
    if not resolver_pk:
        raise RuntimeError(
            "Set BOARDMAN_RESOLVER_KEY (BoardmanEscrow resolver) to settle on-chain"
        )
    if not resolver_pk.startswith("0x"):
        resolver_pk = "0x" + resolver_pk

    w3 = _w3(cfg)
    _, escrow = _contracts(w3, cfg)
    acct = _account(resolver_pk)
    mid = match_id_to_bytes32(match_id)
    mid_hex = match_id_hex(match_id)

    if draw:
        tx = escrow.functions.cancelMatch(mid).build_transaction({"from": acct.address})
        h = _send(w3, acct, tx, "cancelMatch")
        return {
            "success": True,
            "mode": "onchain",
            "result": "draw",
            "tx_hash": h,
            "explorer": _explorer(cfg, h),
            "match_id_bytes32": mid_hex,
            "chain_id": chain_id,
        }

    winner = w3.to_checksum_address(winner_address)
    tx = escrow.functions.resolveMatch(mid, winner).build_transaction(
        {"from": acct.address}
    )
    h = _send(w3, acct, tx, "resolveMatch")
    return {
        "success": True,
        "mode": "onchain",
        "result": "win",
        "winner": winner,
        "tx_hash": h,
        "explorer": _explorer(cfg, h),
        "match_id_bytes32": mid_hex,
        "chain_id": chain_id,
    }


def fund_agent_from_key(
    to_address: str,
    amount_usdc: Decimal,
    *,
    funder_key: Optional[str] = None,
    chain_id: str = "arc",
) -> dict[str, Any]:
    """Transfer USDC to an agent wallet from a funder key (ops / faucet wallet)."""
    pk = (
        funder_key
        or os.getenv("BOARDMAN_FUNDER_KEY")
        or os.getenv("BOARDMAN_RESOLVER_KEY")
        or ""
    ).strip()
    if not pk:
        raise RuntimeError("Set BOARDMAN_FUNDER_KEY or BOARDMAN_RESOLVER_KEY to fund agents")
    if not pk.startswith("0x"):
        pk = "0x" + pk

    cfg = _chain_config(chain_id)
    w3 = _w3(cfg)
    usdc, _ = _contracts(w3, cfg)
    acct = _account(pk)
    raw = usdc_to_raw(amount_usdc)
    bal = usdc.functions.balanceOf(acct.address).call()
    if bal < raw:
        raise RuntimeError(
            f"Funder {acct.address} has {bal / 1e6} USDC, need {amount_usdc}"
        )
    tx = usdc.functions.transfer(
        w3.to_checksum_address(to_address), raw
    ).build_transaction({"from": acct.address})
    h = _send(w3, acct, tx, "fund_agent")
    return {
        "success": True,
        "tx_hash": h,
        "explorer": _explorer(cfg, h),
        "from": acct.address,
        "to": to_address,
        "amount_usdc": str(amount_usdc),
    }
