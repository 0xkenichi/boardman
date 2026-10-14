"""
Demo dual-lock USDC ledger for agent matches.

Mirrors ClawEscrow flow without requiring mainnet keys:
  open → both lock → settle to winner (minus platform fee).

Balances are book-entry USDC in the agentic database (``ledger_balances``),
stored as integer micro-USDC with a ``CHECK (balance_micro >= 0)``. Every
function here is one atomic transaction — or joins the caller's, so a
settlement step and its journal row commit together. Amounts are Decimal at
the edges and never float.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional

from gaming.src.stack.agentic.db import transaction
from gaming.src.stack.agentic.db.docs import reading
from gaming.src.stack.agentic.db.engine import Tx
from gaming.src.stack.agentic.db.money import fmt, fmt_places, from_micro, places, to_micro

LEDGER_FILE = "ledger.json"  # legacy file, imported by scripts/migrate_json_to_db.py
DEFAULT_FEE_BPS = 700  # 7% — align with BoardmanEscrow FEE_BPS
TREASURY_WALLET = "0xboardman_agentic_treasury"


class InsufficientFunds(ValueError):
    """A debit/lock would take a balance below zero."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _dec(x: Any) -> Decimal:
    return Decimal(str(x))


# ── primitives (always inside a transaction) ─────────────────────────────────


def _balance_row(tx: Tx, wallet: str) -> tuple[int, int]:
    row = tx.one("SELECT balance_micro, scale FROM ledger_balances WHERE wallet = ?", (wallet,))
    if row is None:
        return 0, 0
    return int(row["balance_micro"] or 0), int(row["scale"] or 0)


def _balance_micro(tx: Tx, wallet: str) -> int:
    return _balance_row(tx, wallet)[0]


class _Bal(int):
    """New balance in micro, carrying its display scale."""

    scale: int

    def __new__(cls, micro: int, scale: int) -> "_Bal":
        obj = super().__new__(cls, micro)
        obj.scale = scale
        return obj

    def text(self) -> str:
        return fmt_places(int(self), self.scale)


def _apply_delta(tx: Tx, wallet: str, delta: int, *, scale: int = 0, need_msg: str = "") -> _Bal:
    """Atomically add ``delta`` micro to ``wallet``; returns the new balance.

    A negative delta is a conditional update that only succeeds while the
    balance covers it — no read-then-write window, on either backend.
    ``scale`` is the display places of the amount (see money.places).
    """
    now = _now()
    if delta >= 0:
        row = tx.one(
            "INSERT INTO ledger_balances (wallet, balance_micro, scale, updated_at) VALUES (?, ?, ?, ?) "
            "ON CONFLICT (wallet) DO UPDATE SET "
            "balance_micro = ledger_balances.balance_micro + excluded.balance_micro, "
            "scale = CASE WHEN ledger_balances.scale > excluded.scale "
            "THEN ledger_balances.scale ELSE excluded.scale END, "
            "updated_at = excluded.updated_at RETURNING balance_micro, scale",
            (wallet, delta, scale, now),
        )
        return _Bal(int(row["balance_micro"]), int(row["scale"]))
    row = tx.one(
        "UPDATE ledger_balances SET balance_micro = balance_micro + ?, "
        "scale = CASE WHEN scale > ? THEN scale ELSE ? END, updated_at = ? "
        "WHERE wallet = ? AND balance_micro >= ? RETURNING balance_micro, scale",
        (delta, scale, scale, now, wallet, -delta),
    )
    if row is None:
        micro, sc = _balance_row(tx, wallet)
        have = fmt_places(micro, sc)
        need = fmt_places(-delta, scale)
        raise InsufficientFunds((need_msg or "insufficient balance: have {have}, need {need}").format(have=have, need=need))
    return _Bal(int(row["balance_micro"]), int(row["scale"]))


