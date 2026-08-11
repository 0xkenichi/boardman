"""Background jobs: expire, settle, nudge missing reports, timeout one-sided matches."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from backend.supabase_client import get_supabase

logger = logging.getLogger(__name__)


def _get_supabase():
    return get_supabase()


async def expire_challenges() -> int:
    """Flip open challenges past expires_at → expired."""
    sb = _get_supabase()
    now = datetime.now(timezone.utc).isoformat()
    try:
        result = (
            sb.schema("gaming")
            .table("challenges")
            .update({"status": "expired"})
            .eq("status", "open")
            .lt("expires_at", now)
            .execute()
        )
        expired = len(result.data) if result.data else 0
        if expired:
            logger.info("[Expiry] Expired %s stale challenge(s)", expired)
        return expired
    except Exception:
        logger.exception("[Expiry] Failed to expire stale challenges")
        return 0


async def settle_pending_challenges() -> int:
    """Run settlement worker for submitted / ready challenges."""
    try:
        from gaming.src.backend.services.clawstation_settlement import settle_all_pending

        results = await settle_all_pending()
        resolved = sum(1 for r in results if r.get("action") == "resolved")
        if results:
            logger.info(
                "[SettlementJob] processed=%s resolved=%s",
                len(results),
                resolved,
            )
        return resolved
    except Exception:
        logger.exception("[SettlementJob] Failed")
        return 0


async def nudge_and_timeout_reports() -> dict:
    """
    • Nudge silent player when one side reported.
    • No-show: reporter has proof + silent past NO_SHOW_HOURS → settle for
      winner from proof (AI), so losers can't dodge by not reporting.
    • Abandon: nobody reported (or no proof) past REPORT_TIMEOUT_HOURS → refund.
    """
    from gaming.src.backend.services.match_report import (
        abandon_due,
        analyze_reports,
        load_active_matches,
        mark_nudge_sent,
        no_show_due,
        should_nudge,
    )
    from gaming.src.backend.services.clawstation_settlement import settle_no_show
    from gaming.src.bot.utils.notify import notify_user
    from gaming.src.bot.utils.text import code

    nudged = 0
    no_shows = 0
    abandoned = 0

    try:
        matches = await load_active_matches()
    except Exception:
        logger.exception("[ReportJob] load failed")
        return {"nudged": 0, "no_shows": 0, "abandoned": 0}

    for ch in matches:
        cid = ch["id"]
        status = ch.get("status")
        if status not in ("playing", "locked", "submitted"):
            continue

        analysis = analyze_reports(ch)

        # ── No-show settle (winner reported, loser ghosted) ──────────────
        ns = no_show_due(ch)
        if ns:
            try:
                result = await settle_no_show(cid, ns)
                logger.info("[ReportJob] no-show %s → %s", cid, result.get("action"))
                no_shows += 1
            except Exception:
                logger.exception("[ReportJob] no-show settle failed %s", cid)
            continue

        # ── True abandon (nobody useful reported) → refund ───────────────
        if abandon_due(ch):
            try:
                from gaming.src.backend.services.clawstation_escrow import (
                    EscrowError,
                    cancel_match,
                )

                if ch.get("creator_lock_tx_id") or ch.get("opponent_lock_tx_id"):
                    try:
                        await cancel_match(cid)
                    except EscrowError as exc:
                        logger.warning("[ReportJob] cancel failed %s: %s", cid, exc)
                        _get_supabase().schema("gaming").table("challenges").update(
                            {"status": "cancelled"}
                        ).eq("id", cid).execute()
                else:
                    _get_supabase().schema("gaming").table("challenges").update(
                        {"status": "cancelled"}
                    ).eq("id", cid).execute()

                msg = (
                    f"⌛ Match {code(cid)} abandoned (no valid reports).\n"
                    f"Stakes refunded.\n{analysis['reason']}"
                )
                await notify_user(ch["creator_id"], msg)
                if ch.get("opponent_id"):
                    await notify_user(ch["opponent_id"], msg)
                abandoned += 1
            except Exception:
                logger.exception("[ReportJob] abandon failed %s", cid)
            continue

        # ── Nudge silent player ──────────────────────────────────────────
        if should_nudge(ch):
            try:
                action = analysis["action"]
                game_id = str(ch.get("game") or ch.get("game_type") or "")
                try:
                    from gaming.src.backend.services.game_catalog import (
                        how_to_report_short,
                        is_binary_outcome,
                    )

                    howto = how_to_report_short(game_id)
                    cap = "W" if is_binary_outcome(game_id) else "5-3"
                except Exception:
                    howto = "Tap <b>Submit result</b> and follow the on-screen instructions."
                    cap = "5-3 or W/L"

                if action == "wait_opponent" and ch.get("opponent_id"):
                    await notify_user(
                        ch["opponent_id"],
                        f"⏰ Friendly reminder on {code(cid)}:\n"
                        f"Your opponent already reported.\n\n"
                        f"{howto}\n\n"
                        f"Or: <code>/submit_score {cid} {cap}</code>\n\n"
                        f"⚠️ If you stay silent, they can win by <b>no-show</b>.",
                    )
                    await notify_user(
                        ch["creator_id"],
                        f"📨 We reminded your opponent on {code(cid)}.\n"
                        f"If they stay silent, your proof can settle the match.",
                    )
                    await mark_nudge_sent(cid)
                    nudged += 1
                elif action == "wait_creator":
                    await notify_user(
                        ch["creator_id"],
                        f"⏰ Friendly reminder on {code(cid)}:\n"
                        f"Your opponent already reported.\n\n"
                        f"{howto}\n\n"
                        f"Or: <code>/submit_score {cid} {cap}</code>\n\n"
                        f"⚠️ Silence can mean a no-show loss.",
                    )
                    if ch.get("opponent_id"):
                        await notify_user(
                            ch["opponent_id"],
                            f"📨 We reminded the challenger on {code(cid)}.",
                        )
                    await mark_nudge_sent(cid)
                    nudged += 1
                elif action == "wait_screenshots":
                    photo_nudge = (
                        f"📸 Please send your final-screen photo for {code(cid)}.\n\n"
                        f"{howto}\n\n"
                        f"Or: <code>/submit_score {cid} {cap}</code>"
                    )
                    if analysis.get("missing_creator_shot"):
                        await notify_user(ch["creator_id"], photo_nudge)
                    if analysis.get("missing_opponent_shot") and ch.get("opponent_id"):
                        await notify_user(ch["opponent_id"], photo_nudge)
                    await mark_nudge_sent(cid)
                    nudged += 1
            except Exception:
                logger.exception("[ReportJob] nudge failed for %s", cid)

    if nudged or no_shows or abandoned:
        logger.info(
            "[ReportJob] nudged=%s no_shows=%s abandoned=%s",
            nudged,
            no_shows,
            abandoned,
        )
    return {"nudged": nudged, "no_shows": no_shows, "abandoned": abandoned}


async def watch_wallet_activity() -> dict:
    """Poll on-chain USDC and DM players on deposits / unexplained outflows."""
    try:
        from gaming.src.backend.services.wallet_activity import watch_all_wallets

        return await watch_all_wallets()
    except Exception:
        logger.exception("[WalletWatch] tick failed")
        return {}


async def watch_funding_rails() -> dict:
    """Stellar Horizon (+ optional Avalanche) deposit detection for top-ups."""
    out: dict = {}
    try:
        from gaming.src.backend.services.stellar_watcher import watch_stellar_deposits

        out["stellar"] = await watch_stellar_deposits()
    except Exception:
        logger.exception("[RailWatch] stellar tick failed")
        out["stellar"] = {"error": "exception"}
    try:
        from gaming.src.backend.services.avalanche_watcher import watch_avalanche_deposits

        out["avalanche"] = await watch_avalanche_deposits()
    except Exception:
        logger.exception("[RailWatch] avalanche tick failed")
        out["avalanche"] = {"error": "exception"}
    return out


def start_expiry_scheduler(interval_minutes: int = 2) -> AsyncIOScheduler:
    """Start async scheduler for expiry + settlement + report nudges + wallet watch."""
    import os

    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        expire_challenges,
        "interval",
        minutes=interval_minutes,
        id="clawstation_challenge_expiry",
        replace_existing=True,
    )
    scheduler.add_job(
        settle_pending_challenges,
        "interval",
        minutes=max(1, interval_minutes),
        id="clawstation_settlement",
        replace_existing=True,
    )
    scheduler.add_job(
        nudge_and_timeout_reports,
        "interval",
        minutes=max(2, interval_minutes),
        id="clawstation_report_nudge",
        replace_existing=True,
    )
    # Deposit / withdrawal detection. Default 120s (was 45s — starved Telegram handlers).
    # Set WALLET_WATCH_INTERVAL_SEC=0 to disable.
    wallet_sec = int(os.getenv("WALLET_WATCH_INTERVAL_SEC", "120"))
    if wallet_sec > 0:
        scheduler.add_job(
            watch_wallet_activity,
            "interval",
            seconds=max(60, wallet_sec),
            id="clawstation_wallet_watch",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
            misfire_grace_time=30,
        )
    # Stellar memo deposits (+ avax stub). Default 90s. Set STELLAR_WATCH_ENABLED=0 to skip.
    rail_sec = int(os.getenv("FUNDING_RAIL_WATCH_SEC", "90"))
    if rail_sec > 0:
        scheduler.add_job(
            watch_funding_rails,
            "interval",
            seconds=max(45, rail_sec),
            id="boardman_funding_rail_watch",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
            misfire_grace_time=30,
        )
    scheduler.start()
    logger.info(
        "[Jobs] Scheduler started (expiry+settlement+nudge every %sm, wallet watch every %ss, rails every %ss)",
        interval_minutes,
        max(60, wallet_sec) if wallet_sec > 0 else 0,
        max(45, rail_sec) if rail_sec > 0 else 0,
    )
    return scheduler
