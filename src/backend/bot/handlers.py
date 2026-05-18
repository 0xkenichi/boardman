"""
bot/handlers.py — All Telegram commands, Ritual states, and callback handlers.
Imports keyboard functions from bot.keyboards.
Uses services.circle_vault for live balance fetching.
"""
import os
import asyncio
import uuid
import logging
from typing import Optional

from aiogram import Bot, Dispatcher, types, F
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.client.default import DefaultBotProperties
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter

from gaming.src.backend.app_controller import get_controller
controller = get_controller()

from services.trust_safety_service import (
    submit_report, block_user, unblock_user, is_blocked,
    report_no_show, issue_warning, issue_temp_ban, issue_perm_ban,
    submit_appeal, verify_age, check_age_gating, trigger_sos,
    add_emergency_contact, accept_tos, request_data_export,
    request_account_deletion, REPUTATION_THRESHOLDS,
)

from gaming.src.backend.bot.keyboards import (
    main_menu, back_menu, challenge_menu, stake_menu,
    team_menu, opponent_menu, confirm_menu, profile_menu,
    accept_challenge_menu
)

WEB_APP_URL = os.getenv("WEB_APP_URL", "https://playingsidequest.fun")

# Global bot reference for webhooks
_bot: Optional[Bot] = None

def get_bot() -> Optional[Bot]:
    return _bot

def set_bot(bot_instance: Bot):
    global _bot
    _bot = bot_instance

logger = logging.getLogger(__name__)

# ── Send helper ───────────────────────────────────────────────────────────────
async def send(bot: Bot, cid: int, text: str, reply_markup=None, max_retries: int = 5):
    for attempt in range(max_retries):
        try:
            return await bot.send_message(
                cid, text, reply_markup=reply_markup,
                parse_mode=ParseMode.MARKDOWN,
                disable_web_page_preview=True)
        except TelegramRetryAfter as e:
            await asyncio.sleep(e.retry_after)
        except TelegramForbiddenError:
            return None
        except Exception as e:
            logger.error(f"Send fail (attempt {attempt+1}): {e}")
            if attempt < max_retries - 1:
                await asyncio.sleep(2 ** attempt)
            else:
                raise
    return None

# ── DB helpers ────────────────────────────────────────────────────────────────
async def get_profile_by_id(pid: str) -> dict | None:
    try:
        res = controller.db.supabase.table("profiles").select("*").eq("id", pid).execute()
        return res.data[0] if res.data else None
    except Exception:
        return None

async def ensure_public_column():
    """Ensure required DB columns exist."""
    try:
        db = controller.db.supabase
        columns = [
            'is_public_available', 'pending_screenshot_match', 'email',
            'wallet_address', 'linked_wallet', 'circle_wallet_id', 'circle_wallet_set_id'
        ]
        for col in columns:
            try:
                db.rpc('exec_sql', {
                    'query': f"""
                    DO $$
                    BEGIN
                        IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                                     WHERE table_name = 'profiles' AND column_name = '{col}') THEN
                            ALTER TABLE profiles ADD COLUMN {col} TEXT;
                        END IF;
                    END $$;
                    """
                }).execute()
            except Exception:
                pass
        logger.info("✅ DB schema verified")
    except Exception as e:
        logger.warning(f"⚠️  Schema check failed: {e}")

# ── Profile helpers ────────────────────────────────────────────────────────────
async def get_profile(u: types.User) -> dict | None:
    try:
        p = await controller._get_or_create_user(f"tg_{u.id}")
        if p and not p.get("display_name"):
            name = u.full_name or u.username or "Gamer"
            try:
                controller.db.supabase.table("profiles").update(
                    {"display_name": name}).eq("id", p["id"]).execute()
                p["display_name"] = name
            except Exception:
                pass
        return p
    except Exception as e:
        logger.error(f"[get_profile] {e}")
        return None

async def get_profile_by_id(pid: str) -> dict | None:
    try:
        res = controller.db.supabase.table("profiles").select("*").eq("id", pid).execute()
        return res.data[0] if res.data else None
    except Exception:
        return None

