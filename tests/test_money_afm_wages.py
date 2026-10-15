"""AFM wages have a counterparty (deep dive B8): what a club pays lands in
the house wages wallet, in the same transaction, so the book never loses
money between club wallets and nowhere."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal


def test_matchday_wages_are_credited_not_destroyed(tmp_path, monkeypatch):
    monkeypatch.setenv("BOARDMAN_AGENTIC_DATA", str(tmp_path))
    import gaming.src.stack.agentic.ledger as L
    from gaming.src.stack.agentic.games.football_managers import season as S
    from gaming.src.stack.agentic.games.football_managers.club_store import seed_demo_clubs
    from gaming.src.stack.agentic.registry import get_registry

    get_registry().ensure_demo_agents()
    seed_demo_clubs()
    S.open_season(
        agent_ids=["agent_bluelock_demo", "agent_aoashi_demo"],
        start_at=datetime.now(timezone.utc) - timedelta(hours=7),
    )
    assert S.tick()["resolved"] == [1]
    wage_rows = [t for t in L.snapshot()["txs"] if str(t.get("reason") or "").startswith("afm_wages_s")]
    paid = sum((Decimal(t["amount"]) for t in wage_rows if t["type"] == "debit"), Decimal("0"))
    received = sum((Decimal(t["amount"]) for t in wage_rows if t["type"] == "credit"), Decimal("0"))
    assert paid > 0, "scenario needs clubs that pay wages"
    assert received == paid
    assert L.balance(S.AFM_WAGES_WALLET) == paid
