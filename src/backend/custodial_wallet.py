"""
custodial_wallet.py
────────────────────────────────────────────────────────────────────────────
Deterministic custodial wallets for WhatsApp/Telegram users.
Each user gets a unique wallet address derived from their identifier.
The admin controls the private keys but can sign transactions on behalf of users.
"""

import os
import hashlib
import logging
from typing import Optional
from eth_account import Account

logger = logging.getLogger(__name__)

MASTER_SEED = os.getenv("CUSTODIAL_MASTER_SEED", "sidequest_custodial_seed_2024")

def _derive_wallet(identifier: str) -> tuple[str, str]:
    """Derive wallet address + private key from identifier (phone or tg_xxx)."""
    seed_input = f"{MASTER_SEED}:{identifier}"
    key = hashlib.pbkdf2_hmac(
        'sha256',
        seed_input.encode('utf-8'),
        b'sidequest_salt_2024',
        iterations=100000,
        dklen=32
    )
    account = Account.from_key(key)
    return account.address, account.key.hex()

def generate_custodial_wallet(identifier: str) -> dict:
    """Generate a custodial wallet for a user."""
    address, private_key = _derive_wallet(identifier)
    return {
        "address": address,
        "private_key": private_key,
        "identifier": identifier,
    }

def get_wallet_for_user(identifier: str, db_record: Optional[dict] = None) -> Optional[dict]:
    """Get or create a custodial wallet for a user."""
    if db_record and db_record.get("linked_wallet"):
        return {"address": db_record["linked_wallet"], "identifier": identifier}
    return generate_custodial_wallet(identifier)


def sign_transaction(private_key_hex: str, tx_params: dict) -> str:
    """
    Sign an Ethereum transaction with the given private key.
    """
    account = Account.from_key(private_key_hex)
    
    signed_tx = account.sign_transaction(tx_params)
    return signed_tx.rawTransaction.hex()


def format_tx_for_usdc_transfer(
    to_address: str,
    amount_usdc: float,
    usdc_contract: str,
    chain_id: int,
    nonce: int,
    gas_price: int
) -> dict:
    """
    Format a USDC transfer transaction.
    """
    # USDC has 6 decimals
    amount_wei = int(amount_usdc * 1_000_000)
    
    # ERC-20 transfer function selector: 0xa9059cbb
    # Transfer(to, amount)
    data = "0xa9059cbb" + to_address[2:].zfill(64) + hex(amount_wei)[2:].zfill(64)
    
    return {
        "to": usdc_contract,
        "value": 0,
        "gas": 85000,  # Standard ERC-20 transfer gas
        "gasPrice": gas_price,
        "nonce": nonce,
        "chainId": chain_id,
        "data": data,
    }
