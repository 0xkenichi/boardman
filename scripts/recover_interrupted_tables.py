#!/usr/bin/env python3
"""List and recover house tables a crash left without a result.

A kill -9 / redeploy mid-game leaves a table open, locked, playing, settling
or aborting with no result and both stakes locked. The house session and the
API recover these on their own (house.recovery: at boot and every 30s); this
is the manual tool for ops.

DRY RUN by default: prints every candidate table and what recovery would do.

  PYTHONPATH=. python3 scripts/recover_interrupted_tables.py                 # list
  PYTHONPATH=. python3 scripts/recover_interrupted_tables.py --apply         # recover all
  PYTHONPATH=. python3 scripts/recover_interrupted_tables.py --match agm_x --apply
  PYTHONPATH=. python3 scripts/recover_interrupted_tables.py --match agm_x --refund --apply

Actions:
  resume             replay the stored moves and play the game to a result,
                     then settle it through the settlement journal
  resume_settlement  finish a settlement from its journal
  abort              full refund (both stakes, spectator tickets, seeds),
                     journaled; the table ends "cancelled", reason "interrupted"
  skip               a live worker holds the lease, or the table is still in
                     its grace period — never touched

--refund turns a "resume" into a refund. Nothing ever overrides the lease rule:
a table with a fresh lease is left alone (wait for it to expire, or stop the
process that holds it). Resumes run in this process and block until the game
settles, so the script never exits with a half-played table.

Also reports settle_failed tables (a settlement that needs a human) and error
tables whose stakes are still locked — read-only here.
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
    ap.add_argument("--apply", action="store_true", help="recover (default is a dry run)")
    ap.add_argument("--match", help="only this match id")
    ap.add_argument("--refund", action="store_true", help="refund instead of resuming a resumable game")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args(argv)

    from gaming.src.stack.agentic import recovery
    from gaming.src.stack.agentic.db import journal
    from gaming.src.stack.agentic.db.tables import MATCHES

    if args.match:
        m = MATCHES.get(args.match)
        if not m:
            print(f"match {args.match} not found")
            return 1
        plans = [recovery.plan_table(m)]
    else:
        plans = recovery.scan()
    attention = [
        m for m in MATCHES.query("status IN (?, ?)", ("settle_failed", "error"))
        if not args.match or m.get("match_id") == args.match
    ]

    rows = []
    for p in plans:
        d = p.to_dict()
        if args.refund and d["action"] == "resume":
            d["action"], d["why"] = "abort", f"--refund ({d['why']})"
        d["journal"] = [s["step"] for s in journal.steps(p.match_id)]
        rows.append(d)

    if args.json and not args.apply:
        print(json.dumps({"tables": rows, "needs_ops": [_brief(m) for m in attention]}, indent=2, default=str))
        return 0

    if not rows:
        print("No interrupted tables.")
    for d in rows:
        print(
            f"{d['match_id']}  {d['status']:<12} -> {d['action']:<17} {d['why']}"
            f"\n    agents={'/'.join(d['agents'])} game={d['game_id']} moves={d['moves']} "
            f"lease={d['lease'] or '-'} journal={len(d['journal'])} steps"
        )
    for m in attention:
        if m.get("status") == "error" and m.get("match_id") in {d["match_id"] for d in rows}:
            continue
        print(f"NEEDS OPS  {m.get('match_id')}  {m.get('status')}  {m.get('settle_error') or m.get('play_error') or ''}")

    todo = [d for d in rows if d["action"] != "skip"]
    if not args.apply:
        if todo:
            print(f"\nDRY RUN — {len(todo)} table(s) would be recovered. Pass --apply.")
        return 0

    errors = 0
    results = []
    for d in todo:
        try:
            res = recovery.recover_table(
                d["match_id"], resume_inline=True, abort_inline=True, force_abort=args.refund
            )
        except Exception as exc:
            res = {**d, "error": f"{exc.__class__.__name__}: {exc}"}
        results.append(res)
        if res.get("error"):
            errors += 1
            print(f"x {d['match_id']}: {res['error']}")
        else:
            print(f"ok {d['match_id']}: {res.get('action')} -> {res.get('final_status') or res.get('why')}")
    if args.json:
        print(json.dumps(results, indent=2, default=str))
    return 1 if errors else 0


def _brief(m: dict) -> dict:
    return {
        "match_id": m.get("match_id"),
        "status": m.get("status"),
        "error": m.get("settle_error") or m.get("play_error"),
        "agents": [m.get("agent_a_id"), m.get("agent_b_id")],
    }


if __name__ == "__main__":
    sys.exit(main())
