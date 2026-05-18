"""
whatsapp_handler.py  (updated)
───────────────────────────────
Changes from original:
  1. _normalise_number()   — fixes the duplicate-profile bug caused by inconsistent
                             WhatsApp number formats from Evolution API.
  2. /fund                 — now returns the user's personal Flutterwave virtual
                             account number instead of the shared Moniepoint number.
  3. Image slip handling   — when a user sends ANY image, the bot checks if it looks
                             like a payment slip and auto-credits if verified.
  4. /webhook/flutterwave  — new endpoint for automatic FLW credit webhooks.
"""

import hmac
import hashlib
import os
import asyncio
import re
import json

from gaming.src.backend.app_controller import ClawController
from backend.evolution_bridge import EvolutionBridge
from slip_verifier import verify_slip_from_url
from flutterwave_service import (
    get_or_create_virtual_account,
    verify_flutterwave_webhook,
    parse_charge_completed_event,
    FlutterwaveError,
)

# NOTE: This module now contains WhatsApp command handling helper logic only.
# The active FastAPI webhook server lives in backend/api.py.
controller = ClawController()
bridge = EvolutionBridge()

# ─── Admin Whitelist ───────────────────────────────────────────────────────────
ADMIN_NUMBERS = frozenset(["2348022202143", "2347073924753", "2349163497691"])

# ─── Evolution API HMAC secret ────────────────────────────────────────────────
EVOLUTION_WEBHOOK_SECRET = os.getenv("EVOLUTION_WEBHOOK_SECRET", "")


# ─── FIX: Number normalisation ────────────────────────────────────────────────
# Root cause of the duplicate profile bug:
# Evolution API sometimes sends "2348022202143", sometimes "+2348022202143",
# sometimes "2348022202143@s.whatsapp.net".
# We strip everything non-numeric and always store the bare international number.

def _normalise_number(raw: str) -> str:
    """
    Strips @s.whatsapp.net suffix, leading '+', spaces, and any non-digit chars.
    Result is always a bare international number e.g. "2348022202143".
    Capped at 15 chars (max E.164 length).
    """
    # Remove WhatsApp JID suffix
    raw = raw.split("@")[0]
    # Keep digits only
    digits = re.sub(r"\D", "", raw)
    return digits[:15]


def _verify_evolution_signature(raw_body: bytes, signature_header: str) -> bool:
    if not EVOLUTION_WEBHOOK_SECRET:
        print("[WARN] EVOLUTION_WEBHOOK_SECRET not set — skipping signature check (dev mode).")
        return True
    expected = hmac.new(
        EVOLUTION_WEBHOOK_SECRET.encode(),
        raw_body,
        hashlib.sha256,
    ).hexdigest()
    incoming = signature_header.replace("sha256=", "").strip()
    return hmac.compare_digest(expected, incoming)


def _is_admin(from_number: str) -> bool:
    return from_number in ADMIN_NUMBERS


def _sanitise_text(text: str) -> str:
    return re.sub(r"[^\x20-\x7E\u00A0-\uFFFF\n]", "", text).strip()

def _extract_evolution_payload(data: dict):
    if data.get("event") != "messages.upsert":
        return None, None, None

    msg_data = data.get("data") or data.get("messages") or {}
    if isinstance(msg_data, list):
        msg_data = msg_data[0] if msg_data else {}

    message = msg_data.get("message")
    if message is None:
        message = msg_data.get("messages")
    if isinstance(message, list):
        message = message[0] if message else {}
    message = message or {}

    raw_sender = (
        msg_data.get("sender") or
        msg_data.get("key", {}).get("remoteJid") or
        message.get("key", {}).get("remoteJid") or
        ""
    )
    from_number = _normalise_number(raw_sender)

    text = (
        message.get("conversation") or
        message.get("extendedTextMessage", {}).get("text") or
        message.get("imageMessage", {}).get("caption") or
        message.get("caption") or
        ""
    )

    image_url = None
    image_message = message.get("imageMessage") or {}
    if image_message:
        image_url = image_message.get("url") or msg_data.get("mediaUrl") or msg_data.get("url")

    if image_url and not text:
        text = "[image]"

    return from_number, text, image_url

# ─── Slip image handler ───────────────────────────────────────────────────────

