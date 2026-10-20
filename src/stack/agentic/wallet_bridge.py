"""Wallet bridge: a party's play balance <-> their agentic-ledger wallet.

Naira top-ups (Paystack, the Telegram bot) land on the user's *play balance*
— on-chain USDC at their Circle play address plus the play_adjust overlay;
the number the bot and the website show and spectator bets spend. The
football marketplace pays from the agentic ledger (``owner:<party>``). The
bridge moves USDC between the two, for the caller only:

  deposit   play balance -> owner:<party>
  withdraw  owner:<party> -> play balance

The two sides live in different stores (play_adjust.json vs the agentic
database), so no single transaction spans them. Instead every transfer is a
row in ``wallet_bridge_transfers`` — an outbox written before the first side
moves — and the second side only moves after the first one is recorded:

  deposit:  pending   row inserted, nothing moved
            debited   play balance debited (keyed, exactly once)
            completed ledger credited — in the SAME transaction as the status
  withdraw: debited   row inserted in the SAME transaction as the ledger debit
            completed play balance credited (keyed, exactly once)
  failed    nothing moved (e.g. not enough money)
  reversing / reversed   ops chose to undo a stuck transfer; the side that
            moved has been given back

A crash leaves a row in pending / debited / reversing. ``reconcile`` (run
by the house maintenance tick and by ``scripts/reconcile_wallet_bridge.py``)
finishes it — or, for a deposit that never debited, marks it failed. Each
play-balance move carries its own key (``bridge:<transfer>:debit|credit|
reverse``) recorded with the balance change, so a retry always knows whether
it already happened. Amounts are exact micro-USDC; neither side can go
negative (the ledger refuses at the database, the play balance under its
file lock).
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

from gaming.src.stack.agentic import ledger
from gaming.src.stack.agentic.db import transaction
from gaming.src.stack.agentic.db.docs import reading
from gaming.src.stack.agentic.db.engine import now_ms
from gaming.src.stack.agentic.db.money import fmt, to_micro

logger = logging.getLogger(__name__)

DEPOSIT = "deposit"
WITHDRAW = "withdraw"
DIRECTIONS = (DEPOSIT, WITHDRAW)
OPEN_STATUSES = ("pending", "debited", "reversing")
TERMINAL_STATUSES = ("completed", "failed", "reversed")
MAX_TRANSFER_MICRO = to_micro("10000")
# Agents, studios, pots and the House are never a bridge party.
_SYSTEM_PARTY_PREFIXES = ("0x", "agent_", "afm_", "creator_", "house", "platform", "treasury", "boardman")
DEFAULT_STALE_SEC = 300


class BridgeError(ValueError):
    """Bad request (HTTP 400/422)."""


class BridgeConflict(BridgeError):
    """Same idempotency key, different transfer — or still in flight (409)."""


class InsufficientBalance(BridgeError):
    """Not enough money on the side being debited; nothing moved (402)."""


class BalanceUnavailable(RuntimeError):
    """The on-chain play balance could not be read; nothing moved (503)."""


def bridge_chain() -> str:
    """The only chain the wallet bridge touches: the arena's practice chain."""
    from gaming.src.backend.services.realms import arena_chain, assert_practice

    return assert_practice(arena_chain(), path="wallet bridge")


async def read_play_chain_usdc(party_id: str) -> Decimal:
    """On-chain USDC at the party's Circle play address. Never guesses $0 on
    an RPC error (that would let a deposit check pass on stale numbers)."""
    from gaming.src.backend.services.clawstation_circle import get_usdc_balance_strict

    # The football ledger is arena money: only the PRACTICE play balance may
    # ever be read for (or debited by) the bridge. A real-money balance can't.
    bal, err = await get_usdc_balance_strict(party_id, chain_id=bridge_chain())
    if err or bal is None:
        raise BalanceUnavailable(f"could not read the play balance: {err or 'no balance'}")
    return Decimal(str(bal))


def stale_after_sec() -> int:
    try:
        return max(1, int(os.getenv("BOARDMAN_BRIDGE_STALE_SEC") or DEFAULT_STALE_SEC))
    except ValueError:
        return DEFAULT_STALE_SEC


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def party_ledger_wallet(party_id: str) -> str:
    """A person's one football wallet (``owner:<id>``: marketplace, AFM bets,
    stack-API chess tickets), with any legacy bare-id balance folded in."""
    from gaming.src.stack.agentic.games.football_managers.agent_market import _owner_party_wallet
    from gaming.src.stack.agentic.party_wallet import football_wallet, is_person, merge_legacy_wallet

    pid = (party_id or "").strip()
    if not is_person(pid) or pid.lower().startswith(_SYSTEM_PARTY_PREFIXES):
        raise BridgeError("only a signed-in player's own wallet can be bridged")
    wallet = football_wallet(pid)
    if _owner_party_wallet(pid).lower() != wallet:  # a registered agent id
        raise BridgeError("only a signed-in player's own wallet can be bridged")
    merge_legacy_wallet(pid)
    return wallet


