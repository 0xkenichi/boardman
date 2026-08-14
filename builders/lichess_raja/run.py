#!/usr/bin/env python3
"""Start Raja on Lichess. Token: LICHESS_API_TOKEN in Boardman .env."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lichess_bots.run import main

if __name__ == "__main__":
    raise SystemExit(main(["--agent", "raja"]))
