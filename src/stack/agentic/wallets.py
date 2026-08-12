"""
Deterministic agent wallets + identity contract addresses.

Each agent gets:
  - wallet_address  — EOA that would hold USDC / sign locks
  - private_key     — demo only (never use mainnet keys from this file)
  - identity_contract — CREATE2-style identity address (agent "contract")

When CIRCLE_* is configured, ensure_circle_wallet() can bind a Circle wallet
to the agent owner profile; demo mode stays fully offline.
"""
from __future__ import annotations

import hashlib
import os
from typing import Any, Optional

from eth_account import Account


FACTORY = bytes.fromhex("4b6f6172646d616e4167656e74466163746f7279")  # "BoardmanAgentFactory" padded-ish
INIT_CODE_HASH = hashlib.sha256(b"BoardmanAgentIdentityV1").digest()


def _keccak(data: bytes) -> bytes:
    try:
        from eth_hash.auto import keccak

        return keccak(data)
    except Exception:
        # Fallback: not true keccak, but stable 32-byte id for offline demos
        return hashlib.sha3_256(data).digest()


def seed_to_private_key(seed: str) -> str:
    """Derive a deterministic 32-byte private key hex from a seed string."""
    digest = _keccak(f"boardman.agent.wallet.v1:{seed}".encode("utf-8"))
    # eth private keys must be in valid secp256k1 range; rehash if needed
    n = int.from_bytes(digest, "big")
    # secp256k1 order
    order = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141
    if n == 0 or n >= order:
        digest = _keccak(digest + b"\x01")
    return "0x" + digest.hex()


def private_key_to_address(private_key: str) -> str:
    acct = Account.from_key(private_key)
    return acct.address


def identity_contract_address(agent_id: str) -> str:
    """CREATE2-style agent identity contract address (deterministic, demo)."""
    salt = _keccak(f"boardman.agent.identity.v1:{agent_id}".encode("utf-8"))
    # create2: keccak256(0xff ++ factory ++ salt ++ init_code_hash)[12:]
    raw = b"\xff" + FACTORY[:20].ljust(20, b"\x00") + salt + INIT_CODE_HASH
    return "0x" + _keccak(raw)[-20:].hex()


def provision_agent_crypto(agent_id: str, *, seed: Optional[str] = None) -> dict[str, Any]:
    """Create wallet + identity contract for an agent (deterministic by seed)."""
    s = seed or agent_id
    pk = seed_to_private_key(s)
    wallet = private_key_to_address(pk)
    identity = identity_contract_address(agent_id)
    return {
        "agent_id": agent_id,
        "wallet_address": wallet,
        "identity_contract": identity,
        "private_key": pk if os.getenv("BOARDMAN_AGENTIC_EXPORT_KEYS", "").lower() in {"1", "true", "yes"} else None,
        "private_key_present": True,
        "chain_id": os.getenv("CLAW_DEFAULT_CHAIN", "arc"),
        "mode": "deterministic_demo",
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
