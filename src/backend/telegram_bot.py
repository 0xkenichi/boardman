#!/usr/bin/env python3
"""
main.py — sideQuest Telegram Bot (FULLY FIXED)
───────────────────────────────────────────────────────────────────────────────
Fully interactive Telegram bot using aiogram v3.
- Auto-creates user profile + wallet on /start
- Inline keyboard buttons for every major flow
- Complete bet/stake lifecycle with escrow, resolution, and payouts
"""

import os
import asyncio
import base64
from typing import Optional
import logging
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, types, F
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandObject
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.client.default import DefaultBotProperties

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

API_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not API_TOKEN:
    logger.critical("❌ TELEGRAM_BOT_TOKEN missing in .env")
    exit(1)

try:
    from gaming.src.backend.app_controller import get_controller
    controller = get_controller()
    logger.info("✅ Shared ClawController linked")
except Exception as e:
    logger.critical(f"❌ Failed to link ClawController: {e}", exc_info=True)
    exit(1)

bot = Bot(
    token=API_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN),
)
dp = Dispatcher(storage=MemoryStorage())


# ─── Keyboard helpers ─────────────────────────────────────────────────────────

WEB_APP_URL = os.getenv("WEB_APP_URL", "https://playingsidequest.fun")

def main_menu_kb() -> types.InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(
        types.InlineKeyboardButton(text="💰 Wallet",      callback_data="cb_wallet"),
        types.InlineKeyboardButton(text="💳 Fund",        callback_data="cb_fund_menu"),
    )
    b.row(
        types.InlineKeyboardButton(text="⚔️ Find Match",  callback_data="cb_challenge"),
        types.InlineKeyboardButton(text="🏆 Leaderboard", callback_data="cb_leaderboard"),
    )
    b.row(
        types.InlineKeyboardButton(text="🌐 Open App", web_app=types.WebAppInfo(url=WEB_APP_URL)),
        types.InlineKeyboardButton(text="⚙️ Profile",   callback_data="cb_profile"),
    )
    return b.as_markup()

def wallet_kb() -> types.InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(
        types.InlineKeyboardButton(text="➕ Deposit USDC",  callback_data="cb_deposit"),
        types.InlineKeyboardButton(text="➖ Withdraw",      callback_data="cb_withdraw"),
    )
    b.row(types.InlineKeyboardButton(text="📋 Main Menu",   callback_data="cb_main_menu"))
    return b.as_markup()

def fund_kb() -> types.InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(types.InlineKeyboardButton(text="🏦 Bank Transfer (NGN)", callback_data="cb_fund_bank"))
    b.row(types.InlineKeyboardButton(text="🪙 Crypto / USDC",       callback_data="cb_fund_crypto"))
    b.row(types.InlineKeyboardButton(text="◀️ Back",                 callback_data="cb_main_menu"))
    return b.as_markup()

def challenge_kb() -> types.InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(types.InlineKeyboardButton(text="⚽ EA FC",     callback_data="cb_game_eafc"))
    b.row(types.InlineKeyboardButton(text="🏀 NBA",       callback_data="cb_game_nba"))
    b.row(types.InlineKeyboardButton(text="🎮 FIFA",      callback_data="cb_game_fifa"))
    b.row(types.InlineKeyboardButton(text="◀️ Back",      callback_data="cb_main_menu"))
    return b.as_markup()

def profile_kb() -> types.InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(types.InlineKeyboardButton(text="🎮 Link PlayStation (PSN)", callback_data="link_psn"))
    b.row(types.InlineKeyboardButton(text="🎮 Link Xbox Live",          callback_data="link_xbox"))
    b.row(types.InlineKeyboardButton(text="◀️ Back",                    callback_data="cb_main_menu"))
    return b.as_markup()

def match_kb(match_id: str = "") -> types.InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(types.InlineKeyboardButton(text="🕹️ My Active Matches", callback_data="cb_active"))
    b.row(types.InlineKeyboardButton(text="📋 Main Menu",         callback_data="cb_main_menu"))
    return b.as_markup()

def back_kb() -> types.InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(types.InlineKeyboardButton(text="📋 Main Menu", callback_data="cb_main_menu"))
    return b.as_markup()

