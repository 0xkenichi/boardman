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
    {
        "name": "resolver",
        "type": "function",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [{"name": "", "type": "address"}],
    },
]


def onchain_enabled() -> bool:
    """True only when BOARDMAN_AGENTIC_ONCHAIN is explicitly on.

    No auto-enable from a hanging resolver/admin key — that used to flip
    live USDC locks on by accident. Demo ledger is the default.
    """
    v = os.getenv("BOARDMAN_AGENTIC_ONCHAIN", "").strip().lower()
    return v in {"1", "true", "yes", "on"}


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
    from gaming.src.stack.agentic.store import load_json
    from gaming.src.stack.agentic.wallets import seed_to_private_key
    from gaming.src.stack.agentic.agents.boardman.manifest import HOUSE_ID

    if agent_id == HOUSE_ID:
        raise RuntimeError(
            "House has no spend key — resolver signs BoardmanEscrow only"
        )
    secrets = load_json(f"secrets_{agent_id}.json", {})
    if secrets.get("sealed"):
        raise RuntimeError(f"agent {agent_id} secrets are sealed — no spend key")
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


ONCHAIN_STATUS = {0: "OPEN", 1: "LOCKED", 2: "DISPUTED", 3: "RESOLVED", 4: "CANCELLED"}
HOUSE_TX_LABELS = frozenset({"resolveMatch", "cancelMatch", "flagDispute"})


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


def _send_house(w3, acct, tx: dict[str, Any], label: str, escrow_address: str) -> str:
    """Resolver broadcast — escrow resolve/cancel only. Never ERC-20 transfer."""
    from gaming.src.stack.agentic.disbursement import assert_house_escrow_call

    if label not in HOUSE_TX_LABELS:
        raise RuntimeError(f"House signer cannot broadcast {label}")
    assert_house_escrow_call(tx, escrow_address, label)
    return _send(w3, acct, tx, label)


def read_onchain_match(match_id: str, chain_id: str = "arc") -> dict[str, Any]:
    """Read BoardmanEscrow.matches(matchId). Raises if the slot is empty."""
    cfg = _chain_config(chain_id)
    w3 = _w3(cfg)
    _, escrow = _contracts(w3, cfg)
    mid = match_id_to_bytes32(match_id)
    raw = escrow.functions.matches(mid).call()
    player1, player2, stake_raw, status, created_at, locked_at = raw
    zero = "0x0000000000000000000000000000000000000000"
    p1 = str(player1)
    if p1.lower() in {zero, "0x0", ""}:
        raise RuntimeError(f"no on-chain escrow for {match_id}")
    return {
        "match_id": match_id,
        "match_id_bytes32": match_id_hex(match_id),
        "player1": p1,
        "player2": str(player2),
        "stake_raw": int(stake_raw),
        "stake_usdc": str(Decimal(int(stake_raw)) / Decimal(10**USDC_DECIMALS)),
        "status": int(status),
        "status_name": ONCHAIN_STATUS.get(int(status), str(status)),
        "created_at": int(created_at),
        "locked_at": int(locked_at),
        "escrow": cfg["escrow"],
        "chain_id": chain_id,
    }


def usdc_balance(address: str, chain_id: str = "arc") -> Decimal:
    cfg = _chain_config(chain_id)
    w3 = _w3(cfg)
    usdc, _ = _contracts(w3, cfg)
    raw = usdc.functions.balanceOf(w3.to_checksum_address(address)).call()
    return Decimal(raw) / Decimal(10**USDC_DECIMALS)


# ── On-chain transfer volume (eth_getLogs over the USDC contract) ──────────

TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
VOLUME_CACHE_FILE = "onchain_volume_cache.json"
VOLUME_CACHE_TTL_SEC = 300  # re-scan only when a newer block is requested
VOLUME_SCAN_CHUNK = 5000


def _rpc_call(cfg: dict[str, Any], method: str, params: list) -> Any:
    """Raw JSON-RPC call (same shape as scripts/compute_agent_onchain_volume.py)."""
    import requests

    payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
    r = requests.post(cfg["rpc_url"], json=payload, timeout=30)
    r.raise_for_status()
    j = r.json()
    if "error" in j:
        raise RuntimeError(j["error"])
    return j.get("result")


def latest_block(cfg: dict[str, Any]) -> int:
    return int(_rpc_call(cfg, "eth_blockNumber", []), 16)


