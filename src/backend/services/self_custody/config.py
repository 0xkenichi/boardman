"""Flags and chain settings for self-custody wallets, read at call time.

``SELF_CUSTODY_WALLETS_ENABLED``  master switch (default off).
``SELF_CUSTODY_REQUIRED``         players without a passkey wallet are sent to
                                  set one up instead of the custodial lock.
``SELF_CUSTODY_CHAIN``            chain key in config/chains.yaml (default:
                                  the settlement chain, ``arc``).
``SELF_CUSTODY_SPONSOR_GAS``      UserOperations ask Circle Gas Station to pay
                                  gas (``paymaster: true``). Default on.
``SELF_CUSTODY_APPROVE_TTL_SEC``  approve / setup link and setup challenge lifetime (600).
``SELF_CUSTODY_CONFIRM_TTL_SEC``  in-chat "Is this your wallet?" lifetime (1800).
``SELF_CUSTODY_CHANGE_COOLDOWN_SEC`` a changed wallet is unused this long (86400).
``SELF_CUSTODY_REAUTH_SEC``       max age of the web sign-in a change needs (900).
"""
from __future__ import annotations

import os
from typing import Any

_TRUTHY = {"1", "true", "yes", "on"}
_FALSY = {"0", "false", "no", "off"}

# Circle's modular transport path per chain (``${clientUrl}/<path>``).
# arcTestnet is from Circle's quickstart; the mainnet path is not documented
# yet (unverified) and can be overridden with SELF_CUSTODY_MODULAR_PATH.
_MODULAR_PATHS = {"arc": "arcTestnet", "arc_mainnet": "arc"}


def _flag(name: str, default: bool) -> bool:
    raw = (os.getenv(name) or "").strip().lower()
    if raw in _TRUTHY:
        return True
    if raw in _FALSY:
        return False
    return default


def enabled() -> bool:
    return _flag("SELF_CUSTODY_WALLETS_ENABLED", False)


def required() -> bool:
    return enabled() and _flag("SELF_CUSTODY_REQUIRED", False)


def sponsor_gas() -> bool:
    return _flag("SELF_CUSTODY_SPONSOR_GAS", True)


def ttl_ms() -> int:
    try:
        return max(60, int(os.getenv("SELF_CUSTODY_APPROVE_TTL_SEC") or 600)) * 1000
    except ValueError:
        return 600_000


def _secs(name: str, default: int, floor: int) -> int:
    try:
        return max(floor, int(os.getenv(name) or default))
    except ValueError:
        return default


def confirm_ttl_ms() -> int:
    """How long a proven wallet waits for the player's "Yes" in the chat."""
    return _secs("SELF_CUSTODY_CONFIRM_TTL_SEC", 1800, 60) * 1000


def change_cooldown_ms() -> int:
    """A changed wallet receives nothing (top-ups, stakes, payouts) for this long."""
    return _secs("SELF_CUSTODY_CHANGE_COOLDOWN_SEC", 86_400, 3600) * 1000


def reauth_max_age_ms() -> int:
    """A wallet change needs a web sign-in at most this old."""
    return _secs("SELF_CUSTODY_REAUTH_SEC", 900, 60) * 1000


def chain_key() -> str:
    raw = (os.getenv("SELF_CUSTODY_CHAIN") or "").strip()
    if raw:
        return raw
    from gaming.src.backend.services.chains import default_chain_id

    return default_chain_id()


def wallet_key(chain: str | None = None) -> str:
    """The ``payment_wallets.chain`` key a passkey account is stored under."""
    return f"{chain or chain_key()}/passkey"


def chain_settings(chain: str | None = None) -> dict[str, Any]:
    """What the backend and the approve page need to talk to the chain."""
    from gaming.src.backend.services.chains import get_chain

    key = chain or chain_key()
    c = get_chain(key) or {}
    escrow = (os.getenv("SELF_CUSTODY_ESCROW_ADDRESS") or c.get("escrow_address") or "").strip()
    return {
        "chain": key,
        "label": c.get("label") or key,
        "evm_chain_id": int(c.get("chain_id") or 0),
        "rpc_url": (os.getenv("SELF_CUSTODY_RPC_URL") or c.get("rpc_url") or "").strip(),
        "usdc": str(c.get("usdc_address") or ""),
        "escrow": escrow,
        "explorer_tx": c.get("explorer_tx") or "",
        "modular_path": (os.getenv("SELF_CUSTODY_MODULAR_PATH") or _MODULAR_PATHS.get(key) or key),
    }


def escrow_version_override() -> int | None:
    raw = (os.getenv("BOARDMAN_ESCROW_VERSION") or "").strip()
    return int(raw) if raw in {"1", "2"} else None
