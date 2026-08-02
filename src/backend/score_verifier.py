"""
score_verifier.py
────────────────────────────────────────────────────────────────────────────────
AI Mediator — multimodal vision layer that extracts final scores from
player-submitted game screenshots and resolves disputed matches.

Supports:
  - OpenAI GPT-4o Vision (primary)
  - Ollama llama3.2-vision (local fallback)

Flow:
  1. Both players submit screenshots after reporting conflicting scores.
  2. score_verifier extracts the score from each screenshot independently.
  3. If both screenshots agree → auto-resolve.
  4. If they disagree or are unreadable → escalate to admin.
"""

import os
import re
import base64
import logging
import asyncio
from dataclasses import dataclass
from typing import Optional
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import httpx

logger = logging.getLogger(__name__)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
# Optional gateway (e.g. OpenRouter / OpenGateway). Empty = api.openai.com
OPENAI_BASE_URL = (os.getenv("OPENAI_BASE_URL") or os.getenv("OPENAI_API_BASE") or "").rstrip("/")
OPENAI_VISION_MODEL = os.getenv("OPENAI_VISION_MODEL") or os.getenv("OPENAI_MODEL") or "gpt-4o"
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL = (os.getenv("OPENROUTER_BASE_URL") or "https://openrouter.ai/api/v1").rstrip("/")
OPENROUTER_VISION_MODEL = os.getenv(
    "OPENROUTER_VISION_MODEL", "openai/gpt-4o-mini"
)
LIGHTNING_API_KEY = os.getenv("LIGHTNING_API_KEY", "")
LIGHTNING_BASE_URL = (os.getenv("LIGHTNING_BASE_URL") or "https://lightning.ai/api/v1").rstrip("/")
LIGHTNING_VISION_MODEL = os.getenv("LIGHTNING_VISION_MODEL", "openai/gpt-5")
GEMINI_API_KEY = os.getenv("Google_AI_Studio", "") or os.getenv("GEMINI_API_KEY", "")
OLLAMA_URL     = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL   = os.getenv("OLLAMA_MODEL", "llama3.2:11b-vision-preview")

# NVIDIA NIM API (free vision at build.nvidia.com) — accept common env aliases
NIM_API_KEY = (
    os.getenv("NIM_API_KEY", "")
    or os.getenv("NVIDIA_NIM_KEY", "")
    or os.getenv("NVIDIA_API_KEY", "")
)
NIM_BASE_URL = os.getenv("NIM_BASE_URL", "https://integrate.api.nvidia.com")
NIM_VISION_MODEL = os.getenv(
    "NIM_VISION_MODEL", "meta/llama-3.2-11b-vision-instruct"
)

# Support for Google Cloud Vision (OCR)
GOOGLE_VISION_CREDENTIALS = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "")


def _looks_like_openai_key(key: str) -> bool:
    """Real OpenAI keys are sk-…; ogw_live_ etc. are other gateways."""
    k = (key or "").strip()
    return k.startswith("sk-") and not k.startswith("sk-or-")


def _default_provider() -> str:
    """Pick a provider that is actually configured for vision.

    Prefer NVIDIA NIM when present — OPENAI_API_KEY in this project is often
    a non-OpenAI gateway token (ogw_live_…) which 401s on api.openai.com.
    """
    forced = (os.getenv("AI_PROVIDER") or "").strip().lower()
    if forced:
        return forced
    if NIM_API_KEY:
        return "nim"
    if OPENROUTER_API_KEY:
        return "openrouter"
    if _looks_like_openai_key(OPENAI_API_KEY) or OPENAI_BASE_URL:
        return "openai"
    if LIGHTNING_API_KEY:
        return "lightning"
    if GEMINI_API_KEY:
        return "gemini"
    if GOOGLE_VISION_CREDENTIALS:
        return "google_vision"
    return "ollama"


AI_PROVIDER = _default_provider()

