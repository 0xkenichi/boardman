"""Shared domain types for Rematch Stack (builder-facing)."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Optional


@dataclass
class ChainInfo:
    id: str
    label: str
    recommended: bool = False
    enabled: bool = True
    status: str = "live"  # live | next | legacy
    chain_id: Optional[int] = None
    explorer_tx: str = ""
    gas_token: str = ""
    escrow_configured: bool = False
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class StackCapabilities:
    """What this Stack deployment can do (feature discovery for builders)."""

    version: str = "0.1.0"
    product: str = "rematch-stack"
    modules: list[str] = field(
        default_factory=lambda: [
            "chains",
            "wallets",
            "escrow",
            "matches",
            "settlement",
            "proof",
            "reputation",
            "safety",
        ]
    )
    default_chain: str = "arc"
    network: str = "testnet"
    # Product posture: Arc only live; Avalanche next
    live_chains: list[str] = field(default_factory=lambda: ["arc"])
    next_chains: list[str] = field(default_factory=lambda: ["avalanche"])
    games: list[str] = field(default_factory=lambda: ["ea_fc"])
    match_model: str = "1v1_dual_lock_usdc"
    experiences: list[str] = field(
        default_factory=lambda: ["telegram:rematch"]
    )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class StackHealth:
    status: str
    version: str
    checks: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
