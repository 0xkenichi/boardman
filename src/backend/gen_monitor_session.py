"""
Generate Pyrogram Session String for Bot Monitor
────────────────────────────────────────────────────────────────────────────────
Run this script once to generate a session string for the monitor bot.

1. Install required package: pip install pyrogram tgcrypto
2. Run: python gen_monitor_session.py
3. Enter your API_ID and API_HASH from https://my.telegram.org/apps
4. Follow the login prompts (phone number, verification code)
5. Copy the session string into your .env file as MONITOR_SESSION_STRING

Note: The session string is tied to a user account (not a bot). This user account
will be used to monitor your bot. The user account must be able to message your bot.
"""

import asyncio
import os
from pyrogram import Client

async def generate_session():
    print("=" * 60)
    print("Bot Monitor Session Generator")
    print("=" * 60)

    # Get credentials from environment or prompt
    api_id = os.getenv("TELEGRAM_API_ID") or input("Enter API_ID: ").strip()
    api_hash = os.getenv("TELEGRAM_API_HASH") or input("Enter API_HASH: ").strip()

    if not api_id or not api_hash:
        print("\n❌ Error: API_ID and API_HASH are required.")
        print("Get them from: https://my.telegram.org/apps")
        return

    try:
        api_id = int(api_id)
    except ValueError:
        print("❌ Error: API_ID must be a number")
        return

    # Create client and generate session
    app = Client(
        name="sidequest_monitor_session",
        api_id=api_id,
        api_hash=api_hash,
    )

    print("\n📱 You'll be prompted to login with your Telegram account.")
    print("This user account will be used to monitor the bot.")

    async with app:
        # This will trigger the login flow if needed
        me = await app.get_me()
        session_string = app.export_session_string()

        print("\n" + "=" * 60)
        print("✅ Session generated successfully!")
        print("=" * 60)
        print(f"\nLogged in as: {me.first_name} (@{me.username})")
        print(f"\n📋 Your session string (add to .env as MONITOR_SESSION_STRING):")
        print(f"\n{session_string}\n")
        print("=" * 60)
        print("⚠️  Keep this secret! Do not share it.")
        print("=" * 60)


if __name__ == "__main__":
    asyncio.run(generate_session())
