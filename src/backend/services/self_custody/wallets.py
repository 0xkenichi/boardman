"""The player's passkey smart account, per chain.

Stored in the existing per-player wallet table ``payment_wallets`` under the
chain key ``<chain>/passkey``: ``wallet_id`` = ``passkey:<credential id>``,
``account_type`` = ``circle_msca_passkey``. Inserted once; an existing
address always wins, so a stolen setup link cannot silently redirect a
player's deposits (changing it is a support action with a chat notice).
Boardman stores no key material: the credential id is public, the private
key never leaves the player's authenticator.
"""
from __future__ import annotations

import re
from typing import Optional

from gaming.src.backend.services.self_custody import config

ACCOUNT_TYPE = "circle_msca_passkey"
ADDRESS_RE = re.compile(r"^0x[a-fA-F0-9]{40}$")
CRED_RE = re.compile(r"^[A-Za-z0-9_\-+/=]{8,512}$")


class WalletRefused(Exception):
    def __init__(self, kind: str, message: str) -> None:
        super().__init__(message)
        self.kind = kind
        self.message = message


def _store():
    from gaming.src.backend.services.paycrest import store

    return store


def get(profile_id: str, chain: Optional[str] = None) -> Optional[dict]:
    """``{"address", "credential_id", "chain"}`` or None."""
    if not profile_id:
        return None
    row = _store().get_wallet(str(profile_id), config.wallet_key(chain))
    if not row:
        return None
    cred = str(row.get("wallet_id") or "")
    return {
        "address": row["address"],
        "credential_id": cred.removeprefix("passkey:"),
        "chain": chain or config.chain_key(),
        "created_at_ms": row.get("created_at_ms"),
    }


def address(profile_id: str, chain: Optional[str] = None) -> Optional[str]:
    w = get(profile_id, chain)
    return w["address"] if w else None


def owner_of(addr: str, chain: Optional[str] = None) -> Optional[str]:
    return _store().wallet_owner(config.wallet_key(chain), addr)


def register(profile_id: str, addr: str, credential_id: str, chain: Optional[str] = None) -> tuple[dict, bool]:
    """Link a passkey account to a profile. Returns (wallet, created).

    Idempotent for the same address; refuses a different one, or an address
    already linked to another profile.
    """
    from eth_utils import to_checksum_address

    if not ADDRESS_RE.match(addr or ""):
        raise WalletRefused("bad_address", "That is not a wallet address.")
    if not CRED_RE.match(credential_id or ""):
        raise WalletRefused("bad_request", "Passkey details missing.")
    addr = to_checksum_address(addr)
    key = config.wallet_key(chain)
    owner = owner_of(addr, chain)
    if owner and str(owner) != str(profile_id):
        raise WalletRefused("taken", "This wallet is already linked to another Boardman account.")
    cur = get(profile_id, chain)
    if cur:
        if cur["address"].lower() == addr.lower():
            return cur, False
        raise WalletRefused("exists", "You already have a passkey wallet linked. Contact support to change it.")
    _store().put_wallet(str(profile_id), key, f"passkey:{credential_id}", addr, ACCOUNT_TYPE)
    got = get(profile_id, chain)
    if not got or got["address"].lower() != addr.lower():  # lost a race to another registration
        raise WalletRefused("exists", "You already have a passkey wallet linked. Contact support to change it.")
    return got, True
