"""
ClawStation settlement: scores + AI vision → on-chain resolve.

Flow:
  1. Both players submit scores and/or screenshots.
  2. If scores agree (or AI vision agrees) → payout after dispute window
     (window skipped when AI confidence is high).
  3. If conflict unresolved → dispute for admin.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

from backend.supabase_client import get_supabase
from gaming.src.backend.services.challenge_compat import denormalize_challenge, normalize_challenge, normalize_list
from gaming.src.backend.services.clawstation_escrow import (
    EscrowError,
    flag_dispute,
    resolve_match,
)

logger = logging.getLogger(__name__)

DEFAULT_DISPUTE_WINDOW_MINUTES = int(os.getenv("SETTLEMENT_DISPUTE_WINDOW_MINUTES", "5"))
# When AI verifies both screenshots with high confidence, settle immediately.
AI_FAST_SETTLE_CONFIDENCE = float(os.getenv("AI_FAST_SETTLE_CONFIDENCE", "0.75"))


class SettlementError(Exception):
    """Raised when a settlement operation fails."""


def _get_supabase():
    return get_supabase()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _load_challenge(challenge_id: str) -> Optional[dict]:
    sb = _get_supabase()
    result = (
        sb.schema("gaming")
        .table("challenges")
        .select("*")
        .eq("id", challenge_id)
        .maybe_single()
        .execute()
    )
    return normalize_challenge(result.data) if result.data else None


def _load_submitted_challenges() -> list[dict]:
    sb = _get_supabase()
    result = (
        sb.schema("gaming")
        .table("challenges")
        .select("*")
        .eq("status", "submitted")
        .execute()
    )
    return normalize_list(result.data)


async def _load_profile_address(
    profile_id: str, chain_id: Optional[str] = None
) -> Optional[str]:
    """Winner address must be the Circle wallet that locked on the settlement chain.

    ``gaming_deposit_address`` is often the Base wallet and will revert
    resolveMatch with InvalidWinner when the match was created on Arc/Avalanche.
    """
    try:
        from gaming.src.backend.services.clawstation_circle import ensure_user_wallet
        from gaming.src.backend.services.chains import default_chain_id, normalize_chain_id

        cid = normalize_chain_id(chain_id or default_chain_id())
        wallet = await ensure_user_wallet(profile_id, chain_id=cid)
        addr = (wallet or {}).get("address")
        if addr:
            return addr
    except Exception as exc:
        logger.warning(
            "[Settlement] chain wallet lookup failed profile=%s chain=%s: %s",
            profile_id,
            chain_id,
            exc,
        )

    # Last resort legacy field (Base-only matches)
    sb = _get_supabase()
    result = (
        sb.table("profiles")
        .select("gaming_deposit_address")
        .eq("id", profile_id)
        .maybe_single()
        .execute()
    )
    if result.data:
        return result.data.get("gaming_deposit_address")
    return None


def _determine_winner_from_scores(challenge: dict) -> Optional[str]:
    """Determine winner from full scorelines or legacy single scores.

    Prefer home-away reports. If both players report the same home-away
    scoreline, map winner using creator_side / opponent_side.
    Fallback: higher self-reported ``creator_score`` / ``opponent_score``.
    """
    ch = challenge.get("creator_reported_home")
    ca = challenge.get("creator_reported_away")
    oh = challenge.get("opponent_reported_home")
    oa = challenge.get("opponent_reported_away")

    # Both full scorelines present
    if None not in (ch, ca, oh, oa):
        try:
            ch, ca, oh, oa = int(ch), int(ca), int(oh), int(oa)
        except (TypeError, ValueError):
            pass
        else:
            if (ch, ca) != (oh, oa):
                # Conflicting claims — let AI / dispute handle
                return None
            # Agreed scoreline
            if ch == ca:
                return None  # draw
            if ch > ca:
                # home won
                if challenge.get("creator_side") == "home":
                    return challenge["creator_id"]
                if challenge.get("opponent_side") == "home":
                    return challenge["opponent_id"]
                # no sides set: creator treated as home (legacy)
                return challenge["creator_id"]
            # away won
            if challenge.get("creator_side") == "away":
                return challenge["creator_id"]
            if challenge.get("opponent_side") == "away":
                return challenge["opponent_id"]
            return challenge.get("opponent_id")

    # AI home-away available
    ah, aa = challenge.get("ai_home_score"), challenge.get("ai_away_score")
    if ah is not None and aa is not None:
        try:
            ah, aa = int(ah), int(aa)
        except (TypeError, ValueError):
            pass
        else:
            if ah == aa:
                return None
            home_wins = ah > aa
            if home_wins:
                if challenge.get("creator_side") == "home":
                    return challenge["creator_id"]
                if challenge.get("opponent_side") == "home":
                    return challenge["opponent_id"]
                return challenge["creator_id"]
            if challenge.get("creator_side") == "away":
                return challenge["creator_id"]
            if challenge.get("opponent_side") == "away":
                return challenge["opponent_id"]
            return challenge.get("opponent_id")

    # Legacy: each player's "my goals"
    creator_score = challenge.get("creator_score")
    opponent_score = challenge.get("opponent_score")
    if creator_score is None or opponent_score is None:
        return None
    try:
        c, o = int(creator_score), int(opponent_score)
    except (TypeError, ValueError):
        return None
    if c > o:
        return challenge["creator_id"]
    if o > c:
        return challenge["opponent_id"]
    return None  # draw


def _both_scores_present(challenge: dict) -> bool:
    return challenge.get("creator_score") is not None and challenge.get("opponent_score") is not None


def _both_screenshots_present(challenge: dict) -> bool:
    return bool(challenge.get("screenshot_creator_url") and challenge.get("screenshot_opponent_url"))


def _dispute_window_elapsed(challenge: dict) -> bool:
    updated_at = challenge.get("updated_at") or challenge.get("ai_verified_at")
    if not updated_at:
        return False
    try:
        updated = datetime.fromisoformat(str(updated_at).replace("Z", "+00:00"))
    except Exception:
        return False
    return (_utcnow() - updated) >= timedelta(minutes=DEFAULT_DISPUTE_WINDOW_MINUTES)


async def _resolve_screenshot_source(ref: str) -> str:
    """Turn a Telegram file_id into a downloadable HTTPS URL when needed."""
    if not ref:
        return ref
    if ref.startswith("http://") or ref.startswith("https://") or ref.startswith("data:"):
        return ref
    if len(ref) > 200 and "/" not in ref:
        return ref  # already base64
    # Telegram file_id → Bot API file URL
    token = (
        os.getenv("TELEGRAM_BOT_TOKEN_CLAWSTATION")
        or os.getenv("TELEGRAM_BOT_TOKEN")
        or ""
    )
    if not token:
        return ref
    try:
        import httpx

        async with httpx.AsyncClient(timeout=20) as client:
            meta = await client.get(
                f"https://api.telegram.org/bot{token}/getFile",
                params={"file_id": ref},
            )
            data = meta.json()
            if not data.get("ok"):
                logger.warning("[Settlement] getFile failed: %s", data)
                return ref
            path = data["result"]["file_path"]
            return f"https://api.telegram.org/file/bot{token}/{path}"
    except Exception as exc:
        logger.warning("[Settlement] Telegram file resolve failed: %s", exc)
        return ref


async def verify_with_ai_vision(challenge: dict) -> dict:
    """
    Run AI vision on available screenshots.

    Returns:
        {
          resolved: bool,
          winner_id: optional profile id,
          confidence: float,
          verified_score: str,
          reason: str,
          skip_dispute_window: bool,
        }
    """
    creator_ss = challenge.get("screenshot_creator_url")
    opponent_ss = challenge.get("screenshot_opponent_url")
    if not creator_ss and not opponent_ss:
        return {
            "resolved": False,
            "winner_id": None,
            "confidence": 0.0,
            "verified_score": None,
            "reason": "no_screenshots",
            "skip_dispute_window": False,
        }

    creator_ss = await _resolve_screenshot_source(creator_ss) if creator_ss else None
    opponent_ss = await _resolve_screenshot_source(opponent_ss) if opponent_ss else None

    try:
        from gaming.src.backend.score_verifier import get_score_verifier

        verifier = get_score_verifier()
    except Exception as exc:
        logger.warning("[Settlement] Score verifier unavailable: %s", exc)
        return {
            "resolved": False,
            "winner_id": None,
            "confidence": 0.0,
            "verified_score": None,
            "reason": f"verifier_unavailable: {exc}",
            "skip_dispute_window": False,
        }

    creator_score = challenge.get("creator_score")
    opponent_score = challenge.get("opponent_score")
    reported_p1 = f"{creator_score or 0}-{opponent_score or 0}"
    reported_p2 = f"{opponent_score or 0}-{creator_score or 0}"

    # Both screenshots → full dispute verification
    if creator_ss and opponent_ss:
        try:
            result = await verifier.verify_dispute(
                screenshot_p1=creator_ss,
                screenshot_p2=opponent_ss,
                reported_p1=reported_p1,
                reported_p2=reported_p2,
            )
            winner_label = result.get("winner")
            winner_id = None
            if winner_label == "player1":
                winner_id = challenge["creator_id"]
            elif winner_label == "player2":
                winner_id = challenge["opponent_id"]
            conf = 0.0
            p1 = result.get("p1_result")
            p2 = result.get("p2_result")
            if p1 is not None and hasattr(p1, "confidence"):
                conf = max(conf, float(p1.confidence or 0))
            if p2 is not None and hasattr(p2, "confidence"):
                conf = max(conf, float(p2.confidence or 0))
            return {
                "resolved": bool(result.get("resolved")),
                "winner_id": winner_id,
                "confidence": conf,
                "verified_score": result.get("verified_score"),
                "reason": result.get("reason") or "",
                "skip_dispute_window": conf >= AI_FAST_SETTLE_CONFIDENCE and bool(result.get("resolved")),
            }
        except Exception as exc:
            logger.warning("[Settlement] verify_dispute failed: %s", exc)
            return {
                "resolved": False,
                "winner_id": None,
                "confidence": 0.0,
                "verified_score": None,
                "reason": str(exc),
                "skip_dispute_window": False,
            }

    # Single screenshot — extract score and map winner by who is ahead
    ss = creator_ss or opponent_ss
    try:
        single = await verifier.verify_screenshot(ss)
        if not single.is_valid:
            return {
                "resolved": False,
                "winner_id": None,
                "confidence": float(single.confidence or 0),
                "verified_score": None,
                "reason": single.error or "unreadable",
                "skip_dispute_window": False,
            }
        p1, p2 = int(single.player1_score or 0), int(single.player2_score or 0)
        winner_id = None
        if p1 > p2:
            winner_id = challenge["creator_id"]
        elif p2 > p1:
            winner_id = challenge.get("opponent_id")
        return {
            "resolved": True,
            "winner_id": winner_id,
            "confidence": float(single.confidence or 0),
            "verified_score": f"{p1}-{p2}",
            "reason": "single_screenshot",
            "skip_dispute_window": float(single.confidence or 0) >= AI_FAST_SETTLE_CONFIDENCE,
        }
    except Exception as exc:
        logger.warning("[Settlement] single screenshot verify failed: %s", exc)
        return {
            "resolved": False,
            "winner_id": None,
            "confidence": 0.0,
            "verified_score": None,
            "reason": str(exc),
            "skip_dispute_window": False,
        }


def _update_challenge(
    challenge_id: str,
    status: str,
    winner_id: Optional[str] = None,
    tx_hash: Optional[str] = None,
    ai_meta: Optional[dict] = None,
) -> None:
    sb = _get_supabase()
    update: dict = {"status": status}
    if winner_id is not None:
        update["winner_id"] = winner_id
    if tx_hash is not None:
        update["resolved_tx_hash"] = tx_hash
    if ai_meta:
        if ai_meta.get("verified_score"):
            update["ai_verified_score"] = ai_meta["verified_score"]
        if ai_meta.get("confidence") is not None:
            update["ai_confidence"] = ai_meta["confidence"]
        if ai_meta.get("winner_id"):
            update["ai_winner_id"] = ai_meta["winner_id"]
        update["ai_verified_at"] = datetime.now(timezone.utc).isoformat()
    sb.schema("gaming").table("challenges").update(denormalize_challenge(update)).eq(
        "id", challenge_id
    ).execute()


def _score_from_challenge(challenge: dict) -> tuple[Optional[int], Optional[int], str]:
    """Best-effort final scoreline for zingers."""
    home = away = None
    for key in ("final_home", "home_score", "creator_home", "ai_home"):
        if challenge.get(key) is not None:
            try:
                home = int(challenge[key])
                break
            except (TypeError, ValueError):
                pass
    for key in ("final_away", "away_score", "creator_away", "ai_away"):
        if challenge.get(key) is not None:
            try:
                away = int(challenge[key])
                break
            except (TypeError, ValueError):
                pass
    raw = (
        challenge.get("final_score")
        or challenge.get("scoreline")
        or challenge.get("ai_scoreline")
        or ""
    )
    if home is None and away is None and raw:
        import re

        m = re.search(r"(\d+)\s*[-:]\s*(\d+)", str(raw))
        if m:
            home, away = int(m.group(1)), int(m.group(2))
    scoreline = f"{home}-{away}" if home is not None and away is not None else str(raw or "")
    return home, away, scoreline


async def _notify_result(
    challenge: dict,
    winner_id: Optional[str],
    tx_hash: Optional[str],
) -> None:
    from gaming.src.bot.utils.notify import get_balance_snapshot, notify_user
    from gaming.src.bot.utils.zingers import format_result_banner
    from gaming.src.backend.services.match_codes import display_code

    creator_id = challenge["creator_id"]
    opponent_id = challenge.get("opponent_id")
    amount = Decimal(str(challenge["amount_usdc"]))
    match_code = display_code(challenge)
    # Money UX: hide chain noise; optional tx for power users only
    tx_hash_disp = tx_hash or ""
    if tx_hash_disp and not tx_hash_disp.startswith("0x"):
        tx_hash_disp = "0x" + tx_hash_disp
    tx_text = f"\n<code>{tx_hash_disp[:10]}…</code>" if len(tx_hash_disp) > 12 else (
        f"\n<code>{tx_hash_disp}</code>" if tx_hash_disp else ""
    )

    pot = float(amount * 2 * Decimal("0.93"))
    home, away, scoreline = _score_from_challenge(challenge)

    def _tag_for(uid: Optional[str]) -> str:
        if not uid:
            return ""
        try:
            from backend.supabase_client import get_supabase

            r = (
                get_supabase()
                .table("profiles")
                .select("gaming_tag")
                .eq("id", uid)
                .limit(1)
                .execute()
            )
            row = (r.data or [None])[0]
            return (row or {}).get("gaming_tag") or ""
        except Exception:
            return ""

    async def _send(uid: str, you_won: Optional[bool], rival_id: Optional[str]) -> None:
        rival_tag = _tag_for(rival_id)
        head = format_result_banner(
            won=you_won,
            match_code=match_code,
            pot_usdc=pot if you_won is not None else None,
            scoreline=scoreline,
            home=home,
            away=away,
            rival_tag=rival_tag,
        )
        if you_won is True and tx_text:
            head = f"{head}{tx_text}"
        bal = await get_balance_snapshot(uid)
        buttons = None
        if rival_id:
            try:
                from gaming.src.bot.keyboards import rematch_after_result_menu

                buttons = rematch_after_result_menu(rival_id)
            except Exception:
                buttons = None
        await notify_user(
            uid,
            f"{head}\n\n"
            f"<b>Balance</b>\n{bal}\n\n"
            f"Tap <b>Rematch</b> — or open Wallet.",
            buttons=buttons,
        )

    if winner_id is None:
        await _send(creator_id, None, opponent_id)
        if opponent_id:
            await _send(opponent_id, None, creator_id)
    else:
        await _send(creator_id, creator_id == winner_id, opponent_id)
        if opponent_id:
            await _send(opponent_id, opponent_id == winner_id, creator_id)


async def _execute_payout(challenge: dict, winner_id: Optional[str]) -> str:
    challenge_id = challenge["id"]

    if winner_id is None:
        from gaming.src.backend.services.clawstation_escrow import cancel_match

        result = await cancel_match(challenge_id)
        return result.get("tx_hash", "")

    from gaming.src.backend.services.chains import default_chain_id, normalize_chain_id

    chain_id = normalize_chain_id(
        challenge.get("settlement_chain") or default_chain_id()
    )
    winner_address = await _load_profile_address(winner_id, chain_id=chain_id)
    if not winner_address:
        raise SettlementError(
            f"Winner {winner_id} has no deposit address on chain={chain_id}"
        )

    _update_challenge(challenge_id, "submitted", winner_id=winner_id)
    result = await resolve_match(challenge_id, winner_address)
    return result.get("tx_hash", "")


async def settle_challenge(challenge_id: str, admin_winner_id: Optional[str] = None) -> dict:
    """
    Resolve a single challenge via scores and/or AI vision.

    Hard rules (non-admin):
      • Never pay out on one-sided reports.
      • Conflicting scorelines → dispute (unless AI resolves with high confidence).
      • Prefer both screenshots when MATCH_REQUIRE_SCREENSHOTS=true.
    """
    from gaming.src.backend.services.match_report import analyze_reports
    from gaming.src.bot.utils.flow import conflict_message
    from gaming.src.bot.utils.notify import notify_user

    challenge = _load_challenge(challenge_id)
    if not challenge:
        raise SettlementError(f"Challenge {challenge_id} not found")

    if challenge.get("status") == "resolved":
        return {"success": True, "action": "skipped", "reason": "already_resolved"}

    if challenge.get("status") not in ("submitted", "disputed", "locked", "playing"):
        return {"success": True, "action": "skipped", "reason": f"status={challenge.get('status')}"}

    skip_window = False
    ai_meta: Optional[dict] = None
    winner_id: Optional[str] = None

    if admin_winner_id:
        winner_id = admin_winner_id
        logger.info("[Settlement] Admin resolving %s → %s", challenge_id, winner_id)
        skip_window = True
    else:
        analysis = analyze_reports(challenge)
        action = analysis["action"]

        # One-sided / incomplete — never settle
        if action in ("wait_both", "wait_opponent", "wait_creator", "incomplete"):
            return {
                "success": True,
                "action": "waiting_reports",
                "reason": analysis["reason"],
                "challenge_id": challenge_id,
            }

        if action == "sides_conflict":
            try:
                await flag_dispute(challenge_id)
            except EscrowError as exc:
                logger.warning("[Settlement] flag_dispute: %s", exc)
            _update_challenge(challenge_id, "disputed")
            msg = conflict_message(challenge_id, analysis["reason"])
            await notify_user(challenge["creator_id"], msg)
            if challenge.get("opponent_id"):
                await notify_user(challenge["opponent_id"], msg)
            return {"success": True, "action": "disputed", "reason": analysis["reason"]}

        if action == "conflict":
            # Try AI before permanent dispute
            ai = await verify_with_ai_vision(challenge)
            ai_meta = {
                "verified_score": ai.get("verified_score"),
                "confidence": ai.get("confidence"),
                "winner_id": ai.get("winner_id"),
            }
            if ai.get("resolved") and ai.get("skip_dispute_window"):
                winner_id = ai.get("winner_id")
                skip_window = True
            else:
                try:
                    await flag_dispute(challenge_id)
                except EscrowError as exc:
                    logger.warning("[Settlement] flag_dispute: %s", exc)
                _update_challenge(challenge_id, "disputed", ai_meta=ai_meta)
                msg = conflict_message(
                    challenge_id,
                    analysis["reason"]
                    + (f" AI: {ai.get('reason')}" if ai.get("reason") else ""),
                )
                await notify_user(challenge["creator_id"], msg)
                if challenge.get("opponent_id"):
                    await notify_user(challenge["opponent_id"], msg)
                return {
                    "success": True,
                    "action": "disputed",
                    "reason": analysis["reason"],
                    "challenge_id": challenge_id,
                }

        if action == "wait_screenshots":
            # Scores may agree but we want photos — try AI if at least one shot exists
            if challenge.get("screenshot_creator_url") or challenge.get("screenshot_opponent_url"):
                ai = await verify_with_ai_vision(challenge)
                if ai.get("resolved") and float(ai.get("confidence") or 0) >= AI_FAST_SETTLE_CONFIDENCE:
                    winner_id = ai.get("winner_id")
                    skip_window = True
                    ai_meta = {
                        "verified_score": ai.get("verified_score"),
                        "confidence": ai.get("confidence"),
                        "winner_id": ai.get("winner_id"),
                    }
                else:
                    return {
                        "success": True,
                        "action": "waiting_screenshots",
                        "reason": analysis["reason"],
                        "challenge_id": challenge_id,
                    }
            else:
                return {
                    "success": True,
                    "action": "waiting_screenshots",
                    "reason": analysis["reason"],
                    "challenge_id": challenge_id,
                }

        if action == "settle_ready" or winner_id is not None or skip_window:
            if winner_id is None:
                winner_id = _determine_winner_from_scores(challenge)

            # AI when screenshots present (confirm / fill gaps)
            if (
                winner_id is None or _both_screenshots_present(challenge)
            ) and (
                challenge.get("screenshot_creator_url") or challenge.get("screenshot_opponent_url")
            ):
                ai = await verify_with_ai_vision(challenge)
                ai_meta = {
                    "verified_score": ai.get("verified_score"),
                    "confidence": ai.get("confidence"),
                    "winner_id": ai.get("winner_id"),
                }
                if ai.get("resolved"):
                    # Prefer AI winner when confidence high or scorelines inconclusive
                    if ai.get("winner_id") is not None and (
                        winner_id is None
                        or float(ai.get("confidence") or 0) >= AI_FAST_SETTLE_CONFIDENCE
                    ):
                        winner_id = ai.get("winner_id")
                    if ai.get("skip_dispute_window"):
                        skip_window = True
                    # AI draw
                    if ai.get("resolved") and ai.get("winner_id") is None and ai.get("verified_score"):
                        # draw scoreline like 1-1
                        if winner_id is None:
                            skip_window = bool(ai.get("skip_dispute_window"))

            # Still no winner and scores conflict path already handled
            if winner_id is None and analysis.get("scorelines_agree") is False:
                try:
                    await flag_dispute(challenge_id)
                except EscrowError as exc:
                    logger.warning("[Settlement] flag_dispute: %s", exc)
                _update_challenge(challenge_id, "disputed", ai_meta=ai_meta)
                return {"success": True, "action": "disputed", "challenge_id": challenge_id}

            # Draw is valid winner_id=None with agreeing scorelines
            if winner_id is None and not _both_scores_present(challenge) and not (
                ai_meta and ai_meta.get("verified_score")
            ):
                return {
                    "success": True,
                    "action": "skipped",
                    "reason": "cannot_determine_winner",
                    "challenge_id": challenge_id,
                }

            if not skip_window and not _dispute_window_elapsed(challenge):
                return {
                    "success": True,
                    "action": "waiting_dispute_window",
                    "challenge_id": challenge_id,
                    "winner_id": winner_id,
                }
        else:
            return {
                "success": True,
                "action": "skipped",
                "reason": analysis.get("reason") or action,
                "challenge_id": challenge_id,
            }

    try:
        tx_hash = await _execute_payout(challenge, winner_id)
    except EscrowError as exc:
        logger.exception("[Settlement] Payout failed for %s", challenge_id)
        raise SettlementError(f"payout failed: {exc}") from exc

    _update_challenge(
        challenge_id,
        "resolved",
        winner_id=winner_id,
        tx_hash=tx_hash,
        ai_meta=ai_meta,
    )
    await _notify_result(challenge, winner_id, tx_hash)
    await _award_play_points(challenge, winner_id, no_show=False)

    return {
        "success": True,
        "action": "resolved",
        "challenge_id": challenge_id,
        "winner_id": winner_id,
        "tx_hash": tx_hash,
    }


async def _award_play_points(
    challenge: dict,
    winner_id: Optional[str],
    *,
    no_show: bool = False,
) -> None:
    """Best-effort $PLAY awards + DM with $PLAY line (balances already in result notify)."""
    try:
        from gaming.src.backend.services.play_points import (
            award_match_play_points,
            format_play_award_line,
        )
        from gaming.src.bot.utils.notify import get_balance_snapshot, notify_user

        awards = await award_match_play_points(challenge, winner_id, no_show=no_show)
        for a in awards:
            pid = a.get("profile_id")
            if not pid:
                continue
            # PLAY award message is redundant if result notify already sent balances;
            # still send short PLAY line so streak is explicit.
            await notify_user(pid, format_play_award_line(a))
    except Exception:
        logger.exception("[Settlement] $PLAY award failed for %s", challenge.get("id"))


async def admin_resolve_challenge(
    challenge_id: str,
    admin_profile_id: str,
    winner_id: str,
    note: Optional[str] = None,
) -> dict:
    challenge = _load_challenge(challenge_id)
    if not challenge:
        raise SettlementError(f"Challenge {challenge_id} not found")

    if winner_id not in (challenge["creator_id"], challenge.get("opponent_id")):
        raise SettlementError("Winner must be one of the challenge participants")

    sb = _get_supabase()
    sb.schema("gaming").table("challenges").update(
        {
            "admin_resolved_by": admin_profile_id,
            "admin_resolution_note": note or "Manual admin resolution",
        }
    ).eq("id", challenge_id).execute()

    return await settle_challenge(challenge_id, admin_winner_id=winner_id)


async def settle_no_show(challenge_id: str, analysis: Optional[dict] = None) -> dict:
    """
    Settle when one player submitted proof and the other never reported (no-show).

    Priority:
      1. AI on reporter's screenshot (high confidence) → winner from AI + sides
      2. Reporter's home-away scoreline + sides → winner
      3. Else dispute (don't refund an honest winner with a photo)
    """
    from gaming.src.backend.services.match_report import (
        NO_SHOW_AI_CONFIDENCE,
        analyze_reports,
        winner_from_reporter_claim,
    )
    from gaming.src.bot.utils.notify import notify_user
    from gaming.src.bot.utils.text import bold, code
    from gaming.src.backend.services.match_codes import display_code

    challenge = _load_challenge(challenge_id)
    if not challenge:
        raise SettlementError(f"Challenge {challenge_id} not found")
    if challenge.get("status") == "resolved":
        return {"success": True, "action": "skipped", "reason": "already_resolved"}
    match_code = display_code(challenge)

    analysis = analysis or analyze_reports(challenge)
    reporter = analysis.get("reporter")  # "creator" | "opponent"
    if not reporter:
        return {"success": False, "action": "skipped", "reason": "not_one_sided"}

    ai_meta: Optional[dict] = None
    winner_id: Optional[str] = None

    # 1) AI on the single screenshot
    ai = await verify_with_ai_vision(challenge)
    conf = float(ai.get("confidence") or 0)
    ai_meta = {
        "verified_score": ai.get("verified_score"),
        "confidence": conf,
        "winner_id": ai.get("winner_id"),
        "reason": f"no_show:{ai.get('reason')}",
    }
    if ai.get("resolved") and conf >= NO_SHOW_AI_CONFIDENCE:
        winner_id = ai.get("winner_id")
        # If AI only gives scoreline without profile mapping, use claim sides
        if winner_id is None and ai.get("verified_score"):
            winner_id = winner_from_reporter_claim(challenge, reporter)

    # 2) Fall back to reporter's claimed scoreline + sides
    if winner_id is None:
        winner_id = winner_from_reporter_claim(challenge, reporter)

    if winner_id is None and ai.get("resolved") and conf >= NO_SHOW_AI_CONFIDENCE:
        # AI draw
        winner_id = None  # refund path
        try:
            tx_hash = await _execute_payout(challenge, None)
            _update_challenge(challenge_id, "resolved", winner_id=None, tx_hash=tx_hash, ai_meta=ai_meta)
            await _notify_result(challenge, None, tx_hash)
            await _award_play_points(challenge, None, no_show=False)
            return {
                "success": True,
                "action": "resolved_no_show_draw",
                "challenge_id": challenge_id,
                "tx_hash": tx_hash,
            }
        except EscrowError as exc:
            raise SettlementError(f"no-show draw payout failed: {exc}") from exc

    if winner_id is None:
        # Cannot decide fairly — dispute, don't cancel
        try:
            await flag_dispute(challenge_id)
        except EscrowError as exc:
            logger.warning("[Settlement] no-show flag_dispute: %s", exc)
        _update_challenge(challenge_id, "disputed", ai_meta=ai_meta)
        from gaming.src.backend.services.match_codes import support_id_block

        msg = (
            f"⚠️ Match {code(match_code)}: opponent no-show, but we could not "
            f"auto-verify the winner from one screenshot.\n"
            f"Marked <b>disputed</b> for admin review.\n"
            f"AI conf={conf:.0%}\n\n"
            f"{support_id_block(challenge)}"
        )
        await notify_user(challenge["creator_id"], msg)
        if challenge.get("opponent_id"):
            await notify_user(challenge["opponent_id"], msg)
        return {
            "success": True,
            "action": "disputed_no_show",
            "challenge_id": challenge_id,
            "confidence": conf,
        }

    # 3) Pay the winner
    try:
        # Ensure status allows resolve
        if challenge.get("status") not in ("submitted", "disputed", "locked", "playing"):
            _update_challenge(challenge_id, "submitted", winner_id=winner_id)
        else:
            _update_challenge(challenge_id, challenge.get("status") or "submitted", winner_id=winner_id)

        # resolve_match requires submitted/disputed
        challenge = _load_challenge(challenge_id) or challenge
        if challenge.get("status") not in ("submitted", "disputed"):
            _update_challenge(challenge_id, "submitted", winner_id=winner_id)

        tx_hash = await _execute_payout(challenge, winner_id)
    except EscrowError as exc:
        logger.exception("[Settlement] no-show payout failed %s", challenge_id)
        raise SettlementError(f"no-show payout failed: {exc}") from exc

    _update_challenge(
        challenge_id, "resolved", winner_id=winner_id, tx_hash=tx_hash, ai_meta=ai_meta
    )
    await _notify_result(challenge, winner_id, tx_hash)
    await _award_play_points(challenge, winner_id, no_show=True)

    silent = analysis.get("silent_id")
    if silent:
        await notify_user(
            silent,
            f"⌛ You did not report on {code(match_code)} in time.\n"
            f"Match settled as a <b>no-show</b> using your opponent's proof.\n"
            f"Winner paid out.",
        )
    await notify_user(
        winner_id,
        f"✅ Opponent no-show on {code(match_code)}.\n"
        f"Your proof was verified — payout sent.",
    )

    return {
        "success": True,
        "action": "resolved_no_show",
        "challenge_id": challenge_id,
        "winner_id": winner_id,
        "tx_hash": tx_hash,
        "confidence": conf,
    }


async def settle_all_pending() -> list[dict]:
    """Poll and settle every submitted challenge that is ready."""
    challenges = _load_submitted_challenges()
    results = []
    for challenge in challenges:
        try:
            result = await settle_challenge(challenge["id"])
            results.append(result)
        except Exception as exc:
            logger.exception("[Settlement] Failed to settle %s", challenge["id"])
            results.append({"success": False, "challenge_id": challenge["id"], "error": str(exc)})
    return results