def accept_invite_kb(match_id: str) -> types.InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(types.InlineKeyboardButton(text="🥊 Accept Match", callback_data=f"cb_accept_{match_id}"))
    b.row(types.InlineKeyboardButton(text="📋 Main Menu",    callback_data="cb_main_menu"))
    return b.as_markup()

def team_selection_kb(match_id: str) -> types.InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    teams = ["Real Madrid", "Barcelona", "Man City", "Liverpool", "PSG", "Bayern", "Lakers", "Warriors"]
    for i in range(0, len(teams), 2):
        b.row(
            types.InlineKeyboardButton(text=teams[i],   callback_data=f"cb_team_{match_id}_{teams[i]}"),
            types.InlineKeyboardButton(text=teams[i+1], callback_data=f"cb_team_{match_id}_{teams[i+1]}")
        )
    b.row(types.InlineKeyboardButton(text="◀️ Back", callback_data="cb_main_menu"))
    return b.as_markup()


# ─── Helper: resolve Telegram user → sideQuest profile ───────────────────────

async def _get_profile(tg_user: types.User) -> Optional[dict]:
    phone = f"tg_{tg_user.id}"
    try:
        profile = await controller._get_or_create_user(phone)
        if profile and not profile.get("display_name"):
            name = tg_user.full_name or tg_user.username or "Gamer"
            profile["display_name"] = name
        return profile
    except Exception as e:
        logger.error(f"[profile] Failed for {tg_user.id}: {e}", exc_info=True)
        return None


# ─── Command Handlers ─────────────────────────────────────────────────────────

@dp.message(Command("start", "menu"))
async def cmd_start(message: types.Message):
    profile = await _get_profile(message.from_user)
    if not profile:
        await message.answer("❌ Failed to set up your profile. Please try again.")
        return

    name = profile.get("display_name") or message.from_user.first_name or "Gamer"
    balance = float(profile.get("wallet_balance_usdc", 0))
    pts = int(profile.get("play_points", 0))
    wallet = profile.get("wallet_address") or profile.get("linked_wallet")

    if not wallet or wallet == "Not linked":
        try:
            from backend.wallet_service import get_wallet_service
            ws = get_wallet_service()
            result = await ws.create_wallet(profile["id"])
            if result.get("success"):
                full_address = result.get("wallet")
                wallet = full_address[:10] + "..."
                msg = f"🛡️ *Secure Wallet Created!*\n\nAddress: `{full_address}`\n\nThis is a *Platform-Managed Custodial Wallet* on *Base Sepolia*.\nYour funds are secured by Circle."
                await message.answer(msg, parse_mode="Markdown")
                profile["linked_wallet"] = full_address
            else:
                wallet = "Not linked"
        except Exception:
            wallet = "Not linked"

    if wallet and len(wallet) > 10 and not wallet.endswith("..."):
        wallet = wallet[:10] + "..."

    await message.answer(
        f"🎮 *Welcome to sideQuest, {name}!*\n\n"
        f"Stake USDC, play games, and win real money.\n\n"
        f"*Your Account*\n"
        f"💵 Balance: *${balance:.2f} USDC*\n"
        f"🎮 $PLAY Points: *{pts:,}*\n"
        f"🔗 Wallet: `{wallet}`\n\n"
        f"*Quick Actions*\n"
        f"⚔️ Find a match — Challenge other players\n"
        f"💰 Add funds — Deposit USDC to play\n"
        f"🏆 Leaderboard — See top players\n\n"
        f"What would you like to do?",
        reply_markup=main_menu_kb(),
    )


@dp.message(Command("wallet", "balance"))
async def cmd_wallet(message: types.Message):
    profile = await _get_profile(message.from_user)
    if not profile:
        await message.answer("❌ Profile not found."); return
    text = await controller._cmd_wallet(profile, [])
    await message.answer(text, reply_markup=wallet_kb())


@dp.message(Command("deposit", "fund_crypto"))
async def cmd_deposit(message: types.Message):
    profile = await _get_profile(message.from_user)
    if not profile:
        await message.answer("❌ Profile not found."); return
    text = await controller._cmd_deposit(profile, [])
    await message.answer(text, reply_markup=back_kb())


