"""
Kobox partner rail — preferred self-serve on/off ramp for Nigerian users.

Product posture:
  - Recommend Kobox for Naira ↔ USDC, bank withdrawals, and day-to-day banking.
  - Rematch bank top-up remains a fallback when users prefer not to use Kobox.
  - Crypto withdraw to any 0x (including a Kobox deposit address) stays native.

Referral / download URLs come from env so ops can rotate links without code changes.
"""
from __future__ import annotations

import os
from typing import Optional


def kobox_name() -> str:
    return (os.getenv("KOBOX_PARTNER_NAME") or "Kobox").strip() or "Kobox"


def kobox_referral_url() -> Optional[str]:
    """Signup / referral deep link (preferred)."""
    raw = (
        os.getenv("KOBOX_REFERRAL_URL")
        or os.getenv("KOBOX_SIGNUP_URL")
        or os.getenv("KOBOX_APP_URL")
        or ""
    ).strip()
    return raw or None


def kobox_help_url() -> Optional[str]:
    raw = (os.getenv("KOBOX_HELP_URL") or "").strip()
    return raw or None


def kobox_enabled() -> bool:
    """Show partner CTAs when we have a link or KOBOX_ENABLED=1."""
    v = (os.getenv("KOBOX_ENABLED") or "").strip().lower()
    if v in ("0", "false", "no", "off"):
        return False
    if v in ("1", "true", "yes", "on"):
        return True
    # Default on if a referral URL exists; otherwise still show text (ops can set URL later)
    return True


def onramp_copy_html() -> str:
    name = kobox_name()
    return (
        f"⭐ <b>Recommended: {name}</b>\n"
        f"Download {name}, fund with Naira, swap to USDC, then send USDC to your "
        f"<b>Rematch play address</b>. You control the rate and can bank there anytime.\n\n"
        f"Or skip the app — pay our bank and <b>we credit you</b> (fee applies)."
    )


def offramp_copy_html() -> str:
    name = kobox_name()
    return (
        f"⭐ <b>Recommended: cash out via {name}</b>\n"
        f"Withdraw USDC from Rematch to your <b>{name} deposit address</b>, "
        f"then swap to Naira and withdraw to your bank inside {name}.\n\n"
        f"Already have another exchange/wallet? Send to that 0x instead — same flow."
    )


def get_money_intro_html(rate_ngn: float | int) -> str:
    name = kobox_name()
    return (
        "💧 <b>Get money</b>\n\n"
        f"{onramp_copy_html()}\n\n"
        f"<b>Options</b>\n"
        f"• <b>{name}</b> — self-serve Naira ↔ USDC (best for most people)\n"
        f"• <b>Pay our bank (Naira / USD)</b> — we convert & credit (₦{rate_ngn:,.0f}/$1 + fee)\n"
        f"• <b>Crypto</b> — send USDC straight to your play address\n"
    )


def withdraw_intro_extra_html() -> str:
    return f"\n{offramp_copy_html()}\n"
