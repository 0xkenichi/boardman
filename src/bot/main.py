"""Entrypoint for the ClawStation Telegram bot."""
from __future__ import annotations

# Allow imports relative to repo root when running directly.
import os
import sys
from pathlib import Path

# standalone: rematch/src/bot/main.py -> parents[2] = rematch root
# monorepo:   gaming/src/bot/main.py  -> parents[3] = sideQuest root
_here = Path(__file__).resolve()
for _root in (_here.parents[2], _here.parents[3]):
    _root_s = str(_root)
    if _root_s not in sys.path:
        sys.path.insert(0, _root_s)

import asyncio  # noqa: E402
import logging  # noqa: E402

from aiogram import Bot, Dispatcher  # noqa: E402
from aiogram.client.default import DefaultBotProperties  # noqa: E402
from aiogram.fsm.storage.memory import MemoryStorage  # noqa: E402
from aiogram.types import BotCommand  # noqa: E402

from gaming.src.bot.config import settings  # noqa: E402
from gaming.src.bot.handlers import balance, challenge, profile, proof, send, start, tx_password, profile_links  # noqa: E402
from gaming.src.bot.handlers import lock_stake  # noqa: E402
from gaming.src.bot.handlers import submit_score  # noqa: E402
from gaming.src.bot.handlers import dispute  # noqa: E402
from gaming.src.bot.handlers import simple_ui  # noqa: E402
from gaming.src.bot.handlers import fiat_topup  # noqa: E402
from gaming.src.bot.handlers import admin_safety  # noqa: E402
from gaming.src.bot.handlers import tournament  # noqa: E402
from gaming.src.bot.handlers import approvals  # noqa: E402
from gaming.src.bot.handlers import fallback  # noqa: E402
from gaming.src.bot.jobs.expiry import start_expiry_scheduler  # noqa: E402
from gaming.src.bot.utils.notify import set_bot  # noqa: E402

logger = logging.getLogger(__name__)


def _build_dispatcher() -> Dispatcher:
    dp = Dispatcher(storage=MemoryStorage())
    # Instant callback.answer + debounce double-taps (stops spinner / dual replies)
    from gaming.src.bot.middleware.ux_speed import UxCallbackMiddleware

    dp.callback_query.middleware(UxCallbackMiddleware())
    # Button-first UX (FSM) — register early for menu callbacks
    dp.include_router(simple_ui.router)
    dp.include_router(fiat_topup.router)
    dp.include_router(start.router)
    dp.include_router(balance.router)
    dp.include_router(profile.router)
    dp.include_router(challenge.router)
    dp.include_router(tx_password.router)
    dp.include_router(send.router)
    dp.include_router(profile_links.router)
    dp.include_router(lock_stake.router)
    # submit_score before proof so /submit_score photo captions hit AI path first
    dp.include_router(submit_score.router)
    dp.include_router(proof.router)
    dp.include_router(dispute.router)
    dp.include_router(admin_safety.router)
    dp.include_router(tournament.router)
    dp.include_router(approvals.router)
    # Last: catch anything unmatched so Telegram never gets silence
    dp.include_router(fallback.router)
    return dp


async def _set_bot_commands(bot: Bot) -> None:
    commands = [
        BotCommand(command="start", description="Open menu (buttons)"),
        BotCommand(command="howto", description="How to play — simple"),
        BotCommand(command="help", description="Help"),
        BotCommand(command="balance", description="Wallet · USDC"),
        BotCommand(command="profile", description="Your profile"),
        BotCommand(command="playbook", description="PLAY score"),
        BotCommand(command="withdraw", description="Withdraw USDC"),
        BotCommand(command="safety", description="Limits"),
        BotCommand(command="dispute", description="Flag a problem"),
        BotCommand(command="support_id", description="Support ID"),
        BotCommand(command="leaderboard", description="Leaderboard"),
        BotCommand(command="board", description="Public board"),
        BotCommand(command="tlist", description="Tournament cups"),
        BotCommand(command="approvals", description="Approvals: always / ask each time"),
        # /metrics and ops /tcreate are operator-only — not listed
    ]
    await bot.set_my_commands(commands)


