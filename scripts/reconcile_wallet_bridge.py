#!/usr/bin/env python3
"""List and finish wallet-bridge transfers a crash left half-done.

The bridge moves USDC between a player's play balance (play_adjust overlay
on top of their on-chain play address) and their football ledger wallet
(owner:<party>). A crash between the two sides leaves the transfer's row in
``pending`` / ``debited`` / ``reversing``. The house maintenance tick runs
the reconciler every few minutes on rows older than BOARDMAN_BRIDGE_STALE_SEC
(default 300s); this is the manual tool for ops.

DRY RUN by default: prints every open transfer and what would happen.

  PYTHONPATH=. python3 scripts/reconcile_wallet_bridge.py                     # list
  PYTHONPATH=. python3 scripts/reconcile_wallet_bridge.py --apply             # finish all stale
  PYTHONPATH=. python3 scripts/reconcile_wallet_bridge.py --all --apply       # ignore the age gate
  PYTHONPATH=. python3 scripts/reconcile_wallet_bridge.py --reverse 'p1|key' --apply
  PYTHONPATH=. python3 scripts/reconcile_wallet_bridge.py --party <profile_id>

What "finish" does, per state:
  deposit  pending    play debit landed? -> credit the ledger; else -> failed
  deposit  debited    credit the ledger (same transaction as "completed")
  withdraw debited    credit the play balance (keyed, exactly once)
  *        reversing  give the moved side back -> reversed

--reverse undoes a stuck transfer instead (the side that moved goes back).
Every step is idempotent: running this twice, or alongside the tick, is safe.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main(argv: list[str] | None = None, *, bootstrap: bool = True) -> int:
    if bootstrap:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from run_house_session import _bootstrap  # .env of this checkout + gaming/ link

        _bootstrap()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="act (default is a dry run)")
    ap.add_argument("--all", action="store_true", help="include rows younger than the stale threshold")
    ap.add_argument("--reverse", action="append", default=[], help="transfer_key to reverse instead of finish")
    ap.add_argument("--party", help="only show this party's transfers (history, read-only)")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args(argv)

    from gaming.src.stack.agentic import wallet_bridge as wb

    if args.party:
        rows = wb.history(args.party, limit=100)
        print(json.dumps(rows, indent=2) if args.json else "\n".join(
            f"{r['created_at']}  {r['direction']:8} {r['amount_usdc']:>12}  {r['status']:10} {r['transfer_key']}  {r.get('error') or ''}"
            for r in rows
        ) or "no transfers")
        return 0

    age = 0 if args.all else None
    out = wb.reconcile(older_than_sec=age, dry_run=not args.apply, reverse_keys=set(args.reverse))
    if args.json:
        print(json.dumps(out, indent=2, default=str))
    elif not out:
        print("no open transfers" + ("" if args.all else f" older than {wb.stale_after_sec()}s (use --all)"))
    else:
        for r in out:
            what = r.get("action") or f"{r.get('from_status')} -> {r['status']}"
            print(f"{r['transfer_key']}  {r['direction']:8} {r['amount_usdc']:>12}  {what}  {r.get('error') or ''}")
        if not args.apply:
            print("\nDry run. Re-run with --apply.")
    return 1 if any(r.get("error") and args.apply for r in out) else 0


if __name__ == "__main__":
    raise SystemExit(main())