def _log(tx: Tx, doc: dict[str, Any], *, amount_micro: Optional[int] = None,
         balance_after_micro: Optional[int] = None) -> dict[str, Any]:
    tx.execute(
        "INSERT INTO ledger_txs (ts, type, wallet, ref, reason, amount_micro, "
        "balance_after_micro, doc) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            doc.get("ts") or _now(),
            str(doc.get("type") or ""),
            doc.get("wallet"),
            doc.get("ref"),
            doc.get("reason"),
            amount_micro,
            balance_after_micro,
            tx.json(doc),
        ),
    )
    return doc


def _escrow_locked(tx: Tx, match_id: str) -> Optional[dict[str, Any]]:
    row = tx.one(f"SELECT doc FROM ledger_escrows WHERE match_id = ?{tx.for_update}", (match_id,))
    return tx.unjson(row["doc"]) if row else None


def _escrow_write(tx: Tx, esc: dict[str, Any]) -> None:
    tx.execute(
        "UPDATE ledger_escrows SET status = ?, result = ?, settled_at = ?, doc = ? WHERE match_id = ?",
        (esc["status"], esc.get("result"), esc.get("settled_at"), tx.json(esc), esc["match_id"]),
    )


# ── balances ─────────────────────────────────────────────────────────────────


def credit(wallet: str, amount: Decimal, *, reason: str, ref: str = "") -> dict[str, Any]:
    key = wallet.lower()
    micro = to_micro(amount)
    sc = places(amount)
    with transaction() as tx:
        bal = _apply_delta(tx, key, micro, scale=sc, need_msg="credit would overdraw: have {have}, need {need}")
        return _log(
            tx,
            {
                "ts": _now(),
                "type": "credit",
                "wallet": key,
                "amount": fmt_places(micro, sc),
                "reason": reason,
                "ref": ref,
                "balance_after": bal.text(),
            },
            amount_micro=micro,
            balance_after_micro=bal,
        )


def debit(wallet: str, amount: Decimal, *, reason: str, ref: str = "") -> dict[str, Any]:
    """Remove USDC from a wallet (creator fee out, spectator seed, etc.)."""
    key = wallet.lower()
    micro = to_micro(amount)
    if micro <= 0:
        raise ValueError("debit amount must be positive")
    sc = places(amount)
    with transaction() as tx:
        bal = _apply_delta(tx, key, -micro, scale=sc, need_msg="insufficient balance to debit: have {have}, need {need}")
        return _log(
            tx,
            {
                "ts": _now(),
                "type": "debit",
                "wallet": key,
                "amount": fmt_places(micro, sc),
                "reason": reason,
                "ref": ref,
                "balance_after": bal.text(),
            },
            amount_micro=micro,
            balance_after_micro=bal,
        )


def balance(wallet: str) -> Decimal:
    with reading() as tx:
        micro, sc = _balance_row(tx, wallet.lower())
        return Decimal(fmt_places(micro, sc))


def ensure_funded(wallet: str, min_amount: Decimal = Decimal("100")) -> None:
    """Faucet for demo agents so they can lock stakes (top-up is atomic)."""
    key = wallet.lower()
    target = to_micro(min_amount)
    with transaction() as tx:
        # Check-then-credit: two concurrent callers must not both top up.
        tx.lock_key("ledger_balances", key)
        tx.one(f"SELECT balance_micro FROM ledger_balances WHERE wallet = ?{tx.for_update}", (key,))
        have, sc = _balance_row(tx, key)
        if have < target:
            # Same Decimal the old code computed (min_amount - balance).
            top_up = Decimal(str(min_amount)) - Decimal(fmt_places(have, sc))
            credit(key, top_up, reason="demo_faucet", ref="agentic")


# ── escrow ───────────────────────────────────────────────────────────────────


