"""
Updated Telegram Handler for ClawStation
Includes support for Local and Online match types.
"""

import os
import re
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes
)
from dotenv import load_dotenv

from app_controller import ClawController
from match_manager import MatchType, MatchConfig, VerificationLevel

load_dotenv()
controller = ClawController()

# ─── Verification & Whitelist ──────────────────────────────────────────────────
ADMIN_NUMBERS = frozenset(["2348022202143", "2347073924753", "2349163497691"])

def _is_admin(user_id: str) -> bool:
    return True  # Rely on password-based admin access

# ─── Utility Functions ─────────────────────────────────────────────────────────
async def identify_user(update: Update) -> dict:
    from_id = str(update.effective_user.id)
    return controller.get_user("telegram_id", from_id)

def create_main_menu() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton("💰 Wallet", callback_data="btn_wallet"),
         InlineKeyboardButton("👤 Profile", callback_data="btn_profile")],
        [InlineKeyboardButton("⚔️ Match Lobby", callback_data="btn_bets"),
         InlineKeyboardButton("🏆 Challenge", callback_data="btn_challenge")],
        [InlineKeyboardButton("⛏️ Mined $PLAY", callback_data="btn_points")],
        [InlineKeyboardButton("🛠️ Support", callback_data="btn_support")]
    ]
    return InlineKeyboardMarkup(keyboard)

def create_challenge_menu() -> InlineKeyboardMarkup:
    """Menu for challenge type selection"""
    keyboard = [
        [InlineKeyboardButton("🌐 Online Match", callback_data="challenge_online")],
        [InlineKeyboardButton("🏠 Local Match", callback_data="challenge_local")],
        [InlineKeyboardButton("📋 How It Works", callback_data="challenge_help")],
        [InlineKeyboardButton("⬅️ Back", callback_data="btn_back")]
    ]
    return InlineKeyboardMarkup(keyboard)

# ─── Command Handlers ──────────────────────────────────────────────────────────

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    profile = await identify_user(update)
    text = await controller.handle_command(str(update.effective_user.id), "/start")
    text += "\n\n🎮 **Alpha Note:** We are in Testnet Beta. Feelers and feedback welcome!"
    await update.message.reply_text(text, reply_markup=create_main_menu(), parse_mode="Markdown")

async def profile_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    profile = await identify_user(update)
    response = controller.get_profile_status(profile)
    await update.message.reply_text(response)

async def wallet_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    profile = await identify_user(update)
    response = controller.get_wallet_info(profile)
    
    keyboard = [
        [InlineKeyboardButton("🏦 Fund Naira", callback_data="fund_naira"),
         InlineKeyboardButton("⛓️ Fund Crypto", callback_data="fund_crypto")]
    ]
    await update.message.reply_text(response, reply_markup=InlineKeyboardMarkup(keyboard))

async def fund_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    profile = await identify_user(update)
    args = context.args
    if len(args) < 1:
        text = """💳 **Funding Menu**
How would you like to fund your sideQuest account?

1️⃣ **Naira (Bank Transfer)**
   Type: `/fund <amount_in_naira> naira` 

2️⃣ **Crypto (Base Network)**
   Type: `/fund <amount_in_usd> crypto`"""
        await update.message.reply_text(text, parse_mode="Markdown")
        return

    amount = context.args[0]
    method = context.args[1].lower() if len(context.args) > 1 else "naira"
    res = controller.initiate_fund(profile, amount, method)
    await update.message.reply_text(res['text'], parse_mode="Markdown")

async def challenge_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show challenge options menu"""
    text = """🏆 **Create a Challenge**

Choose match type:

🌐 **Online Match**
Play remotely with another player
Requirements: Screenshot + Platform activity
Time: 120 minutes

🏠 **Local Match**  
Play together on same console/TV
Requirements: Photo of both players + screen
Time: 60 minutes

Type:
• `/challenge <amount> <game>` → Online (default)
• `/local <amount> <game>` → Local match