async def _set_bot_branding(bot: Bot) -> None:
    """Name, descriptions, and menu button → Boardman site."""
    from gaming.src.bot.brand_assets import boardman_site_url
    from gaming.src.bot.telegram_env import telegram_bot_username

    site = boardman_site_url()
    uname = telegram_bot_username()
    short = "Boardman · skill 1v1s and live agent chess. Lock, play, settle."
    full = (
        "Boardman by sideQuest — digital boardman for humans and agents.\n"
        "Lock stake · play · settle. Watch Raja vs Nero live.\n\n"
        f"Site: {site}\n"
        f"Arena: {site}/agentic/arena.html\n"
        f"Leaderboard: {site}/leaderboard\n"
        f"Open: https://t.me/{uname}"
    )
    try:
        await bot.set_my_name(name="Boardman · sideQuest")
    except Exception:
        logger.debug("[Bot] set_my_name skipped", exc_info=True)
    try:
        await bot.set_my_short_description(short_description=short[:120])
    except Exception:
        logger.debug("[Bot] set_my_short_description skipped", exc_info=True)
    try:
        await bot.set_my_description(description=full[:512])
    except Exception:
        logger.debug("[Bot] set_my_description skipped", exc_info=True)
    try:
        from aiogram.types import MenuButtonWebApp, WebAppInfo

        await bot.set_chat_menu_button(
            menu_button=MenuButtonWebApp(
                text="Boardman",
                web_app=WebAppInfo(url=f"{site}/app"),
            )
        )
    except Exception:
        # Fallback: open site without mini-app if WebApp domain not configured
        try:
            from aiogram.types import MenuButtonCommands

            await bot.set_chat_menu_button(menu_button=MenuButtonCommands())
        except Exception:
            logger.debug("[Bot] set_chat_menu_button skipped", exc_info=True)


async def run_polling() -> None:
    """Run the bot in polling mode (default for local development)."""
    if not settings.BOT_TOKEN:
        raise RuntimeError(
            "TELEGRAM_BOT_TOKEN_BOARDMAN (or TELEGRAM_BOT_TOKEN_CLAWSTATION / TELEGRAM_BOT_TOKEN) must be set"
        )

    bot = Bot(token=settings.BOT_TOKEN, default=DefaultBotProperties(parse_mode=settings.PARSE_MODE))
    set_bot(bot)
    dp = _build_dispatcher()
    scheduler = start_expiry_scheduler()

    try:
        # Drop webhook + stale queue so laptop polling gets a clean stream.
        await bot.delete_webhook(drop_pending_updates=True)
        try:
            await _set_bot_commands(bot)
            await _set_bot_branding(bot)
        except Exception as exc:
            # Telegram rate-limits SetMyCommands — don't crash the whole container
            logger.warning("[Bot] setup branding skipped: %s", exc)
        me = await bot.get_me()
        logger.info("[Bot] Starting polling as @%s (id=%s)", me.username, me.id)
        # Only message + callbacks — avoids silent "not handled" for other update types
        allowed = settings.ALLOWED_UPDATES or ["message", "callback_query"]
        await dp.start_polling(bot, allowed_updates=allowed)
    finally:
        scheduler.shutdown(wait=False)
        await bot.session.close()
        logger.info("[Bot] Shutdown complete")


async def run_webhook(webhook_url: str, host: str = "0.0.0.0", port: int = 8080) -> None:
    """Run the bot as a Telegram webhook (production path).

    This is a documented code path.  A full aiohttp/FastAPI webhook server
    can be wired in here; polling is the default fallback.
    """
    if not settings.BOT_TOKEN:
        raise RuntimeError(
            "TELEGRAM_BOT_TOKEN_BOARDMAN (or TELEGRAM_BOT_TOKEN_CLAWSTATION / TELEGRAM_BOT_TOKEN) must be set"
        )

    bot = Bot(token=settings.BOT_TOKEN, default=DefaultBotProperties(parse_mode=settings.PARSE_MODE))
    set_bot(bot)
    dp = _build_dispatcher()
    scheduler = start_expiry_scheduler()

    await _set_bot_commands(bot)
    await _set_bot_branding(bot)
    await bot.set_webhook(
        url=webhook_url,
        allowed_updates=settings.ALLOWED_UPDATES,
    )
    logger.info("[Bot] Webhook set to %s", webhook_url)

    try:
        # Minimal webhook server using aiogram's aiohttp helper.  In production
        # this is usually replaced by a FastAPI/ASGI mount.
        from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
        from aiohttp import web

        app = web.Application()
        webhook_handler = SimpleRequestHandler(dispatcher=dp, bot=bot)
        webhook_handler.register(app, path="/webhook")
        setup_application(app, dp, bot=bot)

        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, host, port)
        await site.start()
        logger.info("[Bot] Webhook server listening on %s:%s", host, port)

        # Keep running until interrupted.
        stop_event = asyncio.Event()
        await stop_event.wait()
    finally:
        scheduler.shutdown(wait=False)
        await bot.session.close()
        logger.info("[Bot] Shutdown complete")


def main() -> None:
    """CLI entrypoint."""
    logging.basicConfig(
        level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    if settings.use_webhook:
        asyncio.run(
            run_webhook(
                settings.WEBHOOK_URL,  # type: ignore[arg-type]
                host=settings.WEBHOOK_HOST,
                port=settings.WEBHOOK_PORT,
            )
        )
    else:
        if settings.WEBHOOK_URL and settings.BOT_MODE != "webhook":
            logging.getLogger(__name__).info(
                "[Bot] WEBHOOK_URL is set but CLAWSTATION_BOT_MODE=%s — using polling",
                settings.BOT_MODE,
            )
        asyncio.run(run_polling())


if __name__ == "__main__":
    main()
