"""Club / manager state for AFM v0."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from decimal import Decimal
from typing import Any, Optional

from gaming.src.stack.agentic.games.football_managers.catalog import get_player
from gaming.src.stack.agentic.games.football_managers.rules import (
    MAX_SQUAD_SIZE,
    WAGE_RUNWAY_MATCHDAYS,
)


@dataclass
class Club:
    agent_id: str
    club_name: str
    budget_usdc: str  # Decimal as string
    roster: list[str] = field(default_factory=list)
    formation: str = "4-3-3"
    tactical_tags: list[str] = field(default_factory=list)
    starters: list[str] = field(default_factory=list)
    bench: list[str] = field(default_factory=list)

    def budget(self) -> Decimal:
        return Decimal(self.budget_usdc)

    def set_budget(self, amount: Decimal) -> None:
        self.budget_usdc = str(amount)

    def wages_per_matchday(self) -> Decimal:
        total = Decimal("0")
        for pid in self.roster:
            p = get_player(pid)
            if p:
                total += Decimal(str(p["wage_per_matchday_usdc"]))
        return total

    def can_afford(self, price: Decimal) -> bool:
        wages = self.wages_per_matchday()
        runway = wages * WAGE_RUNWAY_MATCHDAYS
        return self.budget() >= price + runway

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["wages_per_matchday_usdc"] = str(self.wages_per_matchday())
        d["squad_size"] = len(self.roster)
        d["max_squad"] = MAX_SQUAD_SIZE
        return d


def create_club(
    agent_id: str,
    *,
    club_name: Optional[str] = None,
    starting_budget: Decimal | float | str = "100",
) -> Club:
    return Club(
        agent_id=agent_id,
        club_name=club_name or f"FC {agent_id[-6:]}",
        budget_usdc=str(Decimal(str(starting_budget))),
    )
