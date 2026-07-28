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

# Import canonical bot startup from main service
from main import start_bot as main_start_bot

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

async def run_bot():
    """Run the Telegram bot using the canonical dispatcher from main.py."""
    logger.info("🚀 Starting sideQuest Telegram Bot...")
    await main_start_bot()

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