SYSTEM_PROMPT = """You are a competitive gaming score verification AI for sideQuest, a gaming platform.

Your job: extract ALL relevant info from a video game match screenshot.

Extract:
1. FINAL SCORE - both team/player scores
2. TEAM NAMES - full team names (e.g., "FC Barcelona", "Paris Saint-Germain", "Real Madrid FC")
3. HOME/AWAY - which team is home and which is away
4. PLAYER IDs - usernames/Gamertags/PSN IDs if shown
5. GAME NAME - (e.g., "EA Sports FC 26", "EA FC 25")

Rules:
1. Look for the post-match results screen showing final scores.
2. For EA FC (FIFA), find "FT", "Full Time", or match end times.
3. Find team crests/names on left and right sides.
4. Look for "HOME" or "AWAY" labels, or infer from layout.
5. Find player usernames in corners or below team names.
6. Return ONLY JSON — no explanation, no markdown.
7. Format:
{
  "player1_score": <int>,
  "player2_score": <int>,
  "team1_name": "<full team name>",
  "team2_name": "<full team name>",
  "team1_home_away": "home" | "away" | null,
  "team2_home_away": "home" | "away" | null,
  "player1_id": "<username or null>",
  "player2_id": "<username or null>",
  "confidence": <float 0-1>,
  "game_detected": "<game name>"
}
8. If score unreadable: {"error": "unreadable", "reason": "<why>"}
9. player1_score corresponds to team1_name (left side usually).
10. Do NOT guess team names - extract exactly what you see.
"""

@dataclass
class GameScore:
    home_score: int
    away_score: int
    home_team: Optional[str] = None
    away_team: Optional[str] = None
    winner: str = "draw"  # "home", "away", or "draw"
    confidence: float = 0.0
    game_type: Optional[str] = None
    screenshot_verified: bool = False

@dataclass
class ScoreResult:
    player1_score: Optional[int]
    player2_score: Optional[int]
    confidence: float
    game_detected: Optional[str]
    # Extended fields for team/player identification
    team1_name: Optional[str] = None
    team2_name: Optional[str] = None
    team1_home_away: Optional[str] = None  # "home" or "away"
    team2_home_away: Optional[str] = None
    player1_id: Optional[str] = None
    player2_id: Optional[str] = None
    error: Optional[str] = None
    raw_response: Optional[str] = None

    @property
    def is_valid(self) -> bool:
        return self.error is None and self.confidence >= 0.7

    def score_string(self) -> str:
        if not self.is_valid:
            return "UNREADABLE"
        return f"{self.player1_score}-{self.player2_score}"


