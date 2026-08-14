"""
Agent treasury / budget policy set at deploy time.

When drafting an agent, the creator declares margins so every match is
self-funding and spectator markets can be seeded without draining the bot:

  bankroll_usdc          — working capital the agent may stake from
  max_stake_usdc         — hard cap per match
  spectator_seed_bps     — fraction of *this match stake* auto-seeded into
                           the public spectator pot (0–2000 bps = 0–20%)
  draw_seed_bps          — equal per-agent seed into the draw book (same $)
  reserve_bps            — keep this fraction of bankroll unstaked (safety)
  preferred_time_controls — clocks this agent will accept
  auto_challenge         — may keep seeking matches when idle (policy flag)

Stake negotiation (unequal liquidity):
  free = bankroll * (1 - reserve_bps/10_000)
  max_affordable = min(max_stake, free)   # seed comes OUT of free after stake
  matched_stake  = min(max_affordable_a, max_affordable_b, requested)
  True cost per side = stake + spectator_seed(stake)
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from decimal import Decimal, ROUND_DOWN
from typing import Any, Optional


def _clamp_bps(x: int, lo: int = 0, hi: int = 5000) -> int:
    return max(lo, min(int(x), hi))


def _d(x: Any) -> Decimal:
    return Decimal(str(x))


def _q(x: Decimal) -> Decimal:
    return x.quantize(Decimal("0.000001"), rounding=ROUND_DOWN)


@dataclass
class AgentBudget:
    bankroll_usdc: str = "100"
    max_stake_usdc: str = "25"
    min_stake_usdc: str = "1"
    spectator_seed_bps: int = 500  # 5% of stake seeds spectator pot
    draw_seed_bps: int = 250  # 2.5% each into the draw book (equal $)
    reserve_bps: int = 2000  # keep 20% of bankroll unstaked
    creator_fee_bps: int = 500  # 5% of win gross → creator
    # LP profit share: of net skill profit credited to bankroll, this bps
    # is split among liquidity providers pro-rata by their share of bankroll.
    # Owner/creator keeps the residual (10_000 - lp_profit_share_bps).
    lp_profit_share_bps: int = 4000  # 40% of net skill profit → LPs pool
    preferred_time_controls: list[str] = field(
        default_factory=lambda: ["blitz_3|2", "blitz_5|0", "rapid_10|0"]
    )
    auto_challenge: bool = True
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def free_capital(self, current_bankroll: Decimal) -> Decimal:
        """Bankroll available after reserve."""
        br = _d(current_bankroll)
        if br <= 0:
            return Decimal("0")
        reserve = br * Decimal(self.reserve_bps) / Decimal(10_000)
        return _q(max(Decimal("0"), br - reserve))

    def spectator_seed_for_stake(self, stake: Decimal) -> Decimal:
        bps = _clamp_bps(self.spectator_seed_bps, 0, 2000)
        return _q(stake * Decimal(bps) / Decimal(10_000))

    def draw_seed_for_stake(self, stake: Decimal) -> Decimal:
        bps = _clamp_bps(self.draw_seed_bps, 0, 2000)
        return _q(stake * Decimal(bps) / Decimal(10_000))

    def total_lock_cost(self, stake: Decimal, *, draw_seed: Optional[Decimal] = None) -> Decimal:
        """Skill stake + side seed + equal draw seed."""
        stake = _d(stake)
        dseed = _d(draw_seed) if draw_seed is not None else self.draw_seed_for_stake(stake)
        return _q(stake + self.spectator_seed_for_stake(stake) + dseed)

    def max_affordable_stake(self, current_bankroll: Decimal) -> Decimal:
        """
        Largest equal skill stake this agent can lock, including seed cost
        and max_stake / min_stake policy.
        Solve: stake + stake * seed_bps/10k <= free  AND  stake <= max_stake
        """
        free = self.free_capital(current_bankroll)
        if free <= 0:
            return Decimal("0")
        seed_bps = _clamp_bps(self.spectator_seed_bps, 0, 2000)
        draw_bps = _clamp_bps(self.draw_seed_bps, 0, 2000)
        mult = Decimal(10_000 + seed_bps + draw_bps) / Decimal(10_000)
        raw = free / mult if mult > 0 else Decimal("0")
        capped = min(raw, _d(self.max_stake_usdc))
        if capped < _d(self.min_stake_usdc):
            # Can they afford min stake + its seed?
            if self.total_lock_cost(_d(self.min_stake_usdc)) <= free:
                return _d(self.min_stake_usdc)
            return Decimal("0")
        return _q(capped)

    def can_stake(self, stake: Decimal, current_bankroll: Decimal) -> tuple[bool, str]:
        stake = _d(stake)
        if stake < _d(self.min_stake_usdc):
            return False, f"stake below min {self.min_stake_usdc}"
        if stake > _d(self.max_stake_usdc):
            return False, f"stake above max {self.max_stake_usdc}"
        cost = self.total_lock_cost(stake)
        free = self.free_capital(current_bankroll)
        if cost > free:
            return (
                False,
                f"stake+seed {cost} exceeds free bankroll {free} "
                f"(reserve {self.reserve_bps} bps)",
            )
        return True, "ok"


@dataclass
class StakeNegotiation:
    """Result of matching two agents' free liquidity into one equal stake."""

    stake_usdc: str
    seed_a: str
    seed_b: str
    draw_seed: str
    cost_a: str
    cost_b: str
    free_a: str
    free_b: str
    max_a: str
    max_b: str
    bankroll_a: str
    bankroll_b: str
    requested: str
    binding: str  # "a" | "b" | "request" | "none"
    ok: bool
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def negotiate_match_stake(
    bud_a: AgentBudget,
    bud_b: AgentBudget,
    bankroll_a: Decimal,
    bankroll_b: Decimal,
    *,
    requested: Optional[Decimal] = None,
) -> StakeNegotiation:
    """
    Equal-stake negotiation.

    Matched stake = min(max_affordable_a, max_affordable_b, requested or +inf).
    The poorer agent's free capital is the natural ceiling — a $1000 agent
    cannot force a $200 lock against a $100 agent.
    """
    free_a = bud_a.free_capital(bankroll_a)
    free_b = bud_b.free_capital(bankroll_b)
    max_a = bud_a.max_affordable_stake(bankroll_a)
    max_b = bud_b.max_affordable_stake(bankroll_b)
    matched = min(max_a, max_b)
    binding = "a" if max_a <= max_b else "b"
    req = _d(requested) if requested is not None else None
    if req is not None:
        if req < matched:
            matched = req
            binding = "request"
        # if req > matched, keep matched (liquidity binds)

    min_needed = max(_d(bud_a.min_stake_usdc), _d(bud_b.min_stake_usdc))
    if matched < min_needed or matched <= 0:
        return StakeNegotiation(
            stake_usdc="0",
            seed_a="0",
            seed_b="0",
            draw_seed="0",
            cost_a="0",
            cost_b="0",
            free_a=str(free_a),
            free_b=str(free_b),
            max_a=str(max_a),
            max_b=str(max_b),
            bankroll_a=str(_q(bankroll_a)),
            bankroll_b=str(_q(bankroll_b)),
            requested=str(req) if req is not None else "",
            binding="none",
            ok=False,
            reason=(
                f"no mutual stake: max_a={max_a} max_b={max_b} "
                f"min_needed={min_needed}"
            ),
        )

    matched = _q(matched)
    seed_a = bud_a.spectator_seed_for_stake(matched)
    seed_b = bud_b.spectator_seed_for_stake(matched)
    draw_seed = min(bud_a.draw_seed_for_stake(matched), bud_b.draw_seed_for_stake(matched))
    cost_a = bud_a.total_lock_cost(matched, draw_seed=draw_seed)
    cost_b = bud_b.total_lock_cost(matched, draw_seed=draw_seed)
    ok_a, why_a = bud_a.can_stake(matched, bankroll_a)
    ok_b, why_b = bud_b.can_stake(matched, bankroll_b)
    if not ok_a or not ok_b:
        return StakeNegotiation(
            stake_usdc=str(matched),
            seed_a=str(seed_a),
            seed_b=str(seed_b),
            draw_seed=str(draw_seed),
            cost_a=str(cost_a),
            cost_b=str(cost_b),
            free_a=str(free_a),
            free_b=str(free_b),
            max_a=str(max_a),
            max_b=str(max_b),
            bankroll_a=str(_q(bankroll_a)),
            bankroll_b=str(_q(bankroll_b)),
            requested=str(req) if req is not None else "",
            binding=binding,
            ok=False,
            reason=why_a if not ok_a else why_b,
        )

    return StakeNegotiation(
        stake_usdc=str(matched),
        seed_a=str(seed_a),
        seed_b=str(seed_b),
        draw_seed=str(draw_seed),
        cost_a=str(cost_a),
        cost_b=str(cost_b),
        free_a=str(free_a),
        free_b=str(free_b),
        max_a=str(max_a),
        max_b=str(max_b),
        bankroll_a=str(_q(bankroll_a)),
        bankroll_b=str(_q(bankroll_b)),
        requested=str(req) if req is not None else "",
        binding=binding,
        ok=True,
        reason="ok",
    )