# ── Wallet helpers ─────────────────────────────────────────────────────────────
async def ensure_wallet(p: dict) -> str:
    """
    Ensure user has a custodial deposit address (wallet_address).
    Creates via Circle if missing. Returns address or 'Not linked'.
    """
    w = p.get("wallet_address")

    # Migration for legacy accounts
    if not w and p.get("linked_wallet") and p.get("circle_wallet_id"):
        try:
            old_addr = p["linked_wallet"]
            controller.db.supabase.table("profiles").update({"wallet_address": old_addr})\
                .eq("id", p["id"]).execute()
            p["wallet_address"] = old_addr
            w = old_addr
            logger.info(f"[Wallet] Migrated legacy wallet for user {p['id']}: {old_addr}")
        except Exception as e:
            logger.error(f"Wallet migration fail for {p['id']}: {e}")

    # Create new wallet if still missing
    if not w or w in ("Not linked", "", None):
        try:
            from backend.wallet_service import get_wallet_service
            ws = get_wallet_service()
            result = await ws.create_wallet(p["id"])
            if result.get("success"):
                w = result.get("wallet")
                p["wallet_address"] = w
                # Also store circle_wallet_id
                controller.db.supabase.table("profiles")\
                    .update({"circle_wallet_id": result.get("wallet_id")})\
                    .eq("id", p["id"]).execute()
                logger.info(f"[Wallet] Created Circle custodial wallet for user {p['id']}: {w}")
            else:
                logger.error(f"Wallet creation failed for {p['id']}: {result.get('error')}")
        except Exception as e:
            logger.error(f"Wallet ensure fail for {p['id']}: {e}")

    return w or "Not linked"

# ── FSM States ─────────────────────────────────────────────────────────────────
class ChallengeRitual(StatesGroup):
    select_game     = State()
    set_stake       = State()
    select_team     = State()
    choose_opponent = State()
    confirm         = State()

class AcceptChallenge(StatesGroup):
    pick_team = State()

# ── START COMMAND ───────────────────────────────────────────────────────────────
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    args = message.text.split() if message.text else []
    if len(args) > 1 and args[1].startswith("accept_"):
        mid = args[1].replace("accept_", "")
        p = await get_profile(message.from_user)
        if p:
            await state.set_state(AcceptChallenge.pick_team)
            await state.update_data(match_id=mid)
            await send(message.bot, message.chat.id,
                f"⚡ *BATTLE REQUEST*\n\nMatch `{mid}` — pick your team!",
                reply_markup=team_menu("acceptor"))
        return

    p = await get_profile(message.from_user)
    if not p:
        await send(message.bot, message.chat.id, "❌ Profile error."); return
    n = p.get("display_name") or message.from_user.first_name or "Gamer"
    w = await ensure_wallet(p)
    w_d = f"{w[:10]}..." if w and len(w) > 10 else w
    await send(message.bot, message.chat.id,
        f"🎮 *sideQuest — Gamer OS*\n\n"
        f"Hey *{n}*, vault ready.\n"
        f"🔗 `{w_d}`\n\n"
        f"*Choose:*",
        reply_markup=main_menu())

# ── SETTINGS / LINK COMMANDS ────────────────────────────────────────────────────
async def cmd_settings(message: types.Message):
    p = await get_profile(message.from_user)
    if not p:
        await send(message.bot, message.chat.id, "❌ Profile error."); return
    pub = bool(p.get("is_public_available", False))
    await send(message.bot, message.chat.id,
        f"⚙️ *SETTINGS*\n\n"
        f"Public Challenges: {'🔔 ON' if pub else '🔕 OFF'}\n\n"
        f"Toggle to receive BATTLE ALERTS.",
        reply_markup=profile_menu(pub))

async def cmd_link_email(message: types.Message, command: CommandObject):
    # Kept minimal — email logic unchanged
    await send(message.bot, message.chat.id,
        "📧 *LINK EMAIL*\n\n"
        "Use `/link_email <address>` to link your email for notifications.",
        reply_markup=back_menu())