@dp.message(Command("fund"))
async def cmd_fund(message: types.Message, command: CommandObject):
    profile = await _get_profile(message.from_user)
    if not profile:
        await message.answer("❌ Profile not found."); return
    args = command.args.split() if command.args else []
    if not args:
        await message.answer(
            "💳 *How would you like to fund your wallet?*",
            reply_markup=fund_kb(),
        )
        return
    text = await controller._cmd_deposit(profile, args)
    await message.answer(text, reply_markup=back_kb())


@dp.message(Command("withdraw"))
async def cmd_withdraw(message: types.Message, command: CommandObject):
    profile = await _get_profile(message.from_user)
    if not profile:
        await message.answer("❌ Profile not found."); return
    args = command.args.split() if command.args else []
    text = await controller._cmd_withdraw(profile, args)
    await message.answer(text, reply_markup=back_kb())


@dp.message(Command("challenge"))
async def cmd_challenge(message: types.Message, command: CommandObject):
    profile = await _get_profile(message.from_user)
    if not profile:
        await message.answer("❌ Profile not found."); return
    args = command.args.split() if command.args else []
    res = await controller._cmd_challenge(profile, args)
    if isinstance(res, dict):
        text = res["text"]
        match_id = res.get("match_id")
        opp_tele_id = res.get("opponent_tele_id")
        if opp_tele_id:
            try:
                inviter = res.get("creator_name") or "A player"
                invite_text = (
                    f"⚔️ *MATCH CHALLENGE!*\n\n"
                    f"*{inviter}* has challenged you to a match!\n"
                    f"🎮 {res['game']} | 💵 ${res['stake_usd']:.2f}\n\n"
                    f"Accept to lock in your stake and start playing."
                )
                await bot.send_message(opp_tele_id, invite_text, reply_markup=accept_invite_kb(match_id))
            except Exception as e:
                logger.error(f"[Invite] Failed to send to {opp_tele_id}: {e}")
                text += f"\n\n⚠️ Could not notify opponent automatically. Tell them to join with ID: `{match_id}`"
        await message.answer(text, reply_markup=match_kb(match_id))
    else:
        await message.answer(res, reply_markup=match_kb())


@dp.message(Command("local"))
async def cmd_local(message: types.Message, command: CommandObject):
    profile = await _get_profile(message.from_user)
    if not profile:
        await message.answer("❌ Profile not found."); return
    args = command.args.split() if command.args else []
    res = await controller._cmd_local(profile, args)
    if isinstance(res, dict):
        text = res["text"]
        match_id = res.get("match_id")
        await message.answer(text, reply_markup=match_kb(match_id))
    else:
        await message.answer(res, reply_markup=match_kb())


@dp.message(Command("match"))
async def cmd_match(message: types.Message, command: CommandObject):
    profile = await _get_profile(message.from_user)
    if not profile:
        await message.answer("❌ Profile not found."); return
    args = command.args.split() if command.args else []
    text = await controller._cmd_match(profile, args)
    await message.answer(text, reply_markup=match_kb())


@dp.message(Command("report"))
async def cmd_report(message: types.Message, command: CommandObject):
    profile = await _get_profile(message.from_user)
    if not profile:
        await message.answer("❌ Profile not found."); return
    args = command.args.split() if command.args else []
    proof_url = None
    if message.photo:
        try:
            file_id = message.photo[-1].file_id
            file_info = await bot.get_file(file_id)
            proof_url = f"https://api.telegram.org/file/bot{bot.token}/{file_info.file_path}"
        except Exception as e:
            logger.error(f"Failed to process photo: {e}")
    text = await controller._cmd_report(profile, args, proof_url=proof_url)
    await message.answer(text, reply_markup=back_kb())


@dp.message(Command("bets"))
async def cmd_bets(message: types.Message):
    profile = await _get_profile(message.from_user)
    if not profile:
        await message.answer("❌ Profile not found."); return
    text = await controller._cmd_bets(profile, [])
    b = InlineKeyboardBuilder()
    b.row(types.InlineKeyboardButton(text="⚔️ Create Challenge", callback_data="cb_challenge"))
    b.row(types.InlineKeyboardButton(text="📋 Main Menu",        callback_data="cb_main_menu"))
    await message.answer(text, reply_markup=b.as_markup())


