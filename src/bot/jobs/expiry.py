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
                if action == "wait_opponent" and ch.get("opponent_id"):
                    await notify_user(
                        ch["opponent_id"],
                        f"⏰ Reminder: your opponent already reported on {code(cid)}.\n"
                        f"Send your FT <b>photo</b> with caption:\n"
                        f"<code>/submit_score {cid} 5-3</code>\n\n"
                        f"⚠️ If you don't report in time, they can win by "
                        f"<b>no-show</b> (their screenshot + AI).",
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
                        f"⏰ Reminder: your opponent already reported on {code(cid)}.\n"
                        f"Send FT photo caption:\n"
                        f"<code>/submit_score {cid} 5-3</code>\n\n"
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
                    if analysis.get("missing_creator_shot"):
                        await notify_user(
                            ch["creator_id"],
                            f"📸 Please attach a FT photo for {code(cid)}:\n"
                            f"<code>/submit_score {cid} 5-3</code>",
                        )
                    if analysis.get("missing_opponent_shot") and ch.get("opponent_id"):
                        await notify_user(
                            ch["opponent_id"],
                            f"📸 Please attach a FT photo for {code(cid)}:\n"
                            f"<code>/submit_score {cid} 5-3</code>",
                        )
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
    # Deposit / withdrawal detection (balance poll). Default 45s.
    wallet_sec = int(os.getenv("WALLET_WATCH_INTERVAL_SEC", "45"))
    scheduler.add_job(
        watch_wallet_activity,
        "interval",
        seconds=max(20, wallet_sec),
        id="clawstation_wallet_watch",
        replace_existing=True,
        # Don't stack ticks if RPC is slow
        max_instances=1,
        coalesce=True,
    )
    scheduler.start()
    logger.info(
        "[Jobs] Scheduler started (expiry+settlement+nudge every %sm, wallet watch every %ss)",
        interval_minutes,
        max(20, wallet_sec),
    )
    return scheduler
