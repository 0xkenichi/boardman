"""
Creator fee router for agent skill matches + spectator volume.

Money paths (skill pot) — one contest, one settle:

  pot = stake_a + stake_b
  platform_fee = pot * platform_fee_bps / 10_000          # Boardman stack
  winner_gross = pot - platform_fee
  creator_fee  = winner_gross * winner.creator_fee_bps / 10_000
  owner_payout = winner_gross - creator_fee

Creator sets creator_fee_bps on deploy (capped). That is their cut of
every win their agent banks. Loser creator gets nothing from skill pot
(optional: participation crumbs later).

Spectator path (separate pot, same match_id):
  see spectator.py — creators can take a cut of matched spectator volume.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from decimal import Decimal
from typing import Any, Optional

# BoardmanEscrow V1 is 300 bps on-chain; stack fee policy mirrors that.
DEFAULT_PLATFORM_FEE_BPS = 700  # 7% platform fee
# Creator may claim up to 20% of their agent's winner_gross
MAX_CREATOR_FEE_BPS = 2000
DEFAULT_CREATOR_FEE_BPS = 500  # 5% of winner gross → creator
# Optional losing-agent creator crumb from platform fee only (0 = off)
DEFAULT_LOSER_CREATOR_BPS_OF_PLATFORM = 0


def _d(x: Any) -> Decimal:
    return Decimal(str(x))


def _bps(amount: Decimal, bps: int) -> Decimal:
    return (amount * Decimal(int(bps)) / Decimal(10_000)).quantize(Decimal("0.000001"))


def clamp_creator_fee_bps(bps: int) -> int:
    return max(0, min(int(bps), MAX_CREATOR_FEE_BPS))


@dataclass
class FeeSplit:
    pot: str
    platform_fee_bps: int
    platform_fee: str
    winner_gross: str
    winner_agent_id: Optional[str]
    winner_creator_id: Optional[str]
    creator_fee_bps: int
    creator_fee: str
    owner_payout: str
    loser_agent_id: Optional[str] = None
    loser_creator_crumb: str = "0"
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class FeeRouter:
    def __init__(
        self,
        *,
        platform_fee_bps: int = DEFAULT_PLATFORM_FEE_BPS,
        loser_creator_bps_of_platform: int = DEFAULT_LOSER_CREATOR_BPS_OF_PLATFORM,
    ) -> None:
        self.platform_fee_bps = int(platform_fee_bps)
        self.loser_creator_bps_of_platform = int(loser_creator_bps_of_platform)

    def split_skill_pot(
        self,
        *,
        stake_usdc: Decimal,
        winner_agent: Optional[dict[str, Any]],
        loser_agent: Optional[dict[str, Any]] = None,
        draw: bool = False,
    ) -> FeeSplit:
        pot = stake_usdc * 2
        if draw:
            return FeeSplit(
                pot=str(pot),
                platform_fee_bps=self.platform_fee_bps,
                platform_fee="0",
                winner_gross="0",
                winner_agent_id=None,
                winner_creator_id=None,
                creator_fee_bps=0,
                creator_fee="0",
                owner_payout="0",
                loser_agent_id=None,
                notes=["draw: full refund both sides; no creator fee"],
            )

        if not winner_agent:
            raise ValueError("winner_agent required unless draw")

        platform_fee = _bps(pot, self.platform_fee_bps)
        winner_gross = pot - platform_fee
        c_bps = clamp_creator_fee_bps(
            int(
                winner_agent.get("creator_fee_bps")
                or (winner_agent.get("economy") or {}).get("creator_fee_bps")
                or DEFAULT_CREATOR_FEE_BPS
            )
        )
        creator_fee = _bps(winner_gross, c_bps)
        owner_payout = winner_gross - creator_fee

        loser_crumb = Decimal("0")
        notes = [
            f"platform {self.platform_fee_bps} bps of pot",
            f"creator {c_bps} bps of winner_gross (set by creator on deploy)",
        ]
        if loser_agent and self.loser_creator_bps_of_platform > 0:
            loser_crumb = _bps(platform_fee, self.loser_creator_bps_of_platform)
            notes.append(
                f"loser creator crumb {self.loser_creator_bps_of_platform} bps of platform fee"
            )

        return FeeSplit(
            pot=str(pot),
            platform_fee_bps=self.platform_fee_bps,
            platform_fee=str(platform_fee),
            winner_gross=str(winner_gross),
            winner_agent_id=winner_agent.get("agent_id"),
            winner_creator_id=winner_agent.get("creator_id")
            or winner_agent.get("owner_id"),
            creator_fee_bps=c_bps,
            creator_fee=str(creator_fee),
            owner_payout=str(owner_payout),
            loser_agent_id=(loser_agent or {}).get("agent_id"),
            loser_creator_crumb=str(loser_crumb),
            notes=notes,
        )
