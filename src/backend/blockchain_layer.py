"""
blockchain_layer.py
────────────────────────────────────────────────────────────────────────────────
Web3 interaction layer for sideQuest's ClawEscrow contract.
Supports Base Sepolia (testnet) and Base Mainnet via NETWORK env var.

Environment Variables Required:
    NETWORK                 : "testnet" | "mainnet"  (default: testnet)
    ADMIN_PRIVATE_KEY       : hex private key for the resolver/admin wallet
    CSC_ADDRESS             : deployed ClawEscrow contract address
    BASE_SEPOLIA_RPC_URL    : (optional) custom Sepolia RPC
    BASE_MAINNET_RPC_URL    : (optional) custom Mainnet RPC
"""

# =============================================================================
# PARKED / DORMANT — 2026-06-13 ELON FOCUS (see ELON_FOCUS_PLAN.md)
# Web3 + ClawEscrow layer for previous on-chain gaming staking.
# Current product focus = social quests (real-world coordination, off-chain).
# Do not import or activate in quest/friends/chat/reputation flows.
# =============================================================================

import os
import json
import logging
import asyncio
from decimal import Decimal
from functools import wraps
from typing import Optional

from web3 import Web3
# from web3.middleware import geth_poa_middleware  # Removed — Base is OP Stack, not PoA
from eth_account import Account

logger = logging.getLogger(__name__)

# ─── Network Config ───────────────────────────────────────────────────────────

NETWORKS = {
    "testnet": {
        "name": "Base Sepolia",
        "chain_id": 84532,
        "rpc_url": os.getenv("BASE_SEPOLIA_RPC_URL", "https://sepolia.base.org"),
        "usdc_address": "0x036CbD53842c5426634e7929541eC2318f3dCF7e",
        "explorer": "https://sepolia.basescan.org",
        "block_explorer_tx": "https://sepolia.basescan.org/tx/",
    },
    "mainnet": {
        "name": "Base Mainnet",
        "chain_id": 8453,
        "rpc_url": os.getenv("BASE_MAINNET_RPC_URL", "https://mainnet.base.org"),
        "usdc_address": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
        "explorer": "https://basescan.org",
        "block_explorer_tx": "https://basescan.org/tx/",
    },
}

# ─── ClawEscrow ABI (minimal — only functions the backend calls) ──────────────

CLAW_ESCROW_ABI = [
    # createMatch
    {
        "inputs": [
            {"name": "matchId", "type": "bytes32"},
            {"name": "stake",   "type": "uint256"},
        ],
        "name": "createMatch",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    # joinMatch
    {
        "inputs": [{"name": "matchId", "type": "bytes32"}],
        "name": "joinMatch",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    # resolveMatch
    {
        "inputs": [
            {"name": "matchId", "type": "bytes32"},
            {"name": "winner",  "type": "address"},
        ],
        "name": "resolveMatch",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    # flagDispute
    {
        "inputs": [{"name": "matchId", "type": "bytes32"}],
        "name": "flagDispute",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    # cancelMatch
    {
        "inputs": [{"name": "matchId", "type": "bytes32"}],
        "name": "cancelMatch",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    # getMatch (view)
    {
        "inputs": [{"name": "matchId", "type": "bytes32"}],
        "name": "getMatch",
        "outputs": [
            {
                "components": [
                    {"name": "player1",        "type": "address"},
                    {"name": "player2",        "type": "address"},
                    {"name": "stakePerPlayer", "type": "uint256"},
                    {"name": "status",         "type": "uint8"},
                    {"name": "createdAt",      "type": "uint256"},
                    {"name": "lockedAt",       "type": "uint256"},
                ],
                "name": "",
                "type": "tuple",
            }
        ],
        "stateMutability": "view",
        "type": "function",
    },
    # contractBalance (view)
    {
        "inputs": [],
        "name": "contractBalance",
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
    # Events
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True,  "name": "matchId", "type": "bytes32"},
            {"indexed": True,  "name": "player1", "type": "address"},
            {"indexed": False, "name": "stake",   "type": "uint256"},
        ],
        "name": "MatchCreated",
        "type": "event",
    },
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True,  "name": "matchId", "type": "bytes32"},
            {"indexed": True,  "name": "winner",  "type": "address"},
            {"indexed": False, "name": "payout",  "type": "uint256"},
            {"indexed": False, "name": "fee",     "type": "uint256"},
        ],
        "name": "MatchResolved",
        "type": "event",
    },
]