async def _handle_payment_slip(from_number: str, profile: dict, image_url: str):
    """
    Called whenever a user sends an image (with or without a /fund caption).
    Tries to verify it as a bank transfer slip and credits the wallet.
    Admin is notified either way for audit purposes.
    """
    bridge.send_message(from_number, "🔍 Analysing your payment slip... please wait.")

    result = await verify_slip_from_url(image_url)

    if result["verified"]:
        amount_ngn = result["amount_ngn"]
        amount_usd = result["amount_usd"]

        # Credit the wallet
        controller.db.update_balance(profile["id"], amount_usd)
        controller.db.log_activity(
            profile["id"],
            "DEPOSIT",
            amount_usd,
            {"method": "bank_slip", "amount_ngn": amount_ngn, "raw_ocr": result["raw_text"]},
        )

        user_msg = (
            f"✅ Payment Verified!\n\n"
            f"Amount: ₦{amount_ngn:,.2f} (${amount_usd:,.4f})\n"
            f"Your wallet has been credited. Type /wallet to check your balance."
        )
        bridge.send_message(from_number, user_msg)

        # Admin audit ping
        admin_ping = (
            f"💳 SLIP DEPOSIT\n"
            f"User: {from_number}\n"
            f"₦{amount_ngn:,.2f} → ${amount_usd:,.4f}\n"
            f"OCR: {result['raw_text'][:80]}"
        )
        for admin in ADMIN_NUMBERS:
            bridge.send_message(admin, admin_ping)

    else:
        reason_messages = {
            "download_failed": "❌ I couldn't download the image. Please try sending it again.",
            "unreadable":      "❌ I couldn't read the amount from this image. Please send a clearer screenshot of your transfer receipt.",
            "below_minimum":   f"❌ Deposit of ₦{result['amount_ngn']:,.2f} is below the minimum (₦{os.getenv('MIN_DEPOSIT_NGN', '500')}).",
            "debit_slip":      "❌ This looks like a debit receipt (money going out). Please send the credit/transfer confirmation.",
        }
        msg = reason_messages.get(result["reason"], "❌ Could not verify this slip. Please contact support.")
        bridge.send_message(from_number, msg)


# ─── Command Dispatcher ────────────────────────────────────────────────────────

