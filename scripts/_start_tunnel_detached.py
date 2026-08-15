"""Start a fresh cloudflared quick tunnel to the local Boardman API (double-fork).

The harness shell kills background children on exit, so a plain
``nohup ... &`` dies. This daemonizes with os.setsid() so cloudflared keeps
running until explicitly killed.
"""
import os
import sys
from pathlib import Path

CLOUDFLARED = Path.home() / ".local/bin/cloudflared"
LOG = Path("/tmp/cloudflared-boardman.log")

pid = os.fork()
if pid > 0:
    sys.exit(0)
os.setsid()
pid2 = os.fork()
if pid2 > 0:
    sys.exit(0)

log = LOG.open("ab")
devnull = open(os.devnull, "rb")
os.dup2(log.fileno(), 1)
os.dup2(log.fileno(), 2)
os.dup2(devnull.fileno(), 0)
os.execv(
    str(CLOUDFLARED),
    [str(CLOUDFLARED), "tunnel", "--url", "http://127.0.0.1:8000", "--no-autoupdate"],
)