async def cmd_link_wallet(message: types.Message, command: CommandObject):
    p = await get_profile(message.from_user)
    if not p:
        await send(message.bot, message.chat.id, "❌ Profile error."); return
    addr = command.args
    if not addr:
        await send(message.bot, message.chat.id,
            "🏦 *LINK WITHDRAWAL WALLET*\n\n"
            "Use `/link_wallet <ethereum_address>` to set where your winnings go.\n"
            "Example: `/link_wallet 0x123...`\n\n"
            "This address will receive withdrawal payouts.")
        return
    addr = addr.strip()
    if not addr.startswith("0x") or len(addr) != 42:
        await send(message.bot, message.chat.id, "❌ Invalid Ethereum address format.")
        return
    try:
        from web3 import Web3
        checksum = Web3.to_checksum_address(addr)
        controller.db.supabase.table("profiles")\
            .update({"linked_wallet": checksum})\
            .eq("id", p["id"]).execute()
        await send(message.bot, message.chat.id,
            f"✅ *Withdrawal wallet linked!*\n\n"
            f"🏦 `{checksum}`\n\n"
            f"Your winnings will be sent here.",
            reply_markup=profile_menu(p.get("is_public_available", False)))
    except Exception as e:
        logger.error(f"Link wallet fail: {e}")
        await send(message.bot, message.chat.id, "❌ Error linking wallet.")

async def cmd_debug_wallet(message: types.Message):
    p = await get_profile(message.from_user)
    if not p:
        await send(message.bot, message.chat.id, "❌ Profile error."); return
    custodial_addr = p.get("wallet_address")
    circle_id = p.get("circle_wallet_id")
    wallet_bal = "N/A"
    if custodial_addr:
        try:
            from backend.services.circle_vault import get_live_balance
            if circle_id:
                bal = await get_live_balance(circle_id)
                wallet_bal = f"${bal:.2f}" if bal is not None else "Error"
            else:
                wallet_bal = "No Circle ID"
        except Exception as e:
            wallet_bal = f"Error: {e}"
    await send(message.bot, message.chat.id,
        f"🐛 *WALLET DEBUG*\n\n"
        f"circle_wallet_id: `{circle_id or 'N/A'}`\n"
        f"wallet_address: `{custodial_addr or 'N/A'}`\n"
        f"telegram_id: `{p.get('telegram_id') or 'N/A'}`\n"
        f"on_chain_balance: {wallet_bal}\n"
        f"profile_id: `{p.get('id')}`")

async def cmd_balance_history(message: types.Message):
    p = await get_profile(message.from_user)
    if not p:
        await send(message.bot, message.chat.id, "❌ Profile error."); return
    try:
        res = controller.db.supabase.table("global_activity_logs")\
            .select("event_type, amount_usd, details, created_at")\
            .eq("user_id", p["id"])\
            .order("created_at", desc=True)\
            .limit(10).execute()
        logs = res.data if res.data else []
        if not logs:
            await send(message.bot, message.chat.id, "📋 No transaction history yet.")
            return
        text = "📋 *Recent Transactions*\n\n"
        for log in logs:
            etype = log["event_type"]
            amt   = log.get("amount_usd", 0)
            when  = log["created_at"][:16].replace("T", " ")
            tx    = log.get("details", {}).get("tx_hash", "")
            tx    = tx[:10] + "..." if tx else ""
            emoji = "✅" if etype == "DEPOSIT" else "💸" if etype == "WITHDRAWAL" else "🎯"
            text += f"{emoji} `{when}` {etype} ${amt:.2f} `{tx}`\n"
        await send(message.bot, message.chat.id, text, reply_markup=back_menu())
    except Exception as e:
        logger.error(f"History fail: {e}")
        await send(message.bot, message.chat.id, "❌ Could not load history.")

async def cmd_check_balance(message: types.Message):
    p = await get_profile(message.from_user)
    if not p:
        await send(message.bot, message.chat.id, "❌ Profile error."); return

    custodial_addr = p.get("wallet_address")
    circle_id = p.get("circle_wallet_id")
    if not custodial_addr or not circle_id:
        await send(message.bot, message.chat.id, "❌ No custodial wallet. Run /reset_wallet first.")
        return

    try:
        from backend.services.circle_vault import get_live_balance
        onchain = await get_live_balance(circle_id)
        response = (
            f"💰 *Live Balance Check*\n\n"
            f"Deposit Address: `{custodial_addr}`\n\n"
            f"On-Chain Balance: ${onchain:.2f if onchain is not None else 'N/A'} USDC\n\n"
            f"✅ Verified on Base Sepolia"
        )
        await send(message.bot, message.chat.id, response, reply_markup=back_menu())
    except Exception as e:
        logger.error(f"Manual balance check failed for {p['id']}: {e}")
        await send(message.bot, message.chat.id, f"❌ Balance check failed: {e}")

