"""Entrypoint for the ClawStation Telegram bot."""
from __future__ import annotations

# Allow imports relative to repo root when running directly.
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

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
from gaming.src.bot.handlers import admin_safety  # noqa: E402
from gaming.src.bot.jobs.expiry import start_expiry_scheduler  # noqa: E402
from gaming.src.bot.utils.notify import set_bot  # noqa: E402

logger = logging.getLogger(__name__)


def _build_dispatcher() -> Dispatcher:
    dp = Dispatcher(storage=MemoryStorage())
    # Button-first UX (FSM) — register early for menu callbacks
    dp.include_router(simple_ui.router)
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
    ]
    await bot.set_my_commands(commands)


async def run_polling() -> None:
    """Run the bot in polling mode (default for local development)."""
    if not settings.BOT_TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN_CLAWSTATION or TELEGRAM_BOT_TOKEN must be set")

    bot = Bot(token=settings.BOT_TOKEN, default=DefaultBotProperties(parse_mode=settings.PARSE_MODE))
    set_bot(bot)
    dp = _build_dispatcher()
    scheduler = start_expiry_scheduler()

    try:
        # Avoid TelegramConflictError when a webhook is still registered.
        await bot.delete_webhook(drop_pending_updates=False)
        await _set_bot_commands(bot)
        me = await bot.get_me()
        logger.info("[Bot] Starting polling as @%s (id=%s)", me.username, me.id)
        await dp.start_polling(bot, allowed_updates=settings.ALLOWED_UPDATES)
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
        raise RuntimeError("TELEGRAM_BOT_TOKEN_CLAWSTATION or TELEGRAM_BOT_TOKEN must be set")

    bot = Bot(token=settings.BOT_TOKEN, default=DefaultBotProperties(parse_mode=settings.PARSE_MODE))
    set_bot(bot)
    dp = _build_dispatcher()
    scheduler = start_expiry_scheduler()

    await _set_bot_commands(bot)
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
