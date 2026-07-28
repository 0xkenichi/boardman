"""
court_layer.py
───────────────────────────────────────────────────────────────────────────────
Dispute resolution and score consensus layer.

Handles:
  1. Checking if both player score reports agree → auto-resolve
  2. Detecting conflict → triggering AI mediator
  3. Processing AI mediator result → on-chain resolution or admin escalation
  4. Notifying both players of dispute outcome via WhatsApp/Telegram
"""

import os
import re
import logging
import asyncio
from typing import Optional
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

MATCH_TIMEOUT_ONLINE_MINS  = int(os.getenv("MATCH_TIMEOUT_ONLINE",  "120"))
MATCH_TIMEOUT_LOCAL_MINS   = int(os.getenv("MATCH_TIMEOUT_LOCAL",    "60"))
ADMIN_WHATSAPP             = os.getenv("ADMIN_WHATSAPP_NUMBER", "")


class CourtLayer:
    """Arbitrates match outcomes. Called by BettingEngine/MatchManager."""

    def __init__(self):
        from score_verifier import get_score_verifier
        from evolution_bridge import EvolutionBridge
        self.verifier = get_score_verifier()
        self.bridge   = EvolutionBridge()

    # ─── Score Consensus ─────────────────────────────────────────────────────
    async def process_reports(
        self,
        match_id: str,
        player1_id: str,
        player2_id: str,
        player1_report: str,
        player2_report: str,
        stake_usd: float,
        player1_wallet: Optional[str] = None,
        player2_wallet: Optional[str] = None,
        player1_whatsapp: Optional[str] = None,
        player2_whatsapp: Optional[str] = None,
        player1_tele_id: Optional[int] = None,
        player2_tele_id: Optional[int] = None,
    ) -> dict:
        p1_norm = self._normalise_score(player1_report)
        p2_norm = self._normalise_score(player2_report)
        logger.info(f"[Court] Match {match_id}: P1 reports {p1_norm}, P2 reports {p2_norm}")

        # Scores agree → auto-resolve
        if p1_norm == p2_norm and p1_norm is not None:
            winner_id, winner_wallet, loser_id = self._determine_winner(
                p1_norm, player1_id, player1_wallet, player2_id, player2_wallet
            )
            if winner_id is None:
                return await self._handle_draw(match_id, player1_id, player2_id, stake_usd,
                                                player1_whatsapp, player2_whatsapp)
            result = await self._execute_resolution(
                match_id, winner_id, winner_wallet, loser_id, stake_usd, p1_norm
            )
            await self._notify_resolution(
                winner_id=winner_id, loser_id=loser_id,
                winner_whatsapp=player1_whatsapp if winner_id == player1_id else player2_whatsapp,
                loser_whatsapp=player2_whatsapp if winner_id == player1_id else player1_whatsapp,
                winner_tele_id=player1_tele_id if winner_id == player1_id else player2_tele_id,
                loser_tele_id=player2_tele_id if winner_id == player1_id else player1_tele_id,
                score=p1_norm, payout=result.get("payout_usdc", 0),
                winner_points=result.get("winner_points", 0),
                loser_points=result.get("loser_points", 0),
                match_id=match_id,
            )
            return {"action": "auto_resolved", "winner": winner_id, **result}

        # Scores conflict → dispute with AI
        logger.info(f"[Court] Match {match_id}: Score conflict. Entering dispute flow.")
        from betting_engine_onchain import dispute_match_onchain
        await dispute_match_onchain(match_id)
        return {"action": "dispute_started"}

    async def resolve_with_screenshots(
        self, match_id: str, player1_id: str, player2_id: str,
        screenshot_p1: str, screenshot_p2: str,
        reported_p1: str, reported_p2: str,
        stake_usd: float,
        player1_wallet: Optional[str] = None,
        player2_wallet: Optional[str] = None,
        player1_whatsapp: Optional[str] = None,
        player2_whatsapp: Optional[str] = None,
        player1_tele_id: Optional[int] = None,
        player2_tele_id: Optional[int] = None,
    ) -> dict:
        verdict = await self.verifier.verify_from_screenshots(
            screenshot_p1, screenshot_p2, reported_p1, reported_p2
        )
        if verdict["valid"] and verdict["winner"] in ("player1", "player2", "draw"):
            if verdict["winner"] == "draw":
                return await self._handle_draw(match_id, player1_id, player2_id, stake_usd,
                                                player1_whatsapp, player2_whatsapp)
            winner_id     = player1_id if verdict["winner"] == "player1" else player2_id
            winner_wallet = player1_wallet if verdict["winner"] == "player1" else player2_wallet
            loser_id      = player2_id if verdict["winner"] == "player1" else player1_id
            result = await self._execute_resolution(
                match_id, winner_id, winner_wallet, loser_id, stake_usd, verdict["verified_score"]
            )
            await self._notify_ai_resolution(
                winner_whatsapp=player1_whatsapp if winner_id == player1_id else player2_whatsapp,
                loser_whatsapp=player2_whatsapp if winner_id == player1_id else player1_whatsapp,
                winner_tele_id=player1_tele_id if winner_id == player1_id else player2_tele_id,
                loser_tele_id=player2_tele_id if winner_id == player1_id else player1_tele_id,
                score=verdict["verified_score"], reason=verdict["reason"],
                payout=result.get("payout_usdc", 0),
                winner_points=result.get("winner_points", 0),
                loser_points=result.get("loser_points", 0),
                match_id=match_id,
            )
            return {"action": "ai_resolved", "winner": winner_id, **result}
        # Unverifiable → escalate
        await self._escalate_to_admin(match_id, verdict, player1_whatsapp, player2_whatsapp)
        return {"action": "escalated"}

    # ─── Internal Helpers ───────────────────────────────────────────────────────
    @staticmethod
    def _normalise_score(report: str) -> Optional[str]:
        if not report:
            return None
        cleaned = re.sub(r'[^0-9\-]', '-', report.strip())
        cleaned = re.sub(r'-+', '-', cleaned).strip('-')
        parts = cleaned.split('-')
        if len(parts) == 2:
            try:
                a, b = int(parts[0]), int(parts[1])
                return f"{a}-{b}"
            except ValueError:
                pass
        return None

    @staticmethod
    def _determine_winner(score: str, p1_id, p1_wallet, p2_id, p2_wallet):
        try:
            a, b = map(int, score.split('-'))
            if a > b:
                return p1_id, p1_wallet, p2_id
            elif b > a:
                return p2_id, p2_wallet, p1_id
            else:
                return None, None, None
        except Exception:
            return None, None, None

    async def _execute_resolution(self, match_id, winner_id, winner_wallet, loser_id, stake_usd, score):
        from betting_engine_onchain import resolve_match_and_payout
        return await resolve_match_and_payout(
            match_id=match_id, winner_user_id=winner_id,
            winner_wallet=winner_wallet, loser_user_id=loser_id,
            stake_usd=stake_usd,
        )

    async def _handle_draw(self, match_id, p1_id, p2_id, stake_usd, p1_wa, p2_wa):
        from betting_engine_onchain import cancel_match_and_refund
        result = await cancel_match_and_refund(match_id, p1_id, p2_id, stake_usd)
        for wa in [p1_wa, p2_wa]:
            if wa:
                await self.bridge.send_message(wa,
                    f"🤝 *Match Drawn!*\n\nMatch {match_id} ended in a draw.\n"
                    f"Your ${stake_usd:.2f} stake has been refunded.")
        return {"action": "draw_refunded", **result}

    async def _escalate_to_admin(self, match_id, verdict, p1_wa, p2_wa):
        frontend_url = os.getenv("FRONTEND_URL", "https://sidequest.vercel.app")
        dispute_link = f"{frontend_url}/admin/disputes?match_id={match_id}"
        msg = (f"⚠️ *Dispute Escalated — Match {match_id}*\n\n"
               f"AI could not determine winner.\n"
               f"Reason: {verdict['reason']}\n\n"
               f"P1 report: {verdict.get('p1_result', {})}\n"
               f"P2 report: {verdict.get('p2_result', {})}\n\n"
               f"🔗 *Resolve here:* {dispute_link}")
        if ADMIN_WHATSAPP:
            await self.bridge.send_message(ADMIN_WHATSAPP, msg)
        try:
            from api import ADMIN_NUMBERS
            for admin_id in ADMIN_NUMBERS:
                try:
                    from main import bot
                    await bot.send_message(int(admin_id), msg, parse_mode="Markdown")
                except Exception:
                    pass
        except Exception:
            pass
        for wa in [p1_wa, p2_wa]:
            if wa:
                await self.bridge.send_message(wa,
                    f"⚠️ *Dispute Under Review*\n\n"
                    f"Our AI could not determine the winner from the screenshots.\n"
                    f"An admin is reviewing match *{match_id}*.\n"
                    f"You'll be notified within 24 hours.")

    # ─── Notifications ─────────────────────────────────────────────────────────
    async def _notify_resolution(
        self, winner_id, loser_id,
        winner_whatsapp, loser_whatsapp,
        winner_tele_id=None, loser_tele_id=None,
        score=None, payout=0, winner_points=0, loser_points=0, match_id=None
    ):
        from victory_card import VictoryCardGenerator
        from supabase_client import get_supabase
        import os
        winner_team = "Champion"
        loser_team = "Opponent"
        winner_username = ""
        loser_username = ""
        try:
            sb = get_supabase()
            wp = sb.table("profiles").select("display_name").eq("id", winner_id).single().execute().data
            lp = sb.table("profiles").select("display_name").eq("id", loser_id).single().execute().data
            winner_username = wp.get("display_name", str(winner_id)[:8]) if wp else str(winner_id)[:8]
            loser_username = lp.get("display_name", str(loser_id)[:8]) if lp else str(loser_id)[:8]
        except Exception as e:
            logger.error(f"[Court] Failed to fetch profile names: {e}")
        try:
            generator = VictoryCardGenerator()
            card_bytes = generator.generate_card({
                "match_id": match_id or "SQ-UNK",
                "winner_username": winner_username,
                "winner_team": winner_team,
                "loser_username": loser_username,
                "loser_team": loser_team,
                "score": score or "-", "usdc_won": payout,
                "timestamp": datetime.now(timezone.utc),
                "match_hash": match_id or ""
            })
            if winner_tele_id:
                await self._send_telegram_photo(winner_tele_id, card_bytes,
                    caption=f"🏆 *Victory Confirmed!*\n\nScore: *{score}*\n+${payout:.2f} USDC")
            if loser_tele_id:
                await self._send_telegram_photo(loser_tele_id, card_bytes,
                    caption=f"😔 *Match Ended*\n\nScore: *{score}*\n+{loser_points} PLAY points")
            if winner_whatsapp:
                await self.bridge.send_message(winner_whatsapp,
                    f"🏆 *You Win!*\n\nScore: *{score}*\n💵 +${payout:.2f} USDC\n🎮 +{winner_points} PLAY pts")
        except Exception as e:
            logger.error(f"[Court] Failed to generate/send victory card: {e}")
            if winner_whatsapp:
                await self.bridge.send_message(winner_whatsapp,
                    f"🏆 *You Win!*\n\nScore: *{score}*\n💵 +${payout:.2f} USDC\n🎮 +{winner_points} PLAY pts")
        if loser_whatsapp:
            await self.bridge.send_message(loser_whatsapp,
                f"😔 *Match Lost*\n\nScore: *{score}*\n🎮 +{loser_points} PLAY pts\n\nBetter luck next time!")

    async def _notify_ai_resolution(
        self, winner_whatsapp, loser_whatsapp, winner_tele_id, loser_tele_id,
        score, reason, payout, winner_points, loser_points, match_id
    ):
        from victory_card import VictoryCardGenerator
        import os
        try:
            generator = VictoryCardGenerator()
            card_bytes = generator.generate_card({
                "match_id": match_id or "SQ-UNK",
                "winner_username": "Verified", "winner_team": "AI-Verified",
                "loser_username": "Opponent", "loser_team": "Disputed",
                "score": score or "-", "usdc_won": payout,
                "timestamp": datetime.now(timezone.utc), "match_hash": match_id or ""
            })
            if winner_tele_id:
                await self._send_telegram_photo(winner_tele_id, card_bytes,
                    caption=f"🤖 *AI Referee: You Win!*\n\nScore: *{score}*\n+${payout:.2f} USDC\n\n_{reason}_")
            if loser_tele_id:
                await self._send_telegram_photo(loser_tele_id, card_bytes,
                    caption=f"🤖 *AI Referee: Match Lost*\n\nScore: *{score}*\n\n_{reason}_")
            if winner_whatsapp:
                await self.bridge.send_message(winner_whatsapp,
                    f"🤖 *AI Mediator Verdict: You Win!*\n\nVerified score: *{score}*\n"
                    f"💵 +${payout:.2f} USDC\n🎮 +{winner_points} PLAY pts\n\n_{reason}_")
            if loser_whatsapp:
                await self.bridge.send_message(loser_whatsapp,
                    f"🤖 *AI Mediator Verdict: Match Lost*\n\nVerified score: *{score}*\n"
                    f"🎮 +{loser_points} PLAY pts\n\n_{reason}_")
        except Exception as e:
            logger.error(f"[Court] AI resolution card failed: {e}")
            if winner_whatsapp:
                await self.bridge.send_message(winner_whatsapp,
                    f"🤖 *AI Mediator Verdict: You Win!*\n\nVerified score: *{score}*\n💵 +${payout:.2f}")
            if loser_whatsapp:
                await self.bridge.send_message(loser_whatsapp,
                    f"🤖 *AI Mediator Verdict: Match Lost*\n\nVerified score: *{score}*")

    async def _send_telegram_photo(self, chat_id: int, photo_bytes: bytes, caption: str):
        try:
            from main import bot
            from io import BytesIO
            await bot.send_photo(chat_id=chat_id, photo=BytesIO(photo_bytes),
                caption=caption, parse_mode="Markdown")
        except Exception as e:
            logger.error(f"[Court] Failed to send photo to {chat_id}: {e}")

    async def _send_telegram(self, chat_id: int, text: str):
        try:
            from main import bot
            await bot.send_message(chat_id, text, parse_mode="Markdown")
        except Exception as e:
            logger.error(f"[Court] Failed to send Telegram message to {chat_id}: {e}")


# ─── Singleton Accessor ───────────────────────────────────────────────────────
_court_layer_instance = None

def get_court_layer() -> CourtLayer:
    """Global singleton accessor for the CourtLayer instance."""
    global _court_layer_instance
    if _court_layer_instance is None:
        _court_layer_instance = CourtLayer()
    return _court_layer_instance
