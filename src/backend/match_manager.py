"""
match_manager.py
───────────────────────────────────────────────────────────────────────────────
Match lifecycle management.

Handles:
  - Match creation and validation
  - Timer tracking (online: 120 min, local: 60 min)
  - Auto-cancellation of expired open/locked matches
  - Score report collection
  - Routing to CourtLayer for resolution
  - Screenshot collection for disputed matches
"""

import os
import uuid
import logging
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any
from functools import wraps

from supabase import create_client

from bot.keyboards import ALLOWED_TEAMS
from db_layer_blockchain import debit_wallet, get_wallet_balance, credit_wallet

logger = logging.getLogger(__name__)

# ─── Constants ──────────────────────────────────────────────────────────────────

MATCH_TIMEOUT_ONLINE_MINS = 120
MATCH_TIMEOUT_LOCAL_MINS = 60
OPEN_MATCH_EXPIRY_MINS = 1440  # 24 hours
TIMEOUT_CHECK_INTERVAL = 60  # seconds

PROFILE_SELECT = """
    id, display_name, telegram_id, whatsapp_id, google_id, psn_id, xbox_id,
    email, is_public_available,
    balance, is_whitelisted,
    wallet_address, linked_wallet, circle_wallet_id,
    play_points, total_wins, total_losses,
    location_city, location_visible, created_at, updated_at,
    discovery_radius_km, lifecycle_stage, category_affinity_vector,
    is_early_adopter, is_verified, is_content_creator, creator_badges
"""


