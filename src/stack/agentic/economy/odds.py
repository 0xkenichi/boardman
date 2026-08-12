"""
Spectator odds & risk/reward for agent matches.

Three layers (blended live):

1. Prior — agent win rate / form (stats)
2. Pool  — money already on each side (pari-mutuel)
3. Live  — engine eval (white POV → side A if A is white)

Decimal odds = (1 − total_take) / p_side
  so if you stake $1 and win, you get ~decimal dollars back (stake included).

Profit odds (net) = decimal − 1

Total take on spectator pot = platform_fee_bps + creator_pool_bps
  (default 3% + 2% = 5% house+creators; rest to winning bettors)

Agent facilitation:
  Each agent seeds spectator pot with spectator_seed_bps of its skill stake.
  That is the "juice" so odds exist even before fans bet.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from decimal import Decimal
from typing import Any, Optional


def _d(x: Any) -> Decimal:
    return Decimal(str(x))


def _clamp(x: float, lo: float = 0.02, hi: float = 0.98) -> float:
    return max(lo, min(hi, x))


def win_rate_from_stats(stats: Optional[dict[str, Any]]) -> float:
    """Empirical win rate with Laplace smoothing."""
    s = stats or {}
    w = int(s.get("wins") or 0)
    l = int(s.get("losses") or 0)
    d = int(s.get("draws") or 0)
    n = w + l + d
    if n == 0:
        return 0.5
    # draws count half
    return (w + 0.5 * d + 1.0) / (n + 2.0)


def eval_to_win_prob(eval_pawns: Optional[float], *, side_is_white: bool) -> Optional[float]:
    """
    White-POV eval → P(side wins). Logistic similar to Lichess.
    """
    if eval_pawns is None:
        return None
    # P(white wins) ≈ 1 / (1 + exp(-k * cp/100)) with k ~ 0.8–1.0 for midgame
    k = 0.85
    p_white = 1.0 / (1.0 + math.exp(-k * float(eval_pawns)))
    # Draw mass: compress extremes slightly when eval small
    if abs(float(eval_pawns)) < 0.4:
        p_white = 0.5 + (p_white - 0.5) * 0.7
    return _clamp(p_white if side_is_white else 1.0 - p_white)


@dataclass
class SideOdds:
    side: str  # a | b
    agent_id: str
    name: str
    win_rate: float
    pool_usdc: float
    prior_prob: float
    pool_prob: float
    live_prob: float  # blended
    decimal_odds: float  # payout multiplier including stake
    net_odds: float  # profit per $1 if win
    implied_edge: float  # live_prob * decimal - 1  (EV if model correct)
    seed_usdc: float
    fan_bets_usdc: float


@dataclass
class MarketSnapshot:
    match_id: str
    stage: str  # pregame | opening | middlegame | endgame | settled
    pot_total: float
    take_bps: int
    take_usdc: float
    payout_pool: float  # pot after take
    eval_pawns: Optional[float]
    side_a: SideOdds
    side_b: SideOdds
    notes: list[str]

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return d


def market_stage(*, ply: int = 0, settled: bool = False) -> str:
    if settled:
        return "settled"
    if ply <= 0:
        return "pregame"
    if ply < 20:
        return "opening"
    if ply < 50:
        return "middlegame"
    return "endgame"


def blend_probs(
    prior: float,
    pool: float,
    live: Optional[float],
    *,
    stage: str,
) -> float:
    """
    Weight shifts as game progresses:
      pregame:     55% prior, 45% pool
      opening:     35% prior, 25% pool, 40% eval
      middlegame:  15% prior, 20% pool, 65% eval
      endgame:     5% prior,  15% pool, 80% eval
    """
    if stage == "pregame" or live is None:
        return _clamp(0.55 * prior + 0.45 * pool)
    if stage == "opening":
        return _clamp(0.35 * prior + 0.25 * pool + 0.40 * live)
    if stage == "middlegame":
        return _clamp(0.15 * prior + 0.20 * pool + 0.65 * live)
    return _clamp(0.05 * prior + 0.15 * pool + 0.80 * live)


def build_market(
    *,
    match_id: str,
    agent_a: dict[str, Any],
    agent_b: dict[str, Any],
    pot_a: Decimal,
    pot_b: Decimal,
    seed_a: Decimal = Decimal("0"),
    seed_b: Decimal = Decimal("0"),
    eval_pawns: Optional[float] = None,
    a_is_white: bool = True,
    ply: int = 0,
    take_bps: int = 500,  # 3% platform + 2% creators
    settled: bool = False,
) -> MarketSnapshot:
    wr_a = win_rate_from_stats(agent_a.get("stats"))
    wr_b = win_rate_from_stats(agent_b.get("stats"))
    # Prior from relative strength
    prior_a = _clamp(wr_a / (wr_a + wr_b) if (wr_a + wr_b) > 0 else 0.5)
    prior_b = 1.0 - prior_a

    ta, tb = float(pot_a), float(pot_b)
    total = ta + tb
    if total <= 0:
        pool_a, pool_b = 0.5, 0.5
    else:
        # soft floor so empty side isn't 0 odds
        pool_a = _clamp((ta + 0.01) / (total + 0.02))
        pool_b = 1.0 - pool_a

    live_a = eval_to_win_prob(eval_pawns, side_is_white=a_is_white)
    live_b = (1.0 - live_a) if live_a is not None else None

    stage = market_stage(ply=ply, settled=settled)
    p_a = blend_probs(prior_a, pool_a, live_a, stage=stage)
    p_b = 1.0 - p_a

    take = take_bps / 10_000.0
    payout_pool = total * (1.0 - take) if total > 0 else 0.0

    def side_odds(
        side: str,
        agent: dict[str, Any],
        p: float,
        pool: float,
        prior: float,
        seed: float,
        fan: float,
    ) -> SideOdds:
        # Pari-mutuel style decimal if pool has money, else fair from live/prior
        if total > 0 and (ta if side == "a" else tb) > 0:
            side_pool = ta if side == "a" else tb
            # Your share of payout pool if you win: roughly pot*(1-take)/side_pool
            dec = (payout_pool / side_pool) if side_pool > 0 else 1.0 / max(p, 0.02)
        else:
            dec = (1.0 - take) / max(p, 0.02)
        dec = max(1.01, min(dec, 50.0))
        net = dec - 1.0
        edge = p * dec - 1.0
        return SideOdds(
            side=side,
            agent_id=str(agent.get("agent_id") or ""),
            name=str(agent.get("name") or agent.get("agent_id") or side),
            win_rate=round(win_rate_from_stats(agent.get("stats")), 4),
            pool_usdc=round(ta if side == "a" else tb, 6),
            prior_prob=round(prior, 4),
            pool_prob=round(pool, 4),
            live_prob=round(p, 4),
            decimal_odds=round(dec, 3),
            net_odds=round(net, 3),
            implied_edge=round(edge, 4),
            seed_usdc=round(seed, 6),
            fan_bets_usdc=round(fan, 6),
        )

    fan_a = max(0.0, ta - float(seed_a))
    fan_b = max(0.0, tb - float(seed_b))

    notes = [
        f"stage={stage}",
        f"take={take_bps} bps (platform+creators) off spectator pot",
        "skill escrow is separate — agents dual-lock stakes; spectator pot is side market",
        "agent seeds (spectator_seed_bps of skill stake) open the pot for fans",
    ]
    if eval_pawns is not None:
        notes.append(f"engine eval (white POV)={eval_pawns:+.2f}")

    return MarketSnapshot(
        match_id=match_id,
        stage=stage,
        pot_total=round(total, 6),
        take_bps=take_bps,
        take_usdc=round(total * take, 6),
        payout_pool=round(payout_pool, 6),
        eval_pawns=eval_pawns,
        side_a=side_odds("a", agent_a, p_a, pool_a, prior_a, float(seed_a), fan_a),
        side_b=side_odds("b", agent_b, p_b, pool_b, prior_b, float(seed_b), fan_b),
        notes=notes,
    )
