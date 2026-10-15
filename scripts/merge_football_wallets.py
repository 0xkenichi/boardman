#!/usr/bin/env python3
"""Fold every person's legacy bare-id ledger balance into owner:<id>.

AFM bets used to debit and pay the bare ``<profile_id>`` ledger key while the
marketplace used ``owner:<profile_id>``. Both now use owner:<id>, and each
person's legacy balance is merged lazily on their next bet, buy or bridge
transfer. This does it for everyone at once (run after deploy).

Chess spectator credits that landed on a bare id before tickets were funded
were minted (nothing was ever debited); that part is NOT merged and stays on
the bare key — listed here as "held back" for ops review.

DRY RUN by default.

  PYTHONPATH=. python3 scripts/merge_football_wallets.py           # list
  PYTHONPATH=. python3 scripts/merge_football_wallets.py --apply
"""
from __future__ import annotations

import argparse
import sys
from decimal import Decimal
from pathlib import Path


def main(argv: list[str] | None = None, *, bootstrap: bool = True) -> int:
    if bootstrap:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from run_house_session import _bootstrap  # .env of this checkout + gaming/ link

        _bootstrap()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="merge (default is a dry run)")
    args = ap.parse_args(argv)

    from gaming.src.stack.agentic import ledger
    from gaming.src.stack.agentic.party_wallet import is_person, legacy_spectator_mints, merge_legacy_wallet

    rows = []
    for wallet, bal in sorted(ledger.balances().items()):
        if not is_person(wallet) or Decimal(bal) <= 0:
            continue
        held = min(Decimal(bal), legacy_spectator_mints(wallet))
        rows.append((wallet, Decimal(bal), held))
    if not rows:
        print("no legacy balances")
        return 0
    for wallet, bal, held in rows:
        moved = merge_legacy_wallet(wallet) if args.apply else bal - held
        print(f"{wallet}: balance {bal}  merge {moved} -> owner:{wallet}  held back {held}")
    if not args.apply:
        print("\nDry run. Re-run with --apply.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
