#!/usr/bin/env python3
"""
sideQuest Bot Monitor - Startup Script
Runs the bot status monitor continuously
"""

import asyncio
import logging
from gaming.src.backend.bot_monitor import BotMonitor, main as monitor_main

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

if __name__ == "__main__":
    try:
        asyncio.run(monitor_main())
    except KeyboardInterrupt:
        logger.info("👋 Monitor stopped by user")
    except Exception as e:
        logger.critical(f"❌ Fatal error: {e}", exc_info=True)
        exit(1)
