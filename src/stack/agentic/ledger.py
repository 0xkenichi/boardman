"""
Demo dual-lock USDC ledger for agent matches.

Mirrors ClawEscrow flow without requiring mainnet keys:
  open → both lock → settle to winner (minus platform fee).

Balances are book-entry USDC in data/agentic/ledger.json.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional

from gaming.src.stack.agentic.store import load_json, save_json

LEDGER_FILE = "ledger.json"
DEFAULT_FEE_BPS = 300  # 3% — align with BoardmanEscrow V1 FEE_BPS


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _dec(x: Any) -> Decimal:
    return Decimal(str(x))


def _load() -> dict[str, Any]:
    return load_json(
        LEDGER_FILE,
        {
            "balances": {},  # wallet_address lower -> "12.5"
            "escrows": {},  # match_id -> escrow record
            "txs": [],
        },
    )


def _save(data: dict[str, Any]) -> None:
    save_json(LEDGER_FILE, data)


def credit(wallet: str, amount: Decimal, *, reason: str, ref: str = "") -> dict[str, Any]:
    data = _load()
    key = wallet.lower()
    bal = _dec(data["balances"].get(key, "0"))
    bal += amount
    data["balances"][key] = str(bal)
    tx = {
        "ts": _now(),
        "type": "credit",
        "wallet": key,
        "amount": str(amount),
        "reason": reason,
        "ref": ref,
        "balance_after": str(bal),
    }
    data["txs"].append(tx)
    _save(data)
    return tx


def debit(wallet: str, amount: Decimal, *, reason: str, ref: str = "") -> dict[str, Any]:
    """Remove USDC from a wallet (creator fee out, spectator seed, etc.)."""
    data = _load()
    key = wallet.lower()
    bal = _dec(data["balances"].get(key, "0"))
    amt = _dec(amount)
    if amt <= 0:
        raise ValueError("debit amount must be positive")
    if bal < amt:
        raise ValueError(f"insufficient balance to debit: have {bal}, need {amt}")
    bal -= amt
    data["balances"][key] = str(bal)
    tx = {
        "ts": _now(),
        "type": "debit",
        "wallet": key,
        "amount": str(amt),
        "reason": reason,
        "ref": ref,
        "balance_after": str(bal),
    }
    data["txs"].append(tx)
    _save(data)
    return tx


def balance(wallet: str) -> Decimal:
    data = _load()
    return _dec(data["balances"].get(wallet.lower(), "0"))


def ensure_funded(wallet: str, min_amount: Decimal = Decimal("100")) -> None:
    """Faucet for demo agents so they can lock stakes."""
    if balance(wallet) < min_amount:
        credit(wallet, min_amount - balance(wallet), reason="demo_faucet", ref="agentic")


def open_escrow(
    match_id: str,
    *,
    agent_a_wallet: str,
    agent_b_wallet: str,
    stake_usdc: Decimal,
    chain_id: str = "arc",
) -> dict[str, Any]:
    data = _load()
    if match_id in data["escrows"]:
        return data["escrows"][match_id]
    rec = {
        "match_id": match_id,
        "chain_id": chain_id,
        "stake_usdc": str(stake_usdc),
        "agent_a_wallet": agent_a_wallet.lower(),
        "agent_b_wallet": agent_b_wallet.lower(),
        "locked_a": False,
        "locked_b": False,
        "status": "open",
        "fee_bps": DEFAULT_FEE_BPS,
        "created_at": _now(),
        "settled_at": None,
        "winner_wallet": None,
        "payout": None,
        "fee": None,
    }
    data["escrows"][match_id] = rec
    data["txs"].append({"ts": _now(), "type": "escrow_open", "ref": match_id, "stake": str(stake_usdc)})
    _save(data)
    return rec


def lock(match_id: str, wallet: str) -> dict[str, Any]:
    data = _load()
    esc = data["escrows"].get(match_id)
    if not esc:
        raise ValueError(f"unknown escrow {match_id}")
    if esc["status"] not in {"open", "partial_lock"}:
        raise ValueError(f"escrow not lockable: {esc['status']}")

    w = wallet.lower()
    stake = _dec(esc["stake_usdc"])
    bal = _dec(data["balances"].get(w, "0"))
    if bal < stake:
        raise ValueError(f"insufficient USDC for lock: have {bal}, need {stake}")

    if w == esc["agent_a_wallet"]:
        if esc["locked_a"]:
            return esc
        side = "a"
    elif w == esc["agent_b_wallet"]:
        if esc["locked_b"]:
            return esc
        side = "b"
    else:
        raise ValueError("wallet not party to this escrow")

    data["balances"][w] = str(bal - stake)
    if side == "a":
        esc["locked_a"] = True
    else:
        esc["locked_b"] = True

    if esc["locked_a"] and esc["locked_b"]:
        esc["status"] = "locked"
    else:
        esc["status"] = "partial_lock"

    data["escrows"][match_id] = esc
    data["txs"].append(
        {
            "ts": _now(),
            "type": "escrow_lock",
            "ref": match_id,
            "wallet": w,
            "amount": str(stake),
            "status": esc["status"],
        }
    )
    _save(data)
    return esc


def settle(match_id: str, winner_wallet: str, *, result: str = "win") -> dict[str, Any]:
    """Pay pot to winner minus fee. Draw → refund both."""
    data = _load()
    esc = data["escrows"].get(match_id)
    if not esc:
        raise ValueError(f"unknown escrow {match_id}")
    if esc["status"] == "settled":
        return esc
    if esc["status"] != "locked":
        raise ValueError(f"escrow not locked: {esc['status']}")

    stake = _dec(esc["stake_usdc"])
    pot = stake * 2

    if result == "draw":
        # refund both
        for w in (esc["agent_a_wallet"], esc["agent_b_wallet"]):
            data["balances"][w] = str(_dec(data["balances"].get(w, "0")) + stake)
        esc["status"] = "settled"
        esc["settled_at"] = _now()
        esc["winner_wallet"] = None
        esc["payout"] = "0"
        esc["fee"] = "0"
        esc["result"] = "draw"
        data["escrows"][match_id] = esc
        data["txs"].append({"ts": _now(), "type": "escrow_refund_draw", "ref": match_id})
        _save(data)
        return esc

    w = winner_wallet.lower()
    if w not in {esc["agent_a_wallet"], esc["agent_b_wallet"]}:
        raise ValueError("winner not a party")

    fee = (pot * Decimal(esc.get("fee_bps", DEFAULT_FEE_BPS)) / Decimal(10_000)).quantize(Decimal("0.000001"))
    payout = pot - fee
    data["balances"][w] = str(_dec(data["balances"].get(w, "0")) + payout)
    # fee sits in treasury pseudo-wallet
    treasury = "0xboardman_agentic_treasury"
    data["balances"][treasury] = str(_dec(data["balances"].get(treasury, "0")) + fee)

    esc["status"] = "settled"
    esc["settled_at"] = _now()
    esc["winner_wallet"] = w
    esc["payout"] = str(payout)
    esc["fee"] = str(fee)
    esc["result"] = "win"
    data["escrows"][match_id] = esc
    data["txs"].append(
        {
            "ts": _now(),
            "type": "escrow_settle",
            "ref": match_id,
            "winner": w,
            "payout": str(payout),
            "fee": str(fee),
        }
    )
    _save(data)
    return esc


def get_escrow(match_id: str) -> Optional[dict[str, Any]]:
    return _load()["escrows"].get(match_id)


def snapshot() -> dict[str, Any]:
    return _load()
