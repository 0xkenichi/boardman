"""
Agent liquidity providers (LPs).

People who believe in an agent can top up its bankroll (not the spectator pot).
They take market risk with the agent:

  - Deposit USDC → agent free capital grows → larger stakes / seeds possible
  - On skill WIN: net bankroll profit is split
        LP pool gets lp_profit_share_bps of profit (pro-rata by LP deposit share)
        Owner residual keeps the rest (alongside creator fee already taken)
  - On skill LOSS: LPs mark down with the agent (their claim on bankroll shrinks)
  - Withdraw: only free capital above reserve + open escrow locks

This is NOT spectator betting. LPs are equity-like co-funders of the bot.
Spectator pot remains a separate side market.

Demo ledger file: agent_lp_pools.json
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from decimal import Decimal, ROUND_DOWN
from typing import Any, Optional

from gaming.src.stack.agentic.store import load_json, save_json

LP_FILE = "agent_lp_pools.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _d(x: Any) -> Decimal:
    return Decimal(str(x))


def _q(x: Decimal) -> Decimal:
    return x.quantize(Decimal("0.000001"), rounding=ROUND_DOWN)


@dataclass
class LPPayout:
    lp_id: str
    amount: str
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class AgentLPPool:
    def _load(self) -> dict[str, Any]:
        return load_json(LP_FILE, {"pools": {}})

    def _save(self, data: dict[str, Any]) -> None:
        save_json(LP_FILE, data)

    def get_pool(self, agent_id: str) -> dict[str, Any]:
        data = self._load()
        p = data["pools"].get(agent_id)
        if p:
            return p
        return {
            "agent_id": agent_id,
            "total_lp_usdc": "0",
            "positions": {},  # lp_id -> {amount, deposited_at, realized_pnl}
            "history": [],
        }

    def deposit(
        self,
        agent_id: str,
        *,
        lp_id: str,
        amount_usdc: Decimal,
    ) -> dict[str, Any]:
        amount = _q(_d(amount_usdc))
        if amount <= 0:
            raise ValueError("LP deposit must be positive")
        data = self._load()
        pool = data["pools"].get(agent_id) or {
            "agent_id": agent_id,
            "total_lp_usdc": "0",
            "positions": {},
            "history": [],
        }
        pos = pool["positions"].get(lp_id) or {
            "lp_id": lp_id,
            "amount": "0",
            "deposited_at": _now(),
            "realized_pnl": "0",
        }
        pos["amount"] = str(_q(_d(pos["amount"]) + amount))
        pool["positions"][lp_id] = pos
        pool["total_lp_usdc"] = str(_q(_d(pool["total_lp_usdc"]) + amount))
        pool["history"].append(
            {
                "ts": _now(),
                "type": "deposit",
                "lp_id": lp_id,
                "amount": str(amount),
            }
        )
        pool["history"] = pool["history"][-200:]
        data["pools"][agent_id] = pool
        self._save(data)
        return pool

    def withdrawable(
        self,
        agent_id: str,
        *,
        lp_id: str,
        agent_bankroll: Decimal,
        reserve_bps: int,
        locked_usdc: Decimal = Decimal("0"),
    ) -> Decimal:
        """LP may not pull more than their share of free capital."""
        pool = self.get_pool(agent_id)
        pos = pool["positions"].get(lp_id)
        if not pos:
            return Decimal("0")
        claim = _d(pos["amount"])
        if claim <= 0:
            return Decimal("0")
        free = _d(agent_bankroll) - locked_usdc
        reserve = _d(agent_bankroll) * Decimal(int(reserve_bps)) / Decimal(10_000)
        free_after_reserve = max(Decimal("0"), free - reserve)
        # Cap by their claim and free capital
        return _q(min(claim, free_after_reserve))

    def withdraw(
        self,
        agent_id: str,
        *,
        lp_id: str,
        amount_usdc: Decimal,
        agent_bankroll: Decimal,
        reserve_bps: int,
        locked_usdc: Decimal = Decimal("0"),
    ) -> dict[str, Any]:
        amount = _q(_d(amount_usdc))
        max_w = self.withdrawable(
            agent_id,
            lp_id=lp_id,
            agent_bankroll=agent_bankroll,
            reserve_bps=reserve_bps,
            locked_usdc=locked_usdc,
        )
        if amount <= 0 or amount > max_w:
            raise ValueError(f"cannot withdraw {amount}; max {max_w}")
        data = self._load()
        pool = data["pools"][agent_id]
        pos = pool["positions"][lp_id]
        pos["amount"] = str(_q(_d(pos["amount"]) - amount))
        pool["total_lp_usdc"] = str(_q(_d(pool["total_lp_usdc"]) - amount))
        pool["history"].append(
            {
                "ts": _now(),
                "type": "withdraw",
                "lp_id": lp_id,
                "amount": str(amount),
            }
        )
        pool["history"] = pool["history"][-200:]
        data["pools"][agent_id] = pool
        self._save(data)
        return {"pool": pool, "withdrawn": str(amount)}

    def distribute_skill_profit(
        self,
        agent_id: str,
        *,
        net_profit_usdc: Decimal,
        lp_profit_share_bps: int,
    ) -> dict[str, Any]:
        """
        Split net skill profit (after platform + creator fee) between LPs and owner residual.

        Returns {lp_payouts, lp_total, owner_residual, notes}.
        Caller credits LP wallets / updates bankroll accounting.
        """
        profit = _q(_d(net_profit_usdc))
        if profit <= 0:
            return {
                "lp_payouts": [],
                "lp_total": "0",
                "owner_residual": str(max(Decimal("0"), profit)),
                "notes": ["no profit to split"],
            }

        pool = self.get_pool(agent_id)
        total_lp = _d(pool.get("total_lp_usdc") or "0")
        bps = max(0, min(int(lp_profit_share_bps), 8000))

        if total_lp <= 0 or bps == 0 or not pool.get("positions"):
            return {
                "lp_payouts": [],
                "lp_total": "0",
                "owner_residual": str(profit),
                "notes": ["no LPs — all residual to owner/bankroll"],
            }

        lp_pool_profit = _q(profit * Decimal(bps) / Decimal(10_000))
        owner_residual = _q(profit - lp_pool_profit)
        payouts: list[dict[str, Any]] = []
        data = self._load()
        live = data["pools"].get(agent_id) or pool

        positions = live.get("positions") or {}
        if not isinstance(positions, dict):
            positions = {}
            live["positions"] = positions
        for lp_id, pos in list(positions.items()):
            share_amt = _d(pos.get("amount") or "0")
            if share_amt <= 0:
                continue
            part = _q(lp_pool_profit * share_amt / total_lp)
            if part <= 0:
                continue
            # Compound: LP claim on bankroll grows with profit share
            pos["amount"] = str(_q(share_amt + part))
            pos["realized_pnl"] = str(_q(_d(pos.get("realized_pnl") or "0") + part))
            live["positions"][lp_id] = pos
            payouts.append(
                {"lp_id": lp_id, "amount": str(part), "reason": "skill_profit_share"}
            )

        live["total_lp_usdc"] = str(
            _q(sum(_d(p["amount"]) for p in live["positions"].values()))
        )
        live["history"].append(
            {
                "ts": _now(),
                "type": "skill_profit",
                "profit": str(profit),
                "lp_total": str(lp_pool_profit),
                "owner_residual": str(owner_residual),
            }
        )
        live["history"] = live["history"][-200:]
        data["pools"][agent_id] = live
        self._save(data)

        return {
            "lp_payouts": payouts,
            "lp_total": str(lp_pool_profit),
            "owner_residual": str(owner_residual),
            "notes": [
                f"LPs take {bps} bps of net skill profit pro-rata",
                "LP claims compound into total_lp_usdc (claim on bankroll)",
            ],
        }

    def mark_loss(
        self,
        agent_id: str,
        *,
        loss_usdc: Decimal,
        agent_bankroll_before: Decimal,
    ) -> dict[str, Any]:
        """
        After a skill loss, shrink LP claims pro-rata so LP equity tracks bankroll.
        loss_usdc is stake lost (not including seed which may be separate).
        """
        loss = _q(_d(loss_usdc))
        if loss <= 0:
            return {"haircut": "0", "notes": ["no loss"]}
        data = self._load()
        pool = data["pools"].get(agent_id)
        if not pool or _d(pool.get("total_lp_usdc") or "0") <= 0:
            return {"haircut": "0", "notes": ["no LP book"]}

        br = _d(agent_bankroll_before)
        if br <= 0:
            return {"haircut": "0", "notes": ["empty bankroll"]}

        # LP fraction of bankroll before loss
        total_lp = _d(pool["total_lp_usdc"])
        lp_fraction = min(Decimal("1"), total_lp / br)
        haircut = _q(loss * lp_fraction)
        if haircut <= 0:
            return {"haircut": "0", "notes": ["haircut zero"]}

        for lp_id, pos in pool["positions"].items():
            amt = _d(pos["amount"])
            if total_lp <= 0:
                break
            cut = _q(haircut * amt / total_lp)
            pos["amount"] = str(_q(max(Decimal("0"), amt - cut)))
            pos["realized_pnl"] = str(_q(_d(pos.get("realized_pnl") or "0") - cut))
            pool["positions"][lp_id] = pos

        pool["total_lp_usdc"] = str(
            _q(sum(_d(p["amount"]) for p in pool["positions"].values()))
        )
        pool["history"].append(
            {
                "ts": _now(),
                "type": "skill_loss_haircut",
                "loss": str(loss),
                "haircut": str(haircut),
            }
        )
        pool["history"] = pool["history"][-200:]
        data["pools"][agent_id] = pool
        self._save(data)
        return {"haircut": str(haircut), "pool": pool, "notes": ["LP claims marked down"]}
