# sideQuest Telegram Bot - Simple Health Check Server
# Runs alongside the bot to provide health checks for deployment platforms

import os
import logging
from aiohttp import web
import asyncio

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def health_check(request):
    """Simple health check endpoint"""
    return web.Response(text="OK", status=200)

async def start_health_server():
    """Start a simple health check server"""
    app = web.Application()
    app.router.add_get('/health', health_check)
    app.router.add_get('/', health_check)
    
    port = int(os.getenv("HEALTH_CHECK_PORT", "8080"))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    logger.info(f"🏥 Health check server started on port {port}")
    return runner

# This can be imported and run alongside the main bot

if __name__ == "__main__":
    asyncio.run(start_health_server())

if __name__ == "__main__":
    # For standalone testing
    async def main():
        runner = await start_health_server()
        try:
            # Keep running forever
            while True:
                await asyncio.sleep(3600)
        except KeyboardInterrupt:
            pass
        finally:
            await runner.cleanup()
    
    asyncio.run(main())