def budget_from_manifest(manifest: dict[str, Any]) -> AgentBudget:
    eco = manifest.get("economy") or manifest.get("budget") or {}
    tc = eco.get("preferred_time_controls") or manifest.get("preferred_time_controls")
    return AgentBudget(
        bankroll_usdc=str(eco.get("bankroll_usdc", "100")),
        max_stake_usdc=str(eco.get("max_stake_usdc", "25")),
        min_stake_usdc=str(eco.get("min_stake_usdc", "1")),
        spectator_seed_bps=_clamp_bps(int(eco.get("spectator_seed_bps", 500)), 0, 2000),
        draw_seed_bps=_clamp_bps(int(eco.get("draw_seed_bps", 250)), 0, 2000),
        reserve_bps=_clamp_bps(int(eco.get("reserve_bps", 2000)), 0, 5000),
        creator_fee_bps=_clamp_bps(int(eco.get("creator_fee_bps", 500)), 0, 2000),
        lp_profit_share_bps=_clamp_bps(int(eco.get("lp_profit_share_bps", 4000)), 0, 8000),
        preferred_time_controls=list(tc or ["blitz_3|2", "blitz_5|0", "rapid_10|0"]),
        auto_challenge=bool(eco.get("auto_challenge", True)),
        notes=str(eco.get("notes") or ""),
    )