@dp.message(Command("active"))
async def cmd_active(message: types.Message):
    profile = await _get_profile(message.from_user)
    if not profile:
        await message.answer("❌ Profile not found."); return
    text = await controller._cmd_active(profile, [])
    await message.answer(text, reply_markup=back_kb())


@dp.message(Command("points"))
async def cmd_points(message: types.Message):
    profile = await _get_profile(message.from_user)
    if not profile:
        await message.answer("❌ Profile not found."); return
    text = await controller._cmd_points(profile, [])
    await message.answer(text, reply_markup=back_kb())


@dp.message(Command("leaderboard"))
async def cmd_leaderboard(message: types.Message):
    profile = await _get_profile(message.from_user)
    if not profile:
        await message.answer("❌ Profile not found."); return
    text = await controller._cmd_leaderboard(profile, [])
    await message.answer(text, reply_markup=back_kb())


@dp.message(Command("profile"))
async def cmd_profile(message: types.Message):
    profile = await _get_profile(message.from_user)
    if not profile:
        await message.answer("❌ Profile not found."); return
    text = await controller._cmd_profile(profile, [])
    await message.answer(text, reply_markup=profile_kb())


@dp.message(Command("link_psn"))
async def cmd_link_psn(message: types.Message, command: CommandObject):
    profile = await _get_profile(message.from_user)
    if not profile:
        await message.answer("❌ Profile not found."); return
    args = command.args.split() if command.args else []
    text = await controller._cmd_link_psn(profile, args)
    await message.answer(text, reply_markup=back_kb())


@dp.message(Command("link_xbox"))
async def cmd_link_xbox(message: types.Message, command: CommandObject):
    profile = await _get_profile(message.from_user)
    if not profile:
        await message.answer("❌ Profile not found."); return
    args = command.args.split() if command.args else []
    text = await controller._cmd_link_xbox(profile, args)
    await message.answer(text, reply_markup=back_kb())


@dp.message(Command("link_wallet"))
async def cmd_link_wallet(message: types.Message, command: CommandObject):
    profile = await _get_profile(message.from_user)
    if not profile:
        await message.answer("❌ Profile not found."); return
    args = command.args.split() if command.args else []
    text = await controller._cmd_link_wallet(profile, args)
    await message.answer(text, reply_markup=back_kb())


@dp.message(Command("transactions"))
async def cmd_transactions(message: types.Message):
    profile = await _get_profile(message.from_user)
    if not profile:
        await message.answer("❌ Profile not found."); return
    text = await controller._cmd_transactions(profile, [])
    await message.answer(text, reply_markup=back_kb())


@dp.message(Command("screenshot"))
async def cmd_screenshot(message: types.Message, command: CommandObject):
    profile = await _get_profile(message.from_user)
    if not profile:
        await message.answer("❌ Profile not found."); return
    if not message.photo:
        await message.answer("📸 Please attach a screenshot when using /screenshot")
        return
    args = command.args.split() if command.args else []
    match_id = args[0] if args else profile.get("pending_screenshot_match")
    if not match_id:
        await message.answer("❓ No match ID specified. Use /screenshot <match_id> with a photo.")
        return
    file_id = message.photo[-1].file_id
    file_info = await bot.get_file(file_id)
    photo_bytes = await bot.download_file(file_info.file_path)
    image_b64 = base64.b64encode(photo_bytes).decode('utf-8')
    text = await controller._handle_screenshot(profile, image_b64)
    await message.answer(text, reply_markup=back_kb())


@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    profile = await _get_profile(message.from_user)
    text = await controller._cmd_help(profile, [])
    await message.answer(text, reply_markup=main_menu_kb())


# ─── Callback Query Router ────────────────────────────────────────────────────