async def cmd_reset_wallet(message: types.Message):
    p = await get_profile(message.from_user)
    if not p:
        await send(message.bot, message.chat.id, "❌ Profile error."); return
    pid = p["id"]
    try:
        controller.db.supabase.table("profiles").update({
            "wallet_address": None,
            "circle_wallet_id": None,
            "circle_wallet_set_id": None
        }).eq("id", pid).execute()
        logger.info(f"[Reset] Cleared wallet data for {pid}")

        w = await ensure_wallet(p)
        if w and w != "Not linked":
            await send(message.bot, message.chat.id,
                f"✅ *Wallet Reset Complete!*\n\n"
                f"🔑 **Your new custodial wallet:**\n"
                f"`{w}`\n\n"
                f"💵 Send USDC to this address on Base Sepolia.\n"
                f"📊 Balance will update automatically.\n\n"
                f"⚠️ Old wallet data cleared.",
                reply_markup=profile_menu(p.get("is_public_available", False)))
        else:
            await send(message.bot, message.chat.id, "❌ Failed to create new wallet.")
    except Exception as e:
        logger.error(f"Reset wallet fail: {e}")
        await send(message.bot, message.chat.id, f"❌ Error: {e}")

# ── NAVIGATION CALLBACKS ─────────────────────────────────────────────────────────
async def nav_main(cb: types.CallbackQuery, state: FSMContext):
    await cb.answer()
    await state.clear()
    p = await get_profile(cb.from_user)
    n = (p or {}).get("display_name") or cb.from_user.first_name or "Gamer"
    await send(cb.bot, cb.from_user.id, f"📋 *MENU*\n\nHey *{n}*!", reply_markup=main_menu())

async def nav_wallet(cb: types.CallbackQuery):
    await cb.answer()
    p = await get_profile(cb.from_user)
    if not p:
        await send(cb.bot, cb.from_user.id, "❌ Not found", reply_markup=back_menu()); return
    w = await ensure_wallet(p)
    circle_id = p.get("circle_wallet_id")
    wallet_bal = None
    try:
        from backend.services.circle_vault import get_live_balance
        if circle_id:
            wallet_bal = await get_live_balance(circle_id)
    except Exception as e:
        logger.error(f"Wallet balance fetch failed: {e}")
    bal_str = f"${wallet_bal:.2f}" if wallet_bal is not None else "Loading..."
    await send(cb.bot, cb.from_user.id,
        f"💰 *VAULT*\n\n"
        f"Balance: *{bal_str} USDC*\n"
        f"Address: `{w}`\n\n"
        f"✅ USDC only on Base Sepolia",
        reply_markup=back_menu())

async def nav_leader(cb: types.CallbackQuery):
    await cb.answer()
    p = await get_profile(cb.from_user)
    if not p:
        await send(cb.bot, cb.from_user.id, "❌ Error", reply_markup=back_menu()); return
    t = await controller._cmd_leaderboard(p, [])
    await send(cb.bot, cb.from_user.id, t, reply_markup=back_menu())

async def nav_web(cb: types.CallbackQuery):
    await cb.answer()
    await send(cb.bot, cb.from_user.id, f"🌐 *Open Arena*\n\n{WEB_APP_URL}", reply_markup=back_menu())

