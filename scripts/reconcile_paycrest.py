#!/usr/bin/env python3
"""Run one naira-rail (Paycrest + CCTP) reconcile pass by hand, or list open state.

  PYTHONPATH=. python3 scripts/reconcile_paycrest.py --report   # read-only: open orders + bridges
  PYTHONPATH=. python3 scripts/reconcile_paycrest.py --apply    # one pass (rail must be live)

The API process runs the same pass every 30 s while the rail is live; use
this after an incident or to inspect state. Never prints KYC (none is
stored) or full bank account numbers.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def report() -> dict:
    from gaming.src.backend.services.paycrest import config, store

    open_orders = store.list_orders(statuses=tuple(s for s in store.TRANSITIONS if s not in store.TERMINAL),
                                    limit=500)
    bridges = store.list_bridges(statuses=store.BRIDGE_OPEN, limit=500)
    return {
        "config": config.status(),
        "orders": [{"id": o["id"], "dir": o["direction"], "status": o["status"], "profile": o["profile_id"][:8],
                    "usdc": o.get("amount_usdc"), "ngn": o.get("amount_ngn"), "paycrest_id": o.get("paycrest_id"),
                    "error": o.get("error")} for o in open_orders],
        "bridges": [{"id": b["id"], "kind": b["kind"], "status": b["status"], "usdc": b["amount_usdc"],
                     "attempts": b["attempts"], "error": b.get("error")} for b in bridges],
    }


def main(argv: list[str] | None = None, *, bootstrap: bool = True) -> int:
    if bootstrap:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from run_house_session import _bootstrap  # .env of this checkout + gaming/ link

        _bootstrap()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--report", action="store_true", help="read-only listing (default)")
    ap.add_argument("--apply", action="store_true", help="run one reconcile pass")
    args = ap.parse_args(argv)
    if not args.apply:
        print(json.dumps(report(), indent=2, default=str))
        return 0
    from gaming.src.backend.services.paycrest import config, reconcile

    if not config.enabled():
        print("naira rail is off (PAYCREST_ENABLED / REAL_MONEY_ENABLED); use --report", file=sys.stderr)
        return 2
    print(json.dumps(reconcile.reconcile_once(), indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
