"""
whatsapp_blockchain_commands.py
───────────────────────────────────────────────────────────────────────────────
WhatsApp command handlers for crypto wallet operations.
Each user gets a deterministic custodial wallet derived from their WhatsApp number.

Commands:
  /deposit    → Get your personal deposit address
  /balance    → Show USDC balance + $PLAY points
  /withdraw   → Request USDC withdrawal (admin review)
"""

import re
import logging

logger = logging.getLogger(__name__)


async def handle_deposit(user: dict, send_fn) -> str:
    """
    /deposit
    Returns the user's personal custodial deposit address.
    The wallet is auto-generated from their WhatsApp number.
    """
    from custodial_wallet import get_wallet_for_user
    from backend.blockchain_layer import get_blockchain_layer
    
    bl = get_blockchain_layer()
    phone = user.get("whatsapp_number") or user.get("whatsapp_id")
    
    wallet = get_wallet_for_user(phone, user)
    address = wallet["address"]

    return (
        f"💰 *Your Deposit Address*\n\n"
        f"`{address}`\n\n"
        f"Network: *{bl.network['name']}* (Chain ID: {bl.network['chain_id']})\n"
        f"Token: *USDC only*\n\n"
        f"Send USDC to this address — your balance will be credited automatically.\n\n"
        f"⚠️ *Only send USDC on {bl.network['name']}. Other tokens will be lost.*"
    )


async def handle_balance(user: dict, send_fn) -> str:
    """
    /balance or /wallet
    Shows user's USDC balance and $PLAY points.
    """
    from backend.db_layer_blockchain import get_wallet_balance
    
    balance = await get_wallet_balance(user["id"])
    play_points = user.get("play_points", 0)
    
    from custodial_wallet import get_wallet_for_user
    phone = user.get("whatsapp_number") or user.get("whatsapp_id")
    wallet = get_wallet_for_user(phone, user)
    
    return (
        f"👛 *Your Wallet*\n\n"
        f"💵 Balance: *${balance:.2f} USDC*\n"
        f"🎮 $PLAY Points: *{play_points:,}*\n"
        f"🔗 Address: `{wallet['address']}`\n\n"
        f"Type */deposit* to get your deposit address.\n"
        f"Type */challenge <amount> <game>* to play."
    )


async def handle_withdraw(user: dict, amount_str: str, send_fn) -> str:
    """
    /withdraw <amount>
    Initiates a USDC withdrawal request (manual admin review for now).
    """
    try:
        amount = float(amount_str)
    except ValueError:
        return "❌ Invalid amount. Use `/withdraw 10` to withdraw $10 USDC."

    if amount < 5:
        return "❌ Minimum withdrawal is $5 USDC."

    from backend.db_layer_blockchain import get_wallet_balance
    balance = await get_wallet_balance(user["id"])

    if amount > balance:
        return (
            f"❌ Insufficient balance.\n\n"
            f"Your balance: ${balance:.2f}\n"
            f"Requested: ${amount:.2f}"
        )

    from custodial_wallet import get_wallet_for_user
    phone = user.get("whatsapp_number") or user.get("whatsapp_id")
    wallet = get_wallet_for_user(phone, user)
    to_address = wallet["address"]

    from backend.db_layer_blockchain import get_supabase
    sb = get_supabase()
    sb.table("withdrawal_requests").insert({
        "user_id":      user["id"],
        "amount_usdc":  amount,
        "to_address":   to_address,
        "status":       "pending",
    }).execute()

    from backend.blockchain_layer import get_blockchain_layer
    bl = get_blockchain_layer()

    return (
        f"✅ *Withdrawal Requested*\n\n"
        f"Amount: *${amount:.2f} USDC*\n"
        f"To: `{to_address}`\n"
        f"Network: {bl.network['name']}\n\n"
        f"⏱️ Processing within 1–24 hours.\n"
        f"You'll be notified when sent."
    )


async def handle_my_wallet(user: dict, send_fn) -> str:
    """
    /my_wallet
    Shows user's complete wallet info.
    """
    from backend.db_layer_blockchain import get_wallet_balance
    from custodial_wallet import get_wallet_for_user
    
    balance = await get_wallet_balance(user["id"])
    play_points = user.get("play_points", 0)
    
    phone = user.get("whatsapp_number") or user.get("whatsapp_id")
    wallet = get_wallet_for_user(phone, user)
    address = wallet["address"]
    
    from backend.blockchain_layer import get_blockchain_layer
    bl = get_blockchain_layer()
    
    return (
        f"🔐 *Your Wallet*\n\n"
        f"Address:\n`{address}`\n\n"
        f"Balance: *${balance:.2f} USDC*\n"
        f"$PLAY Points: *{play_points:,}*\n\n"
        f"Network: {bl.network['name']}\n"
        f"Contract: `{bl.network['usdc_address']}`\n\n"
        f"Commands:\n"
        f"• /deposit - Get deposit address\n"
        f"• /withdraw <amount> - Request payout"
    )


# ─── Command Router Addition ──────────────────────────────────────────────────
# Add these cases to your existing handle_whatsapp_command() function:

"""
elif command in ("/deposit", "/fund_crypto", "/add_funds"):
    response = await handle_deposit(user, send_message)

elif command in ("/balance", "/wallet", "/bal"):
    response = await handle_balance(user, send_message)

elif command == "/my_wallet":
    response = await handle_my_wallet(user, send_message)

elif command == "/withdraw":
    if not args:
        response = "Usage: /withdraw <amount>  e.g. /withdraw 25"
    else:
        response = await handle_withdraw(user, args[0], send_message)
"""