async def nav_profile(cb: types.CallbackQuery):
    await cb.answer()
    p = await get_profile(cb.from_user)
    if not p:
        await send(cb.bot, cb.from_user.id, "❌ Error", reply_markup=back_menu()); return
    pub = bool(p.get("is_public_available", False))
    email = p.get("email") or "Not linked"
    psn = p.get("psn_id") or "Not linked"
    xbox = p.get("xbox_id") or "Not linked"
    custodial = p.get("wallet_address") or "Not set"
    external = p.get("linked_wallet") or "Not set"
    circle_id = p.get("circle_wallet_id")
    wallet_bal = None
    if custodial and custodial != "Not set" and circle_id:
        try:
            from backend.services.circle_vault import get_live_balance
            wallet_bal = await get_live_balance(circle_id)
        except Exception as e:
            logger.error(f"On-chain balance fetch failed: {e}")
    bal_str = f"${wallet_bal:.2f}" if wallet_bal is not None else "Loading..."
    await send(cb.bot, cb.from_user.id,
        f"👤 *PROFILE*\n\n"
        f"Name: *{p.get('display_name', 'N/A')}*\n"
        f"📧 Email: `{email}`\n"
        f"🎮 PSN: `{psn}`\n"
        f"🕹️ Xbox: `{xbox}`\n"
        f"PLAY: *{p.get('play_points', 0):,}*\n\n"
        f"💰 Wallet Balance: *{bal_str} USDC*\n\n"
        f"Deposit to: `{custodial[:12] if custodial != 'Not set' else 'N/A'}...`\n"
        f"Withdraw to: `{external[:12] if external != 'Not set' else 'N/A'}...`\n\n"
        f"Public Matchmaking: {'🔔 ON' if pub else '🔕 OFF'}",
        reply_markup=profile_menu(pub))

async def toggle_pub(cb: types.CallbackQuery):
    await cb.answer()
    p = await get_profile(cb.from_user)
    if not p:
        await send(cb.bot, cb.from_user.id, "❌ Error"); return
    nv = not bool(p.get("is_public_available", False))
    try:
        controller.db.supabase.table("profiles").update(
            {"is_public_available": nv}).eq("id", p["id"]).execute()
        msg = ("🔔 *PUBLIC CHALLENGES ON*\n\nYou'll receive BATTLE ALERTS!"
               if nv else "🔕 *PUBLIC CHALLENGES OFF*\n\nYou won't receive public challenges.")
        await send(cb.bot, cb.from_user.id, msg, reply_markup=profile_menu(nv))
    except Exception as e:
        logger.error(f"Toggle fail: {e}")
        await send(cb.bot, cb.from_user.id, "❌ Update failed.", reply_markup=profile_menu(not nv))

# ── CHALLENGE RITUAL FSM ─────────────────────────────────────────────────────────
async def ritual_start(cb: types.CallbackQuery, state: FSMContext):
    await cb.answer()
    await state.set_state(ChallengeRitual.select_game)
    await send(cb.bot, cb.from_user.id, "🎮 *STEP 1: SELECT GAME*", reply_markup=challenge_menu())

async def ritual_game(cb: types.CallbackQuery, state: FSMContext):
    await cb.answer()
    games = {"eafc": "EA FC", "nba": "NBA 2K", "fifa": "FIFA"}
    key = cb.data.replace("g_", "", 1)
    if key not in games:
        await send(cb.bot, cb.from_user.id, "❌ Invalid game.", reply_markup=back_menu()); return
    await state.update_data(game=games[key], game_key=key)
    await state.set_state(ChallengeRitual.set_stake)
    await send(cb.bot, cb.from_user.id,
        f"🎯 *STEP 2: STAKE*\n\nGame: *{games[key]}*",
        reply_markup=stake_menu())

async def ritual_stake(cb: types.CallbackQuery, state: FSMContext):
    await cb.answer()
    val = cb.data.replace("s_", "", 1)
    if val == "custom":
        await send(cb.bot, cb.from_user.id, "✏️ Reply with stake in ₦ (e.g. 2500)")
        return
    try:
        stake = float(val)
        if stake < 1000:
            await send(cb.bot, cb.from_user.id, "❌ Min ₦1000.", reply_markup=stake_menu()); return
        await state.update_data(stake_naira=stake, stake_usd=round(stake / 1600, 4))
        await state.set_state(ChallengeRitual.select_team)
        await send(cb.bot, cb.from_user.id,
            f"🎯 Stake: ₦{stake:,.0f}\n\n🎮 *STEP 3: YOUR TEAM*\n\nPick your side:",
            reply_markup=team_menu("host"))
    except Exception:
        await send(cb.bot, cb.from_user.id, "❌ Invalid stake.", reply_markup=stake_menu())

