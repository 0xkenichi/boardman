#!/bin/bash
# sideQuest Bot Monitor - Quick Setup & Run Script
# This script helps you set up and run the bot status monitor

set -e

echo "=========================================="
echo " sideQuest Bot Monitor - Setup"
echo "=========================================="
echo ""

# Check if venv exists
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
fi

# Activate venv
source .venv/bin/activate

# Install monitor dependencies only (not full stack)
echo "Installing monitor dependencies (pyrogram, tgcrypto, pytz)..."
pip install --quiet pyrogram==2.0.106 tgcrypto==1.2.5 pytz==2024.1 python-dotenv

echo ""
echo "✅ Dependencies installed"
echo ""
echo "=========================================="
echo " STEP 1: Generate Session String"
echo "=========================================="
echo "Run: python gen_monitor_session.py"
echo ""
echo "You'll need:"
echo "  - TELEGRAM_API_ID from https://my.telegram.org/apps"
echo "  - TELEGRAM_API_HASH from https://my.telegram.org/apps"
echo ""
echo "Follow the prompts and copy the session string."
echo ""

echo "=========================================="
echo " STEP 2: Configure .env"
echo "=========================================="
echo "Fill in these variables in backend/.env or root .env:"
echo ""
echo "  TELEGRAM_API_ID=your_id"
echo "  TELEGRAM_API_HASH=your_hash"
echo "  MONITOR_SESSION_STRING=your_session_string"
echo "  MONITOR_BOT_USERNAME=your_bot_username  # without @"
echo "  MONITOR_CHANNEL_ID=-1001234567890"
echo "  MONITOR_MESSAGE_ID=      # optional - leave empty to auto-create"
echo "  MONITOR_ADMIN_IDS=123456789 987654321  # optional"
echo "  MONITOR_TIME_ZONE=UTC"
echo ""
echo "=========================================="
echo " STEP 3: Get Channel & Message IDs"
echo "=========================================="
echo "1. Create a private Telegram channel"
echo "2. Add the monitor user (from session) as admin"
echo "3. Add @username_to_id_bot to get channel ID"
echo "4. Send any message in channel; forward it to get Message ID"
echo "   (or leave MONITOR_MESSAGE_ID empty - monitor will create one)"
echo ""
echo "=========================================="
echo " STEP 4: Start the Monitor"
echo "=========================================="
echo "Run: python start_monitor.py"
echo ""
echo "The monitor will:"
echo "  - Post status in your channel"
echo "  - Update every 105 minutes"
echo "  - Alert admins if bot goes down"
echo ""
echo "To run in background (Linux/Mac):"
echo "  nohup python start_monitor.py > monitor.log 2>&1 &"
echo ""
echo "=========================================="
echo "For detailed docs, see backend/BOT_MONITOR_README.md"
echo "=========================================="
