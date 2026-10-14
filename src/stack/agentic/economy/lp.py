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

Stored one row per agent pool in the agentic database (``lp_pools``); every
change is an atomic read-modify-write of that row. Legacy file
agent_lp_pools.json is imported by scripts/migrate_json_to_db.py.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from decimal import Decimal, ROUND_DOWN
from typing import Any, Optional

from gaming.src.stack.agentic.db.tables import LP_POOLS

LP_FILE = "agent_lp_pools.json"


def _empty_pool(agent_id: str) -> dict[str, Any]:
    return {
        "agent_id": agent_id,
        "total_lp_usdc": "0",
        "positions": {},  # lp_id -> {amount, deposited_at, realized_pnl}
        "history": [],
    }


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
        """Legacy whole-file view ``{"pools": {...}}``."""
        return LP_POOLS.snapshot(LP_POOLS.query(), "agent_id")

    def _save(self, data: dict[str, Any]) -> None:
        """Write back only what the caller changed in a ``_load()`` snapshot."""
        LP_POOLS.save_snapshot(data)

    def get_pool(self, agent_id: str) -> dict[str, Any]:
        return LP_POOLS.get(agent_id) or _empty_pool(agent_id)

    def deposit(
        self,
        agent_id: str,
        *,
        lp_id: str,
        amount_usdc: Decimal,
        pull_tx_hash: str = "",
        pull_tx_explorer: str = "",
    ) -> dict[str, Any]:
        amount = _q(_d(amount_usdc))
        if amount <= 0:
            raise ValueError("LP deposit must be positive")

        def _apply(cur: Optional[dict[str, Any]]) -> dict[str, Any]:
            pool = cur or _empty_pool(agent_id)
            self._deposit_into(pool, lp_id, amount, pull_tx_hash, pull_tx_explorer)
            return pool

        pool = LP_POOLS.upsert_with(agent_id, _apply)
        assert pool is not None
        return pool

    @staticmethod
    def _deposit_into(
        pool: dict[str, Any], lp_id: str, amount: Decimal, pull_tx_hash: str, pull_tx_explorer: str
    ) -> None:
        pos = pool["positions"].get(lp_id) or {
            "lp_id": lp_id,
            "amount": "0",
            "deposited_at": _now(),
            "realized_pnl": "0",
        }
        pos["amount"] = str(_q(_d(pos["amount"]) + amount))
        if pull_tx_hash:
            pos["last_tx_hash"] = str(pull_tx_hash)[:80]
            pos["last_tx_explorer"] = str(pull_tx_explorer or "")[:200]
        pool["positions"][lp_id] = pos
        pool["total_lp_usdc"] = str(_q(_d(pool["total_lp_usdc"]) + amount))
        pool["history"].append(
            {
                "ts": _now(),
                "type": "deposit",
                "lp_id": lp_id,
                "amount": str(amount),
                "tx_hash": str(pull_tx_hash)[:80] if pull_tx_hash else "",
            }
        )
        pool["history"] = pool["history"][-200:]

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
        return self._withdrawable_from(
            self.get_pool(agent_id),
            lp_id,
            agent_bankroll=agent_bankroll,
            reserve_bps=reserve_bps,
            locked_usdc=locked_usdc,
        )

    @staticmethod
    def _withdrawable_from(
        pool: dict[str, Any],
        lp_id: str,
        *,
        agent_bankroll: Decimal,
        reserve_bps: int,
        locked_usdc: Decimal = Decimal("0"),
    ) -> Decimal:
        pos = (pool.get("positions") or {}).get(lp_id)
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
        withdraw_tx_hash: str = "",
        withdraw_tx_explorer: str = "",
    ) -> dict[str, Any]:
        amount = _q(_d(amount_usdc))

        def _apply(pool: dict[str, Any]) -> None:
            # Re-check inside the row lock: two concurrent withdrawals must not
            # both pass a stale check.
            max_w = self._withdrawable_from(
                pool, lp_id, agent_bankroll=agent_bankroll, reserve_bps=reserve_bps, locked_usdc=locked_usdc
            )
            if amount <= 0 or amount > max_w:
                raise ValueError(f"cannot withdraw {amount}; max {max_w}")
            self._withdraw_from(pool, lp_id, amount, withdraw_tx_hash, withdraw_tx_explorer)

        pool = LP_POOLS.update(agent_id, _apply)
        if pool is None:
            raise ValueError(f"cannot withdraw {amount}; max 0")
        return {"pool": pool, "withdrawn": str(amount)}

    @staticmethod
    def _withdraw_from(
        pool: dict[str, Any], lp_id: str, amount: Decimal, withdraw_tx_hash: str, withdraw_tx_explorer: str
    ) -> None:
        pos = pool["positions"][lp_id]
        pos["amount"] = str(_q(_d(pos["amount"]) - amount))
        if withdraw_tx_hash:
            pos["last_tx_hash"] = str(withdraw_tx_hash)[:80]
            pos["last_tx_explorer"] = str(withdraw_tx_explorer or "")[:200]
        pool["total_lp_usdc"] = str(_q(_d(pool["total_lp_usdc"]) - amount))
        pool["history"].append(
            {
                "ts": _now(),
                "type": "withdraw",
                "lp_id": lp_id,
                "amount": str(amount),
                "tx_hash": str(withdraw_tx_hash)[:80] if withdraw_tx_hash else "",
            }
        )
        pool["history"] = pool["history"][-200:]

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

        result: dict[str, Any] = {}

        def _apply(cur: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
            live = cur or _empty_pool(agent_id)
            out, changed = self._distribute_in(live, profit, lp_profit_share_bps)
            result.update(out)
            return live if changed and cur is not None else None

        LP_POOLS.upsert_with(agent_id, _apply)
        return result

    @staticmethod
    def _distribute_in(
        live: dict[str, Any], profit: Decimal, lp_profit_share_bps: int
    ) -> tuple[dict[str, Any], bool]:
        pool = live
        total_lp = _d(pool.get("total_lp_usdc") or "0")
        bps = max(0, min(int(lp_profit_share_bps), 8000))

        if total_lp <= 0 or bps == 0 or not pool.get("positions"):
            return {
                "lp_payouts": [],
                "lp_total": "0",
                "owner_residual": str(profit),
                "notes": ["no LPs — all residual to owner/bankroll"],
            }, False

        lp_pool_profit = _q(profit * Decimal(bps) / Decimal(10_000))
        owner_residual = _q(profit - lp_pool_profit)
        payouts: list[dict[str, Any]] = []
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
        live.setdefault("history", []).append(
            {
                "ts": _now(),
                "type": "skill_profit",
                "profit": str(profit),
                "lp_total": str(lp_pool_profit),
                "owner_residual": str(owner_residual),
            }
        )
        live["history"] = live["history"][-200:]

        return {
            "lp_payouts": payouts,
            "lp_total": str(lp_pool_profit),
            "owner_residual": str(owner_residual),
            "notes": [
                f"LPs take {bps} bps of net skill profit pro-rata",
                "LP claims compound into total_lp_usdc (claim on bankroll)",
            ],
        }, True

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
        result: dict[str, Any] = {}

        def _apply(pool: dict[str, Any]) -> None:
            result.update(self._mark_loss_in(pool, loss, agent_bankroll_before))

        pool = LP_POOLS.update(agent_id, _apply)
        if pool is None:
            return {"haircut": "0", "notes": ["no LP book"]}
        if "pool" in result:
            result["pool"] = pool
        return result

    @staticmethod
    def _mark_loss_in(pool: dict[str, Any], loss: Decimal, agent_bankroll_before: Decimal) -> dict[str, Any]:
        if _d(pool.get("total_lp_usdc") or "0") <= 0:
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
        return {"haircut": str(haircut), "pool": pool, "notes": ["LP claims marked down"]}
