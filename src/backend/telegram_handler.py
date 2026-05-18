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

from gaming.src.backend.app_controller import ClawController

load_dotenv()
controller = ClawController()

# ─── Verification & Whitelist ──────────────────────────────────────────────────
ADMIN_NUMBERS = frozenset(["2348022202143", "2347073924753", "2349163497691"])

def _is_admin(user_id: str) -> bool:
    # Telegram sends numeric IDs, we can map Telegram IDs as admins if needed
    # For now, we will rely on password-based admin access like in WhatsApp.
    return True

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
        [InlineKeyboardButton("⛏️ Mined $PLAY", callback_data="btn_points")]
    ]
    return InlineKeyboardMarkup(keyboard)

# ─── Command Handlers ──────────────────────────────────────────────────────────

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    profile = await identify_user(update)
    text = await controller.get_welcome_text()
    text += "\n\nUse the interactive menu below to navigate sideQuest!"
    await update.message.reply_text(text, reply_markup=create_main_menu())

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
    profile = await identify_user(update)
    args = context.args
    if len(args) < 2:
        await update.message.reply_text("Usage: `/challenge <amount> <game_type> [onchain]`\nExample: `/challenge 10 FIFA`", parse_mode="Markdown")
        return
    
    try:
        amount = float(args[0])
        if amount <= 0: raise ValueError
    except ValueError:
        await update.message.reply_text("❌ Invalid amount.")
        return

    game = args[1]
    is_on_chain = len(args) > 2 and args[2].lower() == "onchain"
    
    response = controller.place_challenge(profile, amount, game, is_on_chain)
    await update.message.reply_text(response)

async def bets_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    profile = await identify_user(update)
    response = controller.list_bets()
    await update.message.reply_text(response)

async def match_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    profile = await identify_user(update)
    if not context.args:
        await update.message.reply_text("Usage: /match <bet_id>")
        return
    
    bet_id = context.args[0]
    response = controller.match_challenge(profile, bet_id)
    await update.message.reply_text(response)

async def approve_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    profile = await identify_user(update)
    if not context.args:
        await update.message.reply_text("Usage: /approve <bet_id>")
        return
    
    bet_id = context.args[0]
    response = controller.approve_challenge(profile, bet_id)
    await update.message.reply_text(response)

async def report_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    profile = await identify_user(update)
    if len(context.args) < 2:
        await update.message.reply_text("Usage: /report <bet_id> <score>\nExample: `/report 123 2-1`", parse_mode="Markdown")
        return
    
    bet_id = context.args[0]
    score = context.args[1]
    
    # If they attached a photo, we get the highest res version
    proof_url = None
    if update.message.photo:
        photo_file = await update.message.photo[-1].get_file()
        proof_url = photo_file.file_path

    response = await controller.report_match(profile, bet_id, score, proof_url)
    await update.message.reply_text(response)

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
        response = "To issue a challenge, type:\n`/challenge <amount> <game>\nExample: `/challenge 10 FIFA`"
    elif data == "btn_points":
        response = controller.get_mining_status(profile)
    elif data == "fund_naira":
        res = controller.initiate_fund(profile, "50", "naira") # Placeholder 50
        response = "Example Funding:\n\n" + res["text"]
    elif data == "fund_crypto":
        res = controller.initiate_fund(profile, "10", "crypto")
        response = res["text"]
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
    app.add_handler(CommandHandler("challenge", challenge_command))
    app.add_handler(CommandHandler("bets", bets_command))
    app.add_handler(CommandHandler("match", match_command))
    app.add_handler(CommandHandler("approve", approve_command))
    app.add_handler(CommandHandler("report", report_command))
    
    # Admin Routes
    app.add_handler(CommandHandler("admin_credit", admin_credit_command))
    
    # Interactive Callbacks
    app.add_handler(CallbackQueryHandler(button_handler))
    
    # Fallback Chat
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), generic_message_handler))
    
    print("🚀 Telegram Handler polling initialized...")
    app.run_polling()

if __name__ == '__main__':
    main()
