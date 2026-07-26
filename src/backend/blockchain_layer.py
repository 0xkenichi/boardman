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
    """

    def __init__(self):
        network_key = os.getenv("NETWORK", "testnet").lower()
        if network_key not in NETWORKS:
            raise ValueError(f"Invalid NETWORK '{network_key}'. Must be 'testnet' or 'mainnet'.")

        self.network = NETWORKS[network_key]
        self.network_key = network_key
        logger.info(f"[Blockchain] Connecting to {self.network['name']} ({self.network['rpc_url']})")

        self.w3 = Web3(Web3.HTTPProvider(self.network["rpc_url"], request_kwargs={"timeout": 10}))
        # Base (OP Stack) does not require PoA middleware — blocks have normal extraData

        # Check connectivity but DON'T crash on startup — allow service to start
        try:
            is_connected = self.w3.is_connected()
            if not is_connected:
                logger.error(f"[Blockchain] Cannot connect to {self.network['name']} RPC at {self.network['rpc_url']}. Blockchain features will be unavailable until the RPC becomes reachable.")
        except Exception as e:
            logger.error(f"[Blockchain] RPC connectivity check failed: {e}. Blockchain features will be unavailable.")

        # Admin wallet (resolver)
        private_key = os.getenv("ADMIN_PRIVATE_KEY", "")
        if not private_key:
            raise ValueError("[Blockchain] ADMIN_PRIVATE_KEY not set")
        self.account = Account.from_key(private_key)
        logger.info(f"[Blockchain] Admin wallet: {self.account.address}")

        # Contracts
        escrow_address = os.getenv("CSC_ADDRESS", "")
        if not escrow_address or escrow_address in ("0x...", "0x0000", ""):
            logger.warning("[Blockchain] CSC_ADDRESS not set — onchain features disabled")
            self.escrow = None
        else:
            self.escrow = self.w3.eth.contract(
                address=Web3.to_checksum_address(escrow_address),
                abi=CLAW_ESCROW_ABI,
            )
        self.usdc = self.w3.eth.contract(
            address=Web3.to_checksum_address(self.network["usdc_address"]),
            abi=ERC20_ABI,
        )

        if escrow_address and escrow_address not in ("0x...", "0x0000", ""):
            logger.info(f"[Blockchain] ClawEscrow: {escrow_address}")
        logger.info(f"[Blockchain] USDC:       {self.network['usdc_address']}")

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

    def _build_and_send(self, fn, gas_limit: int = 200_000) -> dict:
        """Build, sign, and send a transaction. Returns receipt."""
        nonce = self.w3.eth.get_transaction_count(self.account.address, "pending")
        gas_price = self.w3.eth.gas_price

        txn = fn.build_transaction({
            "from":     self.account.address,
            "nonce":    nonce,
            "gas":      gas_limit,
            "gasPrice": gas_price,
            "chainId":  self.network["chain_id"],
        })

        signed = self.w3.eth.account.sign_transaction(txn, self.account.key)
        tx_hash = self.w3.eth.send_raw_transaction(signed.raw_transaction)
        logger.info(f"[Blockchain] Tx sent: {tx_hash.hex()}")

        receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
        if receipt.status != 1:
            raise RuntimeError(f"[Blockchain] Transaction reverted: {tx_hash.hex()}")

        logger.info(f"[Blockchain] Tx confirmed in block {receipt.blockNumber}")
        return {
            "tx_hash": tx_hash.hex(),
            "block": receipt.blockNumber,
            "gas_used": receipt.gasUsed,
            "explorer_url": self.network["block_explorer_tx"] + tx_hash.hex(),
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
        mid = self.match_id_to_bytes32(match_id)
        fn = self.escrow.functions.cancelMatch(mid)
        result = await asyncio.to_thread(self._build_and_send, fn)
        logger.info(f"[Blockchain] Match {match_id} cancelled — players refunded")
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

def get_blockchain_layer() -> BlockchainLayer:
    global _instance
    if _instance is None:
        _instance = BlockchainLayer()
    return _instance