Examples:
`/challenge 10 FIFA`
`/local 10 FIFA`"""
    
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=create_challenge_menu())

async def online_challenge_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Create an online match"""
    profile = await identify_user(update)
    args = context.args
    if len(args) < 2:
        await update.message.reply_text(
            "Usage: `/challenge <amount> <game_type>`\nExample: `/challenge 10 FIFA`", 
            parse_mode="Markdown"
        )
        return
    
    try:
        amount = float(args[0])
        if amount <= 0: raise ValueError
    except ValueError:
        await update.message.reply_text("❌ Invalid amount.")
        return

    game = args[1]
    is_on_chain = len(args) > 2 and args[2].lower() == "onchain"
    
    result = await controller.create_online_match(profile, amount, game)
    if result["status"] == "success":
        match = result["match"]
        text = f"""🌐 **Online Match Created!**

🎮 Game: {game}
💰 Stake: ${amount}
🆔 ID: `{match['id']}`

⏱️ **Requirements:**
• Screenshot of final score
• PSN/Xbox activity within 2 hours
• Must complete within 120 minutes

Waiting for opponent to join..."""
        if is_on_chain:
            text += "\n⛓️ **On-Chain enabled!**"
        await update.message.reply_text(text, parse_mode="Markdown")
    else:
        await update.message.reply_text(f"❌ Error: {result.get('message', 'Unknown error')}")

async def local_challenge_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Create a local match"""
    profile = await identify_user(update)
    args = context.args
    if len(args) < 2:
        await update.message.reply_text(
            "Usage: `/local <amount> <game_type>`\nExample: `/local 10 FIFA`\n\n🏠 Local = Both players at same console/TV", 
            parse_mode="Markdown"
        )
        return
    
    try:
        amount = float(args[0])
        if amount <= 0: raise ValueError
    except ValueError:
        await update.message.reply_text("❌ Invalid amount.")
        return

    game = args[1]
    
    result = await controller.create_local_match(profile, amount, game)
    if result["status"] == "success":
        match = result["match"]
        text = f"""🏠 **Local Match Created!**

🎮 Game: {game}
💰 Stake: ${amount}
🆔 ID: `{match['id']}`

⏱️ **Requirements:**
• Photo showing BOTH players + TV screen
• Must complete within 60 minutes
• Same console/TV required

📸 **Important:** When reporting, include a selfie showing:
- Both players in frame
- TV screen showing final score
- Clear and readable

Waiting for opponent to join..."""
        await update.message.reply_text(text, parse_mode="Markdown")
    else:
        await update.message.reply_text(f"❌ Error: {result.get('message', 'Unknown error')}")

async def bets_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List open challenges with match type indicators"""
    profile = await identify_user(update)
    bets = controller.db.get_open_bets()
    if not bets:
        await update.message.reply_text("No open challenges. Create one with /challenge!")
        return
    
    text = "🏆 **Open Challenges:**\n\n"
    for b in bets:
        # Parse config to get match type
        match_type = "🌐 Online"
        try:
            import json
            config = json.loads(b.get('config', '{}'))
            if config.get('match_type') == 'local':
                match_type = "🏠 Local"
        except:
            pass
        
        text += f"🆔 `{b['id']}`\n"
        text += f"{match_type} | {b['game_type']}\n"
        text += f"💰 ${b['amount']}\n"
        text += f"Type `/match {b['id']}` to join\n\n"
    
    await update.message.reply_text(text, parse_mode="Markdown")

