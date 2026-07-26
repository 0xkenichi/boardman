"""
wallet_service.py
────────────────────────────────────────────────────────────────────────────────
Unified wallet management layer.
Handles internal balance tracking, deposit instructions, withdrawal requests,
and wallet linking. Fiat payments are currently paused.
"""

import os
import logging
from typing import Optional
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class WalletService:

    def __init__(self):
        from gaming.src.backend.blockchain_layer import get_blockchain_layer
        from gaming.src.backend.circle_wallet_service import CircleWalletService
        from gaming.src.backend.db_layer import DBLayer
        self.bl = get_blockchain_layer()
        self.circle = CircleWalletService()
        self.db = DBLayer()

    # ─── Balance ──────────────────────────────────────────────────────────────

    async def get_balance(self, user_id: str) -> dict:
        from gaming.src.backend.db_layer_blockchain import get_wallet_balance
        from gaming.src.backend.supabase_client import get_supabase
        sb = get_supabase()
        profile = sb.table("profiles").select("wallet_balance_usdc,play_points,wallet_address,linked_wallet,circle_wallet_id").eq("id", user_id).single().execute().data or {}

        balance = float(profile.get("wallet_balance_usdc", 0))
        points  = int(profile.get("play_points", 0))
        custodial_wallet = profile.get("wallet_address")      # Circle custodial for deposits
        withdrawal_wallet = profile.get("linked_wallet")      # External wallet for withdrawals
        circle_id = profile.get("circle_wallet_id")

        on_chain_balance = None
        if custodial_wallet:  # Check custodial wallet balance
            try:
                # First check if blockchain connection is working
                if not self.bl.is_connected():
                    logger.warning(f"[Balance] Blockchain not connected for user {user_id}")
                else:
                    on_chain_balance = self.bl.get_wallet_usdc_balance(custodial_wallet)
                    logger.info(f"[Balance] User {user_id} custodial wallet {custodial_wallet}: ${on_chain_balance:.2f} USDC")
            except Exception as e:
                logger.error(f"[Balance] Failed to fetch on-chain balance for user {user_id}, wallet {custodial_wallet}: {e}")
                # Don't set on_chain_balance to None here - let it remain None to indicate error

        # Calculate escrowed/staked balance (locked in active bets)
        escrowed_balance = 0.0
        try:
            escrow_entries = sb.table("escrow_entries").select("amount_usdc,status").eq("user_id", user_id).eq("status", "LOCKED").execute()
            escrowed_balance = sum(float(entry.get("amount_usdc", 0)) for entry in escrow_entries.data or [])
        except Exception:
            pass

        return {
            "internal_balance_usdc": balance,
            "on_chain_balance_usdc": on_chain_balance,
            "escrowed_balance_usdc": escrowed_balance,
            "play_points":           points,
            "custodial_wallet":      custodial_wallet,  # Circle wallet for deposits
            "withdrawal_wallet":     withdrawal_wallet,  # External wallet for withdrawals
            "circle_wallet_id":      circle_id,
            "network":               self.bl.network_key,
            "is_custodial":          bool(circle_id)
        }

    # ─── Deposit ─────────────────────────────────────────────────────────────

    def get_crypto_deposit_info(self) -> dict:
        return {
            "deposit_address":   self.bl.get_deposit_address(),
            "network":           self.bl.network["name"],
            "chain_id":          self.bl.network["chain_id"],
            "usdc_contract":     self.bl.network["usdc_address"],
            "minimum":           1.0,
            "confirmation_time": "~30 seconds",
            "note":              "Send USDC only on the correct network. Other tokens will not be credited.",
        }

    # ─── Create Wallet (Circle Custodial) ───────────────────────────────────

    async def create_wallet(self, user_id: str) -> dict:
        """
        Create a new Circle custodial wallet for a user.
        Uses Base Sepolia testnet by default.
        Checks if user already has a wallet first.
        """
        from gaming.src.backend.db_layer_blockchain import link_circle_wallet

        # Check if user already has a custodial wallet
        from supabase_client import get_supabase
        sb = get_supabase()
        existing = sb.table("profiles").select("wallet_address,circle_wallet_id").eq("id", user_id).execute()

        if existing.data and existing.data[0].get("wallet_address"):
            return {
                "success": False,
                "error": "User already has a custodial wallet",
                "existing_wallet": existing.data[0]["wallet_address"]
            }

        try:
            # Create custodial wallet via Circle
            result = self.circle.create_custodial_wallet_for_user(user_id)

            if not result.get("success"):
                logger.error(f"[WalletService] Circle creation failed for {user_id}: {result.get('error')}")
                return {
                    "success": False,
                    "error": f"Circle API Error: {result.get('error')}"
                }

            wallet_address = result["wallet_address"]
            wallet_id      = result["wallet_id"]
            wallet_set_id  = os.getenv("CIRCLE_WALLET_SET_ID")

            # Associate with user profile in DB (with uniqueness validation)
            await link_circle_wallet(user_id, wallet_id, wallet_address, wallet_set_id)

            logger.info(f"[WalletService] Created Circle custodial wallet for user {user_id}: {wallet_address}")
            return {
                "success":      True,
                "wallet":       wallet_address,
                "wallet_id":    wallet_id,
                "is_custodial": True,
                "note":         "Secure custodial wallet created on Base Sepolia."
            }
        except ValueError as ve:
            # Wallet already assigned to another user
            logger.error(f"[WalletService] Wallet conflict for {user_id}: {ve}")
            return {
                "success": False,
                "error": str(ve)
            }
        except Exception as e:
            logger.error(f"[WalletService] Exception creating custodial wallet for {user_id}: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e)
            }

    # ─── Link Wallet ──────────────────────────────────────────────────────────

    async def link_wallet(self, user_id: str, wallet_address: str) -> dict:
        from web3 import Web3
        from gaming.src.backend.db_layer_blockchain import link_wallet_address

        if not Web3.is_address(wallet_address):
            return {"success": False, "error": "Invalid Ethereum wallet address."}

        checksum = Web3.to_checksum_address(wallet_address)
        await link_wallet_address(user_id, checksum)

        return {
            "success":         True,
            "wallet":          checksum,
            "deposit_address": self.bl.get_deposit_address(),
            "network":         self.bl.network["name"],
        }

    async def link_withdrawal_wallet(self, user_id: str, wallet_address: str) -> dict:
        """Link an external wallet for withdrawals (MetaMask, Rabby, Phantom, etc.)"""
        from web3 import Web3

        if not Web3.is_address(wallet_address):
            return {"success": False, "error": "Invalid Ethereum wallet address."}

        checksum = Web3.to_checksum_address(wallet_address)

        # Store in wallet_address field (used for withdrawals)
        self.db.update_profile_field(user_id, "wallet_address", checksum)

        return {
            "success": True,
            "wallet":  checksum,
        }

    # ─── Withdrawal ───────────────────────────────────────────────────────────

    async def request_withdrawal(self, user_id: str, amount_usd: float) -> dict:
        from gaming.src.backend.db_layer_blockchain import get_wallet_balance, debit_wallet
        from supabase_client import get_supabase
        sb = get_supabase()
        profile = sb.table("profiles").select("wallet_address,whatsapp_number").eq("id", user_id).single().execute().data or {}

        to_wallet = profile.get("wallet_address")
        if not to_wallet:
            return {"success": False, "error": "No withdrawal wallet set. Use /link_wallet <address> to set your external wallet (MetaMask, etc.) for withdrawals."}

        if amount_usd < 5:
            return {"success": False, "error": "Minimum withdrawal is $5.00 USDC."}

        balance = await get_wallet_balance(user_id)
        if balance < amount_usd:
            return {"success": False, "error": f"Insufficient balance. Available: ${balance:.2f}"}

        # Debit immediately to prevent double-spend
        await debit_wallet(user_id, amount_usd)

        # Queue for processing
        sb.table("withdrawal_requests").insert({
            "user_id":     user_id,
            "amount_usdc": amount_usd,
            "to_address":  to_wallet,
            "status":      "pending",
            "network":     self.bl.network_key,
            "created_at":  datetime.now(timezone.utc).isoformat(),
        }).execute()

        logger.info(f"[Wallet] Withdrawal request: ${amount_usd} from {user_id} to {to_wallet}")

        return {
            "success":    True,
            "amount":     amount_usd,
            "to_address": to_wallet,
            "network":    self.bl.network["name"],
            "eta":        "1–24 hours",
        }

    # ─── Admin: Process Withdrawal ────────────────────────────────────────────

    async def process_withdrawal(self, withdrawal_id: str) -> dict:
        """
        Admin-triggered: sends USDC from admin wallet to user's address.
        Called manually or via admin panel.
        """
        from supabase_client import get_supabase
        from web3 import Web3

        sb = get_supabase()
        req = sb.table("withdrawal_requests").select("*").eq("id", withdrawal_id).single().execute().data
        if not req or req["status"] != "pending":
            return {"success": False, "error": "Withdrawal not found or already processed."}

        amount_wei = self.bl.usdc_to_wei(float(req["amount_usdc"]))
        to_address = Web3.to_checksum_address(req["to_address"])

        # Build USDC transfer tx
        nonce     = self.bl.w3.eth.get_transaction_count(self.bl.account.address, "pending")
        gas_price = self.bl.w3.eth.gas_price

        txn = self.bl.usdc.functions.transfer(to_address, amount_wei).build_transaction({
            "from":     self.bl.account.address,
            "nonce":    nonce,
            "gas":      100_000,
            "gasPrice": gas_price,
            "chainId":  self.bl.network["chain_id"],
        })

        signed = self.bl.w3.eth.account.sign_transaction(txn, self.bl.account.key)
        tx_hash = self.bl.w3.eth.send_raw_transaction(signed.raw_transaction)
        receipt = self.bl.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)

        if receipt.status != 1:
            # Revert debit
            from gaming.src.backend.db_layer_blockchain import credit_wallet
            await credit_wallet(req["user_id"], float(req["amount_usdc"]), f"refund_{withdrawal_id}", "withdrawal_failed")
            sb.table("withdrawal_requests").update({"status": "failed"}).eq("id", withdrawal_id).execute()
            return {"success": False, "error": "On-chain transfer reverted."}

        # Mark complete
        sb.table("withdrawal_requests").update({
            "status":  "completed",
            "tx_hash": tx_hash.hex(),
            "completed_at": datetime.now(timezone.utc).isoformat(),
        }).eq("id", withdrawal_id).execute()

        logger.info(f"[Wallet] Withdrawal {withdrawal_id} processed: tx {tx_hash.hex()}")

        # Notify user via Telegram
        try:
            from telegram_notifier import send_telegram_message
            profile = sb.table("profiles").select("telegram_id").eq("id", req["user_id"]).single().execute().data
            tg_id = profile.get("telegram_id") if profile else None
            if tg_id:
                explorer_url = self.bl.network["block_explorer_tx"] + tx_hash.hex()
                tg_msg = (
                    f"✅ *Withdrawal Sent!*\n\n"
                    f"💵 ${float(req['amount_usdc']):.2f} USDC has been sent to:\n"
                    f"`{req['to_address']}`\n\n"
                    f"🔗 [View on Explorer]({explorer_url})\n\n"
                    f"Network: *{self.bl.network['name']}*\n"
                    f"ETA: 1–24 hours"
                )
                await send_telegram_message(int(tg_id), tg_msg)
        except Exception as e:
            logger.warning(f"[Wallet] Telegram withdrawal notification failed: {e}")

        return {
            "success":      True,
            "tx_hash":      tx_hash.hex(),
            "explorer_url": self.bl.network["block_explorer_tx"] + tx_hash.hex(),
            "amount":       req["amount_usdc"],
            "to":           req["to_address"],
        }


# ─── Singleton ────────────────────────────────────────────────────────────────

_wallet_service: Optional[WalletService] = None

def get_wallet_service() -> WalletService:
    global _wallet_service
    if _wallet_service is None:
        _wallet_service = WalletService()
    return _wallet_service