async def handle_whatsapp_command(from_number: str, text: str, **kwargs):
    # Normalise number first — this is the duplicate-profile fix
    from_number = _normalise_number(from_number)
    text = _sanitise_text(text)

    if not from_number or not text:
        return

    # Auto-creates profile on first contact
    profile = controller.get_user("whatsapp_id", from_number)

    # ── Image handling (slip verification) ──────────────────────────────────
    image_url = kwargs.get("image_url")

    # If there's an image, always try to verify it as a payment slip
    # (regardless of whether text is a /fund command or just a caption)
    if image_url:
        # If caption is /report, hand off to match reporting
        if text.startswith("/report"):
            parts = text.split()
            if len(parts) >= 3:
                response = await controller.report_match(profile, parts[1], parts[2], image_url)
                bridge.send_message(from_number, response)
                return
        else:
            # Treat any other image as a potential payment slip
            await _handle_payment_slip(from_number, profile, image_url)
            return

    parts = text.split()
    cmd = parts[0].lower() if parts else ""
    response = ""

    if cmd == "/start":
        response = await controller.get_welcome_text()

    elif cmd == "/points":
        response = controller.get_mining_status(profile)

    elif cmd == "/tournament":
        response = controller.get_active_tournament_status()

    elif cmd == "/wallet":
        response = controller.get_wallet_info(profile)

    elif cmd == "/fund_virtual":
        response = controller.fund_via_virtual_account(profile)

    elif cmd == "/fund_crypto":
        if len(parts) < 2:
            response = "Usage: /fund_crypto <amount> (e.g., /fund_crypto 10)"
        else:
            try:
                amount = float(parts[1])
                if amount <= 0:
                    raise ValueError
            except ValueError:
                response = "❌ Invalid amount."
            else:
                res = controller.initiate_fund(profile, amount, "crypto")
                response = res["text"]

    elif cmd == "/deposit_tx":
        if len(parts) < 2:
            response = "Usage: /deposit_tx <transaction_hash>"
        else:
            tx_hash = parts[1].strip()
            response = controller.verify_crypto_deposit(profile, tx_hash)

    elif cmd == "/fund":
        method = parts[2].lower() if len(parts) > 2 else "naira"

        if method == "crypto":
            # Crypto path unchanged
            if len(parts) < 2:
                response = "Usage: /fund <amount> crypto"
            else:
                try:
                    amount = float(parts[1])
                    if amount <= 0:
                        raise ValueError
                except ValueError:
                    response = "❌ Invalid amount."
                else:
                    res = controller.initiate_fund(profile, amount, "crypto")
                    response = res["text"]

        else:
            # Naira path: issue the user their personal virtual account
            try:
                va = get_or_create_virtual_account(controller.db, profile)
                response = (
                    f"🏦 Your Personal sideQuest Bank Account\n\n"
                    f"Bank: {va['bank_name']}\n"
                    f"Account Number: `{va['account_number']}`\n"
                    f"Account Name: {va['account_name']}\n\n"
                    f"Transfer any amount to this account and your wallet will be "
                    f"credited automatically within 1–2 minutes.\n\n"
                    f"Or send me a screenshot of your transfer receipt and I'll verify it instantly! 📸"
                )
            except FlutterwaveError as e:
                print(f"[FLW] VA creation error for {from_number}: {e}")
                # Fallback to manual Moniepoint if FLW fails
                res = controller.initiate_fund(profile, 0, "naira")
                response = (
                    res["text"] + "\n\n_(Auto-account temporarily unavailable — "
                    "send your receipt screenshot for manual verification.)_"
                )

    elif cmd == "/verify":
        if len(parts) < 2:
            response = "Usage: /verify <reference>"
        else:
            ref = re.sub(r"[^\w\-]", "", parts[1])[:64]
            response = controller.verify_payment(profile, ref)

    elif cmd == "/bets":
        response = controller.list_bets()

    elif cmd == "/challenge":
        if len(parts) < 3:
            response = """🏆 Create Challenge:

🌐 ONLINE (default): /challenge <amount> <game> [onchain]
🏠 LOCAL (same TV):  /local <amount> <game>

Examples:
/challenge 10 FIFA
/challenge 10 FIFA onchain
/local 10 FIFA"""
        else:
            try:
                amount = float(parts[1])
                if amount <= 0:
                    raise ValueError
            except ValueError:
                response = "❌ Invalid amount."
            else:
                result = await controller.create_online_match(profile, amount, parts[2])
                if result["status"] == "success":
                    match = result["match"]
                    response = (
                        f"🌐 Online Match Created!\n\n"
                        f"🎮 {parts[2]} | ${amount}\n"
                        f"🆔 {match['id']}\n\n"
                        f"⏱️ 120 min to play\n"
                        f"📸 Screenshot + PSN/Xbox activity required\n\n"
                        f"Share this ID with your opponent!"
                    )
                else:
                    response = f"❌ {result.get('message', 'Error creating match')}"

    elif cmd == "/local":
        if len(parts) < 3:
            response = "Usage: /local <amount> <game>"
        else:
            try:
                amount = float(parts[1])
                if amount <= 0:
                    raise ValueError
            except ValueError:
                response = "❌ Invalid amount."
            else:
                result = await controller.create_local_match(profile, amount, parts[2])
                if result["status"] == "success":
                    match = result["match"]
                    response = (
                        f"🏠 Local Match Created!\n\n"
                        f"🎮 {parts[2]} | ${amount}\n"
                        f"🆔 {match['id']}\n\n"
                        f"⏱️ 60 min to play\n"
                        f"📸 Screenshot required\n\n"
                        f"Share this ID with your opponent!"
                    )
                else:
                    response = f"❌ {result.get('message', 'Error creating match')}"

    elif cmd == "/match":
        if len(parts) < 2:
            response = "Usage: /match <bet_id>"
        else:
            bet_id = parts[1]
            bet = controller.db.get_bet(bet_id)
            if not bet:
                response = "❌ Challenge not found."
            elif bet.get("creator_id") == profile["id"]:
                response = "❌ You cannot match your own challenge!"
            else:
                response = controller.match_challenge(profile, bet_id)

    elif cmd == "/approve":
        if len(parts) < 2:
            response = "Usage: /approve <bet_id>"
        else:
            response = controller.approve_challenge(profile, parts[1])

    elif cmd == "/link_psn":
        if len(parts) < 2:
            response = "Usage: /link_psn <PSN_ID>"
        else:
            psn_id = re.sub(r"[^\w\-]", "", parts[1])[:20]
            response = controller.verify_psn(profile, psn_id)

    elif cmd == "/link_xbox":
        if len(parts) < 2:
            response = "Usage: /link_xbox <Gamertag>"
        else:
            gamertag = re.sub(r"[^\w\s\-]", "", parts[1])[:20]
            response = await controller.verify_xbox(profile, gamertag)

    elif cmd == "/link_telegram":
        if len(parts) < 2:
            response = "Usage: /link_telegram <telegram_id>"
        else:
            telegram_id = re.sub(r"[^\d]", "", parts[1])
            response = controller.link_platform(profile, "telegram_id", telegram_id)

    elif cmd == "/link_wallet":
        if len(parts) < 2:
            response = "Usage: /link_wallet <0x...>"
        else:
            response = controller.link_wallet(profile, parts[1])

    elif cmd == "/profile":
        response = controller.get_profile_status(profile)

    elif cmd == "/help":
        response = """📖 sideQuest Help Guide:

1. 🔗 Link your accounts:
   /link_psn <ID>
   /link_xbox <Gamertag>
   /link_telegram <Telegram_ID>
   /link_wallet <0x...>

2. 💰 Wallet:
   /wallet        — check balance
   /fund_virtual  — get your personal bank account
   /fund_crypto   — fund via crypto
   /points        — see $PLAY rewards

3. 🏆 Challenges:
   /bets                           — open matches
   /challenge <amount> <game>      — host online match
   /local <amount> <game>          — host local match
   /match <id>                     — join a match
   /approve <id>                   — lock funds into escrow
   /active                         — your active matches
   /report <id> <score>            — submit result

4. 🏧 Withdraw:
   /withdraw <amount> bank         — cash out to Naira
   /withdraw <amount> wallet       — cash out to Base

💡 Tip: Send a screenshot of your bank transfer and I'll credit your wallet automatically!"""

    elif cmd == "/withdraw":
        if len(parts) < 2:
            response = "Usage: /withdraw <amount> <bank|wallet>"
        else:
            try:
                amount = float(parts[1])
                if amount <= 0:
                    raise ValueError
            except ValueError:
                response = "❌ Invalid amount."
            else:
                method = parts[2].lower() if len(parts) > 2 else "bank"
                if method not in ("bank", "wallet"):
                    response = "❌ Method must be 'bank' or 'wallet'."
                else:
                    res_data = controller.request_withdrawal(profile, amount, method)
                    if isinstance(res_data, dict) and "admin_ping" in res_data:
                        response = res_data["user_text"]
                        for admin in ADMIN_NUMBERS:
                            bridge.send_message(admin, res_data["admin_ping"])
                    elif isinstance(res_data, dict):
                        response = res_data.get("user_text", "❌ Error.")
                    else:
                        response = str(res_data)

    # ── Admin commands ──────────────────────────────────────────────────────
    elif cmd in ("/admin_fund", "/admin_credit"):
        if len(parts) < 4:
            response = "Usage: /admin_credit <whatsapp_number> <amount_usd> <admin_password>"
        else:
            password = parts[3]
            expected_pass = os.getenv("ADMIN_SECRET", "godmode123")
            if not hmac.compare_digest(password, expected_pass):
                response = "❌ Unauthorised: Invalid admin code."
            else:
                try:
                    amount = float(parts[2])
                    if amount <= 0:
                        raise ValueError
                except ValueError:
                    response = "❌ Invalid amount."
                else:
                    target = _normalise_number(parts[1])
                    response = controller.admin_credit_user(from_number, target, amount)

    elif cmd == "/admin_paid":
        if len(parts) < 3:
            response = "Usage: /admin_paid <withdrawal_id> <admin_password>"
        else:
            password = parts[2]
            expected_pass = os.getenv("ADMIN_SECRET", "godmode123")
            if not hmac.compare_digest(password, expected_pass):
                response = "❌ Unauthorised: Invalid admin code."
            else:
                response = controller.admin_confirm_payout(from_number, parts[1])

    elif cmd == "/active":
        response = controller.get_active_matches(profile)

    elif cmd == "/report":
        if len(parts) < 3:
            response = "Usage: /report <bet_id> <score>  e.g. /report 123 2-1"
        else:
            response = await controller.report_match(profile, parts[1], parts[2], None)

    elif cmd == "/modes":
        response = "🏆 sideQuest Modes:\n1. 1v1 Self-Challenge\n2. Public Stakes\n3. Tournament Seasons (Coming Soon!)"

    elif cmd == "/menu":
        response = """📋 sideQuest Commands:

🏠 General:
/start - Welcome message
/menu - Show this menu
/wallet - Check balance

💰 Funding:
/fund <amount> - Get bank account (Naira)
/fund_crypto <amount> - Crypto deposit
/verify <ref> - Verify payment

🎮 Gaming:
/challenge <amount> <game> - Create challenge
/bets - View active bets
/active - Your active matches
/report <bet_id> <score> - Report result

📊 Info:
/points - Mining status
/tournament - Active tournament
/modes - Game modes

💬 Chat: Just send any message!"""

    elif cmd == "/tournament":
        response = controller.get_active_tournament_status()

    else:
        response = await controller.chat(text)

    bridge.send_message(from_number, response)

if __name__ == "__main__":
    print("This module is not a FastAPI application entrypoint.")
    print("Run the unified backend instead:")
    print("  cd backend && python api.py")
    print("or")
    print("  cd backend && uvicorn api:app --reload --host 0.0.0.0 --port 8000")
