"""Money audit 2026-10 — the wallet-bridge deposit joins the play-spend lock.

The deposit's overlay debit is checked against a chain read taken before
it; a withdrawal or cash-out of the same play wallet in between could
spend the same USDC. With the shared per-profile lock held elsewhere the
deposit is refused (409) and nothing moves.
"""
from __future__ import annotations

from decimal import Decimal

from tests.test_money_wallet_bridge import BASE, _as, _env, _football, _play, chain, client  # noqa: F401


def test_bridge_deposit_waits_for_another_spend_of_the_same_wallet(client, chain):  # noqa: F811
    from gaming.src.backend.services.play_adjust import spend_lock

    with spend_lock("p1"):
        r = client.post(f"{BASE}/deposit", headers=_as("p1"), json={"amount": "5", "idempotency_key": "dep-lock-1"})
    assert r.status_code == 409, r.text
    assert _football("p1") == Decimal("0") and _play("p1", chain) == Decimal("20")
    r = client.post(f"{BASE}/deposit", headers=_as("p1"), json={"amount": "5", "idempotency_key": "dep-lock-1"})
    assert r.status_code == 200, r.text
    assert _football("p1") == Decimal("5") and _play("p1", chain) == Decimal("15")