async def ritual_custom_stake(message: types.Message, state: FSMContext):
    try:
        stake = float(message.text.replace(",", "").replace("₦", "").strip())
        if stake < 1000:
            await send(message.bot, message.chat.id, "❌ Min ₦1000."); return
        await state.update_data(stake_naira=stake, stake_usd=round(stake / 1600, 4))
        await state.set_state(ChallengeRitual.select_team)
        await send(message.bot, message.chat.id,
            f"🎯 Stake: ₦{stake:,.0f}\n\n🎮 *YOUR TEAM*\n\nSelect:",
            reply_markup=team_menu("host"))
    except Exception:
        await send(message.bot, message.chat.id, "❌ Send a number only (e.g. 2500)")

async def ritual_team(cb: types.CallbackQuery, state: FSMContext):
    await cb.answer()
    parts = cb.data.split(":", 2)
    if len(parts) < 3:
        await send(cb.bot, cb.from_user.id, "❌ Invalid selection."); return
    team = parts[2]
    await state.update_data(host_team=team)
    await state.set_state(ChallengeRitual.choose_opponent)
    await send(cb.bot, cb.from_user.id,
        f"🛡️ Your Team: *{team}*\n\n🎯 *STEP 4: OPPONENT*\n\nInvite / Search / Public",
        reply_markup=opponent_menu())

async def ritual_opponent(cb: types.CallbackQuery, state: FSMContext):
    await cb.answer()
    act = cb.data.replace("opp_", "", 1)
    if act == "invite":
        mid = str(uuid.uuid4())[:8]
        me = await cb.bot.get_me()
        link = f"https://t.me/{me.username}?start=challenge_{mid}"
        await state.set_state(ChallengeRitual.confirm)
        await send(cb.bot, cb.from_user.id,
            f"📤 *INVITE FRIEND*\n\nShare this link:\n`{link}`",
            reply_markup=confirm_menu(mid))
    elif act == "search":
        await send(cb.bot, cb.from_user.id, "🔍 Reply with opponent's @username (without @)")
    elif act == "public":
        await state.update_data(is_public=True)
        d = await state.get_data()
        await state.set_state(ChallengeRitual.confirm)
        await send(cb.bot, cb.from_user.id,
            f"🌎 *PUBLIC ARENA*\n\n"
            f"Broadcast to all public users?\n"
            f"Game: {d.get('game')}\n"
            f"Stake: ₦{d.get('stake_naira', 0):,.0f}\n"
            f"Team: {d.get('host_team')}\n\n"
            f"Click *[✅ BROADCAST]* to go live!",
            reply_markup=confirm_menu("public"))

async def ritual_opponent_text(message: types.Message, state: FSMContext):
    uname = message.text.replace("@", "").strip()
    d = await state.get_data()
    await state.update_data(opponent_username=uname, is_public=False)
    await state.set_state(ChallengeRitual.confirm)
    await send(message.bot, message.chat.id,
        f"📋 *CONFIRM CHALLENGE*\n\n"
        f"🎮 {d.get('game')}\n"
        f"💰 ₦{d.get('stake_naira', 0):,.0f}\n"
        f"👤 @{uname}\n\n"
        f"Click *[✅ LOCK STAKES]*",
        reply_markup=confirm_menu("private"))

