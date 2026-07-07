#!/bin/bash
# Quick setup and run for bot monitor
# Works on macOS/Linux

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=========================================="
echo " sideQuest Bot Monitor - Quick Setup"
echo "=========================================="
echo ""

# Check for venv12, create if missing
if [ ! -d ".venv12" ]; then
    echo "Creating Python 3.11 virtual environment..."
    python3.11 -m venv .venv12 2>/dev/null || python3 -m venv .venv12
fi

# Activate
source .venv12/bin/activate

# Install deps
echo "Installing dependencies..."
pip install --quiet pyrogram==2.0.106 tgcrypto==1.2.5 pytz==2024.1 python-dotenv

echo ""
echo "✅ Ready!"
echo ""
echo "=========================================="
echo " STEP 1: Generate Session String"
echo "=========================================="
echo "Command:"
echo "  source .venv12/bin/activate && python gen_monitor_session.py"
echo ""
echo "You'll need:"
echo "  • API_ID & API_HASH from https://my.telegram.org/apps"
echo "  • Your phone number"
echo ""
echo "Copy the session string it outputs."
echo ""
echo "=========================================="
echo " STEP 2: Configure .env"
echo "=========================================="
echo "Edit backend/.env or .env and add:"
echo ""
echo "  TELEGRAM_API_ID=your_api_id"
echo "  TELEGRAM_API_HASH=your_api_hash"
echo "  MONITOR_SESSION_STRING=the_session_string_you_got"
echo "  MONITOR_BOT_USERNAME=your_bot_username   # without @"
echo "  MONITOR_CHANNEL_ID=-1001234567890        # your private channel"
echo "  MONITOR_MESSAGE_ID=                      # optional"
echo "  MONITOR_ADMIN_IDS=123456789              # optional, space-separated"
echo "  MONITOR_TIME_ZONE=UTC or Africa/Lagos"
echo ""
echo "=========================================="
echo " STEP 3: Get Channel ID & Optional Message ID"
echo "=========================================="
echo "1. Create a private Telegram channel"
echo "2. Add @username_to_id_bot → it replies with channel ID"
echo "3. (Optional) Send any message in channel; forward it to get Message ID"
echo ""
echo "=========================================="
echo " STEP 4: Run the Monitor"
echo "=========================================="
echo "Command:"
echo "  source .venv12/bin/activate && python start_monitor.py"
echo ""
echo "Or to run in background:"
echo "  nohup source .venv12/bin/activate && python start_monitor.py > monitor.log 2>&1 &"
echo ""
echo "=========================================="
echo "Docs: backend/BOT_MONITOR_README.md"
echo "=========================================="
