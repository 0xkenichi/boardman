"""The player's passkey smart account, per chain.

Stored in the existing per-player wallet table ``payment_wallets`` under the
chain key ``<chain>/passkey``: ``wallet_id`` = ``passkey:<credential id>``,
``account_type`` = ``circle_msca_passkey``. Boardman stores no key material:
the credential id is public, the private key never leaves the player's
authenticator.

A row only gets here through ``setup``: a signed ERC-1271/6492 proof from
the account *and* the player's "Yes" in their chat (``self_custody_wallet_requests``).
A change additionally needs a fresh web sign-in and waits out a cool-down
(``SELF_CUSTODY_CHANGE_COOLDOWN_SEC``): until then the old account stays the
active one and new naira top-ups go to the custodial play wallet instead of
either passkey account. The swap happens on the first read after the
cool-down (``get``), in one transaction, and only if the active address is
still the one the change was made against.
"""
from __future__ import annotations

import logging
import re
from typing import Optional

from gaming.src.backend.services.self_custody import config, store

logger = logging.getLogger(__name__)

ACCOUNT_TYPE = "circle_msca_passkey"
ADDRESS_RE = re.compile(r"^0x[a-fA-F0-9]{40}$")
CRED_RE = re.compile(r"^[A-Za-z0-9_\-+/=]{8,512}$")
CHANGING = ("pending_confirm", "cooling")


class WalletRefused(Exception):
    def __init__(self, kind: str, message: str) -> None:
        super().__init__(message)
        self.kind = kind
        self.message = message


def _store():
    from gaming.src.backend.services.paycrest import store

    return store


def _promote_due(profile_id: str, chain: Optional[str]) -> None:
    key = chain or config.chain_key()
    try:
        due = [r for r in store.requests_for(str(profile_id), ("cooling",), chain=key)
               if int(r["active_at_ms"] or 0) <= store.now_ms()]
    except Exception:
        logger.warning("[self_custody] wallet change lookup failed", exc_info=True)
        return
    for r in due:
        if store.promote_change(r["id"], wallet_key=config.wallet_key(key), wallet_id=f"passkey:{r['credential_id']}",
                                account_type=ACCOUNT_TYPE, now=store.now_ms()):
            logger.info("[self_custody] wallet change %s is now active", r["id"])


def get(profile_id: str, chain: Optional[str] = None) -> Optional[dict]:
    """``{"address", "credential_id", "chain"}`` of the *active* account, or None."""
    if not profile_id:
        return None
    _promote_due(str(profile_id), chain)
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


def pending(profile_id: str, chain: Optional[str] = None) -> Optional[dict]:
    """The newest request waiting for the chat "Yes" or in its cool-down."""
    if not profile_id:
        return None
    _promote_due(str(profile_id), chain)
    rows = store.requests_for(str(profile_id), CHANGING, chain=chain or config.chain_key())
    now = store.now_ms()
    rows = [r for r in rows if r["status"] == "cooling" or int(r["expires_at_ms"]) > now]
    return rows[0] if rows else None


def deposit_address(profile_id: str, chain: Optional[str] = None) -> Optional[str]:
    """Where new money for this player may land on their passkey account.
    None while a wallet change is waiting or cooling down: top-ups then go to
    the custodial play wallet, never to an address that is not settled yet."""
    acct = address(profile_id, chain)
    if not acct:
        return None
    p = pending(profile_id, chain)
    if p is not None and p["kind"] == "change":
        return None
    return acct


def owner_of(addr: str, chain: Optional[str] = None) -> Optional[str]:
    return _store().wallet_owner(config.wallet_key(chain), addr)


def check_address(addr: str) -> str:
    from eth_utils import to_checksum_address

    if not ADDRESS_RE.match(addr or ""):
        raise WalletRefused("bad_address", "That is not a wallet address.")
    return to_checksum_address(addr)


def link_unverified(profile_id: str, addr: str, credential_id: str, chain: Optional[str] = None) -> tuple[dict, bool]:
    """Insert a passkey account WITHOUT the setup proof or the chat "Yes".

    Not used by any player path (those go through ``setup``). For support
    tooling after an out-of-band check, and for tests. Idempotent for the
    same address; refuses a different one, or one linked to another profile.
    """
    addr = check_address(addr)
    if not CRED_RE.match(credential_id or ""):
        raise WalletRefused("bad_request", "Passkey details missing.")
    key = config.wallet_key(chain)
    owner = owner_of(addr, chain)
    if owner and str(owner) != str(profile_id):
        raise WalletRefused("taken", "This wallet is already linked to another Boardman account.")
    cur = get(profile_id, chain)
    if cur:
        if cur["address"].lower() == addr.lower():
            return cur, False
        raise WalletRefused("exists", "You already have a passkey wallet linked.")
    _store().put_wallet(str(profile_id), key, f"passkey:{credential_id}", addr, ACCOUNT_TYPE)
    got = get(profile_id, chain)
    if not got or got["address"].lower() != addr.lower():  # lost a race to another registration
        raise WalletRefused("exists", "You already have a passkey wallet linked.")
    return got, True