async def ritual_confirm(cb: types.CallbackQuery, state: FSMContext):
    await cb.answer()
    if cb.data == "conf_cancel":
        await state.clear()
        await send(cb.bot, cb.from_user.id, "❌ Cancelled.", reply_markup=main_menu()); return

    p = await get_profile(cb.from_user)
    if not p:
        await send(cb.bot, cb.from_user.id, "❌ Profile error."); return

    d = await state.get_data()
    stake = d.get("stake_naira", 0)
    game = d.get("game", "Unknown")
    host_team = d.get("host_team", "TBD")
    opp_uname = d.get("opponent_username")
    is_pub = d.get("is_public", False)

    try:
        result = await controller._cmd_challenge(p, [str(stake), game, opp_uname or ""])
        if isinstance(result, dict):
            mid = result.get("match_id", str(uuid.uuid4())[:8])
            opp_tid = result.get("opponent_tele_id")
            opp_wa = result.get("opponent_whatsapp")

            # Send invite to opponent via Telegram or WhatsApp
            if opp_tid:
                await send(cb.bot, opp_tid,
                    f"⚔️ *CHALLENGE!*\n\n"
                    f"*{p.get('display_name', 'Player')}* vs you\n"
                    f"🎮 {game} | 💰 ₦{stake:,.0f}\n\n"
                    f"Accept: /match {mid}",
                    reply_markup=accept_challenge_menu(mid))
            elif opp_wa:
                # Send WhatsApp invite
                me = await cb.bot.get_me()
                wa_text = (
                    f"⚔️ *CHALLENGE!*\n\n"
                    f"*{p.get('display_name', 'Player')}* challenged you to {game} for ₦{stake:,.0f}.\n"
                    f"Match ID: {mid}\n"
                    f"Accept via Telegram: https://t.me/{me.username}?start=challenge_{mid}\n"
                    f"Or WhatsApp: send /match {mid} to the sideQuest bot."
                )
                try:
                    await controller.bridge.send_message(opp_wa, wa_text)
                except Exception as e:
                    logger.error(f"WhatsApp invite failed: {e}")

            # Persist creator's team selection (from FSM state)
            host_team = d.get("host_team")
            if host_team:
                try:
                    await controller.matches.set_match_team(mid, p["id"], host_team)
                except Exception as e:
                    logger.error(f"Failed to set creator team for match {mid}: {e}")

            await send(cb.bot, cb.from_user.id,
                f"✅ *CHALLENGE CREATED!*\n\n"
                f"Match `{mid}`\n"
                f"Game: {game} | Stake: ₦{stake:,.0f}\n"
                f"Team: {host_team}\n\n"
                f"Waiting for opponent...",
                reply_markup=main_menu())
            if is_pub:
                stake_usd = d.get("stake_usd", round(stake / 1600, 4))
                asyncio.create_task(
                    broadcast_battle_alert(cb.bot, mid, game, stake_usd,
                                           p.get("display_name", "Player")))
                asyncio.create_task(
                    challenge_expiry(mid, p["id"], stake))
        else:
            await send(cb.bot, cb.from_user.id, str(result), reply_markup=main_menu())
        await state.clear()
    except Exception as e:
        logger.error(f"Challenge confirm fail: {e}", exc_info=True)
        await send(cb.bot, cb.from_user.id, f"❌ Error creating challenge. Try again.", reply_markup=main_menu())

# ── BATTLE ALERT BROADCAST ──────────────────────────────────────────────────────
async def broadcast_battle_alert(bot_instance: Bot, match_id: str, game: str,
                                  stake_usd: float, host_name: str):
    try:
        res = controller.db.supabase.table("profiles").select("telegram_id")\
            .eq("is_public_available", True).execute()
        users = res.data or []
        alert = (
            f"🚨 *BATTLE ALERT :: PUBLIC ARENA* 🚨\n\n"
            f"A new challenger has entered!\n\n"
            f"🎮 *{game}*\n"
            f"💰 Stake: ${stake_usd:.2f} USDC\n"
            f"👑 Host: {host_name}\n\n"
            f"⏳ Expiry: 15 minutes — first to accept wins.\n\n"
            f"⚡ Tap to accept ↓"
        )
        for u in users:
            tid = u.get("telegram_id")
            if tid:
                try:
                    await send(bot_instance, int(tid), alert,
                               reply_markup=accept_challenge_menu(match_id))
                except Exception:
                    pass
    except Exception as e:
        logger.error(f"Broadcast error: {e}")

