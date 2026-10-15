#!/usr/bin/env python3
"""Create ``channel_identities`` rows for existing profiles.

One ``telegram`` row per profile with a ``telegram_id`` and one ``web_wallet``
row per ``linked_wallet`` (CHANNELS_DESIGN §2.2). Rows that already exist are
left alone, so the script can be re-run at any time; the bot's dual-write keeps
new Telegram users covered after that.

Dry run (default): reads profiles and prints what it would create. Nothing is
written. ``--apply`` writes. Prints counts only, never ids or handles.

Prerequisite: supabase/migrations/20261016120000_channel_identities.sql applied.
Needs SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY in the environment.

Exit codes: 0 ok, 2 some rows failed (see the error count).
"""
from __future__ import annotations

import argparse
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _shim() -> None:
    """Make ``gaming.*`` resolve to this checkout (same shim the tests use)."""
    for name, target in (("gaming", ROOT), ("backend", ROOT / "src" / "backend")):
        if (ROOT / name).exists() or name in sys.modules:
            continue
        mod = types.ModuleType(name)
        mod.__path__ = [str(target)]  # type: ignore[attr-defined]
        sys.modules[name] = mod


def backfill(repo, *, apply: bool, page: int = 500) -> dict[str, int]:
    from gaming.src.channels.core.identity.repo import Identity, utcnow

    stats = {"profiles": 0, "telegram_new": 0, "wallet_new": 0, "existing": 0, "conflicts": 0, "errors": 0}
    after = None
    while True:
        rows = repo.profiles_with_telegram(after, page)
        if not rows:
            break
        for p in rows:
            after = p["id"]
            stats["profiles"] += 1
            wanted = [("telegram", str(p["telegram_id"]),
                       str(p.get("gaming_telegram_chat_id") or p["telegram_id"]))]
            wallet = (p.get("linked_wallet") or "").strip().lower()
            if wallet:
                wanted.append(("web_wallet", wallet, None))
            for channel, ext, address in wanted:
                try:
                    cur = repo.get(channel, ext)
                    if cur is not None:
                        if cur.profile_id == str(p["id"]):
                            stats["existing"] += 1
                        else:
                            stats["conflicts"] += 1
                        continue
                    stats["telegram_new" if channel == "telegram" else "wallet_new"] += 1
                    if apply:
                        repo.upsert(Identity(
                            channel=channel,
                            external_id=ext,
                            profile_id=str(p["id"]),
                            address=address,
                            verified_at=utcnow(),
                            verify_method="backfill",
                        ))
                except Exception as exc:  # keep going; report the count
                    stats["errors"] += 1
                    print(f"error: {type(exc).__name__}", file=sys.stderr)
        if len(rows) < page:
            break
    return stats


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--apply", action="store_true", help="write the rows (default: dry run)")
    ap.add_argument("--page", type=int, default=500)
    args = ap.parse_args(argv)
    _shim()
    from gaming.src.channels.core.identity.repo import get_repo

    stats = backfill(get_repo(), apply=args.apply, page=args.page)
    mode = "APPLIED" if args.apply else "DRY RUN (nothing written)"
    print(mode)
    for k, v in stats.items():
        print(f"  {k}: {v}")
    return 2 if stats["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