def parse_amount(raw: Any) -> int:
    """Exact micro-USDC: positive, at most 6 decimals, at most $10,000."""
    try:
        d = Decimal(str(raw).strip())
    except (InvalidOperation, ValueError):
        raise BridgeError(f"not a USDC amount: {raw!r}") from None
    if not d.is_finite() or d <= 0:
        raise BridgeError("amount must be positive")
    if d != d.quantize(Decimal("0.000001")):
        raise BridgeError("amount has more than 6 decimals")
    micro = to_micro(d)
    if micro > MAX_TRANSFER_MICRO:
        raise BridgeError("amount is above the $10,000 per-transfer limit")
    return micro


def transfer_key(party_id: str, idempotency_key: str) -> str:
    k = (idempotency_key or "").strip()
    if not (8 <= len(k) <= 120) or any(c.isspace() for c in k):
        raise BridgeError("idempotency_key must be 8-120 characters, no spaces")
    return f"{party_id}|{k}"


def _play_key(tkey: str, leg: str) -> str:
    return f"bridge:{tkey}:{leg}"


# ── rows ─────────────────────────────────────────────────────────────────────


def _row(tx: Any, tkey: str, *, lock: bool = False) -> Optional[dict[str, Any]]:
    return tx.one(
        "SELECT * FROM wallet_bridge_transfers WHERE transfer_key = ?" + (tx.for_update if lock else ""),
        (tkey,),
    )


def get(tkey: str) -> Optional[dict[str, Any]]:
    with reading() as tx:
        return _row(tx, tkey)


def _advance(tx: Any, tkey: str, frm: tuple[str, ...], to: str, *, error: Optional[str] = None) -> bool:
    marks = ",".join("?" for _ in frm)
    return tx.rowcount(
        f"UPDATE wallet_bridge_transfers SET status = ?, error = COALESCE(?, error), "
        f"updated_at = ?, updated_at_ms = ? WHERE transfer_key = ? AND status IN ({marks})",
        (to, error, _now(), now_ms(), tkey, *frm),
    ) == 1


def advance(tkey: str, frm: tuple[str, ...], to: str, *, error: Optional[str] = None) -> bool:
    with transaction() as tx:
        return _advance(tx, tkey, frm, to, error=error)


def _insert(tx: Any, tkey: str, party: str, direction: str, micro: int, wallet: str, status: str) -> bool:
    stamp = _now()
    return tx.rowcount(
        "INSERT INTO wallet_bridge_transfers (transfer_key, party_id, direction, amount_micro, "
        "ledger_wallet, status, attempts, error, created_at, updated_at, updated_at_ms) "
        "VALUES (?, ?, ?, ?, ?, ?, 1, NULL, ?, ?, ?) ON CONFLICT (transfer_key) DO NOTHING",
        (tkey, party, direction, micro, wallet, status, stamp, stamp, now_ms()),
    ) == 1


def _same(row: dict[str, Any], party: str, direction: str, micro: int) -> bool:
    return (
        str(row["party_id"]) == party
        and str(row["direction"]) == direction
        and int(row["amount_micro"]) == micro
    )