class MatchManager:
    """
    Manages match lifecycle: creation, joining, scoring, dispute resolution, and expiry.

    Attributes:
        court: CourtLayer instance for dispute resolution.
        bridge: EvolutionBridge instance for WhatsApp notifications.
    """

    def __init__(self):
        from court_layer import CourtLayer
        from evolution_bridge import EvolutionBridge

        self.court = CourtLayer()
        self.bridge = EvolutionBridge()

    # ─── Creation ────────────────────────────────────────────────────────────────

    async def create_match(
        self,
        creator_id: str,
        game: str,
        stake_usd: float,
        match_type: str = "online",
        is_public: bool = False,
        challenge_type: str = "private",
        session_id: str = None,
        **kwargs,
    ) -> dict:
        """Create a new match bet between two players."""
        # Validate balance
        balance = await get_wallet_balance(creator_id)
        if balance < stake_usd:
            return {
                "success": False,
                "error": "Insufficient balance. You have ${:.2f}, need ${:.2f}.".format(balance, stake_usd),
            }

        # Validate stake
        if stake_usd < 1.0:
            return {"success": False, "error": "Minimum stake is $1.00 USDC."}
        if stake_usd > 10_000:
            return {"success": False, "error": "Maximum stake is $10,000 USDC."}

        match_id = str(uuid.uuid4())[:8].upper()  # Short friendly ID
        full_match_id = str(uuid.uuid4())          # Full UUID for on-chain

        timeout_mins = MATCH_TIMEOUT_ONLINE_MINS if match_type == "online" else MATCH_TIMEOUT_LOCAL_MINS

        # Debit wallet
        success = await debit_wallet(creator_id, stake_usd)
        if not success:
            return {"success": False, "error": "Failed to debit wallet. Please try again."}

        # Create DB record with new fields
        sb = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_ROLE_KEY"))
        record = {
            "id": full_match_id,
            "short_id": match_id,
            "creator_id": creator_id,
            "amount": stake_usd,
            "stake_usd": stake_usd,
            "game_type": game,
            "status": "OPEN",
            "match_type": match_type,
            "challenge_type": challenge_type,
            "is_public": bool(is_public),
            "session_id": session_id,
            "timeout_minutes": timeout_mins,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        sb.table("bets").insert(record).execute()

        logger.info("Match %s created by %s: $%s %s (public=%s, type=%s)",
                     match_id, creator_id, stake_usd, game, is_public, challenge_type)

        return {
            "success": True,
            "match_id": match_id,
            "full_match_id": full_match_id,
            "game": game,
            "stake_usd": stake_usd,
            "match_type": match_type,
            "timeout_mins": timeout_mins,
            "opponent_id": None,
            "is_public": is_public,
            "challenge_type": challenge_type,
        }

    # ─── Joining ──────────────────────────────────────────────────────────────

    async def join_match(
        self,
        match_id: str,
        player2_id: str,
        player2_whatsapp: str,
    ) -> dict:
        """Player2 joins an open match."""
        sb = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_ROLE_KEY"))

        # Fetch match
        result = sb.table("bets").select("*").or_(
            f"short_id.eq.{match_id},id.eq.{match_id}"
        ).single().execute()

        if not result.data:
            return {"success": False, "error": "Match {} not found.".format(match_id)}

        match = result.data

        if match["status"] != "OPEN":
            return {"success": False, "error": "Match {} is no longer open ({}).".format(match_id, match['status'])}

        if match["creator_id"] == player2_id:
            return {"success": False, "error": "You can't join your own challenge."}

        stake_usd = float(match["stake_usd"])
        balance = await get_wallet_balance(player2_id)
        if balance < stake_usd:
            return {
                "success": False,
                "error": "Insufficient balance. You have ${:.2f}, need ${:.2f}.".format(balance, stake_usd),
            }

        # Debit player2
        success = await debit_wallet(player2_id, stake_usd)
        if not success:
            return {"success": False, "error": "Failed to debit wallet."}

        # Atomic status update — only succeeds if status is still OPEN (race guard)
        update_result = sb.table("bets").update({
            "opponent_id": player2_id,
            "status": "LOCKED",
            "locked_at": datetime.now(timezone.utc).isoformat(),
        }).eq("id", match["id"]).eq("status", "OPEN").execute()

        if not update_result.data:
            # Race condition: someone else joined first — refund player2
            await credit_wallet(player2_id, stake_usd, f"refund_race_{match_id}", "race_condition_refund")
            return {"success": False, "error": "Match was just taken by another player. Your funds have been refunded."}

        # Lock stakes in escrow (record in DB for balance display)
        try:
            from escrow_manager import EscrowManager
            from db_layer import DBLayer
            db = DBLayer()
            escrow_mgr = EscrowManager(db)

            # Lock creator's stake in escrow
            creator_result = await escrow_mgr.lock_user_stake(match["creator_id"], match["id"], stake_usd)
            if not creator_result["success"]:
                logger.error("Failed to escrow creator stake: %s", creator_result['error'])

            # Lock opponent stake in escrow
            opponent_result = await escrow_mgr.lock_user_stake(player2_id, match["id"], stake_usd)
            if not opponent_result["success"]:
                logger.error("Failed to escrow opponent stake: %s", opponent_result['error'])

        except Exception as e:
            logger.error("Escrow locking failed for match %s: %s", match_id, e)

        logger.info("Match %s joined by %s", match_id, player2_id)

        return {
            "success": True,
            "match_id": match_id,
            "game": match["game"],
            "stake_usd": stake_usd,
            "timeout_mins": match["timeout_minutes"],
        }

    # ─── Score Reporting ──────────────────────────────────────────────────────

    async def submit_report(
        self,
        match_id: str,
        reporter_id: str,
        score: str,
        reporter_whatsapp: Optional[str] = None,
    ) -> dict:
        """Record a score report from a player. Triggers resolution if both have reported."""
        sb = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_ROLE_KEY"))

        result = sb.table("bets").select("*").or_(
            f"short_id.eq.{match_id},id.eq.{match_id}"
        ).single().execute()

        if not result.data:
            return {"success": False, "error": "Match {} not found.".format(match_id)}

        match = result.data
        if match["status"] not in ("LOCKED", "DISPUTED"):
            return {"success": False, "error": "Match {} is not in progress ({}).".format(match_id, match['status'])}

        is_creator = match["creator_id"] == reporter_id
        is_opponent = match.get("opponent_id") == reporter_id

        if not is_creator and not is_opponent:
            return {"success": False, "error": "You are not a participant in this match."}

        # Save report
        field = "creator_report" if is_creator else "opponent_report"
        sb.table("bets").update({field: score}).eq("id", match["id"]).execute()

        logger.info("Match %s: %s reports %s", match_id, "creator" if is_creator else "opponent", score)

        # Check if both have reported
        updated = sb.table("bets").select("*").eq("id", match["id"]).single().execute().data
        creator_report = updated.get("creator_report")
        opponent_report = updated.get("opponent_report")

        if creator_report and opponent_report:
            # Both reported — route to court
            asyncio.create_task(self._process_both_reports(updated, sb))
            return {
                "success": True,
                "status": "both_reported",
                "message": "Both scores received. Processing result...",
            }

        return {
            "success": True,
            "status": "waiting",
            "message": "Score recorded. Waiting for opponent to report.",
        }

    async def submit_screenshot(
        self,
        match_id: str,
        submitter_id: str,
        image_path: str,
    ) -> dict:
        """Record a screenshot submission for a disputed match."""
        sb = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_ROLE_KEY"))
        result = sb.table("bets").select("*").or_(
            f"short_id.eq.{match_id},id.eq.{match_id}"
        ).single().execute()

        if not result.data:
            return {"success": False, "error": "Match not found."}

        match = result.data
        is_creator = match["creator_id"] == submitter_id
        field = "creator_screenshot" if is_creator else "opponent_screenshot"

        sb.table("bets").update({field: image_path}).eq("id", match["id"]).execute()

        # Check if both screenshots submitted
        updated = sb.table("bets").select("*").eq("id", match["id"]).single().execute().data
        if updated.get("creator_screenshot") and updated.get("opponent_screenshot"):
            asyncio.create_task(self._process_screenshots(updated))
            return {"success": True, "status": "both_submitted", "message": "AI Mediator is reviewing screenshots..."}

        return {"success": True, "status": "waiting", "message": "Screenshot received. Waiting for opponent."}

    # ─── Internal Processing ──────────────────────────────────────────────────

    async def _process_both_reports(self, match: dict, sb):
        """Route to court layer once both players have reported."""
        try:
            # Fetch user details
            creator = sb.table("profiles").select(PROFILE_SELECT).eq("id", match["creator_id"]).single().execute().data
            opponent = sb.table("profiles").select(PROFILE_SELECT).eq("id", match["opponent_id"]).single().execute().data

            await self.court.process_reports(
                match_id=match["id"],
                player1_id=match["creator_id"],
                player2_id=match["opponent_id"],
                player1_report=match["creator_report"],
                player2_report=match["opponent_report"],
                stake_usd=float(match["stake_usd"]),
                player1_wallet=creator.get("linked_wallet"),
                player2_wallet=opponent.get("linked_wallet"),
                player1_whatsapp=creator.get("whatsapp_number"),
                player2_whatsapp=opponent.get("whatsapp_number"),
                player1_tele_id=creator.get("telegram_id"),
                player2_tele_id=opponent.get("telegram_id"),
            )
        except Exception as e:
            logger.error("[MatchManager] Failed to process reports for match %s: %s", match['id'], e, exc_info=True)

    async def _process_screenshots(self, match: dict):
        """Route to AI mediator once both screenshots are submitted."""
        try:
            sb = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_ROLE_KEY"))
            creator = sb.table("profiles").select(PROFILE_SELECT).eq("id", match["creator_id"]).single().execute().data
            opponent = sb.table("profiles").select(PROFILE_SELECT).eq("id", match["opponent_id"]).single().execute().data

            await self.court.resolve_with_screenshots(
                match_id=match["id"],
                player1_id=match["creator_id"],
                player2_id=match["opponent_id"],
                screenshot_p1=match["creator_screenshot"],
                screenshot_p2=match["opponent_screenshot"],
                reported_p1=match.get("creator_report", ""),
                reported_p2=match.get("opponent_report", ""),
                stake_usd=float(match["stake_usd"]),
                player1_wallet=creator.get("linked_wallet"),
                player2_wallet=opponent.get("linked_wallet"),
                player1_whatsapp=creator.get("whatsapp_number"),
                player2_whatsapp=opponent.get("whatsapp_number"),
                player1_tele_id=creator.get("telegram_id"),
                player2_tele_id=opponent.get("telegram_id"),
            )
        except Exception as e:
            logger.error("[MatchManager] Screenshot processing failed for match %s: %s", match['id'], e, exc_info=True)

    # ─── Timeout Loop ─────────────────────────────────────────────────────────

    async def _timeout_loop(self):
        """Periodically cancels expired matches."""
        while True:
            try:
                await self._cancel_expired_matches()
            except Exception as e:
                logger.error("[MatchManager] Timeout loop error: %s", e)
            await asyncio.sleep(TIMEOUT_CHECK_INTERVAL)

    async def _cancel_expired_matches(self):
        sb = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_ROLE_KEY"))
        now = datetime.now(timezone.utc)

        # Find expired OPEN matches (no opponent joined in 24h)
        open_cutoff = (now - timedelta(minutes=OPEN_MATCH_EXPIRY_MINS)).isoformat()
        open_expired = sb.table("bets").select("*").eq("status", "OPEN").lt("created_at", open_cutoff).execute().data or []

        for match in open_expired:
            logger.info("[MatchManager] Cancelling expired open match %s", match['id'])
            await cancel_match_and_refund(match["id"], match["creator_id"], None, float(match["stake_usd"]))
            creator = sb.table("profiles").select("whatsapp_number").eq("id", match["creator_id"]).single().execute().data
            if creator and creator.get("whatsapp_number"):
                await self.bridge.send_message(
                    creator["whatsapp_number"],
                    "⏰ *Challenge Expired*\n\nNo one joined match *{}* within 24 hours.\n"
                    "Your ${:.2f} has been refunded.".format(match.get('short_id', match['id']), float(match['stake_usd']))
                )

        # Find expired LOCKED matches (game not reported in time)
        locked_expired = sb.table("bets").select("*").eq("status", "LOCKED").execute().data or []
        for match in locked_expired:
            if not match.get("locked_at"):
                continue
            locked_at = datetime.fromisoformat(match["locked_at"].replace("Z", "+00:00"))
            timeout_mins = int(match.get("timeout_minutes", MATCH_TIMEOUT_ONLINE_MINS))
            if (now - locked_at) > timedelta(minutes=timeout_mins):
                logger.info("[MatchManager] Cancelling timed-out locked match %s", match['id'])
                await cancel_match_and_refund(
                    match["id"], match["creator_id"], match.get("opponent_id"), float(match["stake_usd"])
                )
                for uid in [match["creator_id"], match.get("opponent_id")]:
                    if uid:
                        profile = sb.table("profiles").select("whatsapp_number").eq("id", uid).single().execute().data
                        if profile and profile.get("whatsapp_number"):
                            await self.bridge.send_message(
                                profile["whatsapp_number"],
                                "⏰ *Match Timed Out*\n\nMatch *{}* exceeded the {} minute time limit.\n"
                                "Your stake has been refunded.".format(match.get('short_id', match['id']), timeout_mins)
                            )

    async def get_match(self, match_id: str) -> Optional[dict]:
        """Fetch match record by ID."""
        sb = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_ROLE_KEY"))
        res = sb.table("bets").select("*").or_(f"id.eq.{match_id},short_id.eq.{match_id}").execute()
        return res.data[0] if res.data else None

    async def set_match_team(self, match_id: str, player_id: str, team_name: str) -> bool:
        """Update match record with player's team selection."""
        if team_name not in ALLOWED_TEAMS:
            logger.warning("Invalid team '%s' attempted by user %s for match %s", team_name, player_id, match_id)
            return False

        sb = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_ROLE_KEY"))
        match = await self.get_match(match_id)
        if not match:
            return False

        update_data = {}
        if str(match["creator_id"]) == str(player_id):
            update_data["team_p1"] = team_name
        elif str(match["opponent_id"]) == str(player_id):
            update_data["team_p2"] = team_name
        else:
            return False

        sb.table("bets").update(update_data).eq("id", match["id"]).execute()
        return True


# ─── Singleton ────────────────────────────────────────────────────────────────

_manager: Optional[MatchManager] = None


def get_match_manager() -> MatchManager:
    global _manager
    if _manager is None:
        _manager = MatchManager()
    return _manager