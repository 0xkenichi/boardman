"""
escrow_manager.py - Bet Escrow Management
──────────────────────────────────────────

Handles locking user stakes in escrow during active bets
and releasing them to winners when bets resolve.

The escrow wallet is a shared platform wallet controlled by sideQuest.
"""

import os
from datetime import datetime
from db_layer import DBLayer
from circle_wallet_service import CircleWalletService


class EscrowManager:
    def __init__(self, db: DBLayer):
        self.db = db
        self.circle = CircleWalletService()
        self.escrow_wallet_address = os.getenv("ESCROW_WALLET_ADDRESS")
        self.escrow_wallet_id = os.getenv("ESCROW_WALLET_ID")
        self.protocol_fees_wallet = os.getenv("PROTOCOL_FEES_WALLET")
        self.protocol_fee_percent = 0.03  # 3%

    def ensure_escrow_wallet(self) -> dict:
        """
        Ensure escrow wallet exists. Create if needed.
        Store in .env and return details.

        Returns:
            {
                "success": bool,
                "wallet_address": str,
                "wallet_id": str
            }
        """
        if self.escrow_wallet_address and self.escrow_wallet_id:
            return {
                "success": True,
                "wallet_address": self.escrow_wallet_address,
                "wallet_id": self.escrow_wallet_id,
                "note": "Using existing escrow wallet"
            }

        # Create new escrow wallet
        result = self.circle.get_or_create_escrow_wallet()

        if not result["success"]:
            return {"success": False, "error": result["error"]}

        return {
            "success": True,
            "wallet_address": result["wallet_address"],
            "wallet_id": result["wallet_id"],
            "note": "Created new escrow wallet - update .env with these values"
        }

    def lock_user_stake(self, profile_id: str, bet_id: str, stake_amount: float) -> dict:
        """
        Record user's stake as locked in escrow for balance tracking.

        For now, this just records the escrow entry in DB.
        Future: Actually transfer funds to escrow contract.

        Args:
            profile_id: User's profile UUID
            bet_id: Bet UUID this is for
            stake_amount: Amount in USDC

        Returns:
            {
                "success": bool,
                "escrow_entry_id": str,
                "amount_locked": float
            }
        """
        try:
            # Get user's profile
            profile = self.db.get_profile_by_id(profile_id)
            if not profile:
                return {"success": False, "error": "Profile not found"}

            # Record escrow entry in DB (funds remain in internal balance for now)
            escrow_entry = {
                "bet_id": bet_id,
                "user_id": profile_id,
                "amount_usdc": stake_amount,
                "wallet_address": profile.get("linked_wallet") or profile.get("wallet_address"),
                "escrow_tx_id": f"internal_lock_{bet_id}_{profile_id}",
                "tx_hash": None,
                "status": "LOCKED",
                "created_at": datetime.utcnow().isoformat()
            }

            entry_id = self.db.create_escrow_entry(escrow_entry)

            return {
                "success": True,
                "escrow_entry_id": entry_id,
                "amount_locked": stake_amount
            }

        except Exception as e:
            return {"success": False, "error": str(e)}

    def release_to_winner(self, bet_id: str, winner_profile_id: str, payout_amount: float) -> dict:
        """
        Release locked stake to winner's wallet when bet resolves.

        Args:
            bet_id: Bet UUID
            winner_profile_id: Winner's profile UUID
            payout_amount: Amount to pay out in USDC

        Returns:
            {
                "success": bool,
                "payout_tx_id": str,
                "amount_released": float,
                "tx_hash": str
            }
        """
        try:
            # Get winner's wallet address
            winner_profile = self.db.get_profile_by_id(winner_profile_id)
            if not winner_profile:
                return {"success": False, "error": "Winner profile not found"}

            winner_address = winner_profile.get("wallet_address")
            if not winner_address:
                return {"success": False, "error": "Winner has no wallet"}

            # Ensure escrow wallet
            escrow_result = self.ensure_escrow_wallet()
            if not escrow_result["success"]:
                return {"success": False, "error": f"Escrow unavailable: {escrow_result['error']}"}

            escrow_wallet_id = escrow_result["wallet_id"]

            # Release payout from escrow to winner
            payout_result = self.circle.release_stake_to_winner(
                winner_wallet_address=winner_address,
                amount_usdc=payout_amount,
                escrow_wallet_id=escrow_wallet_id,
                bet_id=bet_id
            )

            if not payout_result["success"]:
                return {"success": False, "error": payout_result["error"]}

            # Update escrow entry status
            self.db.update_escrow_entry_status(bet_id, "RELEASED")

            return {
                "success": True,
                "payout_tx_id": payout_result["payout_tx_id"],
                "amount_released": payout_amount,
                "to_address": winner_address,
                "tx_hash": payout_result.get("tx_hash"),
                "time_to_confirm": payout_result.get("time_to_confirm")
            }

        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_escrow_balance(self) -> dict:
        """
        Get total USDC balance in escrow wallet.

        Returns:
            {
                "success": bool,
                "balance_usdc": float,
                "balance_wei": str
            }
        """
        try:
            escrow_result = self.ensure_escrow_wallet()
            if not escrow_result["success"]:
                return {"success": False, "error": "Escrow not available"}

            escrow_address = escrow_result["wallet_address"]

            balance_result = self.circle.get_wallet_balance(escrow_address)
            return balance_result

        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_locked_amount_for_bet(self, bet_id: str) -> dict:
        """
        Get total amount locked in escrow for a specific bet.

        Returns:
            {
                "success": bool,
                "total_locked_usdc": float,
                "entries": [list of escrow entries]
            }
        """
        try:
            entries = self.db.get_escrow_entries_by_bet(bet_id)

            total_locked = sum(
                entry.get("amount_usdc", 0)
                for entry in entries
                if entry.get("status") == "LOCKED"
            )

            return {
                "success": True,
                "total_locked_usdc": total_locked,
                "entry_count": len(entries),
                "entries": entries
            }

        except Exception as e:
            return {"success": False, "error": str(e)}
