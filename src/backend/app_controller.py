"""
app_controller.py
────────────────────────────────────────────────────────────────────────────────
ClawController — main orchestration layer.
Receives parsed WhatsApp/Telegram commands and routes them to the correct service.
All user-facing command logic lives here.
"""

import os
import logging
import asyncio
from typing import Optional

logger = logging.getLogger(__name__)
# ─── Explicit column lists (avoid SELECT * to prevent schema mismatch errors) ─
PROFILE_SELECT = """
    id, display_name, telegram_id, whatsapp_id, google_id, psn_id, xbox_id,
    balance, is_whitelisted,
    wallet_address, play_points, total_wins, total_losses,
    location_city, location_visible, created_at, updated_at
"""



class ClawController:
    """
    Central command dispatcher for sideQuest.
    Instantiated once at app startup and used for all incoming messages.
    """

    def __init__(self):
        from evolution_bridge import EvolutionBridge
        from wallet_service   import get_wallet_service
        from match_manager    import get_match_manager
        from db_layer         import DBLayer

        self.db      = DBLayer()
        self.bridge  = EvolutionBridge()
        self.wallet  = get_wallet_service()
        self.matches = get_match_manager()

    # ─── Main Dispatcher ──────────────────────────────────────────────────────

    async def handle_command(self, phone: str, text: str, image_b64: Optional[str] = None) -> str:
        """
        Route an incoming WhatsApp message to the appropriate handler.
        Returns a response string (sent back to user).
        """
        user = await self._get_or_create_user(phone)
        if not user:
            return "❌ Failed to load your profile. Please try again."

        # Handle screenshot submission for disputed match
        if image_b64 and user.get("pending_screenshot_match"):
            return await self._handle_screenshot(user, image_b64)

        parts   = text.strip().split()
        command = parts[0].lower() if parts else ""
        args    = parts[1:] if len(parts) > 1 else []

        handlers = {
            "/start":        self._cmd_start,
            "/help":         self._cmd_help,
            "/wallet":       self._cmd_wallet,
            "/balance":      self._cmd_wallet,
            "/deposit":      self._cmd_deposit,
            "/fund_crypto":  self._cmd_deposit,
            "/create_wallet": self._cmd_create_wallet,
            "/link_wallet":  self._cmd_link_wallet,
            "/transactions": self._cmd_transactions,
            "/withdraw":     self._cmd_withdraw,
            "/challenge":    self._cmd_challenge,
            "/local":        self._cmd_local,
            "/match":        self._cmd_match,
            "/approve":      self._cmd_match,   # alias
            "/report":       self._cmd_report,
            "/bets":         self._cmd_bets,
            "/active":       self._cmd_active,
            "/points":       self._cmd_points,
            "/leaderboard":  self._cmd_leaderboard,
            "/profile":      self._cmd_profile,
            "/link_psn":     self._cmd_link_psn,
            "/link_xbox":    self._cmd_link_xbox,
            "/link_email":   self._cmd_link_email,
        }

        handler = handlers.get(command)
        if handler:
            try:
                return await handler(user, args)
            except Exception as e:
                logger.error(f"[ClawController] Error in {command}: {e}", exc_info=True)
                return "❌ Something went wrong. Please try again."

        # Unrecognised command
        if text.startswith("/"):
            return f"❓ Unknown command `{command}`.\n\nType */help* to see all commands."

        # Non-command message — friendly nudge
        return (
            "👋 Hey! Type */help* to see what I can do.\n\n"
            "Quick start: */wallet* to check your balance, */challenge* to create a match."
        )

    # ─── Command Handlers ─────────────────────────────────────────────────────

    async def _cmd_start(self, user, args) -> str:
        name = user.get("display_name") or "Gamer"
        return (
            f"🎮 *Welcome to sideQuest (Beta), {name}!*\n\n"
            f"The competitive gaming platform where you stake USDC and play to win.\n\n"
            f"🚀 **Early Adopter Program:**\n"
            f"The first 1,000 Mainnet users get a **3% forever fee**! (Current status: Testnet)\n\n"
            f"*Quick Start:*\n"
            f"1️⃣  `/link_wallet 0x...` — Connect your Base wallet\n"
            f"2️⃣  `/deposit` — Get your test USDC address\n"
            f"3️⃣  `/challenge 10 FIFA` — Create a $10 match\n"
            f"4️⃣  Share the match ID with your opponent\n\n"
            f"Type */help* for all commands."
        )

    async def _cmd_help(self, user, args) -> str:
        return (
            "📖 *sideQuest Full Command List*\n\n"
            "*🎮 Core Navigation*\n"
            "`/start` — Welcome & main menu\n"
            "`/help` — Show this help message\n\n"
            "*💰 Wallet & Banking*\n"
            "`/wallet` — Check your USDC balance & wallet\n"
            "`/deposit` — Get USDC deposit address\n"
            "`/fund <amount>` — Add funds (NGN bank transfer)\n"
            "`/fund_crypto <amount>` — Add funds via crypto/USDC\n"
            "`/withdraw <amount>` — Withdraw USDC to your wallet\n"
            "`/link_wallet 0x...` — Link your external Base wallet\n\n"
            "*⚔️ Match Making*\n"
            "`/challenge <amount> <game>` — Create online match challenge\n"
            "`/local <amount> <game>` — Create local match challenge\n"
            "`/match <ID>` — Join a specific challenge by ID\n"
            "`/report <ID> <score>` — Submit match result (e.g. '2-1')\n"
            "`/bets` — Browse all open challenges\n"
            "`/active` — View your active/in-progress matches\n\n"
            "*📊 Stats & Rankings*\n"
            "`/points` — Check your $PLAY points balance\n"
            "`/leaderboard` — View top players & rankings\n\n"
            "*👤 Profile & Connections*\n"
            "`/profile` — View your complete profile & stats\n"
            "`/link_psn <PSN_ID>` — Link PlayStation Network account\n"
            "`/link_xbox <Gamertag>` — Link Xbox Live account\n\n"
            "*⚙️ Utilities*\n"
            "`/menu` — Show main menu (alias for /start)\n\n"
            "*💡 Usage Examples*\n"
            "• `/challenge 10 FIFA` — Challenge someone to FIFA for $10\n"
            "• `/local 5 NBA` — Create local NBA game for $5\n"
            "• `/fund 5000` — Add ₦5,000 via bank transfer\n"
            "• `/fund_crypto 20` — Add $20 worth of USDC\n"
            "• `/withdraw 15` — Withdraw $15 USDC to your wallet\n\n"
            "*⚖️ Fee Structure*\n"
            "• Early Adopters: **3%** platform fee\n"
            "• Standard Users: **7%** platform fee\n"
            "• Minimum match stake: **$1.00 USDC**\n"
            "• Network fees: Covered by platform (on Base Sepolia)\n\n"
            "🌐 **Web App:** https://playingsidequest.fun\n"
            "📱 **Support:** Use /start to access main menu anytime"
        )

    async def _cmd_wallet(self, user, args) -> str:
        info = await self.wallet.get_balance(user["id"])
        on_chain_bal = info.get("on_chain_balance_usdc") or 0.0
        escrowed_bal = info.get("escrowed_balance_usdc", 0.0)
        available_bal = on_chain_bal - escrowed_bal
        pts  = info["play_points"]
        net  = info["network"]
        custodial = info.get("custodial_wallet") or "Not set"
        withdrawal = info.get("withdrawal_wallet") or "Not set"

        wallet_status = ""
        if custodial != "Not set":
            wallet_status += f"📥 Deposit: `{custodial[:10]}...{custodial[-4:]}`\n"
        else:
            wallet_status += f"📥 Deposit: Not set (use /create_wallet)\n"

        if withdrawal != "Not set":
            wallet_status += f"📤 Withdrawal: `{withdrawal[:10]}...{withdrawal[-4:]}`\n"
        else:
            wallet_status += f"📤 Withdrawal: Not set (use /link_wallet)\n"

        return (
            f"👛 *Your Wallet*\n\n"
            f"💵 Available: *${available_bal:.2f} USDC*\n"
            f"🔗 On-chain: ${on_chain_bal:.2f}\n"
            f"🔒 Escrowed: ${escrowed_bal:.2f}\n"
            f"🎮 $PLAY Points: *{pts:,}*\n"
            f"{wallet_status}"
            f"🌐 Network: {net}\n\n"
            f"*/create_wallet* — Set up custodial deposit wallet\n"
            f"*/link_wallet <addr>* — Set external withdrawal wallet\n"
            f"*/deposit* — Get deposit instructions\n"
            f"*/withdraw <amount>* — Cash out to withdrawal wallet\n"
            f"*/transactions* — View transaction history"
        )

    async def _cmd_deposit(self, user, args) -> str:
        # Check for Circle custodial wallet
        custodial_wallet = user.get("circle_wallet_id") or user.get("wallet_address")
        if not custodial_wallet:
            return "❌ No custodial wallet found. Use `/create_wallet` to set up your secure deposit wallet first."

        # Get Circle wallet address from DB
        profile = self.db.get_profile_by_id(user["id"])
        if profile and profile.get("linked_wallet"):  # This will be the Circle custodial address
            deposit_addr = profile["linked_wallet"]
        else:
            return "❌ Custodial wallet not properly configured. Please contact support."

        return (
            f"💰 *Deposit USDC*\n\n"
            f"Send USDC to:\n`{deposit_addr}`\n\n"
            f"Network: *Base Sepolia* (Chain 84532)\n"
            f"USDC: `0x036CbD53842c5426634e7929541eC2318f3dCF7e`\n"
            f"Minimum: *$1.00*\n"
            f"Confirms in: *~30 seconds*\n\n"
            f"⚠️ Only send USDC on Base Sepolia. Other tokens will be lost.\n"
            f"💡 Your custodial wallet is secure and controlled by sideQuest."
        )

    async def _cmd_create_wallet(self, user, args) -> str:
        """Create a Circle custodial wallet for secure deposits."""
        result = await self.wallet.create_wallet(user["id"])

        if not result["success"]:
            return f"❌ Failed to create custodial wallet: {result.get('error', 'Unknown error')}"

        wallet_addr = result["wallet"]
        return (
            f"✅ *Custodial Wallet Created!*\n\n"
            f"Your secure deposit wallet:\n`{wallet_addr}`\n\n"
            f"💡 This is a **Circle custodial wallet** — sideQuest controls it for security.\n"
            f"📥 Use `/deposit` to get deposit instructions.\n"
            f"📤 For withdrawals, link your external wallet with `/link_wallet <address>`.\n\n"
            f"Network: *Base Sepolia*\n"
            f"Type: *Custodial (Secure)*"
        )

    async def _cmd_link_wallet(self, user, args) -> str:
        if not args:
            return "Usage: `/link_wallet 0xYOUR_WITHDRAWAL_ADDRESS`\n\nThis sets your external wallet (MetaMask, Rabby, Phantom, etc.) for withdrawals only.\n\nFor deposits, use `/create_wallet` to set up your secure custodial wallet."

        import re
        addr = args[0].strip()
        if not re.match(r"^0x[0-9a-fA-F]{40}$", addr):
            return "❌ Invalid wallet address. Must be a 42-character hex address starting with 0x."

        # Store withdrawal address separately from custodial deposit wallet
        # We'll use a new field for withdrawal addresses
        result = await self.wallet.link_withdrawal_wallet(user["id"], addr)
        if not result["success"]:
            return f"❌ {result['error']}"

        return (
            f"✅ *Withdrawal Wallet Set!*\n\n"
            f"`{result['wallet']}`\n\n"
            f"💰 This address will receive your withdrawals from sideQuest.\n"
            f"📥 For deposits, use your custodial wallet created via `/create_wallet`.\n\n"
            f"Supported wallets: MetaMask, Rabby, Phantom, Coinbase Wallet, etc."
        )

    async def _cmd_withdraw(self, user, args) -> str:
        if not args:
            return "Usage: `/withdraw <amount>` e.g. `/withdraw 25`"
        try:
            amount = float(args[0])
        except ValueError:
            return "❌ Invalid amount. Example: `/withdraw 25`"
        if amount <= 0:
            return "❌ Amount must be positive."
        if amount > 100_000:
            return "❌ Maximum withdrawal is $100,000 USDC."
        result = await self.wallet.request_withdrawal(user["id"], amount)
        if not result["success"]:
            return f"❌ {result['error']}"
        return (
            f"✅ *Withdrawal Queued*\n\n"
            f"Amount: *${result['amount']:.2f} USDC*\n"
            f"To: `{result['to_address']}`\n"
            f"Network: {result['network']}\n"
            f"ETA: {result['eta']}"
        )

    async def _cmd_transactions(self, user, args) -> str:
        """Show recent Circle wallet transactions."""
        try:
            from supabase import create_client
            sb = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_ROLE_KEY"))

            # Get recent transactions for this user
            result = sb.table("circle_transactions").select("*").eq("profile_id", user["id"]).order("created_at", desc=True).limit(10).execute()

            if not result.data:
                return "📄 *Transaction History*\n\nNo transactions found.\n\n💡 Your first deposit will appear here after it's confirmed on the blockchain."

            transactions = result.data
            message = "📄 *Transaction History*\n\n"

            for tx in transactions:
                direction = "📥" if tx["type"] == "inbound" else "📤"
                status_emoji = {
                    "pending": "⏳",
                    "confirmed": "🟡",
                    "completed": "✅",
                    "failed": "❌"
                }.get(tx["status"], "❓")

                amount = tx["amount_usdc"]
                created_at = tx["created_at"][:19]  # YYYY-MM-DD HH:MM:SS

                # Truncate tx_hash for display
                tx_hash_short = tx["tx_hash"][:10] + "..." if tx["tx_hash"] else "N/A"

                message += f"{direction} {status_emoji} ${amount:.2f} USDC\n"
                message += f"   {created_at} | {tx_hash_short}\n\n"

            message += "🔍 View full details at:\nhttps://console.circle.com/wallets/dev/transactions"

            return message

        except Exception as e:
            logger.error(f"[Transactions] Failed to fetch history: {e}")
            return "❌ Unable to load transaction history. Please try again later."

    async def _cmd_challenge(self, user, args) -> str:
        return await self._create_challenge(user, args, match_type="online")

    async def _cmd_local(self, user, args) -> str:
        return await self._create_challenge(user, args, match_type="local")

    # Allowed game types for input validation
    ALLOWED_GAMES = {"EAFC", "FIFA", "NBA", "NBA2K", "COD", "MADDEN", "FORTNITE", "APEX", "VALORANT", "LOL"}

    async def _create_challenge(self, user, args, match_type) -> str:
        if len(args) < 1:
            return f"Usage: `/{('challenge' if match_type=='online' else 'local')} <amount> [game] [@opponent]`\nExample: `/challenge 10 EAFC @GamerX`"

        try:
            stake = float(args[0])
        except ValueError:
            return "❌ Invalid stake amount. Example: `/challenge 10 EAFC`"

        # Validate stake bounds
        if stake < 1.0:
            return "❌ Minimum stake is $1.00 USDC."
        if stake > 10_000:
            return "❌ Maximum stake is $10,000 USDC."
        if stake != round(stake, 2):
            return "❌ Stake amount can have at most 2 decimal places."

        # Defaults
        game = "EAFC"
        opponent_handle = None

        # Parse remaining tokens after amount: collect game tokens until a token starting with '@' (opponent) or end
        game_tokens = []
        for token in args[1:]:
            if token.startswith('@'):
                opponent_handle = token
                break
            game_tokens.append(token)

        if game_tokens:
            game_raw = "".join(game_tokens).upper()
            if game_raw not in self.ALLOWED_GAMES:
                return f"❌ Unknown game `{' '.join(game_tokens)}`. Supported: {', '.join(sorted(self.ALLOWED_GAMES))}"
            game = game_raw

        opponent_id = None
        opponent_telegram_id = None
        opponent_whatsapp = None
        if opponent_handle:
            # Try to lookup opponent by username or ID
            opponent = await self._lookup_user(opponent_handle)
            if not opponent:
                return f"❌ User *{opponent_handle}* hasn't linked their sideQuest account yet. Tell them to type /start!"
            opponent_id = opponent["id"]
            opponent_telegram_id = opponent.get("telegram_id")
            opponent_whatsapp = opponent.get("whatsapp_id")

        result = await self.matches.create_match(
            creator_id=user["id"],
            creator_whatsapp=user.get("whatsapp_number"),
            game=game,
            stake_usd=stake,
            match_type=match_type,
            opponent_id=opponent_id
        )

        if not result.get("success"):
            return f"❌ {result.get('error', 'Failed to create match')}"

        icon = "🌐" if match_type == "online" else "🏠"
        if opponent_id:
            msg = (
                f"{icon} *Challenge Sent!*\n\n"
                f"Opponent: *{opponent_handle}*\n"
                f"🎮 {result['game']} | 💵 ${result['stake_usd']:.2f}\n"
                f"🆔 Match ID: *{result['match_id']}*\n\n"
                f"Waiting for them to accept..."
            )
        else:
            msg = (
                f"{icon} *Challenge Created!*\n\n"
                f"🎮 {result['game']} | 💵 ${result['stake_usd']:.2f}\n"
                f"🆔 Match ID: *{result['match_id']}*\n\n"
                f"Share this ID with your opponent!\n"
                f"They join with: `/match {result['match_id']}`"
            )

        return {
            "success":            True,
            "text":               msg,
            "match_id":           result["match_id"],
            "stake_usd":          result["stake_usd"],
            "game":               result["game"],
            "opponent_id":        opponent_id,
            "opponent_tele_id":   opponent_telegram_id,
            "opponent_whatsapp":  opponent_whatsapp,
        }

    async def _lookup_user(self, handle: str) -> Optional[dict]:
        """Lookup user by @username (Telegram), numeric ID, or phone number (WhatsApp)."""
        from supabase import create_client
        sb = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_ROLE_KEY"))
        
        if handle.startswith("@"):
            name_part = handle[1:]
            # If it's purely digits, treat as telegram_id
            if name_part.isdigit():
                res = sb.table("profiles").select(PROFILE_SELECT).eq("telegram_id", int(name_part)).execute()
                if res.data:
                    return res.data[0]
            # Try exact username match first (case-insensitive)
            res = sb.table("profiles").select(PROFILE_SELECT).ilike("username", name_part).execute()
            if res.data:
                return res.data[0]
            # Fallback: case-insensitive display_name match
            res = sb.table("profiles").select(PROFILE_SELECT).ilike("display_name", name_part).execute()
            if res.data:
                return res.data[0]
            return None
        
        # If handle is purely digits, treat as telegram_id
        if handle.isdigit():
            res = sb.table("profiles").select(PROFILE_SELECT).eq("telegram_id", int(handle)).execute()
            if res.data:
                return res.data[0]
        
        # Try as phone number (WhatsApp)
        res = sb.table("profiles").select(PROFILE_SELECT).eq("whatsapp_number", handle).execute()
        if res.data:
            return res.data[0]
        return None

    async def _cmd_match(self, user, args) -> str:
        if not args:
            return "Usage: `/match <MATCH_ID>`"
        result = await self.matches.join_match(
            match_id=args[0].upper(),
            player2_id=user["id"],
            player2_whatsapp=user["whatsapp_number"],
        )
        if not result["success"]:
            return f"❌ {result['error']}"
        return (
            f"✅ *Match Accepted!*\n\n"
            f"🎮 {result['game']} | 💵 ${result['stake_usd']:.2f} staked\n"
            f"⏱️ You have *{result['timeout_mins']} minutes* to play and report.\n\n"
            f"After playing, submit your score:\n"
            f"`/report {args[0].upper()} <your_score>-<their_score>`\n"
            f"Example: `/report {args[0].upper()} 3-1`"
        )

    async def _cmd_report(self, user, args, proof_url: str = None) -> str:
        if len(args) < 2:
            return "Usage: `/report <MATCH_ID> <score>` e.g. `/report ABC123 3-1`"
        match_id = args[0].upper()
        score    = args[1]
        result = await self.matches.submit_report(
            match_id=match_id,
            reporter_id=user["id"],
            score=score,
            reporter_whatsapp=user["whatsapp_number"],
            proof_url=proof_url
        )
        if not result["success"]:
            return f"❌ {result['error']}"
        if result["status"] == "both_reported":
            return f"✅ Score submitted (*{score}*). Both reports in — calculating result..."
        return f"✅ Score submitted (*{score}*). Waiting for your opponent to report."

    async def _cmd_bets(self, user, args) -> str:
        from supabase import create_client
        sb = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_ROLE_KEY"))
        open_matches = sb.table("bets").select("*").eq("status", "OPEN").neq("creator_id", user["id"]).limit(10).execute().data or []
        if not open_matches:
            return "📭 No open challenges right now.\n\nCreate one with `/challenge <amount> <game>`"
        lines = ["🎯 *Open Challenges*\n"]
        for m in open_matches:
            lines.append(f"• *{m.get('short_id', m['id'][:6])}* — {m['game']} | ${float(m['stake_usd']):.2f} | `/match {m.get('short_id', m['id'][:6])}`")
        return "\n".join(lines)

    async def _cmd_active(self, user, args) -> str:
        from supabase import create_client
        sb = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_ROLE_KEY"))
        matches = (
            sb.table("bets").select("*")
            .in_("status", ["OPEN", "LOCKED", "DISPUTED"])
            .or_(f"creator_id.eq.{user['id']},opponent_id.eq.{user['id']}")
            .execute().data or []
        )
        if not matches:
            return "📭 You have no active matches.\n\nCreate one with `/challenge <amount> <game>`"
        lines = ["🎮 *Your Active Matches*\n"]
        for m in matches:
            lines.append(f"• *{m.get('short_id', m['id'][:6])}* — {m['game']} | ${float(m['stake_usd']):.2f} | {m['status']}")
        return "\n".join(lines)

    async def _cmd_points(self, user, args) -> str:
        pts = user.get("play_points", 0)
        return (
            f"🎮 *$PLAY Points*\n\n"
            f"Balance: *{pts:,} points*\n\n"
            f"Earn 10 points per $1 staked.\n"
            f"Winners earn double points!"
        )

    async def _cmd_leaderboard(self, user, args) -> str:
        from supabase import create_client
        sb = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_ROLE_KEY"))
        top = sb.table("profiles").select("display_name,play_points,whatsapp_number").order("play_points", desc=True).limit(10).execute().data or []
        if not top:
            return "🏆 Leaderboard is empty. Be the first to play!"
        lines = ["🏆 *Top Players*\n"]
        medals = ["🥇", "🥈", "🥉"] + ["🎮"] * 7
        for i, p in enumerate(top):
            name = p.get("display_name") or (f"Player ...{p['whatsapp_number'][-4:]}" if p.get('whatsapp_number') else "Anonymous")
            lines.append(f"{medals[i]} {name} — {int(p.get('play_points', 0)):,} pts")
        return "\n".join(lines)

    async def _cmd_profile(self, user, args) -> str:
        psn  = user.get("psn_id", "Not linked")
        xbox = user.get("xbox_gamertag", "Not linked")
        bal  = float(user.get("wallet_balance_usdc", 0))
        pts  = int(user.get("play_points", 0))
        early = "✅ Applied (3% forever)" if user.get("is_early_adopter") else "❌ Standard (7%)"
        
        return (
            f"👤 *Your Profile*\n\n"
            f"🆔 ID: `{user.get('id')}`\n"
            f"💵 Balance: ${bal:.2f} USDC\n"
            f"🎮 $PLAY: {pts:,} pts\n"
            f"🌟 Early Adopter: {early}\n\n"
            f"*Linked Accounts:*\n"
            f"🎮 PSN: {psn}\n"
            f"🎮 Xbox: {xbox}"
        )

    async def _cmd_link_psn(self, user, args) -> str:
        if not args:
            return "Usage: `/link_psn YOUR_PSN_ID`"
        psn_id = " ".join(args)
        from supabase import create_client
        sb = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_ROLE_KEY"))
        sb.table("profiles").update({"psn_id": psn_id}).eq("id", user["id"]).execute()
        return f"✅ PSN account linked: *{psn_id}*"

    async def _cmd_link_xbox(self, user, args) -> str:
        if not args:
            return "Usage: `/link_xbox YOUR_GAMERTAG`"
        gamertag = " ".join(args)
        from supabase import create_client
        sb = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_ROLE_KEY"))
        sb.table("profiles").update({"xbox_gamertag": gamertag}).eq("id", user["id"]).execute()
        return f"✅ Xbox account linked: *{gamertag}*"

    async def _cmd_link_email(self, user, args) -> str:
        if not args:
            return "Usage: `/link_email your@email.com`\n\nLink your email to sync with the web app."
        email = " ".join(args).lower().strip()
        if "@" not in email or "." not in email.split("@")[1]:
            return "❌ Invalid email format. Please provide a valid email."
        import re
        if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
            return "❌ Invalid email format."
        from supabase import create_client
        sb = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_ROLE_KEY"))
        existing = sb.table("profiles").select("id, telegram_id").eq("email", email).execute()
        if existing.data and existing.data[0].get("telegram_id"):
            return "❌ This email is already linked to another account."
        sb.table("profiles").update({"email": email}).eq("id", user["id"]).execute()
        return f"✅ Email linked: *{email}*\n\nUse this email to sign in on the web app and sync your account."

    async def _handle_screenshot(self, user, image_b64: str) -> str:
        match_id = user.get("pending_screenshot_match")
        import tempfile, base64, os as _os
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
            f.write(base64.b64decode(image_b64))
            path = f.name
        result = await self.matches.submit_screenshot(
            match_id=match_id,
            submitter_id=user["id"],
            image_path=path,
        )
        if result["status"] == "both_submitted":
            return "🤖 Both screenshots received. AI Mediator is reviewing — you'll be notified shortly."
        return "📸 Screenshot received. Waiting for your opponent to submit theirs."

    # ─── User Management ──────────────────────────────────────────────────────

    async def _get_or_create_user(self, identifier: str) -> Optional[dict]:
        """Get user by identifier (phone number or tg_<id>), creating profile if it doesn't exist."""
        # Use central DBLayer to handle is_early_adopter and other business rules
        if identifier.startswith("tg_"):
            return self.db.get_or_create_profile("telegram_id", identifier[3:])
        return self.db.get_or_create_profile("whatsapp_id", identifier)

    def get_user(self, platform: str, platform_id: str) -> Optional[dict]:
        """Get or create user profile by platform ID (e.g., telegram_id, whatsapp_id)."""
        return self.db.get_or_create_profile(platform, platform_id)


    async def _cmd_set_team(self, user, match_id: str, team_name: str) -> str:
        """Handle team selection for a specific match."""
        success = await self.matches.set_match_team(match_id, user["id"], team_name)
        if not success:
            return "❌ Failed to set team. Make sure the match is active."
        return f"✅ Team set: *{team_name}* for Match `{match_id}`. Waiting for both players to play and report scores."

    async def _get_telegram_id_by_profile_id(self, profile_id: str) -> Optional[int]:
        """Utility to get telegram_id from profile UUID."""
        from supabase import create_client
        sb = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_ROLE_KEY"))
        res = sb.table("profiles").select("telegram_id").eq("id", profile_id).execute()
        if res.data:
            return res.data[0].get("telegram_id")
        return None

    # ─── Proof of Play / Content Engine Methods ─────────────────────────────────

    async def create_content_session(self, host_id: str, guest_id: str = None, title: str = "",
                                     description: str = "", game_type: str = "",
                                     status: str = "scheduled") -> dict:
        """Create a match session (for tracking series)."""
        result = self.db.create_session(
            host_id=host_id, guest_id=guest_id, title=title,
            description=description, game_type=game_type, status=status
        )
        if not result:
            return {"success": False, "error": "Failed to create session"}
        return {"success": True, "session": result}

    async def create_public_challenge(self, issuer_id: str, game_type: str, stake_amount: float,
                                      target_id: str = None, message: str = "", theme: str = "") -> dict:
        """Create a public challenge that anyone can accept."""
        # Check if issuer is Top 10 for special eligibility
        is_top10 = self.db.is_top10_player(issuer_id)
        
        challenge = self.db.create_challenge(
            issuer_id=issuer_id, game_type=game_type,
            stake_amount=stake_amount, target_id=target_id,
            message=message, theme=theme
        )
        if not challenge:
            return {"success": False, "error": "Failed to create challenge"}
        
        return {
            "success": True,
            "challenge": challenge,
            "is_top10_issuer": is_top10
        }

    async def accept_public_challenge(self, challenge_id: str, bet_id: str = None) -> dict:
        """Accept a public challenge."""
        result = self.db.accept_challenge(challenge_id, bet_id)
        if not result:
            return {"success": False, "error": "Challenge not found or already processed"}
        return {"success": True, "challenge": result}

    async def create_base_market_for_match(self, bet_id: str, session_id: str = None,
                                           liquidity_usdc: float = 1000) -> dict:
        """Create a Base Markets prediction pool for a Top 10 player's public match."""
        # Get bet details
        bet = self.db.get_bet(bet_id)
        if not bet:
            return {"success": False, "error": "Bet not found"}
        
        # Check if creator is Top 10
        if not self.db.is_top10_player(bet["creator_id"]):
            return {"success": False, "error": "Only Top 10 players qualify for auto-markets"}
        
        # Check if bet is public
        if not bet.get("is_public"):
            return {"success": False, "error": "Only public matches qualify for auto-markets"}
        
        # Get player names
        creator = self.db.get_profile_by_id(bet["creator_id"])
        opponent = None
        if bet.get("opponent_id"):
            opponent = self.db.get_profile_by_id(bet["opponent_id"])
        
        creator_name = creator.get("display_name", "Unknown") if creator else "Unknown"
        opponent_name = opponent.get("display_name", "TBD") if opponent else "TBD"
        
        # Create market
        question = f"Who will win: {creator_name} vs {opponent_name}?"
        outcomes = [
            {"name": creator_name, "price": 1.85},
            {"name": opponent_name if opponent else "Opponent", "price": 2.10}
        ]
        
        market = self.db.create_base_market(
            bet_id=bet_id,
            session_id=session_id,
            market_type="match_winner",
            question=question,
            outcomes=outcomes,
            liquidity_usdc=liquidity_usdc,
            spread_fee_pct=0.05  # 5% spread fee
        )
        
        if not market:
            return {"success": False, "error": "Failed to create base market"}
        
        return {
            "success": True,
            "market": market,
            "question": question
        }

    async def create_proof_of_play_receipt(self, bet_id: str, session_id: str = None,
                                          tx_hash: str = "", verification_data: dict = None) -> dict:
        """Create an immutable proof of play receipt linking on-chain tx to session."""
        receipt = self.db.create_proof_of_play(
            bet_id=bet_id, session_id=session_id,
            tx_hash=tx_hash, verification_data=verification_data
        )
        if not receipt:
            return {"success": False, "error": "Failed to create proof of play receipt"}
        return {"success": True, "receipt": receipt}

    async def get_top10_players(self) -> dict:
        """Get Top 10 players eligible for Base Markets."""
        players = self.db.get_top10_qualified(limit=10)
        return {"success": True, "players": players}

    async def get_player_public_stats(self, profile_id: str) -> dict:
        """Get public W-D-L stats for a player."""
        profile = self.db.get_profile_by_id(profile_id)
        if not profile:
            return {"success": False, "error": "Player not found"}
        
        return {
            "success": True,
            "profile": {
                "id": profile["id"],
                "display_name": profile.get("display_name"),
                "public_wins": profile.get("public_wins", 0),
                "public_losses": profile.get("public_losses", 0),
                "is_content_creator": profile.get("is_content_creator", False),
                "is_verified": profile.get("is_verified", False),
                "creator_badges": profile.get("creator_badges", [])
            }
        }

    async def update_profile_badges(self, profile_id: str, badges: list) -> dict:
        """Update creator badges for a profile."""
        # Clear existing badges
        self.db.supabase.table("profiles").update({
            "creator_badges": badges
        }).eq("id", profile_id).execute()
        return {"success": True, "badges": badges}

# ─── Singleton ────────────────────────────────────────────────────────────────

_controller: Optional[ClawController] = None

def get_controller() -> ClawController:
    global _controller
    if _controller is None:
        _controller = ClawController()
    return _controller