class ScoreVerifier:
    """
    Extracts and verifies game scores from screenshots using Vision AI.
    """

    def __init__(self):
        if AI_PROVIDER == "openai" and not OPENAI_API_KEY:
            logger.warning("[ScoreVerifier] OPENAI_API_KEY not set. Using Ollama fallback.")

    # ─── Main Entry Point ────────────────────────────────────────────────────

    async def verify_screenshot(self, image_path: str) -> ScoreResult:
        """
        Extract score from a screenshot file path or base64 string.
        Returns ScoreResult.
        """
        try:
            image_b64 = await self._load_image_b64(image_path)
        except Exception as e:
            return ScoreResult(None, None, 0.0, None, error=f"image_load_failed: {e}")

        return await self._verify_with_prompt(image_b64, SYSTEM_PROMPT)

    async def verify_screenshot_with_context(
        self, image_path: str, context: Optional[dict] = None
    ) -> ScoreResult:
        """Vision extract with known home/away teams and console IDs as hints."""
        try:
            image_b64 = await self._load_image_b64(image_path)
        except Exception as e:
            return ScoreResult(None, None, 0.0, None, error=f"image_load_failed: {e}")

        ctx = context or {}
        catalog = ctx.get("catalog") if isinstance(ctx.get("catalog"), dict) else {}
        cat = (catalog.get("category") or "").lower()
        outcome = (catalog.get("outcome_type") or "scoreline").lower()
        hints = catalog.get("ai_hints") or []

        game_key = str(ctx.get("game") or catalog.get("game_id") or "")
        if (
            cat in ("imessage", "mobile")
            or game_key.startswith("imessage.")
            or game_key.startswith("mobile.")
        ):
            # Phone / iMessage finals — not console living-room layout
            venue = "iMessage / GamePigeon" if cat == "imessage" or game_key.startswith("imessage.") else "mobile phone game"
            hint_lines = [
                f"This is a {venue} final result screen (NOT console living-room EA FC unless catalog says FC Mobile).",
                f"- Game: {catalog.get('display_name') or ctx.get('game') or venue}",
                f"- Outcome type: {outcome}",
                f"- Expected result screen: {catalog.get('result_screen') or 'winner or scores'}",
                "Catalog AI hints:",
            ]
            for h in hints:
                hint_lines.append(f"  • {h}")
            if "fc_mobile" in game_key or (catalog.get("display_name") or "").lower().find("fc mobile") >= 0:
                hint_lines.extend(
                    [
                        "FC Mobile: extract full-time home and away goals.",
                        "Mobile UI — scores often large at top/center after FT.",
                        "player1_score = home/left, player2_score = away/right when layout is clear.",
                    ]
                )
            if outcome == "binary_winner":
                hint_lines.extend(
                    [
                        "Binary match: set the WINNER as higher score.",
                        "If you see 'You Win' / Victory for the local player on the left, use player1_score=1, player2_score=0.",
                        "If 'You Lose' / Defeat, use player1_score=0, player2_score=1.",
                        "If both names and a clear winner label, map winner to the higher of the two scores.",
                        "Use confidence < 0.7 if the screen is not a final result (e.g. BR placement only).",
                    ]
                )
            else:
                hint_lines.extend(
                    [
                        "Scoreline match: extract both players'/teams final points as player1_score and player2_score.",
                        "player1 = left / top / home when possible; player2 = right / bottom / away.",
                    ]
                )
            hint_lines.append(
                "Return the same JSON schema (player1_score, player2_score, confidence, game_detected)."
            )
            prompt = SYSTEM_PROMPT + "\n\n" + "\n".join(hint_lines)
            return await self._verify_with_prompt(image_b64, prompt)

        hint_lines = [
            "Match context provided by players (use to disambiguate, do not invent):",
            f"- Expected home team: {ctx.get('home_team') or 'unknown'}",
            f"- Expected away team: {ctx.get('away_team') or 'unknown'}",
            f"- Creator side: {ctx.get('creator_side') or 'unknown'}",
            f"- Opponent side: {ctx.get('opponent_side') or 'unknown'}",
            f"- Creator console ID: {ctx.get('creator_console_id') or 'unknown'}",
            f"- Opponent console ID: {ctx.get('opponent_console_id') or 'unknown'}",
            f"- Platform: {ctx.get('console_platform') or 'unknown'}",
            f"- Game: {ctx.get('game') or 'unknown'}",
            "If a club crest/logo is visible, name the club exactly.",
            "If PSN/Xbox gamertags appear, extract them into player1_id / player2_id.",
            "player1 = left side of screenshot; player2 = right side.",
        ]
        if hints:
            hint_lines.append("Extra catalog hints: " + "; ".join(str(x) for x in hints))
        prompt = SYSTEM_PROMPT + "\n\n" + "\n".join(hint_lines)
        return await self._verify_with_prompt(image_b64, prompt)

    async def _verify_with_prompt(self, image_b64: str, system_prompt: str) -> ScoreResult:
        # Temporarily swap prompt for provider calls that close over SYSTEM_PROMPT
        global SYSTEM_PROMPT
        old = SYSTEM_PROMPT
        SYSTEM_PROMPT = system_prompt
        try:
            # Ordered cascade: try preferred first, then any other configured
            # vision backend so a dead OpenAI key never blocks settlement.
            preferred = (AI_PROVIDER or "nim").lower()
            order = [
                "nim",
                "openrouter",
                "openai",
                "lightning",
                "gemini",
                "google_vision",
                "ollama",
            ]
            providers = [preferred] + [p for p in order if p != preferred]
            errors: list[str] = []
            for provider in providers:
                result: Optional[ScoreResult] = None
                try:
                    if provider == "nim" and NIM_API_KEY:
                        result = await self._verify_nim(image_b64)
                    elif provider == "openrouter" and OPENROUTER_API_KEY:
                        result = await self._verify_openrouter(image_b64)
                    elif provider == "openai" and (
                        _looks_like_openai_key(OPENAI_API_KEY) or OPENAI_BASE_URL
                    ):
                        result = await self._verify_openai(image_b64)
                    elif provider == "lightning" and LIGHTNING_API_KEY:
                        result = await self._verify_lightning(image_b64)
                    elif provider == "gemini" and GEMINI_API_KEY:
                        result = await self._verify_gemini(image_b64)
                    elif provider == "google_vision" and GOOGLE_VISION_CREDENTIALS:
                        result = await self._verify_google_vision_ocr(image_b64)
                    elif provider == "ollama":
                        result = await self._verify_ollama(image_b64)
                except Exception as exc:
                    errors.append(f"{provider}:{exc}")
                    logger.warning("[ScoreVerifier] %s raised: %s", provider, exc)
                    continue

                if result is None:
                    continue
                if result.error:
                    errors.append(f"{provider}:{result.error}")
                    # Auth/quota failures → try next provider
                    err_l = (result.error or "").lower()
                    if any(
                        x in err_l
                        for x in (
                            "401",
                            "402",
                            "403",
                            "429",
                            "unauthorized",
                            "insufficient",
                            "credit",
                            "quota",
                            "balance",
                        )
                    ):
                        logger.warning(
                            "[ScoreVerifier] %s failed (%s) — trying next",
                            provider,
                            result.error,
                        )
                        continue
                    # Unreadable / parse errors from a working model — return as-is
                    return result
                logger.info("[ScoreVerifier] score read via %s conf=%.2f", provider, result.confidence)
                return result

            return ScoreResult(
                None,
                None,
                0.0,
                None,
                error="all_vision_providers_failed: " + "; ".join(errors[:4]),
            )
        finally:
            SYSTEM_PROMPT = old

    async def verify_match_outcome(
        self,
        game_type: str,
        player1_id: str,
        player2_id: Optional[str],
        screenshot_url: Optional[str],
        expected_score: Optional[str],
        psn_id: Optional[str] = None,
        xbox_id: Optional[str] = None
    ) -> dict:
        """
        New unified method called by betting_engine to verify a single report.
        Returns a dictionary compatible with the betting engine.
        """
        if not screenshot_url:
            return {
                "verified": False,
                "confidence": 0,
                "reason": "No screenshot provided",
                "score": None
            }

        logger.info(f"[ScoreVerifier] Verifying match outcome. Expected: {expected_score}, URL: {screenshot_url[:30]}...")

        result = await self.verify_screenshot(screenshot_url)

        if not result.is_valid:
            return {
                "verified": False,
                "confidence": 0,
                "reason": result.error or "Unreadable screenshot",
                "score": None
            }

        # Convert ScoreResult to GameScore for betting engine compatibility
        winner = "draw"
        if result.player1_score > result.player2_score:
            winner = "home"  # player1
        elif result.player2_score > result.player1_score:
            winner = "away"  # player2

        score_obj = GameScore(
            home_score=result.player1_score,
            away_score=result.player2_score,
            home_team=player1_id,
            away_team=player2_id,
            winner=winner,
            confidence=result.confidence * 100,  # convert to 0-100 scale
            game_type=result.game_detected or game_type,
            screenshot_verified=True
        )

        # Optional: check if the extracted score matches the expected score
        matches_expected = False
        if expected_score:
            try:
                a, b = map(int, expected_score.replace(":", "-").split('-'))
                if (a == result.player1_score and b == result.player2_score) or \
                   (a == result.player2_score and b == result.player1_score):
                    matches_expected = True
            except ValueError:
                pass

        return {
            "verified": result.confidence >= 0.7,
            "confidence": result.confidence * 100,
            "reason": "Verified" if matches_expected else "Score extracted but mismatch with expected",
            "score": score_obj
        }

    async def verify_dispute(
        self,
        screenshot_p1: str,
        screenshot_p2: str,
        reported_p1: str,   # e.g. "3-1"
        reported_p2: str,   # e.g. "2-1"
    ) -> dict:
        """
        Full dispute resolution flow.
        Verifies both screenshots and determines the correct score.

        Returns:
            {
              "resolved": bool,
              "winner": "player1" | "player2" | None,
              "verified_score": "3-1" | None,
              "reason": str,
              "p1_result": ScoreResult,
              "p2_result": ScoreResult,
            }
        """
        logger.info(f"[ScoreVerifier] Starting dispute resolution. P1 reports {reported_p1}, P2 reports {reported_p2}")

        # Run both verifications in parallel
        p1_result, p2_result = await asyncio.gather(
            self.verify_screenshot(screenshot_p1),
            self.verify_screenshot(screenshot_p2),
        )

        logger.info(f"[ScoreVerifier] P1 screenshot: {p1_result.score_string()} (conf={p1_result.confidence:.2f})")
        logger.info(f"[ScoreVerifier] P2 screenshot: {p2_result.score_string()} (conf={p2_result.confidence:.2f})")

        # ── Both unreadable ──────────────────────────────────────────────
        if not p1_result.is_valid and not p2_result.is_valid:
            return {
                "resolved": False,
                "winner": None,
                "verified_score": None,
                "reason": "Both screenshots are unreadable. Escalating to admin.",
                "p1_result": p1_result,
                "p2_result": p2_result,
            }

        # ── One unreadable ───────────────────────────────────────────────
        if not p1_result.is_valid and p2_result.is_valid:
            # Trust P2's screenshot
            winner = self._determine_winner_from_score(p2_result)
            return {
                "resolved": True,
                "winner": winner,
                "verified_score": p2_result.score_string(),
                "reason": f"P1 screenshot unreadable. P2 screenshot shows {p2_result.score_string()}.",
                "p1_result": p1_result,
                "p2_result": p2_result,
            }

        if p1_result.is_valid and not p2_result.is_valid:
            winner = self._determine_winner_from_score(p1_result)
            return {
                "resolved": True,
                "winner": winner,
                "verified_score": p1_result.score_string(),
                "reason": f"P2 screenshot unreadable. P1 screenshot shows {p1_result.score_string()}.",
                "p1_result": p1_result,
                "p2_result": p2_result,
            }

        # ── Both readable — check agreement ──────────────────────────────
        p1_score = (p1_result.player1_score, p1_result.player2_score)
        p2_score = (p2_result.player1_score, p2_result.player2_score)

        # Scores agree (note: P2's screenshot may have scores swapped)
        scores_agree = (
            p1_score == p2_score or
            p1_score == (p2_score[1], p2_score[0])
        )

        if scores_agree:
            winner = self._determine_winner_from_score(p1_result)
            return {
                "resolved": True,
                "winner": winner,
                "verified_score": p1_result.score_string(),
                "reason": f"Both screenshots confirm score {p1_result.score_string()}.",
                "p1_result": p1_result,
                "p2_result": p2_result,
            }

        # Screenshots disagree — use higher confidence one
        if p1_result.confidence > p2_result.confidence and p1_result.confidence > 0.85:
            winner = self._determine_winner_from_score(p1_result)
            return {
                "resolved": True,
                "winner": winner,
                "verified_score": p1_result.score_string(),
                "reason": f"Screenshots disagree. Trusting P1 screenshot (conf={p1_result.confidence:.2f}).",
                "p1_result": p1_result,
                "p2_result": p2_result,
            }

        if p2_result.confidence > p1_result.confidence and p2_result.confidence > 0.85:
            winner = self._determine_winner_from_score(p2_result)
            return {
                "resolved": True,
                "winner": winner,
                "verified_score": p2_result.score_string(),
                "reason": f"Screenshots disagree. Trusting P2 screenshot (conf={p2_result.confidence:.2f}).",
                "p1_result": p1_result,
                "p2_result": p2_result,
            }

        # Cannot determine — escalate
        return {
            "resolved": False,
            "winner": None,
            "verified_score": None,
            "reason": (
                f"Screenshots disagree and confidence is low. "
                f"P1 shows {p1_result.score_string()}, P2 shows {p2_result.score_string()}. "
                f"Escalating to admin."
            ),
            "p1_result": p1_result,
            "p2_result": p2_result,
        }

    # ─── Gemini Vision ───────────────────────────────────────────────────────
    
    async def _verify_gemini(self, image_b64: str) -> ScoreResult:
        try:
            try:
                import google.genai as genai
            except ImportError:
                import google.generativeai as genai
            import json
            
            genai.configure(api_key=GEMINI_API_KEY)
            model = genai.GenerativeModel("gemini-flash-latest")
            
            # Prepare image data
            image_data = base64.b64decode(image_b64)
            image_parts = [
                {"mime_type": "image/jpeg", "data": image_data}
            ]
            
            # Generate content
            response = await asyncio.to_thread(
                model.generate_content,
                [SYSTEM_PROMPT, image_parts[0]]
            )
            
            return self._parse_ai_response(response.text)
        except Exception as e:
            logger.error(f"[ScoreVerifier] Gemini error: {e}")
            return ScoreResult(None, None, 0.0, None, error=f"gemini_error: {e}")

    # ─── Google Cloud Vision (OCR) ───────────────────────────────────────────

    async def _verify_google_vision_ocr(self, image_b64: str) -> ScoreResult:
        """
        Extracts text via Cloud Vision API and parses it for scores.
        This is a 'fallback' for when LLM vision is not desired.
        """
        try:
            from google.cloud import vision
            import json

            client = vision.ImageAnnotatorClient()
            content = base64.b64decode(image_b64)
            image = vision.Image(content=content)

            # Perform text detection
            response = await asyncio.to_thread(client.text_detection, image=image)
            texts = response.text_annotations
            
            if not texts:
                return ScoreResult(None, None, 0.0, None, error="no_text_found")

            full_text = texts[0].description
            logger.info(f"[ScoreVerifier] Google OCR Text: {full_text[:200]}...")

            # Since OCR only gives raw text, we use Gemini or OpenAI to PARSE that text 
            # if we want high accuracy, or we can use regex.
            # For simplicity, if we are in Google mode, we'll ask Gemini to parse the OCR text.
            parse_prompt = f"{SYSTEM_PROMPT}\n\nBelow is the raw text extracted from a screenshot via OCR. Extract the score:\n\n{full_text}"
            
            if GEMINI_API_KEY:
                import google.generativeai as genai
                genai.configure(api_key=GEMINI_API_KEY)
                model = genai.GenerativeModel("gemini-flash-latest")
                resp = await asyncio.to_thread(model.generate_content, parse_prompt)
                return self._parse_ai_response(resp.text)
            
            return ScoreResult(None, None, 0.0, None, error="parsing_not_implemented_for_raw_ocr")

        except Exception as e:
            logger.error(f"[ScoreVerifier] Google Cloud Vision error: {e}")
            return ScoreResult(None, None, 0.0, None, error=f"google_vision_error: {e}")

    # ─── NVIDIA NIM Vision ───────────────────────────────────────────────────

    async def _verify_nim(self, image_b64: str) -> ScoreResult:
        """
        Verify score using NVIDIA NIM API (free at build.nvidia.com)
        Uses mistral-small-3.1-24b vision model.
        """
        try:
            import httpx
            
            model_name = NIM_VISION_MODEL

            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.post(
                    f"{NIM_BASE_URL.rstrip('/')}/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {NIM_API_KEY}",
                        "Content-Type": "application/json",
                        "Accept": "application/json",
                    },
                    json={
                        "model": model_name,
                        "max_tokens": 200,
                        "messages": [
                            {"role": "system", "content": SYSTEM_PROMPT},
                            {
                                "role": "user",
                                "content": [
                                    {
                                        "type": "image_url",
                                        "image_url": {
                                            "url": f"data:image/jpeg;base64,{image_b64}"
                                        },
                                    },
                                    {"type": "text", "text": "Extract the final score from this game screenshot. Return only JSON."},
                                ],
                            },
                        ],
                    },
                )
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
            return self._parse_ai_response(content)
        except Exception as e:
            logger.error(f"[ScoreVerifier] NIM error: {e}")
            return ScoreResult(None, None, 0.0, None, error=f"nim_error: {e}")

    # ─── OpenAI Vision ───────────────────────────────────────────────────────

    async def _verify_openai(self, image_b64: str) -> ScoreResult:
        try:
            import httpx

            base = OPENAI_BASE_URL or "https://api.openai.com/v1"
            if not base.endswith("/v1") and "openai.com" in base:
                base = base.rstrip("/") + "/v1"
            url = f"{base.rstrip('/')}/chat/completions"
            # Gateway keys (ogw_live_…) only work against their own base URL
            if not OPENAI_BASE_URL and not _looks_like_openai_key(OPENAI_API_KEY):
                return ScoreResult(
                    None,
                    None,
                    0.0,
                    None,
                    error="openai_error: invalid OPENAI_API_KEY for api.openai.com",
                )
            model = OPENAI_VISION_MODEL
            # Vision needs a multimodal model — avoid pure text Claude names on gateways
            if "claude" in (model or "").lower() and not OPENAI_BASE_URL:
                model = "gpt-4o"
            async with httpx.AsyncClient(timeout=45) as client:
                resp = await client.post(
                    url,
                    headers={
                        "Authorization": f"Bearer {OPENAI_API_KEY}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": model,
                        "max_tokens": 300,
                        "messages": [
                            {"role": "system", "content": SYSTEM_PROMPT},
                            {
                                "role": "user",
                                "content": [
                                    {
                                        "type": "image_url",
                                        "image_url": {
                                            "url": f"data:image/jpeg;base64,{image_b64}",
                                            "detail": "high",
                                        },
                                    },
                                    {
                                        "type": "text",
                                        "text": "Extract the final score from this game screenshot. Return only JSON.",
                                    },
                                ],
                            },
                        ],
                    },
                )
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
            return self._parse_ai_response(content)
        except Exception as e:
            logger.error(f"[ScoreVerifier] OpenAI error: {e}")
            return ScoreResult(None, None, 0.0, None, error=f"openai_error: {e}")

    async def _verify_openrouter(self, image_b64: str) -> ScoreResult:
        try:
            import httpx

            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.post(
                    f"{OPENROUTER_BASE_URL}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                        "Content-Type": "application/json",
                        "HTTP-Referer": "https://playingsidequest.fun",
                        "X-Title": "ClawStation Score Verifier",
                    },
                    json={
                        "model": OPENROUTER_VISION_MODEL,
                        "max_tokens": 300,
                        "messages": [
                            {"role": "system", "content": SYSTEM_PROMPT},
                            {
                                "role": "user",
                                "content": [
                                    {
                                        "type": "image_url",
                                        "image_url": {
                                            "url": f"data:image/jpeg;base64,{image_b64}"
                                        },
                                    },
                                    {
                                        "type": "text",
                                        "text": "Extract the final score from this game screenshot. Return only JSON.",
                                    },
                                ],
                            },
                        ],
                    },
                )
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
            return self._parse_ai_response(content)
        except Exception as e:
            logger.error(f"[ScoreVerifier] OpenRouter error: {e}")
            return ScoreResult(None, None, 0.0, None, error=f"openrouter_error: {e}")

    async def _verify_lightning(self, image_b64: str) -> ScoreResult:
        try:
            import httpx

            base = LIGHTNING_BASE_URL.rstrip("/")
            url = f"{base}/chat/completions"
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.post(
                    url,
                    headers={
                        "Authorization": f"Bearer {LIGHTNING_API_KEY}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": LIGHTNING_VISION_MODEL,
                        "max_tokens": 300,
                        "messages": [
                            {"role": "system", "content": SYSTEM_PROMPT},
                            {
                                "role": "user",
                                "content": [
                                    {
                                        "type": "image_url",
                                        "image_url": {
                                            "url": f"data:image/jpeg;base64,{image_b64}"
                                        },
                                    },
                                    {
                                        "type": "text",
                                        "text": "Extract the final score from this game screenshot. Return only JSON.",
                                    },
                                ],
                            },
                        ],
                    },
                )
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
            return self._parse_ai_response(content)
        except Exception as e:
            logger.error(f"[ScoreVerifier] Lightning error: {e}")
            return ScoreResult(None, None, 0.0, None, error=f"lightning_error: {e}")

    # ─── Ollama Fallback ─────────────────────────────────────────────────────

    async def _verify_ollama(self, image_b64: str) -> ScoreResult:
        try:
            import httpx
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.post(
                    f"{OLLAMA_URL}/api/generate",
                    json={
                        "model": OLLAMA_MODEL,
                        "prompt": SYSTEM_PROMPT + "\n\nExtract the final score from this game screenshot. Return only JSON.",
                        "images": [image_b64],
                        "stream": False,
                    },
                )
            resp.raise_for_status()
            content = resp.json().get("response", "")
            return self._parse_ai_response(content)
        except Exception as e:
            logger.error(f"[ScoreVerifier] Ollama error: {e}")
            return ScoreResult(None, None, 0.0, None, error=f"ollama_error: {e}")

    # ─── Helpers ─────────────────────────────────────────────────────────────

    @staticmethod
    async def _load_image_b64(image_path: str) -> str:
        """Load an image from path, URL, data-URL, or raw base64 string."""
        if image_path.startswith("http://") or image_path.startswith("https://"):
            try:
                import httpx
                async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
                    resp = await client.get(image_path)
                    resp.raise_for_status()
                    return base64.b64encode(resp.content).decode("utf-8")
            except Exception as e:
                logger.error(f"Failed to download image from URL: {e}")
                raise FileNotFoundError(f"Failed to download image from {image_path}: {e}")

        if image_path.startswith("data:image"):
            return image_path.split(",", 1)[1]

        # Telegram file_id is short alphanumeric — not an image; caller should download first.
        # Raw base64 from bot download path (long, no path separators).
        if len(image_path) > 200 and "/" not in image_path and not image_path.startswith("AgAC"):
            try:
                base64.b64decode(image_path[:64] + "==", validate=False)
                return image_path
            except Exception:
                pass

        path = Path(image_path)
        if not path.exists():
            # Last resort: treat as raw base64 (Telegram bot path passes b64)
            if len(image_path) > 64:
                return image_path
            raise FileNotFoundError(f"Image not found: {image_path}")
        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode()

    @staticmethod
    def _parse_ai_response(response: str) -> ScoreResult:
        """Parse JSON response from the AI into a ScoreResult."""
        import json

        # Extract JSON from response (model sometimes wraps in ```json```)
        json_match = re.search(r'\{.*\}', response, re.DOTALL)
        if not json_match:
            return ScoreResult(None, None, 0.0, None, error="no_json_in_response", raw_response=response)

        try:
            data = json.loads(json_match.group())
        except json.JSONDecodeError:
            return ScoreResult(None, None, 0.0, None, error="json_parse_error", raw_response=response)

        if "error" in data:
            return ScoreResult(None, None, 0.0, None, error=data["error"], raw_response=response)

        return ScoreResult(
            player1_score=int(data.get("player1_score", 0)) if data.get("player1_score") else None,
            player2_score=int(data.get("player2_score", 0)) if data.get("player2_score") else None,
            confidence=float(data.get("confidence", 0.0)),
            game_detected=data.get("game_detected"),
            team1_name=data.get("team1_name"),
            team2_name=data.get("team2_name"),
            team1_home_away=data.get("team1_home_away"),
            team2_home_away=data.get("team2_home_away"),
            player1_id=data.get("player1_id"),
            player2_id=data.get("player2_id"),
            raw_response=response,
        )

    @staticmethod
    def _determine_winner_from_score(result: ScoreResult) -> str:
        """Returns 'player1' or 'player2' based on who has the higher score."""
        if result.player1_score > result.player2_score:
            return "player1"
        elif result.player2_score > result.player1_score:
            return "player2"
        return "draw"  # Ties handled upstream (cancel + refund)


# ─── Singleton ───────────────────────────────────────────────────────────────

_verifier: Optional[ScoreVerifier] = None

def get_score_verifier() -> ScoreVerifier:
    global _verifier
    if _verifier is None:
        _verifier = ScoreVerifier()
    return _verifier

async def verify_match(*args, **kwargs):
    """Convenience function that uses the singleton verifier."""
    return await get_score_verifier().verify_match_outcome(*args, **kwargs)