@dp.callback_query()
async def handle_callbacks(callback: types.CallbackQuery):
    await callback.answer()
    uid   = callback.from_user.id
    data  = callback.data
    send  = lambda text, kb=None: bot.send_message(uid, text, reply_markup=kb)
    profile = await _get_profile(callback.from_user)

    if data == "cb_main_menu":
        name = profile.get("display_name") or callback.from_user.first_name or "Gamer"
        await send(
            f"📋 *sideQuest Menu*\n\nHey {name}, what do you want to do?",
            main_menu_kb()
        )

    elif data == "cb_wallet":
        if not profile:
            await send("❌ Profile not found.")
            return
        text = await controller._cmd_wallet(profile, [])
        await send(text, wallet_kb())

    elif data == "cb_deposit":
        if not profile:
            await send("❌ Profile not found.")
            return
        text = await controller._cmd_deposit(profile, [])
        await send(text, back_kb())

    elif data == "cb_withdraw":
        await send(
            "💸 *Withdraw USDC*\n\nSend the command:\n`/withdraw <amount>`\n\nExample:\n`/withdraw 25`",
            back_kb()
        )

    elif data == "cb_fund_menu":
        await send("💳 *Fund Your Wallet*\n\nHow would you like to deposit?", fund_kb())

    elif data == "cb_fund_bank":
        await send(
            "🏦 *Bank Transfer (NGN)*\n\n"
            "Send:\n`/fund <amount>`\n\n"
            "Example:\n`/fund 5000`\n\n"
            "You'll receive your sideQuest bank details to transfer to.",
            back_kb()
        )

    elif data == "cb_fund_crypto":
        if not profile:
            await send("❌ Profile not found.")
            return
        text = await controller._cmd_deposit(profile, [])
        await send(text, back_kb())

    elif data == "cb_challenge":
        await send(
            "⚔️ *Create a Match*\n\nWhich game do you want to play?",
            challenge_kb()
        )

    elif data == "cb_leaderboard":
        if not profile:
            await send("❌ Profile not found.")
            return
        text = await controller._cmd_leaderboard(profile, [])
        await send(text, back_kb())

    elif data == "cb_active":
        if not profile:
            await send("❌ Profile not found.")
            return
        text = await controller._cmd_active(profile, [])
        await send(text, back_kb())

    elif data == "cb_profile":
        if not profile:
            await send("❌ Profile not found.")
            return
        text = await controller._cmd_profile(profile, [])
        await send(text, profile_kb())

    elif data in ("cb_game_eafc", "cb_game_nba", "cb_game_fifa"):
        game_map = {
            "cb_game_eafc": "EA FC",
            "cb_game_nba":  "NBA",
            "cb_game_fifa": "FIFA",
        }
        game = game_map[data]
        await send(
            f"🎮 *{game} Match*\n\n"
            f"Set your stake amount:\n`/challenge <amount> {game}`\n\n"
            f"Example:\n`/challenge 10 {game}`\n\n"
            f"Minimum stake: *$1 USDC*",
            back_kb()
        )

    elif data.startswith("cb_accept_"):
        match_id = data.replace("cb_accept_", "")
        if not profile:
            await send("❌ Profile not found.")
            return
        text = await controller._cmd_match(profile, [match_id])
        if "Accepted" in text or "Joined" in text:
            await send(
                f"✅ *Match Joined!*\n\nNow, *Pick Your Team* for Match `{match_id}`:",
                team_selection_kb(match_id)
            )
            match_data = await controller.matches.get_match(match_id)
            if match_data:
                creator_tele_id = await controller._get_telegram_id_by_profile_id(match_data["creator_id"])
                if creator_tele_id:
                    await bot.send_message(
                        creator_tele_id,
                        f"🔥 *Match {match_id} is ACTIVE!*\n\nQuick! *Pick Your Team*:",
                        reply_markup=team_selection_kb(match_id)
                    )
        else:
            await send(text, match_kb(match_id))

    elif data.startswith("cb_team_"):
        parts = data.split("_")
        match_id  = parts[2]
        team_name = "_".join(parts[3:])
        res = await controller._cmd_set_team(profile, match_id, team_name)
        await send(res, match_kb(match_id))

    elif data.startswith("cb_screenshot_"):
        match_id = data.replace("cb_screenshot_", "")
        profile["pending_screenshot_match"] = match_id
        await send(
            f"📸 *Upload Screenshot for Match {match_id}*\n\n"
            f"Attach a photo with your score and send it as a reply to this message.",
            back_kb()
        )

    else:
        logger.warning(f"[callback] Unhandled: {data}")