async def match_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Join a match with type-specific instructions"""
    profile = await identify_user(update)
    if not context.args:
        await update.message.reply_text("Usage: /match <bet_id>")
        return
    
    bet_id = context.args[0]
    
    # Get match details to show type-specific instructions
    match_details = controller.get_match_details(bet_id)
    
    response = controller.match_challenge(profile, bet_id)
    
    if match_details and "local" in match_details.get("match_type", ""):
        response += "\n\n🏠 **Local Match Note:**\n"
        response += "Both players must be physically present at the same console/TV."
    
    await update.message.reply_text(response)

async def approve_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    profile = await identify_user(update)
    if not context.args:
        await update.message.reply_text("Usage: /approve <bet_id>")
        return
    
    bet_id = context.args[0]
    
    # Get match details
    match_details = controller.get_match_details(bet_id)
    
    response = controller.approve_challenge(profile, bet_id)
    
    # Add match-specific instructions
    if match_details:
        match_type = match_details.get("match_type", "online")
        if match_type == "local":
            response += "\n\n📸 **Remember:** Take a photo of BOTH players + TV screen when finished!"
        else:
            response += "\n\n📸 **Remember:** Screenshot of final score + platform activity required!"
    
    await update.message.reply_text(response)

async def report_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Enhanced report with image support"""
    profile = await identify_user(update)
    if len(context.args) < 2:
        await update.message.reply_text(
            "Usage: `/report <bet_id> <score>`\n\n"
            "Attach a photo for verification!\n"
            "📸 For local matches: Include both players in photo\n"
            "📸 For online matches: Screenshot of final score",
            parse_mode="Markdown"
        )
        return
    
    bet_id = context.args[0]
    score = context.args[1]
    
    # Get the photo if attached
    proof_url = None
    if update.message.photo:
        photo_file = await update.message.photo[-1].get_file()
        proof_url = photo_file.file_path
        await update.message.reply_text("📸 Processing screenshot...", parse_mode="Markdown")
    
    # Submit report
    response = await controller.report_match(profile, bet_id, score, proof_url)
    await update.message.reply_text(response, parse_mode="Markdown")

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Check match status and deadlines"""
    profile = await identify_user(update)
    if not context.args:
        await update.message.reply_text("Usage: /status <bet_id>")
        return
    
    bet_id = context.args[0]
    details = controller.get_match_details(bet_id)
    
    if not details:
        await update.message.reply_text("❌ Match not found.")
        return
    
    from datetime import datetime
    
    text = f"📊 **Match Status**\n\n"
    text += f"🆔 ID: `{details['id']}`\n"
    text += f"🎮 Game: {details['game_type']}\n"
    text += f"💰 Amount: ${details['amount']}\n"
    text += f"📍 Type: {details['match_type'].title()}\n"
    text += f"📋 Status: {details['status'].upper()}\n\n"
    
    if details.get('play_deadline'):
        deadline = datetime.fromisoformat(details['play_deadline'])
        now = datetime.now()
        if deadline > now:
            remaining = deadline - now
            text += f"⏱️ **Play deadline:** {remaining.seconds // 60} minutes remaining\n"
        else:
            text += "⚠️ **Play deadline passed**\n"
    
    if details.get('report_deadline'):
        deadline = datetime.fromisoformat(details['report_deadline'])
        now = datetime.now()
        if deadline > now:
            remaining = deadline - now
            text += f"📸 **Report deadline:** {remaining.seconds // 60} minutes remaining\n"
    
    # Verification requirements
    req = details.get('verification_requirements', {})
    text += f"\n🔍 **Requirements:**\n"
    text += f"• Screenshot: {'Required' if req.get('screenshot_required') else 'Optional'}\n"
    text += f"• Platform Activity: {'Required' if req.get('platform_activity_required') else 'Optional'}\n"
    
    await update.message.reply_text(text, parse_mode="Markdown")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Explicit help command"""
    profile = await identify_user(update)
    text = await controller.handle_command(str(update.effective_user.id), "/help")
    await update.message.reply_text(text, parse_mode="Markdown")

async def support_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Support & Feedback command"""
    text = """🛠️ **SideQuest Support**
    
Need help with a match or have a suggestion?
    
📢 **Community Hall:** [Link to Telegram Group/Channel]
📩 **Direct Support:** @SideQuestAdmin
    
We are currently in **Testnet Beta**. Your feedback helps us build the future of competitive Couch Play!"""
    await update.message.reply_text(text, parse_mode="Markdown")

# Admin Commands
async def admin_credit_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if len(args) < 3:
        await update.message.reply_text("Usage: `/admin_credit <telegram_id> <amount_usd> <admin_password>`", parse_mode="Markdown")
        return
    
    password = args[2]
    expected_pass = os.getenv("ADMIN_SECRET", "godmode123")
    if password != expected_pass:
        await update.message.reply_text("❌ Unauthorised: Invalid admin code.")
        return

    try:
        amount = float(args[1])
        if amount <= 0: raise ValueError
    except ValueError:
        await update.message.reply_text("❌ Invalid amount.")
        return
        
    admin_id = str(update.effective_user.id)
    target_id = re.sub(r'[^\d]', '', args[0])[:20]
    
    response = controller.admin_credit_user(admin_id, target_id, amount)
    await update.message.reply_text(response)

async def admin_resolve_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command to resolve disputes"""
    args = context.args
    if len(args) < 2:
        await update.message.reply_text("Usage: `/admin_resolve <bet_id> <admin_password>`", parse_mode="Markdown")
        return
    
    password = args[1]
    expected_pass = os.getenv("ADMIN_SECRET", "godmode123")
    if password != expected_pass:
        await update.message.reply_text("❌ Unauthorised: Invalid admin code.")
        return
    
    bet_id = args[0]
    admin_id = str(update.effective_user.id)
    
    result = await controller.resolve_match_dispute(admin_id, bet_id)
    
    if result["status"] == "resolved":
        text = f"✅ **Dispute Resolved!**\n\n"
        text += f"Decision: {result.get('decision')}\n"
        text += f"Winner: {result.get('winner_id')}\n"
        text += f"Confidence: {result.get('confidence', 'N/A')}%\n\n"
        text += f"Reasoning: {result.get('reasoning', 'N/A')[:200]}..."
    else:
        text = f"❌ Error: {result.get('message', 'Failed to resolve')}"
    
    await update.message.reply_text(text, parse_mode="Markdown")


