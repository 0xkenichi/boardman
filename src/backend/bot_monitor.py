"""
sideQuest Bot Status Monitor
────────────────────────────────────────────────────────────────────────────────
Continuously monitors the sideQuest Telegram bot to ensure it's running and
responding to messages. Sends alerts if the bot goes down.

Based on: https://github.com/teletips/powerful-botstatus-teletips

Usage:
    python bot_monitor.py

Environment Variables:
    TELEGRAM_API_ID           - Telegram API ID (from my.telegram.org)
    TELEGRAM_API_HASH         - Telegram API Hash (from my.telegram.org)
    MONITOR_SESSION_STRING    - Pyrogram session string (generated once)
    MONITOR_BOT_USERNAME      - Your bot's username (without @)
    MONITOR_CHANNEL_ID        - Telegram channel/group ID (e.g., -1001234567890)
    MONITOR_MESSAGE_ID        - Message ID to edit in the channel
    MONITOR_ADMIN_IDS         - Space-separated admin user IDs for alerts
    MONITOR_TIME_ZONE         - Timezone (default: UTC)
    MONITOR_CHECK_INTERVAL    - Check interval in seconds (default: 6300 = 105 min)
    MONITOR_RESPONSE_WAIT     - Wait time for bot response in seconds (default: 10)
"""

import os
import sys
import asyncio
import datetime
import logging
from dotenv import load_dotenv
from pyrogram import Client
from pyrogram.errors import FloodWait
import pytz

# Load environment variables from .env file
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)


class BotMonitor:
    """Monitors a Telegram bot's health status"""

    def __init__(self):
        self.api_id = int(os.getenv("TELEGRAM_API_ID", "0"))
        self.api_hash = os.getenv("TELEGRAM_API_HASH", "")
        self.session_string = os.getenv("MONITOR_SESSION_STRING", "")
        self.bot_username = os.getenv("MONITOR_BOT_USERNAME", "").replace("@", "").strip()
        self.channel_id = int(os.getenv("MONITOR_CHANNEL_ID", "0"))
        self.message_id = int(os.getenv("MONITOR_MESSAGE_ID", "0"))
        self.admin_ids = [
            int(i.strip()) for i in os.getenv("MONITOR_ADMIN_IDS", "").split()
            if i.strip()
        ]
        self.time_zone = os.getenv("MONITOR_TIME_ZONE", "UTC")
        # Check interval in seconds (default: 6300 = 105 minutes)
        self.check_interval = int(os.getenv("MONITOR_CHECK_INTERVAL", "6300"))
        # Response wait time in seconds (default: 10)
        self.response_wait = int(os.getenv("MONITOR_RESPONSE_WAIT", "10"))

        if not all([self.api_id, self.api_hash, self.session_string, self.bot_username]):
            raise ValueError(
                "Missing required environment variables: "
                "TELEGRAM_API_ID, TELEGRAM_API_HASH, MONITOR_SESSION_STRING, MONITOR_BOT_USERNAME"
            )

        self.app = Client(
            name="sidequest_bot_monitor",
            api_id=self.api_id,
            api_hash=self.api_hash,
            session_string=self.session_string,
        )

    async def check_bot(self) -> bool:
        """Check if the bot is responding by sending a test message"""
        try:
            # Send a test message to the bot
            test_msg = await self.app.send_message(self.bot_username, "/start")
            await asyncio.sleep(self.response_wait)  # Wait for response

            # Get most recent message in bot chat
            history = self.app.get_chat_history(self.bot_username, limit=1)
            last_msg_id = None
            async for msg in history:
                last_msg_id = msg.id
                break

            if last_msg_id is None:
                return False

            # If bot responded, its message ID will be different from our sent message
            is_alive = test_msg.id != last_msg_id

            # Mark conversation as read
            await self.app.read_chat_history(self.bot_username)

            return is_alive

        except FloodWait as e:
            logger.warning(f"Flood wait: sleeping for {e.x} seconds")
            await asyncio.sleep(e.x)
            return False
        except Exception as e:
            logger.error(f"Error checking bot: {e}")
            return False

    def build_status_message(self, is_alive: bool, check_time: datetime.datetime) -> str:
        """Build the status message"""
        tz = pytz.timezone(self.time_zone)
        local_time = check_time.astimezone(tz)
        last_update = local_time.strftime("%d %b %Y at %I:%M %p")

        status_emoji = "✅" if is_alive else "❌"
        status_text = "Alive" if is_alive else "Down"

        message = (
            f"📈 | **Real-Time Bot Status**\n\n"
            f"🤖  @{self.bot_username}\n"
            f"        └ **{status_text}** {status_emoji}\n\n"
            f"✔️ Last checked on: {last_update} ({self.time_zone})\n\n"
            f"<i>♻️ Refreshes automatically every 105 minutes</i>"
        )
        return message

    async def send_alert(self, is_alive: bool):
        """Send alert to admins if bot is down"""
        if not self.admin_ids:
            return

        try:
            if is_alive:
                # Optional: send recovery message
                alert_text = f"✅ **Bot is back online!**\n\n@{self.bot_username} is responding again."
            else:
                alert_text = f"🚨 **Beep! Beep! @{self.bot_username} is down!** ❌\n\nPlease check the bot immediately."

            for admin_id in self.admin_ids:
                try:
                    await self.app.send_message(admin_id, alert_text)
                except Exception as e:
                    logger.error(f"Failed to alert admin {admin_id}: {e}")

        except Exception as e:
            logger.error(f"Error sending alert: {e}")

    async def update_channel_status(self, message: str):
        """Update or create the status message in the channel"""
        try:
            if self.message_id and self.message_id > 0:
                try:
                    await self.app.edit_message_text(
                        chat_id=self.channel_id,
                        message_id=self.message_id,
                        text=message
                    )
                    logger.info(f"Updated status message {self.message_id}")
                    return
                except Exception as e:
                    logger.warning(f"Could not edit message {self.message_id}: {e}")
                    # Fall through to sending a new message
                    self.message_id = 0  # Reset to force creation

            # Create new status message
            sent = await self.app.send_message(
                chat_id=self.channel_id,
                text=message
            )
            self.message_id = sent.id
            logger.info(f"Created new status message {sent.id}")
            logger.info(f"⚠️  Set MONITOR_MESSAGE_ID={sent.id} in .env for persistent updates")

        except Exception as e:
            logger.error(f"Failed to update channel: {e}")

    async def run(self):
        """Main monitoring loop"""
        logger.info("🚀 Starting Bot Status Monitor...")
        logger.info(f"Monitoring: @{self.bot_username}")
        logger.info(f"Channel ID: {self.channel_id}")
        logger.info(f"Timezone: {self.time_zone}")

        async with self.app:
            logger.info("✅ Monitor connected to Telegram")

            while True:
                check_time = datetime.datetime.now(pytz.UTC)

                logger.info("Checking bot status...")
                is_alive = await self.check_bot()

                status_msg = self.build_status_message(is_alive, check_time)
                await self.update_channel_status(status_msg)

                # Send alert if down
                if not is_alive:
                    await self.send_alert(is_alive)

                logger.info(f"Bot status: {'✅ Alive' if is_alive else '❌ Down'}")

                # Wait before next check (default: 105 minutes)
                await asyncio.sleep(self.check_interval)


async def main():
    """Entry point"""
    try:
        monitor = BotMonitor()
        await monitor.run()
    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        logger.info("👋 Monitor stopped")
    except Exception as e:
        logger.critical(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