# ERC-20 transfer ABI (for monitoring incoming USDC deposits)
ERC20_ABI = [
    {
        "inputs": [{"name": "account", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [
            {"name": "spender", "type": "address"},
            {"name": "amount",  "type": "uint256"},
        ],
        "name": "approve",
        "outputs": [{"name": "", "type": "bool"}],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True,  "name": "from",  "type": "address"},
            {"indexed": True,  "name": "to",    "type": "address"},
            {"indexed": False, "name": "value", "type": "uint256"},
        ],
        "name": "Transfer",
        "type": "event",
    },
]

# Match status enum mapping (matches Solidity enum order)
MATCH_STATUS = {
    0: "OPEN",
    1: "LOCKED",
    2: "DISPUTED",
    3: "RESOLVED",
    4: "CANCELLED",
}

USDC_DECIMALS = 6


# ─── BlockchainLayer ─────────────────────────────────────────────────────────

class BlockchainLayer:
    """
    Wraps all Web3 interactions for sideQuest.

    Usage:
        bl = BlockchainLayer()
        tx = await bl.resolve_match("match-uuid-abc", winner_wallet_address)

        # Multi-chain (Arc / Base / Avalanche):
        bl = get_blockchain_layer_for_chain("arc")
    """

    def __init__(
        self,
        *,
        chain_id: Optional[str] = None,
        rpc_url: Optional[str] = None,
        usdc_address: Optional[str] = None,
        escrow_address: Optional[str] = None,
        explorer_tx: Optional[str] = None,
        evm_chain_id: Optional[int] = None,
        label: Optional[str] = None,
    ):
        # Legacy NETWORK=testnet|mainnet path when no chain_id override
        if chain_id is None and rpc_url is None:
            network_key = os.getenv("NETWORK", "testnet").lower()
            if network_key not in NETWORKS:
                raise ValueError(
                    f"Invalid NETWORK '{network_key}'. Must be 'testnet' or 'mainnet'."
                )
            self.network = dict(NETWORKS[network_key])
            self.network_key = network_key
            escrow = os.getenv("CSC_ADDRESS", "") or os.getenv(
                "CLAW_ESCROW_ADDRESS_BASE_SEPOLIA", ""
            )
        else:
            # Multi-chain Rematch path (Arc-first)
            self.network_key = (chain_id or "arc").lower()
            self.network = {
                "name": label or self.network_key,
                "chain_id": int(evm_chain_id or 0),
                "rpc_url": rpc_url or "",
                "usdc_address": usdc_address or "",
                "explorer": (explorer_tx or "").rstrip("/"),
                "block_explorer_tx": explorer_tx or "",
            }
            escrow = escrow_address or ""

        if rpc_url:
            self.network["rpc_url"] = rpc_url
        if usdc_address:
            self.network["usdc_address"] = usdc_address
        if explorer_tx:
            self.network["block_explorer_tx"] = explorer_tx
        if evm_chain_id:
            self.network["chain_id"] = int(evm_chain_id)

        logger.info(
            "[Blockchain] Connecting to %s (%s)",
            self.network.get("name"),
            self.network.get("rpc_url"),
        )

        self.w3 = Web3(
            Web3.HTTPProvider(self.network["rpc_url"], request_kwargs={"timeout": 20})
        )

        try:
            is_connected = self.w3.is_connected()
            if not is_connected:
                logger.error(
                    "[Blockchain] Cannot connect to %s RPC at %s. "
                    "Blockchain features will be unavailable until the RPC becomes reachable.",
                    self.network.get("name"),
                    self.network.get("rpc_url"),
                )
        except Exception as e:
            logger.error(
                "[Blockchain] RPC connectivity check failed: %s. "
                "Blockchain features will be unavailable.",
                e,
            )

        # Admin wallet (resolver) — cancel/resolve/dispute
        private_key = (
            os.getenv("ADMIN_PRIVATE_KEY")
            or os.getenv("RESOLVER_PRIVATE_KEY")
            or os.getenv("GAS_TANK_PRIVATE_KEY")
            or ""
        )
        if not private_key:
            raise ValueError(
                "[Blockchain] ADMIN_PRIVATE_KEY not set "
                "(needed for cancel/refund/resolve on-chain)"
            )
        if private_key.startswith("0x"):
            pass
        self.account = Account.from_key(private_key)
        logger.info("[Blockchain] Admin wallet: %s", self.account.address)

        # Contracts
        if not escrow or escrow in ("0x...", "0x0000", ""):
            logger.warning(
                "[Blockchain] Escrow address not set for %s — onchain features disabled",
                self.network_key,
            )
            self.escrow = None
            self.escrow_address = ""
        else:
            self.escrow_address = escrow
            self.escrow = self.w3.eth.contract(
                address=Web3.to_checksum_address(escrow),
                abi=CLAW_ESCROW_ABI,
            )
        usdc = self.network.get("usdc_address") or ""
        if usdc:
            self.usdc = self.w3.eth.contract(
                address=Web3.to_checksum_address(usdc),
                abi=ERC20_ABI,
            )
        else:
            self.usdc = None

        if self.escrow_address:
            logger.info("[Blockchain] ClawEscrow: %s", self.escrow_address)
        logger.info("[Blockchain] USDC:       %s", usdc)

    # ─── Helpers ─────────────────────────────────────────────────────────────

    @staticmethod
    def match_id_to_bytes32(match_id: str) -> bytes:
        """Convert a string match ID (UUID or custom) to bytes32."""
        import hashlib
        return hashlib.sha256(match_id.encode()).digest()

    @staticmethod
    def usdc_to_wei(amount_usd: float) -> int:
        """Convert dollar amount to USDC units (6 decimals)."""
        return int(Decimal(str(amount_usd)) * Decimal(10 ** USDC_DECIMALS))

    @staticmethod
    def wei_to_usdc(amount_wei: int) -> float:
        """Convert USDC units to dollar amount."""
        return float(Decimal(str(amount_wei)) / Decimal(10 ** USDC_DECIMALS))

    def _build_and_send(self, fn, gas_limit: int = 300_000) -> dict:
        """Build, sign, and send a transaction. Returns receipt."""
        if self.escrow is None:
            raise RuntimeError(
                f"[Blockchain] Escrow contract not configured for {self.network_key}"
            )
        nonce = self.w3.eth.get_transaction_count(self.account.address, "pending")
        chain_id = int(self.network.get("chain_id") or self.w3.eth.chain_id)

        # EIP-1559 when available (Arc / modern nets); else legacy gasPrice
        base: dict = {
            "from": self.account.address,
            "nonce": nonce,
            "gas": gas_limit,
            "chainId": chain_id,
        }
        try:
            latest = self.w3.eth.get_block("latest")
            base_fee = latest.get("baseFeePerGas")
            if base_fee is not None:
                tip = self.w3.to_wei(1, "gwei")
                base["maxPriorityFeePerGas"] = tip
                base["maxFeePerGas"] = int(base_fee) * 2 + tip
            else:
                base["gasPrice"] = self.w3.eth.gas_price
        except Exception:
            base["gasPrice"] = self.w3.eth.gas_price

        txn = fn.build_transaction(base)

        signed = self.w3.eth.account.sign_transaction(txn, self.account.key)
        raw = getattr(signed, "raw_transaction", None) or getattr(signed, "rawTransaction")
        tx_hash = self.w3.eth.send_raw_transaction(raw)
        hx = tx_hash.hex() if hasattr(tx_hash, "hex") else str(tx_hash)
        logger.info("[Blockchain] Tx sent: %s", hx)

        receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
        if receipt.status != 1:
            raise RuntimeError(f"[Blockchain] Transaction reverted: {hx}")

        logger.info("[Blockchain] Tx confirmed in block %s", receipt.blockNumber)
        explorer = self.network.get("block_explorer_tx") or ""
        return {
            "tx_hash": hx,
            "block": receipt.blockNumber,
            "gas_used": receipt.gasUsed,
            "explorer_url": f"{explorer}{hx}" if explorer else hx,
        }

    # ─── Match Lifecycle ──────────────────────────────────────────────────────

    async def create_match_onchain(self, match_id: str, stake_usd: float) -> dict:
        """
        Called by the backend when creator confirms a challenge.
        NOTE: The admin wallet does NOT fund matches — players fund themselves.
        This method is used for admin-sponsored test matches or future automation.
        """
        mid = self.match_id_to_bytes32(match_id)
        stake_wei = self.usdc_to_wei(stake_usd)
        fn = self.escrow.functions.createMatch(mid, stake_wei)
        return await asyncio.to_thread(self._build_and_send, fn)

    async def resolve_match_onchain(self, match_id: str, winner_address: str) -> dict:
        """
        Called after both players report the same score OR after AI mediator decides.
        Admin (resolver) wallet signs this transaction.
        """
        mid = self.match_id_to_bytes32(match_id)
        winner = Web3.to_checksum_address(winner_address)
        fn = self.escrow.functions.resolveMatch(mid, winner)
        result = await asyncio.to_thread(self._build_and_send, fn)
        logger.info(f"[Blockchain] Match {match_id} resolved → winner: {winner_address}")
        return result

    async def flag_dispute_onchain(self, match_id: str) -> dict:
        """Called when score reports conflict. Locks match as DISPUTED on-chain."""
        mid = self.match_id_to_bytes32(match_id)
        fn = self.escrow.functions.flagDispute(mid)
        result = await asyncio.to_thread(self._build_and_send, fn)
        logger.info(f"[Blockchain] Match {match_id} flagged as disputed")
        return result

    async def cancel_match_onchain(self, match_id: str) -> dict:
        """Refunds both players. Called on timeout or admin cancel."""
        if self.escrow is None:
            raise RuntimeError(
                f"Escrow not configured for {self.network_key} — set CLAW_ESCROW_ADDRESS_*"
            )
        mid = self.match_id_to_bytes32(match_id)
        fn = self.escrow.functions.cancelMatch(mid)
        result = await asyncio.to_thread(self._build_and_send, fn)
        logger.info("[Blockchain] Match %s cancelled — players refunded", match_id)
        return result

    # ─── Read-Only Queries ────────────────────────────────────────────────────

    def get_match_status(self, match_id: str) -> dict:
        """Returns current on-chain match state."""
        mid = self.match_id_to_bytes32(match_id)
        m = self.escrow.functions.getMatch(mid).call()
        return {
            "player1":          m[0],
            "player2":          m[1],
            "stake_per_player": self.wei_to_usdc(m[2]),
            "status":           MATCH_STATUS.get(m[3], "UNKNOWN"),
            "created_at":       m[4],
            "locked_at":        m[5],
        }

    def get_admin_balance(self) -> float:
        """Returns admin wallet ETH balance (for gas monitoring)."""
        bal = self.w3.eth.get_balance(self.account.address)
        return float(Web3.from_wei(bal, "ether"))

    def get_contract_usdc_balance(self) -> float:
        """Returns total USDC held in escrow contract."""
        bal = self.escrow.functions.contractBalance().call()
        return self.wei_to_usdc(bal)

    def get_wallet_usdc_balance(self, address: str) -> float:
        """Returns USDC balance of any wallet address."""
        bal = self.usdc.functions.balanceOf(Web3.to_checksum_address(address)).call()
        return self.wei_to_usdc(bal)

    def is_connected(self) -> bool:
        return self.w3.is_connected()

    def get_network_info(self) -> dict:
        return {
            "network":    self.network_key,
            "name":       self.network["name"],
            "chain_id":   self.network["chain_id"],
            "rpc_url":    self.network["rpc_url"],
            "admin":      self.account.address,
            "escrow":     os.getenv("CSC_ADDRESS"),
            "usdc":       self.network["usdc_address"],
            "connected":  self.is_connected(),
            "eth_balance": self.get_admin_balance(),
        }

    # ─── USDC Transfer Monitoring ─────────────────────────────────────────────

    def get_deposit_address(self) -> str:
        """
        Returns the admin wallet address that users send USDC to for wallet top-up.
        The backend monitors this wallet and credits user accounts internally.
        """
        return self.account.address

    async def scan_usdc_transfers_to_wallet(
        self,
        wallet_address: str,
        from_block: int,
        to_block: Optional[int] = None,
    ) -> list[dict]:
        """
        Scans for USDC Transfer events sent to a specific wallet address.
        Used by transaction_manager to detect deposits to custodial wallets.
        """
        to_block = to_block or self.w3.eth.block_number

        try:
            events = self.usdc.events.Transfer.getLogs(
                fromBlock=from_block,
                toBlock=to_block,
            )
            # Filter for transfers to the specified wallet
            events = [e for e in events if e.get("args", {}).get("to", "").lower() == wallet_address.lower()]
        except Exception:
            return []

        deposits = []
        for e in events:
            deposits.append({
                "tx_hash":      e["transactionHash"].hex(),
                "from_address": e["args"]["from"],
                "to_address":   e["args"]["to"],
                "amount_usdc":  self.wei_to_usdc(e["args"]["value"]),
                "block":        e["blockNumber"],
            })

        return deposits

    async def scan_incoming_usdc(
        self,
        from_block: int,
        to_block: Optional[int] = None,
    ) -> list[dict]:
        """
        Legacy method: Scans for USDC Transfer events sent to the admin wallet.
        Kept for backward compatibility but deprecated.
        """
        return await self.scan_usdc_transfers_to_wallet(
            self.account.address,
            from_block,
            to_block,
        )


