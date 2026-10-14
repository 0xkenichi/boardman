"""
Agent wallets + identity contract addresses.

Each agent gets:
  - wallet_address  — EOA that holds USDC / signs locks. Its key is RANDOM and
                      sealed in the keystore (see keystore.py); it is never
                      derived from a seed, label or agent_id.
  - identity_contract — CREATE2-style identity address (agent "contract")

Without BOARDMAN_KEYSTORE_SECRET, off-chain demos still register agents, but
at an *unprovisioned* address that nobody holds a key for. Live on-chain mode
(BOARDMAN_AGENTIC_ONCHAIN=1) refuses to register without the keystore.

When CIRCLE_* is configured, ensure_circle_wallet() can bind a Circle wallet
to the agent owner profile; demo mode stays fully offline.
"""
from __future__ import annotations

import hashlib
import logging
import os
from typing import Any, Optional

from eth_account import Account

logger = logging.getLogger(__name__)

FACTORY = bytes.fromhex("4b6f6172646d616e4167656e74466163746f7279")  # "BoardmanAgentFactory" padded-ish
INIT_CODE_HASH = hashlib.sha256(b"BoardmanAgentIdentityV1").digest()


def _keccak(data: bytes) -> bytes:
    try:
        from eth_hash.auto import keccak

        return keccak(data)
    except Exception:
        # Fallback: not true keccak, but stable 32-byte id for offline demos
        return hashlib.sha3_256(data).digest()


def unprovisioned_address(agent_id: str) -> str:
    """A hash-derived placeholder address. No private key exists for it."""
    from eth_utils import to_checksum_address

    raw = _keccak(f"boardman.agent.unprovisioned.v1:{agent_id}".encode("utf-8"))[-20:]
    return to_checksum_address("0x" + raw.hex())


def _onchain_required() -> bool:
    return os.getenv("BOARDMAN_AGENTIC_ONCHAIN", "").strip().lower() in {"1", "true", "yes"}


def private_key_to_address(private_key: str) -> str:
    acct = Account.from_key(private_key)
    return acct.address


def identity_contract_address(agent_id: str) -> str:
    """CREATE2-style agent identity contract address (deterministic, demo)."""
    salt = _keccak(f"boardman.agent.identity.v1:{agent_id}".encode("utf-8"))
    # create2: keccak256(0xff ++ factory ++ salt ++ init_code_hash)[12:]
    raw = b"\xff" + FACTORY[:20].ljust(20, b"\x00") + salt + INIT_CODE_HASH
    return "0x" + _keccak(raw)[-20:].hex()


def provision_agent_crypto(agent_id: str, *, role: str = "contestant") -> dict[str, Any]:
    """Bind a wallet + identity contract for an agent.

    Contestants get a random keystore key (reused if one already exists). The
    House never gets a spend key. Private keys are never returned.
    """
    from gaming.src.stack.agentic.keystore import get_keystore, keystore_unlocked

    identity = identity_contract_address(agent_id)
    if role == "house":
        wallet, custody = unprovisioned_address(agent_id), "none"
    else:
        ks = get_keystore()
        wallet = ks.address(agent_id)
        custody = "keystore"
        if not wallet:
            if keystore_unlocked() or _onchain_required():
                wallet = ks.create(agent_id)  # raises KeystoreLocked if no secret
            else:
                logger.warning(
                    "[agentic.wallets] keystore locked; %s registered at an "
                    "unprovisioned address (no spend key)", agent_id,
                )
                wallet, custody = unprovisioned_address(agent_id), "unprovisioned"
    return {
        "agent_id": agent_id,
        "wallet_address": wallet,
        "identity_contract": identity,
        "key_custody": custody,
        "chain_id": os.getenv("CLAW_DEFAULT_CHAIN", "arc"),
    }


async def try_circle_bind(profile_id: str, chain_id: Optional[str] = None) -> Optional[dict[str, Any]]:
    """Optional live Circle wallet for a human owner profile (not required for demo)."""
    if not (os.getenv("CIRCLE_API_KEY") and os.getenv("CIRCLE_ENTITY_SECRET")):
        return None
    try:
        from gaming.src.backend.services.clawstation_circle import ensure_user_wallet

        return await ensure_user_wallet(profile_id, chain_id=chain_id)
    except Exception:
        return None
