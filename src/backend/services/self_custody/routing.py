"""Which path a chat action takes: passkey link, setup link, or custodial.

With ``SELF_CUSTODY_WALLETS_ENABLED`` off this always answers ``custodial``
without touching any table, so the existing flows are untouched.
"""
from __future__ import annotations

import logging
from typing import Optional

from gaming.src.backend.services.self_custody import config

logger = logging.getLogger(__name__)

PASSKEY, SETUP, CUSTODIAL = "passkey", "setup", "custodial"


def account(profile_id: Optional[str]) -> Optional[str]:
    if not config.enabled() or not profile_id:
        return None
    try:
        from gaming.src.backend.services.self_custody import wallets

        return wallets.address(str(profile_id))
    except Exception:
        logger.warning("[self_custody] wallet lookup failed", exc_info=True)
        return None


def lock_route(profile_id: str, challenge: dict) -> str:
    """Sync (reads the store): call off the event loop."""
    if not config.enabled():
        return CUSTODIAL
    acct = account(profile_id)
    if not acct:
        return SETUP if config.required() else CUSTODIAL
    if str(profile_id) == str(challenge.get("creator_id")):
        return PASSKEY
    from gaming.src.backend.services.self_custody import intents

    try:
        return PASSKEY if intents.join_allowed(str(challenge["id"]), acct) else CUSTODIAL
    except Exception:
        logger.warning("[self_custody] join routing failed; custodial", exc_info=True)
        return CUSTODIAL


def withdraw_route(profile_id: str) -> str:
    if not config.enabled():
        return CUSTODIAL
    if account(profile_id):
        return PASSKEY
    return SETUP if config.required() else CUSTODIAL