# ─── Module-level singleton ───────────────────────────────────────────────────

_instance: Optional[BlockchainLayer] = None
_chain_instances: dict[str, BlockchainLayer] = {}


def get_blockchain_layer() -> BlockchainLayer:
    """Legacy singleton (NETWORK=testnet Base path). Prefer get_blockchain_layer_for_chain."""
    global _instance
    if _instance is None:
        _instance = BlockchainLayer()
    return _instance


def get_blockchain_layer_for_chain(chain_id: str) -> BlockchainLayer:
    """Return a BlockchainLayer bound to Rematch settlement chain (arc/base/…).

    Used by clawstation_escrow cancel / resolve / dispute / status.
    """
    cid = (chain_id or "arc").lower().strip()
    if cid in _chain_instances:
        return _chain_instances[cid]

    from gaming.src.backend.services.chains import (
        get_chain,
        get_escrow_address,
        get_rpc_url,
        get_usdc_address,
        normalize_chain_id,
    )

    cid = normalize_chain_id(cid)
    meta = get_chain(cid)
    layer = BlockchainLayer(
        chain_id=cid,
        rpc_url=get_rpc_url(cid),
        usdc_address=get_usdc_address(cid),
        escrow_address=get_escrow_address(cid),
        explorer_tx=meta.get("explorer_tx") or "",
        evm_chain_id=int(meta.get("chain_id") or 0),
        label=meta.get("label") or cid,
    )
    _chain_instances[cid] = layer
    return layer
