"""
blockchain_whatsapp_agent.py
─────────────────────────────
Unified blockchain transaction agent for WhatsApp users.
Handles:
  - Transaction approvals via WhatsApp buttons
  - Real-time transaction tracking
  - Event listening on ClawEscrow contract
  - Balance syncing from Base
  - Transaction history in WhatsApp
  - Gas estimation and user confirmation
  - Transaction notifications with explorer links
"""

import json
import asyncio
import threading
import time
from decimal import Decimal
from typing import Optional, Dict, List, Tuple
from enum import Enum
from dataclasses import dataclass, asdict
from datetime import datetime
from web3 import Web3
from web3.contract import Contract
from dotenv import load_dotenv
import os

from db_layer import DBLayer
from blockchain_layer import BlockchainLayer
from evolution_bridge import EvolutionBridge

load_dotenv()

class TxStatus(Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    FAILED = "failed"
    CANCELLED = "cancelled"

@dataclass
class Transaction:
    tx_hash: str
    user_whatsapp_id: str
    tx_type: str  # "create_pool", "join_pool", "resolve_pool", "transfer"
    amount: float
    status: TxStatus
    created_at: datetime
    confirmed_at: Optional[datetime] = None
    gas_fee: Optional[float] = None
    explorer_url: Optional[str] = None
    pool_id: Optional[int] = None
    error: Optional[str] = None

class BlockchainWhatsAppAgent:
    def __init__(self, db: DBLayer, blockchain: BlockchainLayer, bridge: EvolutionBridge):
        self.db = db
        self.blockchain = blockchain
        self.bridge = bridge
        self.w3 = blockchain.w3
        self.escrow_contract = blockchain.escrow_contract

        # Use Sepolia explorer for testnet, mainnet for production
        chain_id = blockchain.chain_id
        if chain_id == 84532:  # Base Sepolia
            self.base_explorer = "https://sepolia.basescan.org/tx/"
        else:  # Base Mainnet or other
            self.base_explorer = "https://basescan.org/tx/"

        self.usdc_decimals = 6
        self.chain_id = chain_id

        # Transaction cache
        self.pending_txs: Dict[str, Transaction] = {}
        self.tx_history: Dict[str, List[Transaction]] = {}

        # Event listener thread
        self.listener_thread = None
        self.should_run = True

        # Approval queue (whatsapp_id -> pending_tx_data)
        self.approval_queue: Dict[str, Dict] = {}

    def start_event_listener(self):
        """Start background thread listening for ClawEscrow events"""
        if self.listener_thread is None or not self.listener_thread.is_alive():
            self.listener_thread = threading.Thread(daemon=True, target=self._listen_for_events)
            self.listener_thread.start()

    def stop_event_listener(self):
        """Stop the event listener thread"""
        self.should_run = False
        if self.listener_thread:
            self.listener_thread.join(timeout=5)

    def _listen_for_events(self):
        """Background loop listening to ClawEscrow contract events"""
        while self.should_run:
            try:
                # Poll for new PoolCreated events
                event_filter = self.escrow_contract.events.PoolCreated.create_filter(from_block='latest')
                for event in event_filter.get_new_entries():
                    self._handle_pool_created_event(event)

                # Poll for Payout events
                payout_filter = self.escrow_contract.events.Payout.create_filter(from_block='latest')
                for event in payout_filter.get_new_entries():
                    self._handle_payout_event(event)

                time.sleep(5)  # Check every 5 seconds
            except Exception as e:
                print(f"[Event Listener Error] {e}")
                time.sleep(10)

    def _handle_pool_created_event(self, event):
        """Handle PoolCreated event from contract"""
        pool_id = event['args']['poolId']
        entry_fee = event['args']['entryFee']
        print(f"[Event] Pool created: {pool_id}, Entry fee: {entry_fee}")
        # Update db with new pool (if needed)

    def _handle_payout_event(self, event):
        """Handle Payout event - notify user"""
        pool_id = event['args']['poolId']
        winner = event['args']['winner']
        amount = event['args']['amount']

        # Find associated user
        user = self.db.find_user_by_wallet(winner)
        if user:
            amount_usd = amount / (10 ** self.usdt_decimals)
            self._notify_user_payout(user['whatsapp_id'], pool_id, amount_usd)

    def estimate_gas(self, tx_type: str, **kwargs) -> Tuple[float, str]:
        """
        Estimate gas cost for transaction
        Returns: (gas_fee_usd, gas_fee_eth_str)
        """
        try:
            gas_price = self.w3.eth.gas_price

            # Estimate gas based on transaction type
            if tx_type == "create_pool":
                estimated_gas = 300000
            elif tx_type == "join_pool":
                estimated_gas = 200000
            elif tx_type == "resolve_pool":
                estimated_gas = 300000
            else:
                estimated_gas = 100000

            gas_cost_wei = gas_price * estimated_gas
            gas_cost_eth = self.w3.from_wei(gas_cost_wei, 'ether')

            # Convert to USD (assuming 1 ETH = $3000 for estimation)
            eth_to_usd = 3000
            gas_cost_usd = float(gas_cost_eth) * eth_to_usd

            return gas_cost_usd, str(gas_cost_eth)
        except Exception as e:
            print(f"[Gas Estimation Error] {e}")
            return 0.0, "0.0"

    def create_pool_request(self, whatsapp_id: str, pool_type: int, entry_fee_usd: float) -> str:
        """
        Create a pool request - requires WhatsApp approval
        Returns: approval_token
        """
        approval_token = f"pool_{int(time.time())}_{whatsapp_id[:8]}"

        gas_fee, gas_eth = self.estimate_gas("create_pool")

        self.approval_queue[approval_token] = {
            "user": whatsapp_id,
            "action": "create_pool",
            "pool_type": pool_type,
            "entry_fee": entry_fee_usd,
            "gas_fee": gas_fee,
            "created_at": datetime.now().isoformat()
        }

        # Send WhatsApp approval message with buttons
        self._send_approval_request(
            whatsapp_id,
            f"🔐 Confirm Pool Creation\n\n"
            f"Entry Fee: ${entry_fee_usd:.2f}\n"
            f"Gas Fee: ${gas_fee:.2f}\n"
            f"Total: ${entry_fee_usd + gas_fee:.2f}\n\n"
            f"Confirm to proceed.",
            approval_token
        )

        return approval_token

    def approve_transaction(self, approval_token: str) -> Tuple[bool, str, Optional[str]]:
        """
        Approve pending transaction
        Returns: (success, message, tx_hash)
        """
        if approval_token not in self.approval_queue:
            return False, "Invalid approval token", None

        req = self.approval_queue.pop(approval_token)
        whatsapp_id = req["user"]
        action = req["action"]

        try:
            if action == "create_pool":
                tx_hash = self._execute_create_pool(
                    whatsapp_id,
                    req["pool_type"],
                    int(req["entry_fee"] * (10 ** self.usdt_decimals))
                )
            elif action == "join_pool":
                tx_hash = self._execute_join_pool(whatsapp_id, req["pool_id"])
            elif action == "resolve_pool":
                tx_hash = self._execute_resolve_pool(
                    whatsapp_id,
                    req["pool_id"],
                    req["winners"],
                    req["amounts"]
                )
            else:
                return False, "Unknown action", None

            # Create transaction record
            tx = Transaction(
                tx_hash=tx_hash,
                user_whatsapp_id=whatsapp_id,
                tx_type=action,
                amount=req.get("entry_fee", 0),
                status=TxStatus.PENDING,
                created_at=datetime.now(),
                gas_fee=req.get("gas_fee"),
                pool_id=req.get("pool_id")
            )

            self.pending_txs[tx_hash] = tx
            if whatsapp_id not in self.tx_history:
                self.tx_history[whatsapp_id] = []
            self.tx_history[whatsapp_id].append(tx)

            # Send confirmation to user
            self._notify_user_tx_pending(whatsapp_id, tx)

            return True, "Transaction approved", tx_hash

        except Exception as e:
            error_msg = f"Transaction failed: {str(e)}"
            self._notify_user_tx_failed(whatsapp_id, action, error_msg)
            return False, error_msg, None

    def reject_transaction(self, approval_token: str) -> bool:
        """Reject pending transaction approval"""
        if approval_token in self.approval_queue:
            req = self.approval_queue.pop(approval_token)
            whatsapp_id = req["user"]
            self._notify_user_tx_rejected(whatsapp_id, req["action"])
            return True
        return False

    def _execute_create_pool(self, whatsapp_id: str, pool_type: int, entry_fee_wei: int) -> str:
        """Execute create_pool transaction"""
        consensus_mode = 0  # SIMPLE_MAJORITY
        duration = 86400  # 24 hours
        is_public = True

        nonce = self.w3.eth.get_transaction_count(self.blockchain.account.address)
        txn = self.escrow_contract.functions.createPool(
            pool_type,
            consensus_mode,
            entry_fee_wei,
            duration,
            is_public
        ).build_transaction({
            'chainId': self.base_chain_id,
            'gas': 300000,
            'gasPrice': self.w3.eth.gas_price,
            'nonce': nonce,
        })

        signed_txn = self.w3.eth.account.sign_transaction(txn, private_key=self.blockchain.account.key)
        tx_hash = self.w3.eth.send_raw_transaction(signed_txn.rawTransaction)
        return self.w3.to_hex(tx_hash)

    def _execute_join_pool(self, whatsapp_id: str, pool_id: int) -> str:
        """Execute join_pool transaction"""
        nonce = self.w3.eth.get_transaction_count(self.blockchain.account.address)
        txn = self.escrow_contract.functions.joinPool(pool_id).build_transaction({
            'chainId': self.base_chain_id,
            'gas': 200000,
            'gasPrice': self.w3.eth.gas_price,
            'nonce': nonce,
        })

        signed_txn = self.w3.eth.account.sign_transaction(txn, private_key=self.blockchain.account.key)
        tx_hash = self.w3.eth.send_raw_transaction(signed_txn.rawTransaction)
        return self.w3.to_hex(tx_hash)

    def _execute_resolve_pool(self, whatsapp_id: str, pool_id: int, winners: List[str], amounts: List[int]) -> str:
        """Execute resolve_pool transaction"""
        nonce = self.w3.eth.get_transaction_count(self.blockchain.account.address)
        txn = self.escrow_contract.functions.resolvePool(pool_id, winners, amounts).build_transaction({
            'chainId': self.base_chain_id,
            'gas': 300000,
            'gasPrice': self.w3.eth.gas_price,
            'nonce': nonce,
        })

        signed_txn = self.w3.eth.account.sign_transaction(txn, private_key=self.blockchain.account.key)
        tx_hash = self.w3.eth.send_raw_transaction(signed_txn.rawTransaction)
        return self.w3.to_hex(tx_hash)

    def get_tx_status(self, tx_hash: str) -> Tuple[str, Optional[str]]:
        """Get transaction status from blockchain"""
        try:
            receipt = self.w3.eth.get_transaction_receipt(tx_hash)
            if receipt:
                if receipt['status'] == 1:
                    return TxStatus.CONFIRMED.value, None
                else:
                    return TxStatus.FAILED.value, "Transaction reverted"
            else:
                return TxStatus.PENDING.value, None
        except Exception as e:
            return TxStatus.PENDING.value, str(e)

    def get_transaction_history(self, whatsapp_id: str, limit: int = 10) -> List[Dict]:
        """Get transaction history for user"""
        txs = self.tx_history.get(whatsapp_id, [])
        return [asdict(tx) for tx in txs[-limit:]]

    def get_user_balance(self, whatsapp_id: str) -> float:
        """Get user's current balance from database"""
        try:
            profile = self.db.get_profile(whatsapp_id)
            if profile:
                return float(profile.get('balance', 0))
            return 0.0
        except Exception as e:
            print(f"[Balance Fetch Error] {e}")
            return 0.0

    def _send_approval_request(self, whatsapp_id: str, message: str, token: str):
        """Send WhatsApp approval buttons"""
        try:
            self.bridge.send_interactive_buttons(
                whatsapp_id,
                message,
                [
                    {"id": f"{token}_approve", "title": "✅ Approve"},
                    {"id": f"{token}_reject", "title": "❌ Reject"}
                ]
            )
        except Exception as e:
            print(f"[WhatsApp Send Error] {e}")

    def _notify_user_tx_pending(self, whatsapp_id: str, tx: Transaction):
        """Notify user of pending transaction"""
        explorer_link = f"{self.base_explorer}{tx.tx_hash}"
        message = (
            f"⏳ Transaction Submitted\n\n"
            f"Type: {tx.tx_type.replace('_', ' ').title()}\n"
            f"Amount: ${tx.amount:.2f}\n"
            f"Gas Fee: ${tx.gas_fee:.2f}\n"
            f"Status: Pending confirmation\n\n"
            f"🔗 Track: {explorer_link}"
        )
        try:
            self.bridge.send_text_message(whatsapp_id, message)
        except Exception as e:
            print(f"[Notification Error] {e}")

    def _notify_user_tx_confirmed(self, whatsapp_id: str, tx: Transaction):
        """Notify user of confirmed transaction"""
        explorer_link = f"{self.base_explorer}{tx.tx_hash}"
        message = (
            f"✅ Transaction Confirmed!\n\n"
            f"Type: {tx.tx_type.replace('_', ' ').title()}\n"
            f"Amount: ${tx.amount:.2f}\n"
            f"Gas Fee: ${tx.gas_fee:.2f}\n"
            f"Block: {tx.confirmed_at}\n\n"
            f"🔗 Details: {explorer_link}"
        )
        try:
            self.bridge.send_text_message(whatsapp_id, message)
        except Exception as e:
            print(f"[Notification Error] {e}")

    def _notify_user_tx_failed(self, whatsapp_id: str, tx_type: str, error: str):
        """Notify user of failed transaction"""
        message = (
            f"❌ Transaction Failed\n\n"
            f"Type: {tx_type.replace('_', ' ').title()}\n"
            f"Error: {error}\n\n"
            f"Please try again or contact support."
        )
        try:
            self.bridge.send_text_message(whatsapp_id, message)
        except Exception as e:
            print(f"[Notification Error] {e}")

    def _notify_user_tx_rejected(self, whatsapp_id: str, tx_type: str):
        """Notify user of rejected transaction"""
        message = f"❌ Transaction rejected: {tx_type.replace('_', ' ').title()}"
        try:
            self.bridge.send_text_message(whatsapp_id, message)
        except Exception as e:
            print(f"[Notification Error] {e}")

    def _notify_user_payout(self, whatsapp_id: str, pool_id: int, amount_usd: float):
        """Notify user of payout"""
        message = (
            f"🎉 You won!\n\n"
            f"Pool ID: {pool_id}\n"
            f"Payout: ${amount_usd:.2f} USDT\n\n"
            f"Funds credited to your wallet"
        )
        try:
            self.bridge.send_text_message(whatsapp_id, message)
        except Exception as e:
            print(f"[Notification Error] {e}")
