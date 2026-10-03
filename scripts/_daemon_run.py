"""Run a command fully detached (double-fork daemon).

The harness shell kills background children when a tool call exits, so a
plain ``nohup ... &`` dies with it. This daemonizes with os.setsid() so the
process survives the call (it only stops on an explicit kill or a host
restart). Modeled on ``_start_next_detached.py``; generic on purpose so the
API and every agent webhook server boot the same way.

Usage:
  python scripts/_daemon_run.py LOGFILE CWD -- CMD [ARGS...]

Environment (PYTHONPATH etc.) is inherited from the caller; the parent
returns immediately, so callers can launch several daemons in one command.
"""
import os
import sys

if len(sys.argv) < 5 or sys.argv[3] != "--":
    sys.exit("usage: _daemon_run.py LOGFILE CWD -- CMD [ARGS...]")

log_path, cwd, cmd = sys.argv[1], sys.argv[2], sys.argv[4:]

pid = os.fork()
if pid > 0:
    sys.exit(0)  # parent exits; child continues
os.setsid()
pid2 = os.fork()
if pid2 > 0:
    sys.exit(0)  # first child exits; grandchild is session leader

log = open(log_path, "ab")
devnull = open(os.devnull, "rb")
os.dup2(log.fileno(), 1)
os.dup2(log.fileno(), 2)
os.dup2(devnull.fileno(), 0)
os.chdir(cwd)
os.execvp(cmd[0], cmd)
