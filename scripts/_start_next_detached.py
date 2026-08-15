"""Start the Next.js frontend dev server fully detached (double-fork daemon).

The harness shell kills background children on exit, so a plain
``nohup ... &`` dies. This daemonizes with os.setsid() so the server keeps
running on :3000 until explicitly killed.
"""
import os
import sys
from pathlib import Path

FRONTEND = Path(__file__).resolve().parents[1] / "frontend"
LOG = Path("/tmp/boardman-next.log")

pid = os.fork()
if pid > 0:
    sys.exit(0)  # parent exits; child continues
os.setsid()
pid2 = os.fork()
if pid2 > 0:
    sys.exit(0)  # first child exits; grandchild is session leader

log = LOG.open("ab")
devnull = open(os.devnull, "rb")
os.dup2(log.fileno(), 1)
os.dup2(log.fileno(), 2)
os.dup2(devnull.fileno(), 0)
os.chdir(FRONTEND)
os.execv(
    "./node_modules/.bin/next",
    ["./node_modules/.bin/next", "dev", "-p", "3000"],
)