# ─── Callbacks (Interactive Buttons) ───────────────────────────────────────────
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    profile = await identify_user(update)
    data = query.data
    
    if data == "btn_wallet":
        response = controller.get_wallet_info(profile)
    elif data == "btn_profile":
        response = controller.get_profile_status(profile)
    elif data == "btn_bets":
        response = controller.list_bets()
    elif data == "btn_challenge":
        await query.edit_message_text(
            "🏆 **Create Challenge**\n\nChoose match type:",
            reply_markup=create_challenge_menu(),
            parse_mode="Markdown"
        )
        return
    elif data == "btn_points":
        response = controller.get_mining_status(profile)
    elif data == "challenge_online":
        await query.edit_message_text(
            "🌐 **Online Match**\n\n"
            "Play remotely with another player.\n\n"
            "Requirements:\n"
            "• Screenshot of final score\n"
            "• PSN/Xbox activity within 2 hours\n\n"
            "Use: `/challenge <amount> <game>`",
            parse_mode="Markdown"
        )
        return
    elif data == "challenge_local":
        await query.edit_message_text(
            "🏠 **Local Match**\n\n"
            "Play together on same console/TV.\n\n"
            "Requirements:\n"
            "• Photo showing BOTH players + TV screen\n"
            "• Complete within 60 minutes\n\n"
            "Use: `/local <amount> <game>`",
            parse_mode="Markdown"
        )
        return
    elif data == "challenge_help":
        response = """📚 **Match Types & Fees**

🌐 **Online Match:**
Play remotely via internet (Screenshot + Platform required)

🏠 **Local Match:**
Play together physically (Photo of both players required)

⚖️ **Fees & Sustainable Gaming:**
• Early Adopters: **3%** (First 1,000 Mainnet users)
• Standard Rate: **7%**
• Minimum Fee: **$0.50 per match**

Both use AI verification to ensure fair outcomes!"""
    elif data == "btn_support":
        response = """🛠️ **Support & Feedback**
        
Need help? Message @SideQuestAdmin or join our community channel for announcements.

Test users: Thank you for helping us launch! 🚀"""
    elif data == "fund_naira":
        res = controller.initiate_fund(profile, "50", "naira")
        response = "Example Funding:\n\n" + res["text"]
    elif data == "fund_crypto":
        res = controller.initiate_fund(profile, "10", "crypto")
        response = res["text"]
    elif data == "btn_back":
        await query.edit_message_text(
            await controller.get_welcome_text(),
            reply_markup=create_main_menu(),
            parse_mode="Markdown"
        )
        return
    else:
        response = "Unknown action."
        
    await query.edit_message_text(text=response, parse_mode="Markdown")

# ─── Chat Fallback ────────────────────────────────────────────────────────────
async def generic_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text and not update.message.text.startswith('/'):
        # Pass generic chatter to the Ollama Brain
        response = await controller.chat(update.message.text)
        await update.message.reply_text(response)

# ─── Main ─────────────────────────────────────────────────────────────────────
def main():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        print("[ERROR] TELEGRAM_BOT_TOKEN missing in .env")
        return

    app = Application.builder().token(token).build()

    # Core Routes
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("profile", profile_command))
    app.add_handler(CommandHandler("wallet", wallet_command))
    app.add_handler(CommandHandler("fund", fund_command))
    
    # Challenge Routes (new)
    app.add_handler(CommandHandler("challenge", online_challenge_command))  # Online by default
    app.add_handler(CommandHandler("local", local_challenge_command))  # Local match
    app.add_handler(CommandHandler("online", online_challenge_command))  # Explicit online
    
    # Match Routes
    app.add_handler(CommandHandler("bets", bets_command))
    app.add_handler(CommandHandler("match", match_command))
    app.add_handler(CommandHandler("approve", approve_command))
    app.add_handler(CommandHandler("report", report_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("support", support_command))
    
    # Admin Routes
    app.add_handler(CommandHandler("admin_credit", admin_credit_command))
    app.add_handler(CommandHandler("admin_resolve", admin_resolve_command))
    
    # Interactive Callbacks
    app.add_handler(CallbackQueryHandler(button_handler))
    
    # Fallback Chat
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), generic_message_handler))
    
    print("🚀 Telegram Handler with Match Types initialized...")
    print("\nAvailable commands:")
    print("  /challenge <amount> <game> - Online match")
    print("  /local <amount> <game> - Local match")
    print("  /status <match_id> - Check match status")
    print("  /report <id> <score> - Report with photo")
    app.run_polling()

if __name__ == '__main__':
    main()
