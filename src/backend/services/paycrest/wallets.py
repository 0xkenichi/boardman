"""Which wallet holds what on the naira rail.

* Play wallet (Arc, settlement chain): the player's existing Circle wallet,
  via ``clawstation_circle.ensure_user_wallet``. Stakes only ever use this.
* Base "in" wallet: where Paycrest delivers on-ramp USDC. Swept to Arc.
* Base "out" wallet: where cash-out USDC lands from Arc before it is sent to
  Paycrest; Paycrest refunds come back here (``refundAddress``) and are
  bridged home.

Separate in/out wallets mean a sweep can never grab cash-out money in
flight. Base wallets are Circle developer-controlled, created once per
player (idempotency key per player and purpose) as SCA when Gas Station pays
gas, EOA when the Boardman gas tank does. They are recorded in
``payment_wallets`` and never replace the profile's play address.
"""
from __future__ import annotations

import asyncio
from typing import Any

from gaming.src.backend.services.bridge.chain_ops import get_chain_ops
from gaming.src.backend.services.paycrest import config, store

PURPOSES = ("in", "out")


def _key(purpose: str) -> str:
    if purpose not in PURPOSES:
        raise ValueError(purpose)
    return f"{config.delivery_chain()}/{purpose}"


def base_wallet(profile_id: str, purpose: str) -> dict[str, Any]:
    """Get or create the player's Base wallet for ``purpose`` (sync)."""
    key = _key(purpose)
    row = store.get_wallet(profile_id, key)
    if row:
        return row
    acct = config.base_account_type()
    wallet_id, address = get_chain_ops().create_wallet(
        config.delivery_chain(), profile_id, acct, f"paycrest-wallet|{profile_id}|{key}")
    return store.put_wallet(profile_id, key, wallet_id, address, acct)


async def play_wallet(profile_id: str) -> dict[str, Any]:
    """The player's Arc play wallet on the settlement chain: {wallet_id, address}."""
    from gaming.src.backend.services import clawstation_circle as circle

    w = await circle.ensure_user_wallet(profile_id, chain_id=config.settlement_chain())
    return {"wallet_id": w.get("wallet_id"), "address": w.get("address")}


def play_wallet_sync(profile_id: str) -> dict[str, Any]:
    return asyncio.run(play_wallet(profile_id))


def passkey_account(profile_id: str) -> str:
    """The player's self-custody passkey account on Arc, or '' (flag off / none)."""
    try:
        from gaming.src.backend.services.self_custody import routing

        return routing.account(profile_id) or ""
    except Exception:
        return ""


def passkey_deposit_account(profile_id: str) -> str:
    """The passkey account new money may be minted to, or ''. Empty while a
    wallet change is waiting for the chat or cooling down (24 h)."""
    try:
        from gaming.src.backend.services.self_custody import routing

        return routing.deposit_account(profile_id) or ""
    except Exception:
        return ""


async def arc_destination(profile_id: str) -> str:
    """Where naira USDC lands on Arc: the player's own passkey account when
    they have one (CCTP mints straight to it), else their play wallet."""
    return passkey_deposit_account(profile_id) or (await play_wallet(profile_id)).get("address") or ""


def arc_destination_sync(profile_id: str) -> str:
    return passkey_deposit_account(profile_id) or play_wallet_sync(profile_id).get("address") or ""
