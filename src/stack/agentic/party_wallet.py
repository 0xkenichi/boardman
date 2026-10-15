"""One football wallet per person: ``owner:<profile_id>`` in the agentic ledger.

The marketplace always paid a human from (and paid proceeds to)
``owner:<profile_id>``, but AFM spectator bets debited — and paid winnings
to — the bare ``<profile_id>`` key, so the same person held two balances and
could not stake marketplace proceeds (AFM deep dive, B9). Every human
football money path now uses ``football_wallet``: the wallet bridge,
marketplace buys and sales, and AFM bets, payouts and refunds.

Balances left on the legacy bare key are *migrated*, not summed: before any
debit the party's legacy balance moves into the canonical wallet in one
transaction (``football_wallet_merge`` out/in rows, ref = the party), so a
debit can never see half of it. ``scripts/merge_football_wallets.py`` does
the same for everyone at once.
"""
from __future__ import annotations

from decimal import Decimal

# Ids that are never a person: agents, clubs, pots, studios, the House.
SYSTEM_PREFIXES = ("0x", "agent_", "afm_", "creator_", "house", "platform", "treasury", "boardman")


def is_person(party_id: str) -> bool:
    p = (party_id or "").strip().lower()
    return bool(p) and ":" not in p and "|" not in p and not p.startswith(SYSTEM_PREFIXES)


def football_wallet(party_id: str) -> str:
    """The canonical ledger key of a person's football money."""
    if not is_person(party_id):
        raise ValueError(f"{party_id!r} is not a person's party id")
    return f"owner:{party_id.strip().lower()}"


def merge_legacy_wallet(party_id: str) -> Decimal:
    """Move whatever sits on the legacy bare ``<party_id>`` key into
    ``owner:<party_id>``, atomically. Returns the amount moved (0 when there
    is nothing, or the id is not a person's)."""
    from gaming.src.stack.agentic import ledger
    from gaming.src.stack.agentic.db import transaction

    if not is_person(party_id):
        return Decimal("0")
    legacy = party_id.strip().lower()
    target = football_wallet(party_id)
    with transaction():
        have = ledger.balance(legacy)
        if have <= 0:
            return Decimal("0")
        movable = have - legacy_spectator_mints(legacy)
        if movable <= 0:
            return Decimal("0")
        ledger.debit(legacy, movable, reason="football_wallet_merge_out", ref=target)
        ledger.credit(target, movable, reason="football_wallet_merge_in", ref=legacy)
    return movable


def legacy_spectator_mints(legacy_key: str) -> Decimal:
    """Chess spectator credits that landed on a bare id before tickets were
    funded: settlement credited them without ever debiting a stake, so they
    are minted money. They stay on the legacy key for ops to review and are
    never folded into a spendable wallet (see RUNBOOK §3.5)."""
    from gaming.src.stack.agentic import ledger

    total = Decimal("0")
    for t in ledger.txs(wallet=legacy_key):
        reason = str(t.get("reason") or "")
        if t.get("type") == "credit" and (reason.startswith("spectator_") or reason == "draw_win"):
            total += Decimal(str(t.get("amount") or "0"))
    return total
