#!/usr/bin/env python3
"""
Bot watchdog - continuously monitors bot health and restarts if needed
Run this as: python3 backend/bot_watchdog.py
"""

import os
import sys
import time
import subprocess
import logging
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] WATCHDOG — %(message)s",
)
logger = logging.getLogger(__name__)

BOT_DIR = Path(__file__).parent
BOT_SCRIPT = BOT_DIR / "main.py"
PYTHON_BIN = sys.executable
PID_FILE = BOT_DIR / "bot.pid"
LOG_FILE = BOT_DIR / "bot.log"

def get_bot_pid():
    if PID_FILE.exists():
        pid = int(PID_FILE.read_text().strip())
        # Check if process is actually running
        try:
            os.kill(pid, 0)
            return pid
        except OSError:
            return None
    return None

def start_bot():
    """Start the bot process"""
    if get_bot_pid():
        logger.warning("Bot already running")
        return get_bot_pid()
    
    env = os.environ.copy()
    env["USE_POLLING"] = "true"
    
    with open(LOG_FILE, "a") as log_f:
        proc = subprocess.Popen(
            [PYTHON_BIN, "-u", str(BOT_SCRIPT)],
            cwd=BOT_DIR,
            stdout=log_f,
            stderr=subprocess.STDOUT,
            env=env,
        )
    
    PID_FILE.write_text(str(proc.pid))
    logger.info(f"Bot started (PID: {proc.pid})")
    return proc.pid

def stop_bot():
    """Stop the bot process"""
    pid = get_bot_pid()
    if pid:
        try:
            os.kill(pid, 15)  # SIGTERM
            time.sleep(3)
            # Force kill if still alive
            try:
                os.kill(pid, 0)
                os.kill(pid, 9)  # SIGKILL
            except OSError:
                pass
            PID_FILE.unlink(missing_ok=True)
            logger.info(f"Bot stopped (PID: {pid})")
            return True
        except Exception as e:
            logger.error(f"Failed to stop bot: {e}")
    return False

def check_bot_health():
    """Check if bot is responding by checking log activity"""
    if not LOG_FILE.exists():
        return False
    
    # Check if log has been updated in last 60 seconds
    mtime = LOG_FILE.stat().st_mtime
    if time.time() - mtime > 60:
        logger.warning("Bot log not updated in 60s - may be hung")
        return False
    
    # Check for recent errors in log
    try:
        with open(LOG_FILE) as f:
            lines = f.readlines()[-50:]  # Last 50 lines
            for line in lines:
                if "Fatal error" in line or "Traceback" in line:
                    logger.error(f"Found error in bot log: {line.strip()}")
                    return False
    except Exception:
        pass
    
    return True

def main():
    logger.info("Watchdog starting...")
    
    while True:
        try:
            pid = get_bot_pid()
            
            if pid is None:
                logger.warning("Bot not running - restarting...")
                pid = start_bot()
                time.sleep(10)  # Give it time to start
            elif not check_bot_health():
                logger.warning(f"Bot (PID {pid}) unhealthy - restarting...")
                stop_bot()
                time.sleep(2)
                pid = start_bot()
                time.sleep(10)
            else:
                # Bot is healthy - check again in 30s
                pass
            
            time.sleep(30)
            
        except KeyboardInterrupt:
            logger.info("Watchdog stopped by user")
            stop_bot()
            break
        except Exception as e:
            logger.error(f"Watchdog error: {e}")
            time.sleep(10)

if __name__ == "__main__":
    main()
