"""
Minimal Telegram webhook server for sideQuest
Run with: python telegram_webhook.py
"""

import os
import logging
import requests
from fastapi import FastAPI, Request
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not BOT_TOKEN:
    logger.warning("TELEGRAM_BOT_TOKEN not set - webhook will not work")

RESPONSES = {
    "/start": "🎮 *Welcome to sideQuest!*\n\nStake USDC, play games, and win real money.\n\nUse /help to see all commands.",
    "/help": "Available commands:\n/start - Welcome\n/wallet - Check balance\n/deposit - Get deposit address\n/withdraw - Withdraw USDC\n/challenge - Create a match\n/bets - Browse challenges\n/leaderboard - Top players",
    "/wallet": "Check your wallet balance",
    "/deposit": "Get your USDC deposit address",
    "/withdraw": "Withdraw USDC to your wallet",
    "/challenge": "Create or join a match",
    "/bets": "Browse open challenges",
    "/leaderboard": "View top players",
}

@app.post("/webhook/telegram")
@app.post("/webhook/telegram/{token}")
@app.get("/webhook/telegram")
async def telegram_webhook(request: Request, token: str = None):
    if token and token != BOT_TOKEN:
        return {"error": "Invalid token"}, 403
    
    try:
        body = await request.json()
        message = body.get("message", {})
        from_id = message.get("from", {}).get("id")
        text = message.get("text", "").strip()
        
        logger.info(f"[TELEGRAM] {from_id}: {text}")
        
        response_text = RESPONSES.get(text, "⚔️ *sideQuest*\n\nUse /start to begin!")
        
        if from_id and BOT_TOKEN:
            requests.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                json={"chat_id": from_id, "text": response_text, "parse_mode": "Markdown"},
                timeout=5
            )
        
        return {"ok": True}
    except Exception as e:
        logger.error(f"[TELEGRAM] Error: {e}")
        return {"ok": False}

@app.get("/")
async def root():
    return {"status": "ok", "service": "sideQuest-telegram-webhook"}

@app.get("/health")
async def health():
    return {"status": "healthy", "service": "telegram-webhook"}

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT") or os.getenv("API_PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)