def _get_logs_paged(
    cfg: dict[str, Any],
    usdc_addr: str,
    topics: list,
    start_block: int,
    end_block: int,
    chunk: int = VOLUME_SCAN_CHUNK,
) -> list:
    """eth_getLogs in bounded chunks with retry/backoff (respects RPC limits)."""
    import time

    out: list = []
    b = start_block
    while b <= end_block:
        hi = min(b + chunk - 1, end_block)
        params = [
            {
                "address": usdc_addr,
                "topics": topics,
                "fromBlock": hex(b),
                "toBlock": hex(hi),
            }
        ]
        attempts = 0
        while True:
            try:
                res = _rpc_call(cfg, "eth_getLogs", params)
                if res:
                    out.extend(res)
                break
            except Exception as exc:
                attempts += 1
                if attempts >= 6:
                    raise RuntimeError(
                        f"logs failed for {hex(b)}->{hex(hi)}: {exc}"
                    )
                time.sleep(0.5 * (2 ** (attempts - 1)))
        time.sleep(0.05)
        b = hi + 1
    return out


def _load_volume_cache() -> dict[str, Any]:
    from gaming.src.stack.agentic.store import load_json

    return load_json(VOLUME_CACHE_FILE, {})


def _save_volume_cache(payload: dict[str, Any]) -> None:
    from gaming.src.stack.agentic.store import save_json

    save_json(VOLUME_CACHE_FILE, payload)


def block_timestamp(cfg: dict[str, Any], block_number: int) -> int:
    """Unix timestamp of a block (for resolving day windows)."""
    res = _rpc_call(cfg, "eth_getBlockByNumber", [hex(block_number), False])
    if not res:
        raise RuntimeError(f"block {block_number} not found")
    return int(res.get("timestamp") or 0, 16)


def from_block_for_days(cfg: dict[str, Any], days: int) -> int:
    """Estimate the block height `days` days ago from block timestamps.

    Samples the latest block and a block ~10k back to derive avg block time,
    then walks back `days` days. Clamped at block 0.
    """
    latest = latest_block(cfg)
    if days <= 0:
        return latest
    now_ts = block_timestamp(cfg, latest)
    back = min(latest, 10_000)
    old_ts = block_timestamp(cfg, latest - back)
    span = max(now_ts - old_ts, 1)
    avg_sec = span / back
    want_sec = days * 86400
    est = latest - int(want_sec / avg_sec)
    return max(est, 0)


def usdc_transfer_volume(
    address: str,
    chain_id: str = "arc",
    *,
    from_block: Optional[int] = None,
    to_block: Optional[int] = None,
    days: Optional[int] = None,
    use_cache: bool = True,
) -> dict[str, Any]:
    """
    Real USDC transfer volume (in/out) for an address via eth_getLogs.

    Scans Transfer events on the chain's USDC contract where the address is
    sender or recipient and sums values (6 decimals). Results are cached per
    address in data/agentic/onchain_volume_cache.json; a later call that asks
    for a newer `to_block` only scans the delta, so repeated reads stay fast.

    Pass `days=N` for a rolling N-day window (resolved from block timestamps);
    otherwise the full history from block 0 is scanned.

    Returns {in_usdc, out_usdc, count_in, count_out, scanned_from, scanned_to,
             cached, chain_id, address, window_days}.
    """
    cfg = _chain_config(chain_id)
    addr_l = address.lower()
    if not addr_l.startswith("0x"):
        addr_l = "0x" + addr_l
    addr_topic = "0x" + addr_l.replace("0x", "").rjust(64, "0")

    if to_block is None:
        to_block = latest_block(cfg)
    if days is not None and from_block is None:
        from_block = from_block_for_days(cfg, days)
    if from_block is None:
        from_block = 0

    # Rolling windows are keyed separately from the full-history cache so a
    # 30-day read never mixes with the lifetime entry.
    cache_key = (
        f"{chain_id}:{addr_l}:d{days}"
        if days is not None
        else f"{chain_id}:{addr_l}"
    )

    cache = _load_volume_cache()
    entry = cache.get(cache_key) or {}
    cached_to = int(entry.get("scanned_to") or -1)

    # Full-history incremental scan (the common path: from block 0 upward).
    incremental = from_block == 0
    if use_cache and entry and incremental and cached_to >= to_block:
        age = time.time() - float(entry.get("scanned_at") or 0)
        if age < VOLUME_CACHE_TTL_SEC:
            return {
                **entry,
                "cached": True,
                "scanned_from": from_block,
                "scanned_to": to_block,
                "chain_id": chain_id,
                "address": address,
                "window_days": days,
            }

    if use_cache and entry and incremental and cached_to >= from_block:
        start = cached_to + 1
        base_in = float(entry.get("in_usdc") or 0)
        base_out = float(entry.get("out_usdc") or 0)
        base_count_in = int(entry.get("count_in") or 0)
        base_count_out = int(entry.get("count_out") or 0)
    else:
        start = from_block
        base_in = base_out = 0.0
        base_count_in = base_count_out = 0

    logs_from = _get_logs_paged(
        cfg, cfg["usdc"], [TRANSFER_TOPIC, addr_topic, None], start, to_block
    )
    logs_to = _get_logs_paged(
        cfg, cfg["usdc"], [TRANSFER_TOPIC, None, addr_topic], start, to_block
    )

    add_in = sum(int(l.get("data", "0x0"), 16) for l in logs_to or []) / 10**6
    add_out = sum(int(l.get("data", "0x0"), 16) for l in logs_from or []) / 10**6

    result = {
        "chain_id": chain_id,
        "address": address,
        "in_usdc": round(base_in + add_in, 6),
        "out_usdc": round(base_out + add_out, 6),
        "count_in": base_count_in + len(logs_to or []),
        "count_out": base_count_out + len(logs_from or []),
        "scanned_from": from_block,
        "scanned_to": to_block,
        "scanned_at": time.time(),
        "cached": False,
        "window_days": days,
    }
    if use_cache:
        cache[cache_key] = result
        _save_volume_cache(cache)
    return result


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


