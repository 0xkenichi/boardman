"""Repair AFM club transfer authority distorted by the old double-count.

Before the cost-basis model, the transfer market debited a buyer's
``budget_usdc`` by the price *and* counted the player's price again in its
squad commitment, and credited a seller its full net while also freeing the
player's catalog price from its commitment. So:

  * every free-agent buy left the buyer short by the price;
  * every agent-to-agent sale left the buyer short by the price and the
    seller long by the player's cost basis.

This script replays the transfer-window log entries settled under the old
math (no ``authority`` tag), in order, and computes the correction:

  free_agent   club.budget += price;  basis[player] = price
  sale         buyer.budget += price; basis[player] = price
               seller.budget -= seller's basis for the player

Seller basis = what the seller paid in an earlier replayed entry, else the
basis already recorded on its club, else today's catalog price (what the old
commitment used). Corrected entries are tagged ``authority_repaired`` so a
second run is a no-op.

Dry run by default — prints every change and touches nothing:

    PYTHONPATH=. .venv/bin/python scripts/repair_afm_transfer_authority.py
    PYTHONPATH=. .venv/bin/python scripts/repair_afm_transfer_authority.py --apply

``--apply`` copies both files aside (``*.bak-authority-<ts>``) first. Stop the
API and the season runner before applying. ``BOARDMAN_AGENTIC_DATA`` selects
the store (default: the repo's data/agentic).
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Optional

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

CLUBS_FILE = "afm_clubs.json"
WINDOW_FILE = "afm_transfer_window.json"
BASIS_KEY = "cost_basis_usdc"
REPAIRED = "authority_repaired"


def plan_repair(
    clubs_state: dict[str, Any],
    window_state: dict[str, Any],
    catalog_price: Callable[[str], Decimal],
) -> dict[str, Any]:
    """Pure planner: returns budget deltas, basis entries and log indexes to tag."""
    clubs = clubs_state.get("clubs", {})
    deltas: dict[str, Decimal] = {}
    basis_set: dict[str, dict[str, str]] = {}
    paid: dict[tuple[str, str], Decimal] = {}  # (club, player) -> replayed basis
    entries: list[int] = []
    skipped: list[str] = []

    def bump(aid: str, amount: Decimal) -> None:
        deltas[aid] = deltas.get(aid, Decimal("0")) + amount

    def seller_basis(aid: str, pid: str) -> Decimal:
        if (aid, pid) in paid:
            return paid[(aid, pid)]
        recorded = (clubs.get(aid, {}).get(BASIS_KEY) or {}).get(pid)
        if recorded is not None:
            return Decimal(str(recorded))
        return catalog_price(pid)

    for i, e in enumerate(window_state.get("log") or []):
        kind = e.get("kind")
        if kind not in {"free_agent", "sale"} or e.get("authority") or e.get(REPAIRED):
            continue
        pid = str(e.get("player_id") or "")
        price = Decimal(str(e.get("price_usdc") or "0"))
        buyer = str(e.get("club") if kind == "free_agent" else e.get("to") or "")
        if buyer not in clubs:
            skipped.append(f"#{i} {kind} {pid}: buyer club {buyer!r} is gone")
            continue
        if kind == "sale":
            seller = str(e.get("from") or "")
            if seller in clubs:
                bump(seller, -seller_basis(seller, pid))
            else:
                skipped.append(f"#{i} sale {pid}: seller club {seller!r} is gone")
            paid.pop((seller, pid), None)
        bump(buyer, price)
        paid[(buyer, pid)] = price
        entries.append(i)

    # basis only for players still where the replay left them
    for (aid, pid), price in paid.items():
        if pid in (clubs.get(aid, {}).get("roster") or []):
            basis_set.setdefault(aid, {})[pid] = str(price)
    return {
        "deltas": {k: v for k, v in deltas.items() if v != 0},
        "basis": basis_set,
        "entries": entries,
        "skipped": skipped,
    }


def apply_plan(clubs_state: dict[str, Any], window_state: dict[str, Any], plan: dict[str, Any]) -> None:
    clubs = clubs_state.get("clubs", {})
    for aid, delta in plan["deltas"].items():
        rec = clubs[aid]
        rec["budget_usdc"] = str(Decimal(str(rec.get("budget_usdc") or "0")) + delta)
    for aid, rows in plan["basis"].items():
        clubs[aid].setdefault(BASIS_KEY, {}).update(rows)
    log = window_state.get("log") or []
    for i in plan["entries"]:
        log[i][REPAIRED] = True


def _balance(rec: dict[str, Any], catalog: Callable[[str], Optional[dict[str, Any]]]) -> Decimal:
    from gaming.src.stack.agentic.games.football_managers.rules import WAGE_RUNWAY_MATCHDAYS

    total = Decimal("0")
    for pid in rec.get("roster") or []:
        p = catalog(pid)
        if not p:
            continue
        b = (rec.get(BASIS_KEY) or {}).get(pid)
        total += Decimal(str(b if b is not None else p.get("game_price_usdc") or "0"))
        total += Decimal(str(p.get("wage_per_matchday_usdc") or "0")) * WAGE_RUNWAY_MATCHDAYS
    return Decimal(str(rec.get("budget_usdc") or "0")) - total


def main(argv: Optional[list[str]] = None) -> int:
    import copy

    from gaming.src.stack.agentic.games.football_managers.catalog import get_player
    from gaming.src.stack.agentic.store import data_dir, save_json

    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--apply", action="store_true", help="write the repair (default: dry run)")
    args = ap.parse_args(argv)

    base = data_dir()
    clubs_path, window_path = base / CLUBS_FILE, base / WINDOW_FILE
    if not clubs_path.exists() or not window_path.exists():
        print(f"nothing to repair: {clubs_path.name} or {window_path.name} missing in {base}")
        return 0
    clubs_state = json.loads(clubs_path.read_text(encoding="utf-8"))
    window_state = json.loads(window_path.read_text(encoding="utf-8"))

    def price(pid: str) -> Decimal:
        return Decimal(str((get_player(pid) or {}).get("game_price_usdc") or "0"))

    plan = plan_repair(clubs_state, window_state, price)
    print(f"store: {base}")
    print(f"old-math transfer entries to correct: {len(plan['entries'])}")
    for s in plan["skipped"]:
        print(f"  skipped {s}")
    if not plan["entries"]:
        print("live data does not need this repair.")
        return 0

    after = copy.deepcopy(clubs_state)
    apply_plan(after, copy.deepcopy(window_state), plan)
    for aid in sorted(set(plan["deltas"]) | set(plan["basis"])):
        b0 = clubs_state["clubs"][aid]
        b1 = after["clubs"][aid]
        print(
            f"  {aid}: budget {b0.get('budget_usdc')} -> {b1.get('budget_usdc')}; "
            f"transfer balance {_balance(b0, get_player)} -> {_balance(b1, get_player)}; "
            f"basis set for {len(plan['basis'].get(aid, {}))} player(s)"
        )

    if not args.apply:
        print("dry run — re-run with --apply to write (stop the API + season runner first).")
        return 0

    ts = time.strftime("%Y%m%d-%H%M%S")
    for p in (clubs_path, window_path):
        shutil.copy2(p, p.with_name(f"{p.name}.bak-authority-{ts}"))
    apply_plan(clubs_state, window_state, plan)
    save_json(CLUBS_FILE, clubs_state)
    save_json(WINDOW_FILE, window_state)
    print(f"applied; backups *.bak-authority-{ts} beside the originals.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