# ─── Fallback (unknown text) ──────────────────────────────────────────────────

@dp.message()
async def fallback_handler(message: types.Message):
    if message.text and message.text.startswith("/"):
        await message.answer(
            "❓ Unknown command.\n\nType /help to see all available commands.",
            reply_markup=back_kb(),
        )
    else:
        profile = await _get_profile(message.from_user)
        if profile:
            text = await controller.handle_command(f"tg_{message.from_user.id}", message.text or "")
        else:
            text = "👋 Hey! Type /start to get going."
        await message.answer(text, reply_markup=main_menu_kb())


# ─── Entry Point ──────────────────────────────────────────────────────────────

async def main():
    logger.info("🚀 sideQuest Telegram Bot starting…")
    try:
        me = await bot.get_me()
        logger.info(f"✅ Connected as @{me.username} (ID: {me.id})")

        try:
            wh_info = await bot.get_webhook_info()
            if wh_info.url:
                logger.info(f"📡 Webhook currently set to: {wh_info.url}")
            else:
                logger.info("📡 No webhook currently set")
        except Exception as e:
            logger.warning(f"Could not check webhook status: {e}")

        await bot.set_my_commands([
            types.BotCommand(command="start",       description="🎮 Welcome & main menu"),
            types.BotCommand(command="help",        description="📖 Show all commands"),
            types.BotCommand(command="wallet",      description="💰 Check your balance"),
            types.BotCommand(command="deposit",     description="💳 Get USDC deposit address"),
            types.BotCommand(command="withdraw",    description="💸 Withdraw USDC"),
            types.BotCommand(command="fund",        description="🏦 Add funds to wallet"),
            types.BotCommand(command="challenge",   description="⚔️ Create/join a match"),
            types.BotCommand(command="bets",        description="🎯 Browse open challenges"),
            types.BotCommand(command="active",      description="🏃 Your active matches"),
            types.BotCommand(command="leaderboard", description="🏆 Top players"),
            types.BotCommand(command="profile",     description="👤 View your profile"),
            types.BotCommand(command="link_psn",    description="🎮 Link PlayStation account"),
            types.BotCommand(command="link_xbox",   description="🎯 Link Xbox account"),
            types.BotCommand(command="link_wallet", description="🔗 Link crypto wallet"),
            types.BotCommand(command="transactions",description="📄 View transaction history"),
            types.BotCommand(command="screenshot",  description="📸 Submit dispute screenshot"),
        ])
        logger.info("✅ Bot commands registered")

        use_polling = os.getenv("USE_POLLING", "false").lower() == "true"
        webhook_url = os.getenv("WEBHOOK_URL")

        if use_polling and webhook_url:
            logger.warning("⚠️  Both USE_POLLING=true and WEBHOOK_URL are set — using polling mode")

        if use_polling or not webhook_url:
            logger.info("🔄 Starting long polling")
            try:
                await bot.delete_webhook(drop_pending_updates=True)
                logger.info("✅ Cleared any existing webhook")
            except Exception as e:
                logger.warning(f"Failed to delete webhook: {e}")
            await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
        else:
            logger.info(f"📡 Setting webhook to {webhook_url}")
            webhook_path = os.getenv("WEBHOOK_PATH", "/webhook/telegram")
            full_url = f"{webhook_url.rstrip('/')}{webhook_path}"
            try:
                await bot.delete_webhook()
                logger.info("✅ Cleared existing webhook")
            except Exception as e:
                logger.warning(f"Failed to delete webhook: {e}")
            await bot.set_webhook(url=full_url, allowed_updates=dp.resolve_used_update_types(), drop_pending_updates=True)
            logger.info("✅ Webhook set")
            while True:
                await asyncio.sleep(3600)
                logger.debug("💓 Bot heartbeat")

    except Exception as e:
        logger.critical(f"❌ Fatal error: {e}", exc_info=True)
        await asyncio.sleep(5)
        raise


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user.")