def load_resolver_key() -> str:
    """Return the resolver private key (32-byte), raising on missing/invalid.

    Looks in process env first, then local .env for developer convenience.
    Rejects values that are addresses (20-byte) rather than private keys — a
    common misconfiguration that otherwise surfaces as a confusing revert.
    """
    candidates = [
        "BOARDMAN_RESOLVER_KEY",
        "CLAW_RESOLVER_PRIVATE_KEY",
        "RESOLVER_PRIVATE_KEY",
        # Last-resort ops aliases — never BOARDMAN_FUNDER_KEY (faucet ≠ resolver).
        "ADMIN_PRIVATE_KEY",
        "OWNER_PRIVATE_KEY",
    ]
    resolver_pk = ""
    for name in candidates:
        v = (os.getenv(name) or "").strip()
        if v:
            resolver_pk = v
            break
    if not resolver_pk:
        try:
            from pathlib import Path

            envf = Path.cwd() / ".env"
            if envf.exists():
                for line in envf.read_text(encoding="utf-8").splitlines():
                    if not line or line.strip().startswith("#"):
                        continue
                    if "=" not in line:
                        continue
                    k, v = line.split("=", 1)
                    k = k.strip()
                    v = v.strip().strip('"').strip("'")
                    if k in candidates and v:
                        resolver_pk = v
                        break
        except Exception:
            pass
    if not resolver_pk:
        raise RuntimeError(
            "Set BOARDMAN_RESOLVER_KEY (BoardmanEscrow resolver) to settle on-chain"
        )
    if not resolver_pk.startswith("0x"):
        resolver_pk = "0x" + resolver_pk
    # A 20-byte value is an address, not a private key — catch this early.
    try:
        hex_body = resolver_pk[2:]
        if len(hex_body) != 64:
            raise ValueError(f"private key must be 32 bytes, got {len(hex_body) // 2} bytes")
        int(hex_body, 16)
    except ValueError as exc:
        raise RuntimeError(
            f"BOARDMAN_RESOLVER_KEY is not a valid 32-byte private key ({exc}). "
            "It looks like an address — set it to the private key whose address "
            "matches the contract resolver (see contracts/deployments/*)."
        ) from exc
    return resolver_pk


def _verify_resolver(escrow, signer_address: str, cfg: dict[str, Any]) -> None:
    """Fail fast if the signer is not the contract resolver (or owner).

    The contract's `onlyResolver` modifier accepts either the configured
    `resolver` or the `owner`. We check `resolver()` directly; when that
    differs from the signer we raise before broadcasting a doomed tx.
    """
    try:
        onchain_resolver = escrow.functions.resolver().call()
    except Exception:
        return  # contract ABI lacks resolver() — let the tx attempt happen
    signer = signer_address.lower()
    if onchain_resolver.lower() != signer:
        raise RuntimeError(
            f"Resolver key address {signer} does not match contract resolver "
            f"{onchain_resolver} on {cfg.get('chain_id')}. "
            "Set BOARDMAN_RESOLVER_KEY to the private key of the contract resolver "
            "(see contracts/deployments/boardman_v1_arcTestnet.json)."
        )


