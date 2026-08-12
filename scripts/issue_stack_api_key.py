#!/usr/bin/env python3
"""
Issue a Boardman Stack API key for a third-party builder.

Keys are generated on YOUR machine. You hand the secret to the builder once.
They must send it on every Stack request:

  X-Rematch-Key: <key>
  # or X-Boardman-Key / Authorization: Bearer …

Usage:
  python3 scripts/issue_stack_api_key.py --builder acme_lab
  python3 scripts/issue_stack_api_key.py --builder acme_lab --append .stack_keys
  python3 scripts/issue_stack_api_key.py --master

Then put keys on the API host:

  # master (you)
  REMATCH_API_KEY=sk_bm_...

  # builders (many)
  BOARDMAN_STACK_API_KEYS=sk_bm_acme_...:acme_lab,sk_bm_bob_...:bob_forge

  # or file (chmod 600)
  BOARDMAN_STACK_API_KEYS_FILE=/secure/boardman_stack_keys.txt
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))
    gaming = root / "gaming"
    if not (gaming / "src").exists():
        try:
            gaming.mkdir(exist_ok=True)
            (gaming / "src").symlink_to(Path("..") / "src")
        except OSError:
            pass

    from gaming.src.backend.rematch_auth import generate_stack_api_key

    ap = argparse.ArgumentParser(description="Issue Boardman Stack API key")
    ap.add_argument("--builder", default="builder", help="Builder id label (e.g. acme_lab)")
    ap.add_argument("--master", action="store_true", help="Label as platform master key")
    ap.add_argument(
        "--append",
        metavar="FILE",
        help="Append key:builder line to this file (for BOARDMAN_STACK_API_KEYS_FILE)",
    )
    args = ap.parse_args()

    builder = "platform" if args.master else args.builder.strip() or "builder"
    key = generate_stack_api_key(builder_id=builder if builder != "platform" else "")

    print()
    print("=== Boardman Stack API key (show once) ===")
    print(f"  builder_id : {builder}")
    print(f"  secret     : {key}")
    print()
    print("Give the builder:")
    print(f'  export BOARDMAN_STACK_KEY="{key}"')
    print("  curl -H \"X-Rematch-Key: $BOARDMAN_STACK_KEY\" \\")
    print("       https://YOUR_API_HOST/api/stack/agentic/health")
    print()
    print("On YOUR API server, add one of:")
    if builder == "platform":
        print(f"  REMATCH_API_KEY={key}")
    else:
        print(f"  # append to BOARDMAN_STACK_API_KEYS")
        print(f"  {key}:{builder}")
        print(f"  # or line in keys file:")
        print(f"  {key}:{builder}")
    print()

    if args.append:
        path = Path(args.append)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(f"{key}:{builder}\n")
        try:
            path.chmod(0o600)
        except OSError:
            pass
        print(f"Appended to {path} (chmod 600 if possible)")
        print(f"Set: BOARDMAN_STACK_API_KEYS_FILE={path.resolve()}")
        print()

    print("Revoke = remove that line / env entry and restart the API.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
