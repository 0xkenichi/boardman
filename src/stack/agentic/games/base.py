"""Game module protocol — finite outcome, verifiable, 1v1."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from typing import Any, Optional


@dataclass
class MoveResult:
    ok: bool
    move: str = ""
    error: str = ""
    state: dict[str, Any] = field(default_factory=dict)


@dataclass
class GameResult:
    """terminal outcome after a match."""

    done: bool
    # p1_win | p2_win | draw | ongoing
    outcome: str
    winner_side: Optional[str] = None  # "p1" | "p2" | None
    reason: str = ""
    state: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class GameModule(ABC):
    game_id: str
    display_name: str
    # sides: p1 always moves first (maps to white / X / black stones for go etc.)

    @abstractmethod
    def new_game(self, **kwargs: Any) -> dict[str, Any]:
        """Return initial state dict (JSON-serializable)."""

    @abstractmethod
    def legal_moves(self, state: dict[str, Any]) -> list[str]:
        """List of move strings in this game's notation."""

    @abstractmethod
    def apply_move(self, state: dict[str, Any], move: str) -> MoveResult:
        """Apply move; return new state inside MoveResult.state on success."""

    @abstractmethod
    def status(self, state: dict[str, Any]) -> GameResult:
        """Whether game is over and who won."""

    def current_side(self, state: dict[str, Any]) -> str:
        """p1 or p2 to move."""
        return state.get("to_move", "p1")

    def encode_public(self, state: dict[str, Any]) -> dict[str, Any]:
        """State shown to agents / UI (no secrets)."""
        return dict(state)

    def simple_ai_move(self, state: dict[str, Any], *, rng=None) -> str:
        """Fallback bot: random legal (override for smarter defaults)."""
        import random

        r = rng or random
        moves = self.legal_moves(state)
        if not moves:
            raise ValueError("no legal moves")
        return r.choice(moves)
