#!/usr/bin/env python3
"""Import the agentic JSON store into the database (SQLite or Supabase Postgres).

Reads (never writes) these files from the agentic data dir:
  ledger.json, matches.json, matches_archive.json, spectator_books.json,
  spectator_books_archive.json, agent_lp_pools.json

Dry run (default): imports into a throwaway SQLite database and prints counts,
problems and the balance checksum (sum and number of balances before == after).
Nothing outside a temp dir is written.

--apply: imports into the configured database in ONE transaction, verifies the
checksum, then writes the ``legacy_import`` marker that lets the app start
(until then the app refuses to run next to un-imported JSON). Refuses to
import into a database that already holds agentic data.

Target database: BOARDMAN_DATABASE_URL, else DATABASE_URL (postgres:// or
sqlite:///path), else <data dir>/boardman.sqlite3.

Corrupt files are reported. A truncated file has every complete record before
the damage salvaged, and is reported as "partial". Either one makes the exit
code 2 unless you pass --accept-problems after reviewing the report.

Cutover:
  1. stop the API and the house session (no writers)
  2. python scripts/migrate_json_to_db.py                  # dry run, read the report
  3. python scripts/migrate_json_to_db.py --apply
  4. start the services (BOARDMAN_STORAGE=db, the default)
Rollback: redeploy the previous release; the JSON files were never touched.

Exit codes: 0 ok, 2 problems or checksum mismatch, 3 refused (target not empty).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _alias_packages() -> None:
    """Make ``gaming.*`` resolve to this checkout (same shim the tests use)."""
    import types

    for name, target in (("gaming", ROOT), ("backend", ROOT / "src" / "backend")):
        if (ROOT / name).exists() or name in sys.modules:
            continue
        mod = types.ModuleType(name)
        mod.__path__ = [str(target)]  # type: ignore[attr-defined]
        sys.modules[name] = mod


def run(data_dir: Path, *, apply: bool, accept_problems: bool = False) -> tuple[int, dict]:
    _alias_packages()
    os.environ["BOARDMAN_AGENTIC_DATA"] = str(data_dir)
    # The app's "never migrated" guard must not block the migration itself.
    os.environ["BOARDMAN_STORAGE_ALLOW_UNMIGRATED"] = "1"
    os.environ["BOARDMAN_STORAGE"] = "db"

    from gaming.src.stack.agentic.db import engine
    from gaming.src.stack.agentic.db.legacy import ImportReport, db_is_empty, import_into, mark_imported, read_legacy

    report = ImportReport()
    data = read_legacy(data_dir, report)

    if not apply:
        scratch = Path(tempfile.mkdtemp(prefix="boardman-migrate-dry-"))
        db = engine.Database("dry-run", sqlite_path=scratch / "dry.sqlite3", check_migrated=False)
        target = f"dry run (scratch SQLite in {scratch})"
        with db.transaction() as tx:
            import_into(tx, data, report)
        db.close_all()
    else:
        db = engine.get_db()
        target = db.key if not db.is_postgres else "postgres (DATABASE_URL)"
        with db.transaction() as tx:
            if not db_is_empty(tx):
                return 3, {"target": target, "refused": "target database already holds agentic data", **report.to_dict()}
            import_into(tx, data, report)
            if not report.checksum_ok:
                raise SystemExit(
                    f"checksum mismatch: json={report.balance_sum_json} db={report.balance_sum_db} — rolled back"
                )
            if report.problems and not accept_problems:
                # Roll back: problems need a human decision first.
                raise _Abort()
            mark_imported(tx, report)
        # Rebuild the house log from the imported settled matches.
        from gaming.src.stack.agentic import tx_log

        report.counts["house_log"] = tx_log.sync_from_matches()["games_total"]

    out = {"target": target, "applied": apply, **report.to_dict()}
    code = 0
    if not report.checksum_ok or (report.problems and not accept_problems):
        code = 2
    return code, out


class _Abort(Exception):
    pass


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data-dir", default=os.getenv("BOARDMAN_AGENTIC_DATA") or str(ROOT / "data" / "agentic"))
    ap.add_argument("--apply", action="store_true", help="write to the configured database (default: dry run)")
    ap.add_argument("--accept-problems", action="store_true", help="import even with corrupt/partial files reported")
    ap.add_argument("--json", action="store_true", help="print the report as JSON")
    args = ap.parse_args(argv)
    data_dir = Path(args.data_dir).resolve()
    try:
        code, out = run(data_dir, apply=args.apply, accept_problems=args.accept_problems)
    except _Abort:
        print("problems found — nothing imported (re-run the dry run, then --accept-problems)", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(out, indent=2, default=str))
    else:
        print(f"target:   {out['target']}")
        for name, info in out["files"].items():
            extra = f" salvaged={info['salvaged_records']}" if "salvaged_records" in info else ""
            print(f"  {name:32s} {info['status']:8s} {info.get('bytes', '')}{extra}")
        print("counts:   " + ", ".join(f"{k}={v}" for k, v in out["counts"].items()))
        b = out["balances"]
        print(
            f"balances: json sum={b['sum_json']} ({b['wallets_json']} wallets)  "
            f"db sum={b['sum_db']} ({b['wallets_db']} wallets)  checksum_ok={b['checksum_ok']}"
        )
        for p in out["problems"]:
            print(f"  PROBLEM: {p}")
        if out.get("refused"):
            print(f"REFUSED: {out['refused']}")
        if not args.apply:
            print("dry run — nothing written. Re-run with --apply to import.")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
