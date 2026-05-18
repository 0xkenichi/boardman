"""
blockchain_whatsapp_commands.py
───────────────────────────────
WhatsApp command handlers for blockchain operations.
Commands:
  /blockchain_balance - Check wallet balance
  /blockchain_history - View transaction history
  /blockchain_status - Check transaction status
  /blockchain_pool_create - Create a new pool
  /blockchain_pool_join - Join an existing pool
"""

import re
from blockchain_whatsapp_agent import BlockchainWhatsAppAgent, TxStatus
from evolution_bridge import EvolutionBridge

class BlockchainWhatsAppCommands:
    def __init__(self, agent: BlockchainWhatsAppAgent, bridge: EvolutionBridge):
        self.agent = agent
        self.bridge = bridge

    async def handle_command(self, whatsapp_id: str, text: str, is_admin: bool = False) -> bool:
        """
        Route blockchain commands
        Returns: True if command was handled
        """
        text_lower = text.strip().lower()

        if text_lower == "/blockchain_balance":
            await self.cmd_balance(whatsapp_id)
            return True

        elif text_lower == "/blockchain_history":
            await self.cmd_history(whatsapp_id)
            return True

        elif text_lower.startswith("/blockchain_status"):
            parts = text.split()
            if len(parts) >= 2:
                tx_hash = parts[1]
                await self.cmd_status(whatsapp_id, tx_hash)
                return True

        elif text_lower.startswith("/blockchain_pool_create"):
            # Usage: /blockchain_pool_create <pool_type> <entry_fee_usd>
            parts = text.split()
            if len(parts) >= 3:
                try:
                    pool_type = int(parts[1])
                    entry_fee = float(parts[2])
                    await self.cmd_create_pool(whatsapp_id, pool_type, entry_fee)
                    return True
                except ValueError:
                    self.bridge.send_text_message(
                        whatsapp_id,
                        "❌ Invalid format\n\nUsage: /blockchain_pool_create <type> <fee>\n\nExample: /blockchain_pool_create 0 10.50"
                    )
                    return True

        elif text_lower.startswith("/blockchain_pool_join"):
            # Usage: /blockchain_pool_join <pool_id>
            parts = text.split()
            if len(parts) >= 2:
                try:
                    pool_id = int(parts[1])
                    await self.cmd_join_pool(whatsapp_id, pool_id)
                    return True
                except ValueError:
                    self.bridge.send_text_message(
                        whatsapp_id,
                        "❌ Invalid pool ID\n\nUsage: /blockchain_pool_join <pool_id>"
                    )
                    return True

        elif text_lower.startswith("/approve"):
            # Handle transaction approval from button callback
            parts = text.split("_")
            if len(parts) >= 3 and parts[-1] == "approve":
                token = "_".join(parts[:-1])
                await self.cmd_approve(whatsapp_id, token)
                return True

        elif text_lower.startswith("/reject"):
            # Handle transaction rejection from button callback
            parts = text.split("_")
            if len(parts) >= 3 and parts[-1] == "reject":
                token = "_".join(parts[:-1])
                await self.cmd_reject(whatsapp_id, token)
                return True

        return False

    async def cmd_balance(self, whatsapp_id: str):
        """Show user's blockchain balance"""
        try:
            balance = self.agent.get_user_balance(whatsapp_id)
            message = (
                f"💰 Your Balance\n\n"
                f"Available: ${balance:.2f} USDT\n"
                f"Network: Base Mainnet\n"
                f"Chain ID: 8453"
            )
            self.bridge.send_text_message(whatsapp_id, message)
        except Exception as e:
            self.bridge.send_text_message(whatsapp_id, f"❌ Error: {str(e)}")

    async def cmd_history(self, whatsapp_id: str):
        """Show transaction history"""
        try:
            history = self.agent.get_transaction_history(whatsapp_id, limit=10)

            if not history:
                self.bridge.send_text_message(whatsapp_id, "📭 No transactions yet")
                return

            message = "📜 Recent Transactions\n\n"
            for i, tx in enumerate(history[-5:], 1):  # Show last 5
                status_emoji = {
                    TxStatus.PENDING.value: "⏳",
                    TxStatus.CONFIRMED.value: "✅",
                    TxStatus.FAILED.value: "❌",
                    TxStatus.CANCELLED.value: "🚫"
                }.get(tx['status'], "❓")

                message += (
                    f"{i}. {status_emoji} {tx['tx_type'].replace('_', ' ').title()}\n"
                    f"   Amount: ${tx['amount']:.2f}\n"
                    f"   Status: {tx['status']}\n"
                    f"   Hash: {tx['tx_hash'][:10]}...\n\n"
                )

            self.bridge.send_text_message(whatsapp_id, message)
        except Exception as e:
            self.bridge.send_text_message(whatsapp_id, f"❌ Error: {str(e)}")

    async def cmd_status(self, whatsapp_id: str, tx_hash: str):
        """Check transaction status"""
        try:
            status, error = self.agent.get_tx_status(tx_hash)

            status_emoji = {
                TxStatus.PENDING.value: "⏳",
                TxStatus.CONFIRMED.value: "✅",
                TxStatus.FAILED.value: "❌",
                TxStatus.CANCELLED.value: "🚫"
            }.get(status, "❓")

            message = (
                f"{status_emoji} Transaction Status\n\n"
                f"Hash: {tx_hash}\n"
                f"Status: {status.upper()}"
            )

            if error:
                message += f"\nError: {error}"

            explorer_link = f"https://basescan.org/tx/{tx_hash}"
            message += f"\n\n🔗 View: {explorer_link}"

            self.bridge.send_text_message(whatsapp_id, message)
        except Exception as e:
            self.bridge.send_text_message(whatsapp_id, f"❌ Error: {str(e)}")

    async def cmd_create_pool(self, whatsapp_id: str, pool_type: int, entry_fee: float):
        """Create a new pool (with approval)"""
        try:
            balance = self.agent.get_user_balance(whatsapp_id)

            if balance < entry_fee:
                self.bridge.send_text_message(
                    whatsapp_id,
                    f"❌ Insufficient balance\n\n"
                    f"Required: ${entry_fee:.2f}\n"
                    f"Available: ${balance:.2f}"
                )
                return

            # Estimate gas
            gas_fee, gas_eth = self.agent.estimate_gas("create_pool")

            if balance < entry_fee + gas_fee:
                self.bridge.send_text_message(
                    whatsapp_id,
                    f"❌ Insufficient funds for gas\n\n"
                    f"Entry Fee: ${entry_fee:.2f}\n"
                    f"Gas Fee: ${gas_fee:.2f}\n"
                    f"Total: ${entry_fee + gas_fee:.2f}\n"
                    f"Available: ${balance:.2f}"
                )
                return

            # Create pool request
            token = self.agent.create_pool_request(whatsapp_id, pool_type, entry_fee)

        except Exception as e:
            self.bridge.send_text_message(whatsapp_id, f"❌ Error: {str(e)}")

    async def cmd_join_pool(self, whatsapp_id: str, pool_id: int):
        """Join an existing pool (with approval)"""
        try:
            balance = self.agent.get_user_balance(whatsapp_id)

            # Estimate gas
            gas_fee, gas_eth = self.agent.estimate_gas("join_pool")

            # For now, assume we need to estimate pool fee (would come from contract)
            estimated_pool_fee = 10.0  # Placeholder

            total_cost = estimated_pool_fee + gas_fee

            if balance < total_cost:
                self.bridge.send_text_message(
                    whatsapp_id,
                    f"❌ Insufficient balance\n\n"
                    f"Pool Fee: ${estimated_pool_fee:.2f}\n"
                    f"Gas Fee: ${gas_fee:.2f}\n"
                    f"Total: ${total_cost:.2f}\n"
                    f"Available: ${balance:.2f}"
                )
                return

            # Send approval request
            self.agent.approval_queue[f"pool_join_{pool_id}_{whatsapp_id[:8]}"] = {
                "user": whatsapp_id,
                "action": "join_pool",
                "pool_id": pool_id,
                "gas_fee": gas_fee,
                "created_at": datetime.now().isoformat()
            }

            self.agent._send_approval_request(
                whatsapp_id,
                f"🔐 Confirm Pool Join\n\n"
                f"Pool ID: {pool_id}\n"
                f"Estimated Fee: ${estimated_pool_fee:.2f}\n"
                f"Gas Fee: ${gas_fee:.2f}\n"
                f"Total: ${total_cost:.2f}\n\n"
                f"Confirm to proceed.",
                f"pool_join_{pool_id}_{whatsapp_id[:8]}"
            )

        except Exception as e:
            self.bridge.send_text_message(whatsapp_id, f"❌ Error: {str(e)}")

    async def cmd_approve(self, whatsapp_id: str, token: str):
        """Approve pending transaction"""
        try:
            success, message, tx_hash = self.agent.approve_transaction(token)

            if success:
                self.bridge.send_text_message(
                    whatsapp_id,
                    f"✅ {message}\n\n"
                    f"Hash: {tx_hash[:16]}...\n"
                    f"⏳ Waiting for confirmation..."
                )
            else:
                self.bridge.send_text_message(whatsapp_id, f"❌ {message}")

        except Exception as e:
            self.bridge.send_text_message(whatsapp_id, f"❌ Error: {str(e)}")

    async def cmd_reject(self, whatsapp_id: str, token: str):
        """Reject pending transaction"""
        try:
            if self.agent.reject_transaction(token):
                self.bridge.send_text_message(whatsapp_id, "❌ Transaction rejected")
            else:
                self.bridge.send_text_message(whatsapp_id, "❌ Invalid approval token")

        except Exception as e:
            self.bridge.send_text_message(whatsapp_id, f"❌ Error: {str(e)}")


# Integration point in whatsapp_handler.py
def register_blockchain_commands(controller, bridge, db, blockchain):
    """Register blockchain commands with the main WhatsApp handler"""
    agent = BlockchainWhatsAppAgent(db, blockchain, bridge)
    commands = BlockchainWhatsAppCommands(agent, bridge)

    # Start event listener
    agent.start_event_listener()

    return agent, commands
