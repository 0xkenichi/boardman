"""Withdraw request: validate in the chat, confirm on the web.

The chat collects a destination and an amount, runs the cheap checks early
(pause, limits, daily cap, link hold, geo) so the player is not sent to a page
that will refuse, and issues a one-time link (``withdraw_links``). The payout
and every authoritative check happen when the link is confirmed.
"""
from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Optional

from gaming.src.channels.core import withdraw_links
from gaming.src.channels.core.principal import Principal

ADDRESS_RE = re.compile(r"^0x[a-fA-F0-9]{40}$")
TAG_RE = re.compile(r"^@[A-Za-z0-9_]{2,32}$")


class WithdrawRefused(Exception):
    pass


@dataclass
class Destination:
    address: str
    recipient_id: Optional[str] = None
    tag: Optional[str] = None

    def label(self) -> str:
        return f"@{self.tag}" if self.tag else self.address


def parse_amount(raw: str) -> Optional[Decimal]:
    s = (raw or "").strip().lstrip("$").replace(",", "")
    s = s.lower().removesuffix("usdc").strip()
    try:
        amt = Decimal(s)
    except (InvalidOperation, ValueError):
        return None
    if not amt.is_finite() or amt <= 0:
        return None
    return amt.quantize(Decimal("0.01"))


def _find_tag_sync(tag: str) -> Optional[dict]:
    from gaming.src.bot.utils.db import _get_profile_by_tag_sync

    return _get_profile_by_tag_sync(tag)


async def resolve_destination(principal: Principal, raw: str) -> Destination:
    text = (raw or "").strip()
    if ADDRESS_RE.match(text):
        return Destination(text)
    if TAG_RE.match(text):
        tag = text.lstrip("@")
        prof = await asyncio.to_thread(_find_tag_sync, tag)
        if not prof:
            raise WithdrawRefused(f"Player @{tag} not found.")
        addr = prof.get("gaming_deposit_address") or prof.get("wallet_address") or ""
        if not ADDRESS_RE.match(addr):
            raise WithdrawRefused(f"@{tag} does not have a wallet yet.")
        if str(prof.get("id")) == str(principal.profile_id):
            raise WithdrawRefused("You cannot withdraw to yourself.")
        return Destination(addr, str(prof["id"]), tag)
    raise WithdrawRefused("Send a wallet address (0x… 42 characters) or a player tag like @ada.")


def precheck(principal: Principal, amount: Decimal) -> Optional[str]:
    """Plain-text reason to refuse now, or None. Does not count against limits."""
    from gaming.src.backend.services.safety import (
        check_daily_withdraw,
        is_paused,
        validate_withdraw,
    )
    from gaming.src.backend.services.withdrawals import _plain

    if is_paused():
        return "Withdrawals are paused for now while we keep funds safe. Try again later."
    if principal.withdraw_hold_active():
        until = principal.withdraw_hold_until.strftime("%d %b %H:%M UTC")
        return (f"This chat was linked recently, so withdrawals from it open on {until}. "
                "You can still withdraw from the app you signed up with.")
    for err in (validate_withdraw(amount), check_daily_withdraw(principal.profile_id, amount)):
        if err:
            return _plain(err)
    return None


def request_link(principal: Principal, dest: Destination, amount: Decimal) -> withdraw_links.IssuedLink:
    from gaming.src.backend.services.self_custody import routing

    route = routing.withdraw_route(principal.profile_id)
    if route != routing.CUSTODIAL:
        return _self_custody_link(principal, dest, amount, route)
    reason = precheck(principal, amount)
    if reason:
        raise WithdrawRefused(reason)
    try:
        return withdraw_links.issue(
            principal.profile_id,
            channel=principal.channel,
            external_id=principal.external_id,
            amount=amount,
            address=dest.address,
            recipient_id=dest.recipient_id,
            tag=dest.tag,
        )
    except withdraw_links.LinkRefused as exc:
        raise WithdrawRefused(exc.message) from exc


def _self_custody_link(principal: Principal, dest: Destination, amount: Decimal,
                       route: str) -> withdraw_links.IssuedLink:
    """Passkey players send from their own wallet: an approve link, no PIN.
    Boardman's pause and caps do not apply to money it does not hold."""
    from gaming.src.backend.services.self_custody import intents, setup
    from gaming.src.backend.services.self_custody.routing import SETUP

    try:
        if route == SETUP:
            url, expires = setup.issue_link(principal.profile_id, channel=principal.channel,
                                            external_id=principal.external_id)
            return withdraw_links.IssuedLink(url.rsplit("t=", 1)[-1], url, expires, kind="setup")
        p = intents.prepare_withdraw(principal.profile_id, dest.address, amount, channel=principal.channel,
                                     external_id=principal.external_id)
    except intents.IntentRefused as exc:
        raise WithdrawRefused(exc.message) from exc
    return withdraw_links.IssuedLink(p.token, p.url, p.expires_at_ms, kind="passkey")


def link_label(kind: str = "pin") -> str:
    return {"passkey": "Approve with passkey", "setup": "Set up wallet"}.get(kind, "Confirm withdrawal")


def link_message(dest: Destination, amount: Decimal, kind: str = "pin") -> str:
    minutes = withdraw_links.ttl_ms() // 60000
    if kind == "passkey":
        return (
            f"*Approve your withdrawal*\n"
            f"${amount:,.2f} USDC from your wallet to {dest.label()}\n\n"
            f"Open the secure page and approve with your passkey. You hold the keys; Boardman can't move "
            f"your money. The link works once and expires in {minutes} minutes. "
            f"If the page can't use your passkey, choose *Open in browser*."
        )
    if kind == "setup":
        return ("*Set up your wallet first*\nWithdrawals now come from a wallet only you control, approved "
                "with a passkey. It takes a minute; then start the withdrawal again.")
    return (
        f"*Confirm your withdrawal*\n"
        f"${amount:,.2f} USDC to {dest.label()}\n\n"
        f"Open the secure page and enter your withdrawal PIN there. "
        f"The link works once and expires in {minutes} minutes. "
        f"Never type your PIN in a chat and never share this link."
    )
