#!/usr/bin/env python3
import asyncio
import os
os.environ['USE_POLLING'] = 'true'
from main import bot

async def test_bot():
    try:
        print(f"Bot token: {bot.token}")
        result = await bot.send_message(
            chat_id=6277067771, 
            text='🧪 Test message from bot diagnostic\\n\\nIf you see this, the bot can send messages!'
        )
        print(f'✅ Test message sent successfully: {result.message_id}')
        return True
    except Exception as e:
        print(f'❌ Failed to send test message: {e}')
        return False

if __name__ == "__main__":
    asyncio.run(test_bot())