# ── CHALLENGE EXPIRY ────────────────────────────────────────────────────────────
async def challenge_expiry(match_id: str, creator_id: str, stake_naira: float):
    await asyncio.sleep(900)
    try:
        m = await controller.matches.get_match(match_id)
        if not m or m.get("status") != "OPEN":
            return
        sb = controller.db.supabase
        sb.table("bets").update({"status": "CANCELLED"}).eq("id", m.get("id", match_id)).execute()
        from backend.db_layer_blockchain import credit_wallet
        stake_usd = round(stake_naira / 1600, 4)
        await credit_wallet(creator_id, stake_usd, f"refund_expiry_{match_id}", "expiry_refund")
        creator = await get_profile_by_id(creator_id)
        if creator and creator.get("telegram_id"):
            await send_to_user(int(creator["telegram_id"]),
                f"⏰ *CHALLENGE EXPIRED*\n\n"
                f"Match `{match_id}` cancelled after 15 min.\n"
                f"₦{stake_naira:,.0f} refunded to your wallet.")
    except Exception as e:
        logger.error(f"Expiry error for {match_id}: {e}")

async def send_to_user(tid: int, text: str):
    b = Bot(token=os.getenv("TELEGRAM_BOT_TOKEN"), default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN))
    try:
        await send(b, tid, text)
    finally:
        await b.session.close()

# ── ACCEPT CHALLENGE ────────────────────────────────────────────────────────────
async def accept_challenge(cb: types.CallbackQuery, state: FSMContext):
    await cb.answer()
    parts = cb.data.split(":", 1)
    match_id = parts[1] if len(parts) > 1 else ""
    p = await get_profile(cb.from_user)
    if not p:
        await send(cb.bot, cb.from_user.id, "❌ Profile error."); return
    try:
        m = await controller.matches.get_match(match_id)
        if not m or m.get("status") != "OPEN":
            await send(cb.bot, cb.from_user.id,
                "❌ Slot already filled or match closed.", reply_markup=main_menu()); return
        text = await controller._cmd_match(p, [match_id])
        if any(kw in text for kw in ("Accepted", "Joined", "✅")):
            await state.set_state(AcceptChallenge.pick_team)
            await state.update_data(match_id=match_id)
            await send(cb.bot, cb.from_user.id,
                f"✅ *MATCH JOINED!*\n\nPick your team for `{match_id}`:",
                reply_markup=team_menu("acceptor"))
        else:
            await send(cb.bot, cb.from_user.id, text, reply_markup=main_menu())
    except Exception as e:
        logger.error(f"accept_challenge error: {e}")
        await send(cb.bot, cb.from_user.id, f"❌ {e}", reply_markup=main_menu())

async def pick_team(cb: types.CallbackQuery, state: FSMContext):
    await cb.answer()
    parts = cb.data.split(":", 2)
    if len(parts) < 3:
        await send(cb.bot, cb.from_user.id, "❌ Invalid selection."); return
    team = parts[2]
    data = await state.get_data()
    match_id = data.get("match_id", "")
    p = await get_profile(cb.from_user)
    if not p:
        await send(cb.bot, cb.from_user.id, "❌ Profile error."); return
    try:
        res = await controller._cmd_set_team(p, match_id, team)
        await send(cb.bot, cb.from_user.id,
            f"✅ *{team}* locked in!\n\n"
            f"Match `{match_id}` is LIVE.\n"
            f"Finish & submit scores with /report",
            reply_markup=main_menu())
        await state.clear()
        m = await controller.matches.get_match(match_id)
        if m:
            creator = await get_profile_by_id(m.get("creator_id", ""))
            if creator and creator.get("telegram_id"):
                await send_to_user(int(creator["telegram_id"]),
                    f"🔥 *Match `{match_id}` ACTIVE!*\n\n"
                    f"Opponent joined — start playing!")
    except Exception as e:
        logger.error(f"pick_team error: {e}")
        await send(cb.bot, cb.from_user.id, f"❌ {e}", reply_markup=main_menu())

# ── FALLBACK ────────────────────────────────────────────────────────────────────
async def fallback(message: types.Message, state: FSMContext):
    cur = await state.get_state()
    if cur:
        return
    if message.text and message.text.startswith("/"):
        await send(message.bot, message.chat.id,
            "❓ Unknown command. Use menu buttons.", reply_markup=main_menu())
    else:
        await send(message.bot, message.chat.id,
            "👋 Tap a button to start.", reply_markup=main_menu())