def resolve_onchain(
    match_id: str,
    winner_address: str,
    *,
    chain_id: str = "arc",
    draw: bool = False,
    authorization: Any = None,
) -> dict[str, Any]:
    """Resolver settles winner (or cancelMatch for draw).

    Requires an AuthorizedDisbursement from disbursement.py. The House
    cannot pick a winner or an amount — the contract pays 2*stake-fee to
    a locked player, or refunds both on cancel.
    """
    from gaming.src.stack.agentic.disbursement import (
        AuthorizedDisbursement,
        DisbursementDenied,
    )

    if authorization is None:
        raise DisbursementDenied(
            "resolve_onchain requires an AuthorizedDisbursement — "
            "Boardman will not sign a fund movement without a contract trigger"
        )
    if not isinstance(authorization, AuthorizedDisbursement):
        raise DisbursementDenied("authorization is not an AuthorizedDisbursement")
    authorization.assert_for_resolve(match_id, winner_address, draw)

    cfg = _chain_config(chain_id)
    resolver_pk = load_resolver_key()
    acct = _account(resolver_pk)

    w3 = _w3(cfg)
    _, escrow = _contracts(w3, cfg)
    _verify_resolver(escrow, acct.address, cfg)
    mid = match_id_to_bytes32(match_id)
    mid_hex = match_id_hex(match_id)

    on = read_onchain_match(match_id, chain_id=chain_id)
    status = int(on["status"])
    if status in {3, 4}:  # already RESOLVED / CANCELLED — idempotent success
        return {
            "success": True,
            "mode": "onchain",
            "already_settled": True,
            "result": "draw" if status == 4 or draw else "win",
            "winner": on["player1"] if not draw else None,
            "tx_hash": None,
            "match_id_bytes32": mid_hex,
            "chain_id": chain_id,
            "onchain_status": on["status_name"],
        }
    if status not in {1, 2} and not (draw and status == 0):
        raise DisbursementDenied(
            f"on-chain match {match_id} is {on['status_name']} — cannot settle"
        )

    players = {on["player1"].lower(), str(on["player2"]).lower()}
    players.discard("0x0000000000000000000000000000000000000000")
    auth_players = {w.lower() for w in authorization.player_wallets}
    if players and not players.issubset(auth_players) and not auth_players.issubset(players):
        # Allow if the authorized players are exactly the on-chain pair
        if players != auth_players:
            raise DisbursementDenied(
                f"on-chain players {sorted(players)} do not match authorization "
                f"{sorted(auth_players)}"
            )

    if draw:
        tx = escrow.functions.cancelMatch(mid).build_transaction({"from": acct.address})
        h = _send_house(w3, acct, tx, "cancelMatch", cfg["escrow"])
        return {
            "success": True,
            "mode": "onchain",
            "result": "draw",
            "tx_hash": h,
            "explorer": _explorer(cfg, h),
            "match_id_bytes32": mid_hex,
            "chain_id": chain_id,
            "authorization": authorization.fingerprint,
        }

    winner = w3.to_checksum_address(authorization.winner_wallet or winner_address)
    if winner.lower() not in players:
        raise DisbursementDenied(
            f"winner {winner} is not player1/player2 on BoardmanEscrow"
        )
    tx = escrow.functions.resolveMatch(mid, winner).build_transaction(
        {"from": acct.address}
    )
    h = _send_house(w3, acct, tx, "resolveMatch", cfg["escrow"])
    return {
        "success": True,
        "mode": "onchain",
        "result": "win",
        "winner": winner,
        "tx_hash": h,
        "explorer": _explorer(cfg, h),
        "match_id_bytes32": mid_hex,
        "chain_id": chain_id,
        "authorization": authorization.fingerprint,
    }


def fund_agent_from_key(
    to_address: str,
    amount_usdc: Decimal,
    *,
    funder_key: Optional[str] = None,
    chain_id: str = "arc",
) -> dict[str, Any]:
    """Ops faucet: USDC to a registered contestant. Never the House resolver key."""
    from gaming.src.stack.agentic.disbursement import (
        DisbursementDenied,
        assert_faucet_destination,
        assert_not_resolver_funder,
    )

    pk = (funder_key or os.getenv("BOARDMAN_FUNDER_KEY") or "").strip()
    if not pk:
        raise DisbursementDenied(
            "Set BOARDMAN_FUNDER_KEY to fund contestants. "
            "The House resolver key cannot ERC-20 transfer."
        )
    if not pk.startswith("0x"):
        pk = "0x" + pk
    assert_not_resolver_funder(pk)
    if amount_usdc <= 0:
        raise DisbursementDenied("faucet amount must be positive")
    assert_faucet_destination(to_address)

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
