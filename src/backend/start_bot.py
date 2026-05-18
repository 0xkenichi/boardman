#!/usr/bin/env python3
"""
sideQuest Telegram Bot Startup Script
Runs both the Telegram bot and a health check server for deployment platforms
"""

import os
import asyncio
import logging
from threading import Thread

# Import the health check server
from health_check import start_health_server

# Import bot components
from main import bot, dp
from aiogram import types

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

async def run_bot():
    """Run the Telegram bot"""
    logger.info("🚀 Starting sideQuest Telegram Bot...")
    
    # Delete any existing webhook to avoid conflicts when using polling
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        logger.info("✅ Cleared any existing webhook")
    except Exception as e:
        logger.warning(f"Failed to delete webhook: {e}")
    
    # Set bot commands
    await bot.set_my_commands([
        types.BotCommand(command="start",       description="🎮 Welcome & main menu"),
        types.BotCommand(command="help",        description="📖 Show all commands"),
        types.BotCommand(command="wallet",      description="💰 Check your balance"),
        types.BotCommand(command="deposit",     description="💳 Get USDC deposit address"),
        types.BotCommand(command="withdraw",    description="💸 Withdraw USDC"),
        types.BotCommand(command="fund",        description="🏦 Add funds to wallet"),
        types.BotCommand(command="challenge",   description="⚔️ Create/join a match"),
        types.BotCommand(command="bets",        description="🎯 Browse open challenges"),
        types.BotCommand(command="active",      description="🏃 Your active matches"),
        types.BotCommand(command="leaderboard", description="🏆 Top players"),
        types.BotCommand(command="profile",     description="👤 View your profile"),
        types.BotCommand(command="link_psn",    description="🎮 Link PlayStation account"),
        types.BotCommand(command="link_xbox",   description="🎯 Link Xbox account"),
        types.BotCommand(command="link_wallet", description="🔗 Link crypto wallet"),
        types.BotCommand(command="link_email",  description="📧 Link email for web app"),
    ])
    logger.info("✅ Bot commands registered")
    
    # Start polling
    logger.info("🔄 Starting long polling...")
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())

def run_health_server():
    """Run the health check server in a separate thread"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    async def start_server():
        runner = await start_health_server()
        try:
            # Keep the event loop running
            while True:
                await asyncio.sleep(3600)
        except KeyboardInterrupt:
            pass
        finally:
            await runner.cleanup()
    
    loop.run_until_complete(start_server())

if __name__ == "__main__":
    # Start health check server in background thread
    health_thread = Thread(target=run_health_server, daemon=True)
    health_thread.start()
    logger.info("🏥 Health check server started in background")
    
    # Run the bot in the main thread
    try:
        asyncio.run(run_bot())
    except KeyboardInterrupt:
        logger.info("👋 Bot stopped by user")
    except Exception as e:
        logger.critical(f"❌ Fatal error: {e}", exc_info=True)