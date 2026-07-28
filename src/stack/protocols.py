"""
Builder-facing protocols (interfaces) for Rematch Stack.

Implementations today live in gaming.src.backend.services.* and are wired
through RematchStack. Future apps should depend on these shapes so the
Telegram bot can be swapped for Discord/web without rewriting money rails.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any, Optional, Protocol, runtime_checkable


@runtime_checkable
class WalletProvider(Protocol):
    async def ensure_wallet(self, user_id: str, chain_id: Optional[str] = None) -> dict[str, Any]:
        """Return {wallet_id, address, blockchain, chain_id}."""
        ...

    async def get_usdc_balance(self, user_id: str, chain_id: Optional[str] = None) -> Decimal:
        ...


@runtime_checkable
class EscrowEngine(Protocol):
    async def lock_stake(self, challenge_id: str, user_id: str) -> dict[str, Any]:
        ...

    async def cancel_match(self, challenge_id: str, user_id: str) -> dict[str, Any]:
        ...


@runtime_checkable
class MatchEngine(Protocol):
    """Match lifecycle — create/accept/report are app-shaped; settle is stack-shaped."""

    def get_public_board(self, leaderboard_limit: int = 25, open_limit: int = 30) -> dict[str, Any]:
        ...


@runtime_checkable
class OutcomeVerifier(Protocol):
    """Pluggable proof: vision, oracle, manual, etc."""

    def verify(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Return structured result: {ok, scoreline?, confidence?, reason?}."""
        ...


@runtime_checkable
class ReputationEngine(Protocol):
    def leaderboard(self, limit: int = 25) -> list[dict[str, Any]]:
        ...