def view(row: Optional[dict[str, Any]]) -> dict[str, Any]:
    if not row:
        return {}
    return {
        "transfer_key": row["transfer_key"],
        "party_id": row["party_id"],
        "direction": row["direction"],
        "amount_usdc": fmt(row["amount_micro"]),
        "ledger_wallet": row["ledger_wallet"],
        "status": row["status"],
        "error": row.get("error"),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


# ── the two sides ────────────────────────────────────────────────────────────


def _play_apply(party: str, micro: int, key: str, *, chain_usdc: Optional[Decimal] = None) -> bool:
    from gaming.src.backend.services.play_adjust import apply_once

    return apply_once(party, Decimal(fmt(micro)), key=key, chain_usdc=chain_usdc)


def _play_applied(party: str, key: str) -> bool:
    from gaming.src.backend.services.play_adjust import was_applied

    return was_applied(party, key)


def _complete_deposit(row: dict[str, Any]) -> bool:
    """Ledger credit + status, one transaction (never one without the other)."""
    tkey = row["transfer_key"]
    with transaction() as tx:
        if not _advance(tx, tkey, ("debited",), "completed"):
            return False
        ledger.credit(row["ledger_wallet"], Decimal(fmt(row["amount_micro"])), reason="bridge_deposit", ref=tkey)
    return True


def _drive(row: dict[str, Any], *, reverse: bool = False) -> dict[str, Any]:
    """Move a transfer forward from wherever a crash (or a retry) left it.

    Every leg is idempotent: the play-balance legs by key, the ledger legs by
    the conditional status change in their own transaction.
    """
    tkey = row["transfer_key"]
    party = str(row["party_id"])
    micro = int(row["amount_micro"])
    for _ in range(4):  # at most pending -> debited -> reversing -> reversed
        row = get(tkey) or row
        st = row["status"]
        if st in TERMINAL_STATUSES:
            return row
        if row["direction"] == DEPOSIT:
            if st == "pending":
                if _play_applied(party, _play_key(tkey, "debit")):
                    advance(tkey, ("pending",), "debited")
                else:
                    advance(tkey, ("pending",), "failed", error="abandoned before the play balance was debited")
                continue
            if st == "debited":
                if reverse:
                    advance(tkey, ("debited",), "reversing", error="reversed by ops")
                else:
                    _complete_deposit(row)
                continue
            if st == "reversing":
                _play_apply(party, micro, _play_key(tkey, "reverse"))
                advance(tkey, ("reversing",), "reversed")
                continue
        else:
            if st == "debited":
                if reverse:
                    advance(tkey, ("debited",), "reversing", error="reversed by ops")
                else:
                    _play_apply(party, micro, _play_key(tkey, "credit"))
                    advance(tkey, ("debited",), "completed")
                continue
            if st == "reversing":
                if _play_applied(party, _play_key(tkey, "credit")):
                    # The play credit landed after all: the transfer is done.
                    advance(tkey, ("reversing",), "completed")
                    continue
                with transaction() as tx:
                    if _advance(tx, tkey, ("reversing",), "reversed"):
                        ledger.credit(row["ledger_wallet"], Decimal(fmt(micro)), reason="bridge_withdraw_reversed", ref=tkey)
                continue
            if st == "pending":  # withdraw rows are born debited; never here
                advance(tkey, ("pending",), "failed", error="invalid withdraw state")
                continue
    return get(tkey) or row


def _existing(row: dict[str, Any], party: str, direction: str, micro: int) -> dict[str, Any]:
    """A retry with a key we have seen: same transfer -> same outcome."""
    if not _same(row, party, direction, micro):
        raise BridgeConflict("idempotency_key was already used for a different transfer")
    if row["status"] in OPEN_STATUSES:
        age = (now_ms() - int(row["updated_at_ms"] or 0)) / 1000
        if row["status"] == "pending" and age < stale_after_sec():
            raise BridgeConflict("this transfer is still in progress — retry in a moment")
        row = _drive(row)
    return row


def _result(row: dict[str, Any]) -> dict[str, Any]:
    out = view(row)
    if row["status"] == "failed" and str(row.get("error") or "").startswith("insufficient"):
        raise InsufficientBalance(str(row["error"]))
    out["ledger_balance_usdc"] = str(ledger.balance(row["ledger_wallet"]))
    return out


# ── public API ───────────────────────────────────────────────────────────────


def deposit(party_id: str, amount: Any, idempotency_key: str, *, chain_usdc: Decimal) -> dict[str, Any]:
    """Play balance -> ``owner:<party>``. ``chain_usdc`` is the party's
    on-chain play-address balance, read by the caller just before."""
    party = (party_id or "").strip()
    if not party:
        raise BridgeError("party is required")
    bridge_chain()  # practice money only (realms.py); raises if misconfigured
    if ledger._money_chain_is_mainnet():
        raise BridgeError("the football wallet is book-entry and testnet-only; bind a Circle wallet on mainnet")
    micro = parse_amount(amount)
    wallet = party_ledger_wallet(party)
    tkey = transfer_key(party, idempotency_key)

    with transaction() as tx:
        row = _row(tx, tkey, lock=True)
        if row is None and not _insert(tx, tkey, party, DEPOSIT, micro, wallet, "pending"):
            row = _row(tx, tkey, lock=True)
    if row is not None:
        return _result(_existing(row, party, DEPOSIT, micro))

    # 1) Debit the play balance (keyed: exactly once), refusing to go negative.
    from gaming.src.backend.services.play_adjust import InsufficientPlayBalance

    try:
        _play_apply(party, -micro, _play_key(tkey, "debit"), chain_usdc=chain_usdc)
    except InsufficientPlayBalance as exc:
        advance(tkey, ("pending",), "failed", error=f"insufficient play balance: {exc}")
        raise InsufficientBalance(str(exc)) from None
    _after_leg("deposit:debited")
    if not advance(tkey, ("pending",), "debited"):
        # The reconciler gave up on this row in between (it looked abandoned):
        # give the debit back rather than leave it orphaned.
        _play_apply(party, micro, _play_key(tkey, "reverse"))
        advance(tkey, ("failed",), "reversed")
        raise BridgeConflict("transfer timed out and was rolled back — try again")
    # 2) Credit the ledger and close the row in one transaction.
    _after_leg("deposit:recorded")
    _complete_deposit(get(tkey) or {})
    return _result(get(tkey) or {})


def withdraw(party_id: str, amount: Any, idempotency_key: str) -> dict[str, Any]:
    """``owner:<party>`` -> play balance."""
    party = (party_id or "").strip()
    if not party:
        raise BridgeError("party is required")
    # The single realm gate (realms.py): the football wallet is book-entry
    # practice money and only ever pays out to the PRACTICE play overlay,
    # which never counts toward a real-money balance, withdraw link or
    # cash-out. Raises if the arena chain is misconfigured as real money.
    bridge_chain()
    micro = parse_amount(amount)
    wallet = party_ledger_wallet(party)
    tkey = transfer_key(party, idempotency_key)

    # 1) Ledger debit and the outbox row: one transaction, all or nothing.
    try:
        with transaction() as tx:
            row = _row(tx, tkey, lock=True)
            if row is None:
                if _insert(tx, tkey, party, WITHDRAW, micro, wallet, "debited"):
                    ledger.debit(wallet, Decimal(fmt(micro)), reason="bridge_withdraw", ref=tkey)
                else:
                    row = _row(tx, tkey, lock=True)
    except ledger.InsufficientFunds as exc:
        raise InsufficientBalance(f"football wallet: {exc}") from None
    if row is not None:
        return _result(_existing(row, party, WITHDRAW, micro))
    _after_leg("withdraw:debited")
    # 2) Credit the play balance (keyed), then close the row.
    _play_apply(party, micro, _play_key(tkey, "credit"))
    _after_leg("withdraw:credited")
    advance(tkey, ("debited",), "completed")
    return _result(get(tkey) or {})


def pending(*, older_than_sec: float = 0, limit: int = 500) -> list[dict[str, Any]]:
    """Transfers a crash (or a live request) left between the two sides."""
    cutoff = now_ms() - int(older_than_sec * 1000)
    marks = ",".join("?" for _ in OPEN_STATUSES)
    with reading() as tx:
        rows = tx.all(
            f"SELECT * FROM wallet_bridge_transfers WHERE status IN ({marks}) AND updated_at_ms <= ? "
            "ORDER BY updated_at_ms LIMIT ?",
            (*OPEN_STATUSES, cutoff, int(limit)),
        )
    return rows


def reconcile(
    *,
    older_than_sec: Optional[float] = None,
    dry_run: bool = False,
    reverse_keys: Optional[set[str]] = None,
) -> list[dict[str, Any]]:
    """Finish (or, for keys in ``reverse_keys``, reverse) every stale open
    transfer. Safe to run any time, from any process, as often as you like."""
    age = stale_after_sec() if older_than_sec is None else older_than_sec
    out: list[dict[str, Any]] = []
    for row in pending(older_than_sec=age):
        before = row["status"]
        if dry_run:
            out.append({**view(row), "action": "would_reverse" if row["transfer_key"] in (reverse_keys or set()) else "would_finish"})
            continue
        try:
            with transaction() as tx:
                tx.execute(
                    "UPDATE wallet_bridge_transfers SET attempts = attempts + 1 WHERE transfer_key = ?",
                    (row["transfer_key"],),
                )
            after = _drive(row, reverse=row["transfer_key"] in (reverse_keys or set()))
            out.append({**view(after), "from_status": before})
            logger.warning("[bridge] reconciled %s: %s -> %s", row["transfer_key"], before, after["status"])
        except Exception as exc:  # leave it open; the next run retries
            logger.exception("[bridge] reconcile %s failed", row["transfer_key"])
            out.append({**view(row), "from_status": before, "error": str(exc)})
    return out


def history(party_id: str, limit: int = 20) -> list[dict[str, Any]]:
    with reading() as tx:
        rows = tx.all(
            "SELECT * FROM wallet_bridge_transfers WHERE party_id = ? ORDER BY created_at DESC LIMIT ?",
            (party_id, int(limit)),
        )
    return [view(r) for r in rows]


# Crash-test hook (tests only): called between legs.
_LEG_HOOK = None


def _after_leg(name: str) -> None:
    hook = _LEG_HOOK
    if hook is not None:
        hook(name)
