"""
Security utilities for transaction password hashing and verification.
"""

import hashlib
import hmac
import secrets
from typing import Dict

__all__ = ["hash_tx_password", "verify_tx_password", "has_tx_password"]


def hash_tx_password(password: str) -> str:
    """
    Hash a transaction password using PBKDF2-HMAC-SHA256.

    Args:
        password: The plain-text password to hash.

    Returns:
        A string in the format: "pbkdf2_sha256$260000$<salt_hex>$<hash_hex>"
    """
    salt = secrets.token_bytes(32)
    iterations = 260000
    hash_bytes = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        iterations,
    )
    return f"pbkdf2_sha256${iterations}${salt.hex()}${hash_bytes.hex()}"


def verify_tx_password(password: str, hashed: str) -> bool:
    """
    Verify a transaction password against a stored hash.

    Args:
        password: The plain-text password to verify.
        hashed: The stored hash string in format "pbkdf2_sha256$260000$<salt_hex>$<hash_hex>".

    Returns:
        True if the password matches, False otherwise.
    """
    try:
        # Parse the hash format: pbkdf2_sha256$iterations$salt_hex$hash_hex
        parts = hashed.split("$")
        if len(parts) != 4 or parts[0] != "pbkdf2_sha256":
            return False

        iterations = int(parts[1])
        salt = bytes.fromhex(parts[2])
        expected_hash = bytes.fromhex(parts[3])

        # Recompute the hash with the same parameters
        computed_hash = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt,
            iterations,
        )

        # Use constant-time comparison to prevent timing attacks
        return hmac.compare_digest(computed_hash, expected_hash)
    except (ValueError, IndexError):
        # Invalid hash format
        return False


def has_tx_password(profile: Dict) -> bool:
    """
    Check if a user profile has a transaction password set.

    Args:
        profile: User profile dictionary.

    Returns:
        True if the profile has a non-empty gaming_tx_password_hash, False otherwise.
    """
    return bool(profile.get("gaming_tx_password_hash"))