def open_escrow(
    match_id: str,
    *,
    agent_a_wallet: str,
    agent_b_wallet: str,
    stake_usdc: Decimal,
    chain_id: str = "arc",
) -> dict[str, Any]:
    stake_micro = to_micro(stake_usdc)
    stake_text = fmt_places(stake_micro, places(stake_usdc))
    with transaction() as tx:
        existing = _escrow_locked(tx, match_id)
        if existing is not None:
            return existing
        rec = {
            "match_id": match_id,
            "chain_id": chain_id,
            "stake_usdc": stake_text,
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
        created = tx.rowcount(
            "INSERT INTO ledger_escrows (match_id, status, stake_micro, agent_a_wallet, "
            "agent_b_wallet, result, created_at, settled_at, doc) VALUES (?, ?, ?, ?, ?, NULL, ?, NULL, ?) "
            "ON CONFLICT (match_id) DO NOTHING",
            (match_id, "open", stake_micro, rec["agent_a_wallet"], rec["agent_b_wallet"],
             rec["created_at"], tx.json(rec)),
        )
        if not created:
            # Opened concurrently (FOR UPDATE cannot lock a missing row).
            return _escrow_locked(tx, match_id)
        _log(tx, {"ts": _now(), "type": "escrow_open", "ref": match_id, "stake": stake_text})
        return rec


def lock(match_id: str, wallet: str) -> dict[str, Any]:
    with transaction() as tx:
        esc = _escrow_locked(tx, match_id)
        if not esc:
            raise ValueError(f"unknown escrow {match_id}")
        w = wallet.lower()
        if w == esc["agent_a_wallet"]:
            side = "a"
        elif w == esc["agent_b_wallet"]:
            side = "b"
        else:
            raise ValueError("wallet not party to this escrow")
        if esc.get(f"locked_{side}"):
            return esc  # idempotent re-lock
        if esc["status"] not in {"open", "partial_lock"}:
            raise ValueError(f"escrow not lockable: {esc['status']}")

        stake = to_micro(esc["stake_usdc"])
        stake_sc = places(esc["stake_usdc"])
        _apply_delta(tx, w, -stake, scale=stake_sc, need_msg="insufficient USDC for lock: have {have}, need {need}")
        esc[f"locked_{side}"] = True
        esc["status"] = "locked" if esc["locked_a"] and esc["locked_b"] else "partial_lock"
        _escrow_write(tx, esc)
        _log(
            tx,
            {
                "ts": _now(),
                "type": "escrow_lock",
                "ref": match_id,
                "wallet": w,
                "amount": str(esc["stake_usdc"]),
                "status": esc["status"],
            },
            amount_micro=stake,
        )
        return esc


def settle(match_id: str, winner_wallet: str, *, result: str = "win") -> dict[str, Any]:
    """Pay pot to winner minus fee. Draw → refund both. Idempotent per result."""
    with transaction() as tx:
        esc = _escrow_locked(tx, match_id)
        if not esc:
            raise ValueError(f"unknown escrow {match_id}")
        if esc["status"] == "settled":
            # Idempotent no-op ONLY for the same result. A conflicting re-settle
            # (draw refund after a real win, or vice versa) must be loud, not
            # silently swallowed — that is how money went missing on agm_91dadd7c75f5.
            prev_result = str(esc.get("result") or "")
            if prev_result and prev_result != result:
                raise ValueError(
                    f"escrow {match_id} already settled as '{prev_result}'; refusing conflicting settle as '{result}'"
                )
            return esc
        if esc["status"] != "locked":
            raise ValueError(f"escrow not locked: {esc['status']}")

        stake = to_micro(esc["stake_usdc"])
        stake_sc = places(esc["stake_usdc"])
        pot = stake * 2

        if result == "draw":
            for w in (esc["agent_a_wallet"], esc["agent_b_wallet"]):
                _apply_delta(tx, w, stake, scale=stake_sc)
            esc.update(
                status="settled",
                settled_at=_now(),
                winner_wallet=None,
                payout="0",
                fee="0",
                result="draw",
            )
            _escrow_write(tx, esc)
            _log(tx, {"ts": _now(), "type": "escrow_refund_draw", "ref": match_id})
            return esc

        w = winner_wallet.lower()
        if w not in {esc["agent_a_wallet"], esc["agent_b_wallet"]}:
            raise ValueError("winner not a party")

        # Tiered platform fee — mirrors BoardmanEscrow._platformFee (V1 tiers).
        from gaming.src.stack.agentic.economy.fees import platform_fee_for_pot

        fee_dec = platform_fee_for_pot(Decimal(str(esc["stake_usdc"])) * 2, int(esc.get("fee_bps", DEFAULT_FEE_BPS)))
        fee = to_micro(fee_dec)
        payout = pot - fee
        pay_sc = max(stake_sc, places(fee_dec))
        _apply_delta(tx, w, payout, scale=pay_sc)
        # fee sits in treasury pseudo-wallet
        _apply_delta(tx, TREASURY_WALLET, fee, scale=places(fee_dec))
        esc.update(
            status="settled",
            settled_at=_now(),
            winner_wallet=w,
            payout=fmt_places(payout, pay_sc),
            fee=str(fee_dec),
            result="win",
        )
        _escrow_write(tx, esc)
        _log(
            tx,
            {
                "ts": _now(),
                "type": "escrow_settle",
                "ref": match_id,
                "winner": w,
                "payout": fmt_places(payout, pay_sc),
                "fee": str(fee_dec),
            },
            amount_micro=payout,
        )
        return esc


def get_escrow(match_id: str) -> Optional[dict[str, Any]]:
    with reading() as tx:
        row = tx.one("SELECT doc FROM ledger_escrows WHERE match_id = ?", (match_id,))
        return tx.unjson(row["doc"]) if row else None


def escrows(statuses: Optional[set[str]] = None) -> dict[str, dict[str, Any]]:
    """Escrow records keyed by match_id (optionally only some statuses)."""
    with reading() as tx:
        if statuses:
            marks = ",".join("?" for _ in statuses)
            rows = tx.all(
                f"SELECT match_id, doc FROM ledger_escrows WHERE status IN ({marks})",
                sorted(statuses),
            )
        else:
            rows = tx.all("SELECT match_id, doc FROM ledger_escrows", ())
        return {str(r["match_id"]): tx.unjson(r["doc"]) for r in rows}


def txs(*, wallet: Optional[str] = None, ref: Optional[str] = None,
        limit: Optional[int] = None) -> list[dict[str, Any]]:
    """Ledger rows oldest-first, filtered by wallet and/or ref (indexed)."""
    where, args = [], []
    if wallet is not None:
        where.append("wallet = ?")
        args.append(wallet.lower())
    if ref is not None:
        where.append("ref = ?")
        args.append(ref)
    sql = "SELECT doc FROM ledger_txs"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY id"
    if limit is not None:
        sql = f"SELECT doc FROM ({sql.replace(' ORDER BY id', ' ORDER BY id DESC')} LIMIT ?) t"
        args.append(int(limit))
    with reading() as tx:
        rows = [tx.unjson(r["doc"]) for r in tx.all(sql, args)]
    if limit is not None:
        rows.reverse()
    return rows


def balances() -> dict[str, str]:
    with reading() as tx:
        return {
            str(r["wallet"]): fmt_places(r["balance_micro"], r["scale"])
            for r in tx.all("SELECT wallet, balance_micro, scale FROM ledger_balances", ())
        }


def total_micro() -> int:
    """Sum of every balance (migration checksum, invariant checks)."""
    with reading() as tx:
        return int(tx.scalar("SELECT COALESCE(SUM(balance_micro), 0) AS s FROM ledger_balances", ()) or 0)


def snapshot() -> dict[str, Any]:
    """The legacy ``ledger.json`` shape: balances, escrows, txs (oldest first)."""
    with reading() as tx:
        bals = {
            str(r["wallet"]): fmt_places(r["balance_micro"], r["scale"])
            for r in tx.all("SELECT wallet, balance_micro, scale FROM ledger_balances", ())
        }
        escs = {
            str(r["match_id"]): tx.unjson(r["doc"])
            for r in tx.all("SELECT match_id, doc FROM ledger_escrows", ())
        }
        rows = [tx.unjson(r["doc"]) for r in tx.all("SELECT doc FROM ledger_txs ORDER BY id", ())]
    return {"balances": bals, "escrows": escs, "txs": rows}


# Back-compat for callers that read the whole ledger (read-only now).
_load = snapshot


def _save(_data: dict[str, Any]) -> None:
    raise RuntimeError(
        "the ledger is database-backed — use credit/debit/lock/settle, not a whole-file save"
    )
