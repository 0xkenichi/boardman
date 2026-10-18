"""Paycrest naira rail settings: flags from the environment, the rest from
``config/funding_rails.yaml`` (``rails.paycrest_ngn``). Read at call time.

Two flags, both default OFF, both required before a player sees anything:

``PAYCREST_ENABLED``
    The naira rail exists (menus, webhook, worker). Also needs
    ``PAYCREST_API_KEY``.
``REAL_MONEY_ENABLED``
    Boardman may move real money on mainnet. Paycrest is mainnet-only, so
    the rail is invisible without it.

Secrets (set blind by ``scripts/set_paycrest_env.sh``, never logged):
``PAYCREST_API_KEY`` (``API-Key`` header) and ``PAYCREST_API_SECRET`` (HMAC
key for the ``X-Paycrest-Signature`` webhook header; Paycrest calls it the
API Secret).
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

_TRUTHY = {"1", "true", "yes", "on"}

DEFAULT_API_BASE = "https://api.paycrest.io/v2"


def _flag(name: str) -> bool:
    return (os.getenv(name) or "").strip().lower() in _TRUTHY


def api_key() -> str:
    return (os.getenv("PAYCREST_API_KEY") or "").strip()


def api_secret() -> str:
    return (os.getenv("PAYCREST_API_SECRET") or "").strip()


def real_money_enabled() -> bool:
    return _flag("REAL_MONEY_ENABLED")


def paycrest_flag() -> bool:
    return _flag("PAYCREST_ENABLED")


def enabled() -> bool:
    """The rail is live: both flags on and an API key present."""
    return paycrest_flag() and real_money_enabled() and bool(api_key())


def rail() -> dict[str, Any]:
    from gaming.src.backend.services.funding_rails import get_rail

    return dict(get_rail("paycrest_ngn") or {})


def _section(name: str) -> dict[str, Any]:
    return dict(rail().get(name) or {})


def api_base() -> str:
    raw = os.getenv("PAYCREST_API_BASE") or rail().get("api_base") or DEFAULT_API_BASE
    return str(raw).strip().rstrip("/")


def network() -> str:
    return str(rail().get("network") or "base").lower()


def token() -> str:
    return str(rail().get("token") or "USDC").upper()


def currency() -> str:
    return str(rail().get("currency") or "NGN").upper()


def delivery_chain() -> str:
    return os.getenv("PAYCREST_DELIVERY_CHAIN") or str(rail().get("delivery_chain") or "base_mainnet")


def settlement_chain() -> str:
    return os.getenv("PAYCREST_SETTLEMENT_CHAIN") or str(rail().get("settlement_chain") or "arc_mainnet")


def sender_fee_percent() -> Decimal:
    return Decimal(str(rail().get("sender_fee_percent") or "0"))


def transaction_fee_payer() -> str:
    v = str(rail().get("transaction_fee_payer") or "customer").lower()
    return v if v in ("customer", "sender") else "customer"


def kyc_id_types() -> tuple[str, ...]:
    raw = rail().get("kyc_id_types") or ["BVN", "nationalID"]
    return tuple(str(x) for x in raw)


@dataclass(frozen=True)
class Limits:
    onramp_min_ngn: Decimal
    onramp_max_ngn: Decimal
    onramp_daily_ngn: Decimal
    offramp_min_usdc: Decimal
    offramp_max_usdc: Decimal
    offramp_daily_usdc: Decimal
    quote_ttl_sec: int


def limits() -> Limits:
    s = _section("limits")

    def d(key: str, default: str) -> Decimal:
        return Decimal(str(s.get(key, default)))

    return Limits(
        onramp_min_ngn=d("onramp_min_ngn", "1000"),
        onramp_max_ngn=d("onramp_max_ngn", "500000"),
        onramp_daily_ngn=d("onramp_daily_ngn", "1000000"),
        offramp_min_usdc=d("offramp_min_usdc", "1"),
        offramp_max_usdc=d("offramp_max_usdc", "300"),
        offramp_daily_usdc=d("offramp_daily_usdc", "500"),
        quote_ttl_sec=int(s.get("quote_ttl_sec", 600)),
    )


@dataclass(frozen=True)
class BridgeSettings:
    onramp_fast_transfer: bool
    max_fee_bps: Decimal
    min_sweep_usdc: Decimal
    max_attempts: int


def bridge() -> BridgeSettings:
    s = _section("bridge")
    return BridgeSettings(
        onramp_fast_transfer=bool(s.get("onramp_fast_transfer", True)),
        max_fee_bps=Decimal(str(s.get("max_fee_bps", "5"))),
        min_sweep_usdc=Decimal(str(s.get("min_sweep_usdc", "0.50"))),
        max_attempts=int(s.get("max_attempts", 8)),
    )


def base_gas_mode() -> str:
    """``gas_station`` (Circle sponsors, SCA wallets) or ``hot_wallet``."""
    v = (os.getenv("PAYCREST_BASE_GAS_MODE") or _section("gas").get("base_mode") or "gas_station").lower()
    return v if v in ("gas_station", "hot_wallet") else "gas_station"


def base_account_type() -> str:
    if base_gas_mode() == "hot_wallet":
        return str(_section("gas").get("base_account_type_hot_wallet") or "EOA").upper()
    return str(_section("gas").get("base_account_type") or "SCA").upper()


def relayer_wallet_id(chain_id: str) -> str:
    """Boardman wallet that calls receiveMessage on ``chain_id`` (pays the mint gas)."""
    key = "PAYCREST_ARC_RELAYER_WALLET_ID" if chain_id.startswith("arc") else "PAYCREST_BASE_RELAYER_WALLET_ID"
    return (os.getenv(key) or "").strip()


def status() -> dict[str, Any]:
    """Operator view; never includes secret values."""
    return {
        "paycrest_enabled_flag": paycrest_flag(),
        "real_money_enabled": real_money_enabled(),
        "api_key_set": bool(api_key()),
        "api_secret_set": bool(api_secret()),
        "live": enabled(),
        "network": network(),
        "delivery_chain": delivery_chain(),
        "settlement_chain": settlement_chain(),
        "base_gas_mode": base_gas_mode(),
    }
