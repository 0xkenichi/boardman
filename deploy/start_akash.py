#!/usr/bin/env python3
"""Container entrypoint (Railway / Akash / Fly / docker-compose).

Supervises the Boardman processes inside one container:

  webhooks  ten builder-webhook servers (Raja, Nero, Sheila and the seven
            football managers). Started first so the API and the house
            session find them already listening and do not spawn their own
            unsupervised copies. Output is prefixed ``[wh:<name>]``.
  api       uvicorn gaming.src.backend.main:app. If it dies the container
            exits so the platform restarts it (health checks hit this).
  bot       Telegram bot (polling). Restarted with backoff.
  house     scripts/run_house_session.py — the real lock/play/settle loop.
            Restarted with backoff.

Pick roles with BOARDMAN_PROCS (comma list, default "webhooks,api,bot,house").
BOARDMAN_HOUSE_SESSION=0 still removes the house role.

Persistent state: BOARDMAN_AGENTIC_DATA defaults to /data/agentic (mount a
volume at /data). With REQUIRE_PERSISTENT_DATA=1 the container refuses to
start when that directory is not writable, sits on the container's own
ephemeral disk, or is missing its marker file — see docs/RUNBOOK.md.

Pure Python (no bash) so crash reasons show up clearly in platform logs.
"""
from __future__ import annotations

import json
import os
import pwd
import signal
import socket
import subprocess
import sys
import threading
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

APP_ROOT = Path(os.environ.get("BOARDMAN_APP_ROOT", "/app"))
DEFAULT_DATA_DIR = "/data/agentic"
DATA_MARKER = ".boardman-data-volume"
STATE_FILES = ("ledger.json", "matches.json", "agents.json", "house_log.db")
APP_USER = os.environ.get("BOARDMAN_APP_USER", "rematch")

TRUTHY = {"1", "true", "yes", "on"}
FALSY = {"0", "false", "no", "off"}

# Keep in sync with house.ensure_builder_webhooks (QA-owned module).
WEBHOOKS: list[tuple[str, int, str, str]] = [
    # (name, port, module, port env override)
    ("raja", 18761, "gaming.src.stack.agentic.agents.raja.serve", "RAJA_WEBHOOK_PORT"),
    ("nero", 18762, "gaming.src.stack.agentic.agents.nero.serve", "NERO_WEBHOOK_PORT"),
    ("sheila", 18764, "gaming.src.stack.agentic.agents.sheila.serve", "SHEILA_WEBHOOK_PORT"),
    ("bluelock", 18771, "gaming.src.stack.agentic.agents.bluelock.serve", "BLUELOCK_WEBHOOK_PORT"),
    ("aoashi", 18772, "gaming.src.stack.agentic.agents.aoashi.serve", "AOASHI_WEBHOOK_PORT"),
    ("matchslice", 18773, "gaming.src.stack.agentic.agents.matchslice.serve", "MATCHSLICE_WEBHOOK_PORT"),
    # season-2 football managers
    ("academy", 18774, "gaming.src.stack.agentic.agents.academy.serve", "ACADEMY_WEBHOOK_PORT"),
    ("galactico", 18775, "gaming.src.stack.agentic.agents.galactico.serve", "GALACTICO_WEBHOOK_PORT"),
    ("catenaccio", 18776, "gaming.src.stack.agentic.agents.catenaccio.serve", "CATENACCIO_WEBHOOK_PORT"),
    ("tinkerer", 18777, "gaming.src.stack.agentic.agents.tinkerer.serve", "TINKERER_WEBHOOK_PORT"),
]


def log(msg: str) -> None:
    print(f"[akash] {msg}", flush=True)


def _env_flag(name: str, default: bool = False) -> bool:
    v = (os.environ.get(name) or "").strip().lower()
    if not v:
        return default
    return v in TRUTHY


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── layout / preflight ──────────────────────────────────────────────────────


def _ensure_layout() -> None:
    """Match start_free_local.sh package layout used by imports."""
    os.chdir(APP_ROOT)
    (APP_ROOT / "gaming").mkdir(exist_ok=True)
    links = {
        APP_ROOT / "gaming" / "src": APP_ROOT / "src",
        APP_ROOT / "gaming" / "config": APP_ROOT / "config",
        APP_ROOT / "backend": APP_ROOT / "src" / "backend",
    }
    for dest, src in links.items():
        if dest.is_symlink() or dest.exists():
            continue
        try:
            dest.symlink_to(src)
            log(f"linked {dest} -> {src}")
        except FileExistsError:
            pass
    init = APP_ROOT / "gaming" / "__init__.py"
    if not init.exists():
        init.touch()


def _preflight(roles: set[str]) -> None:
    """Fail fast with a clear traceback if imports are broken."""
    log("preflight: checking imports…")
    try:
        import backend.supabase_client  # noqa: F401

        if "api" in roles:
            import gaming.src.backend.main  # noqa: F401
        if "bot" in roles:
            import gaming.src.bot.main  # noqa: F401
    except Exception:
        log("FATAL: preflight import failed:")
        traceback.print_exc()
        raise SystemExit(1)
    log("preflight: OK")


# ── persistent data guard ───────────────────────────────────────────────────


def _app_ids() -> Optional[tuple[int, int]]:
    try:
        pw = pwd.getpwnam(APP_USER)
        return pw.pw_uid, pw.pw_gid
    except KeyError:
        return None


def _chown_tree(root: Path, uid: int, gid: int) -> None:
    for dirpath, dirnames, filenames in os.walk(root):
        for n in [dirpath, *[os.path.join(dirpath, f) for f in dirnames + filenames]]:
            try:
                st = os.lstat(n)
                if st.st_uid != uid or st.st_gid != gid:
                    os.lchown(n, uid, gid)
            except OSError:
                pass


def check_persistent_data() -> Optional[str]:
    """Prepare the agentic data dir. Returns an error string when boot must stop."""
    data = Path(os.environ.setdefault("BOARDMAN_AGENTIC_DATA", DEFAULT_DATA_DIR))
    require = _env_flag("REQUIRE_PERSISTENT_DATA")

    try:
        data.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        msg = (
            f"data dir {data} cannot be created ({exc.__class__.__name__}: {exc}); "
            "on Railway set RAILWAY_RUN_UID=0 so the root-owned volume can be prepared"
        )
        if require:
            return msg
        log(f"WARN {msg}")
        return None

    # Volumes on Railway/Akash mount root-owned. When the supervisor runs as
    # root (RAILWAY_RUN_UID=0) hand the tree to the app user; children run
    # unprivileged (see _child_user_kwargs).
    ids = _app_ids()
    if os.geteuid() == 0 and ids:
        _chown_tree(data, *ids)

    probe = data / f".write-probe-{os.getpid()}"
    try:
        with open(probe, "w", encoding="utf-8") as fh:
            fh.write("ok")
            fh.flush()
            os.fsync(fh.fileno())
        probe.unlink()
        writable = True
    except OSError as exc:
        writable = False
        write_err = f"{exc.__class__.__name__}: {exc}"

    # Same device as / means no volume is mounted. Bare-metal/VPS installs
    # that keep data on the root disk on purpose set BOARDMAN_DATA_ALLOW_ROOTFS=1.
    ephemeral = os.stat(data).st_dev == os.stat("/").st_dev and not _env_flag(
        "BOARDMAN_DATA_ALLOW_ROOTFS"
    )
    marker = data / DATA_MARKER

    if not require:
        if not writable:
            log(f"WARN data dir {data} is not writable ({write_err})")
        if ephemeral:
            log(
                f"WARN data dir {data} is on the container's ephemeral disk — "
                "balances, escrows and books are lost on every redeploy. Mount a "
                "volume and set REQUIRE_PERSISTENT_DATA=1 (docs/RUNBOOK.md)."
            )
        return None

    if not writable:
        return f"data dir {data} is not writable ({write_err})"
    if ephemeral:
        return (
            f"data dir {data} is on the container root filesystem, not a mounted "
            "volume — attach the volume (mount path /data) before starting"
        )
    if not marker.exists():
        has_state = any((data / n).exists() for n in STATE_FILES)
        if has_state or _env_flag("BOARDMAN_DATA_INIT"):
            reason = "existing state adopted" if has_state else "BOARDMAN_DATA_INIT=1"
            marker.write_text(
                json.dumps({"created_at": _now_iso(), "reason": reason}) + "\n",
                encoding="utf-8",
            )
            if os.geteuid() == 0 and ids:
                os.lchown(marker, *ids)
            log(f"data marker written ({reason})")
        else:
            return (
                f"data dir {data} has no {DATA_MARKER} marker and no state files. "
                "An empty volume would look like every balance was reset while "
                "on-chain escrows stay locked. If this really is a brand-new "
                "volume, deploy once with BOARDMAN_DATA_INIT=1, then remove it."
            )
    log(f"data dir OK (volume, writable, marker present): {data}")
    return None


# ── supervision ─────────────────────────────────────────────────────────────


def _child_user_kwargs() -> dict:
    """Drop to the app user for children when the supervisor runs as root."""
    ids = _app_ids()
    if os.geteuid() != 0 or not ids or _env_flag("BOARDMAN_CHILDREN_AS_ROOT"):
        return {}
    return {"user": ids[0], "group": ids[1], "extra_groups": []}


def _port_open(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.3):
            return True
    except OSError:
        return False


class Child:
    """One supervised subprocess with exponential restart backoff."""

    BACKOFF_MIN = 1.0
    BACKOFF_MAX = 60.0
    STABLE_AFTER = 300.0  # a run this long resets the backoff

    def __init__(
        self,
        name: str,
        argv: list[str],
        env: dict[str, str],
        *,
        critical: bool = False,
        prefix_output: bool = False,
        port: Optional[int] = None,
    ) -> None:
        self.name = name
        self.argv = argv
        self.env = env
        self.critical = critical
        self.prefix_output = prefix_output
        self.port = port
        self.proc: Optional[subprocess.Popen] = None
        self.started_at = 0.0
        self.restarts = 0
        self.backoff = self.BACKOFF_MIN
        self.next_start = 0.0
        self.last_exit: Optional[int] = None
        self.last_exit_at: Optional[str] = None
        self.adopted = False  # port held by a process we did not start

    def start(self) -> None:
        drop = _child_user_kwargs()
        env = dict(self.env, HOME=str(APP_ROOT)) if drop else self.env
        kw: dict = dict(cwd=str(APP_ROOT), env=env, **drop)
        if self.prefix_output:
            kw.update(stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        self.proc = subprocess.Popen(self.argv, **kw)
        self.started_at = time.time()
        self.adopted = False
        log(f"started {self.name} pid={self.proc.pid}")
        if self.prefix_output and self.proc.stdout is not None:
            threading.Thread(
                target=self._pump, args=(self.proc.stdout,), daemon=True
            ).start()

    def _pump(self, stream) -> None:
        tag = f"[wh:{self.name}] "
        try:
            for raw in iter(stream.readline, b""):
                line = raw.decode("utf-8", "replace").rstrip("\n")
                sys.stdout.write(tag + line + "\n")
                sys.stdout.flush()
        except Exception:
            pass
        finally:
            try:
                stream.close()
            except Exception:
                pass

    def running(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def reap(self) -> Optional[int]:
        """Return the exit code if the process just exited, else None."""
        if self.proc is None:
            return None
        code = self.proc.poll()
        if code is None:
            return None
        self.proc = None
        self.last_exit = code
        self.last_exit_at = _now_iso()
        ran = time.time() - self.started_at
        if ran >= self.STABLE_AFTER:
            self.backoff = self.BACKOFF_MIN
        self.next_start = time.time() + self.backoff
        log(
            f"{self.name} exited code={code} after {ran:.0f}s — "
            f"restart in {self.backoff:.0f}s"
        )
        self.backoff = min(self.BACKOFF_MAX, self.backoff * 2)
        return code

    def maybe_restart(self) -> None:
        if self.proc is not None or time.time() < self.next_start:
            return
        if self.port is not None and _port_open(self.port):
            # Someone else (house.ensure_builder_webhooks) bound the port while
            # we were backing off. Leave it; check again later.
            if not self.adopted:
                log(f"{self.name} port {self.port} held by another process — not restarting")
                self.adopted = True
            self.next_start = time.time() + 30
            return
        self.restarts += 1
        self.start()

    def stop(self) -> None:
        if self.running():
            try:
                self.proc.terminate()  # type: ignore[union-attr]
            except Exception:
                pass

    def status(self) -> dict:
        return {
            "running": self.running(),
            "adopted": self.adopted,
            "restarts": self.restarts,
            "last_exit": self.last_exit,
            "last_exit_at": self.last_exit_at,
            "up_sec": int(time.time() - self.started_at) if self.running() else 0,
        }


def _write_status(children: list[Child], roles: set[str]) -> None:
    """Small status file the deep health endpoint reads (no secrets)."""
    try:
        data = Path(os.environ["BOARDMAN_AGENTIC_DATA"])
        rt = data / ".runtime"
        rt.mkdir(exist_ok=True)
        host = socket.gethostname() or "local"
        payload = {
            "ts": time.time(),
            "at": _now_iso(),
            "host": host,
            "roles": sorted(roles),
            "children": {c.name: c.status() for c in children},
        }
        tmp = rt / f"supervisor-{host}.json.tmp"
        tmp.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
        tmp.replace(rt / f"supervisor-{host}.json")
    except Exception:
        pass


def _roles() -> set[str]:
    raw = os.environ.get("BOARDMAN_PROCS") or "webhooks,api,bot,house"
    roles = {r.strip().lower() for r in raw.split(",") if r.strip()}
    if (os.environ.get("BOARDMAN_HOUSE_SESSION") or "1").strip().lower() in FALSY:
        roles.discard("house")
    unknown = roles - {"webhooks", "api", "bot", "house"}
    if unknown:
        log(f"WARN ignoring unknown roles in BOARDMAN_PROCS: {sorted(unknown)}")
    return roles & {"webhooks", "api", "bot", "house"}


def _webhook_children(env: dict[str, str]) -> list[Child]:
    out: list[Child] = []
    ethereal = APP_ROOT / "engines" / "Ethereal" / "src" / "ethereal"
    for name, default_port, mod, port_env in WEBHOOKS:
        port = int(os.environ.get(port_env) or default_port)
        cenv = dict(env)
        if name == "sheila" and ethereal.is_file() and os.access(ethereal, os.X_OK):
            cenv["BOARDMAN_UCI_ENGINE"] = str(ethereal)
        out.append(
            Child(
                f"{name}",
                [sys.executable, "-m", mod],
                cenv,
                prefix_output=True,
                port=port,
            )
        )
    return out


def main() -> int:
    os.environ.setdefault("PYTHONUNBUFFERED", "1")
    os.environ.setdefault("PYTHONPATH", str(APP_ROOT))
    os.environ.setdefault("CLAWSTATION_BOT_MODE", "polling")
    os.environ.setdefault("CLAW_DEFAULT_CHAIN", "arc")
    os.environ.setdefault("PORT", "8000")
    os.environ.setdefault("BLOCKED_REGIONS_FILE", str(APP_ROOT / "config" / "blocked_regions.json"))
    port = os.environ["PORT"]

    roles = _roles()
    log(f"roles: {','.join(sorted(roles)) or '(none)'}")

    _ensure_layout()

    err = check_persistent_data()
    if err:
        log(f"FATAL: {err}")
        return 2

    if "bot" in roles:
        token = (
            os.environ.get("TELEGRAM_BOT_TOKEN_BOARDMAN")
            or os.environ.get("TELEGRAM_BOT_TOKEN_CLAWSTATION")
            or os.environ.get("TELEGRAM_BOT_TOKEN")
        )
        if not token:
            log(
                "FATAL: TELEGRAM_BOT_TOKEN_BOARDMAN (or TELEGRAM_BOT_TOKEN_CLAWSTATION / "
                "TELEGRAM_BOT_TOKEN) is not set"
            )
            return 1
    log(
        f"env ok chain={os.environ.get('CLAW_DEFAULT_CHAIN')} "
        f"mode={os.environ.get('CLAWSTATION_BOT_MODE')}"
    )

    try:
        _preflight(roles)
    except SystemExit as e:
        return int(e.code or 1)

    env = os.environ.copy()
    env["PYTHONPATH"] = str(APP_ROOT)
    if "webhooks" in roles:
        # Tells run_house_session.py not to spawn its own copies.
        env["BOARDMAN_WEBHOOKS_SUPERVISED"] = "1"

    children: list[Child] = []
    api: Optional[Child] = None

    if "webhooks" in roles:
        hooks = _webhook_children(env)
        for h in hooks:
            if _port_open(h.port or 0):
                log(f"{h.name} port {h.port} already in use — skipping")
                h.adopted = True
                h.next_start = time.time() + 30
            else:
                h.start()
        children.extend(hooks)
        # Let them bind before the API / house look for them.
        deadline = time.time() + 20
        while time.time() < deadline and not all(
            _port_open(h.port or 0) for h in hooks
        ):
            time.sleep(0.25)
        up = [h.name for h in hooks if _port_open(h.port or 0)]
        log(f"webhooks listening: {', '.join(up) or 'none'}")

    if "api" in roles:
        api = Child(
            "api",
            [
                sys.executable, "-m", "uvicorn", "gaming.src.backend.main:app",
                "--host", "0.0.0.0", "--port", str(port),
            ],
            env,
            critical=True,
        )
        log(f"starting API on :{port}")
        api.start()
        children.append(api)
        # Give API a moment so bot and API don't stampede CPU on small boxes
        time.sleep(2)

    if "bot" in roles:
        bot = Child("bot", [sys.executable, "-m", "gaming.src.bot.main"], env)
        log("starting Telegram bot (polling)")
        bot.start()
        children.append(bot)

    if "house" in roles:
        house = Child(
            "house",
            [
                sys.executable, "scripts/run_house_session.py",
                "--games", os.environ.get("BOARDMAN_HOUSE_GAMES", "0"),
                "--delay", os.environ.get("BOARDMAN_HOUSE_MOVE_DELAY", "0.05"),
                "--pause", os.environ.get("BOARDMAN_HOUSE_PAUSE", "2"),
            ],
            env,
        )
        log("starting house session (continuous)")
        house.start()
        children.append(house)

    if not children:
        log("FATAL: no roles to run")
        return 1

    stopping = threading.Event()

    def shutdown(signum: Optional[int] = None, _frame=None) -> None:
        if stopping.is_set():
            return
        stopping.set()
        log(f"shutting down (signal={signum})")
        for c in children:
            c.stop()
        deadline = time.time() + 10
        for c in children:
            if c.proc is None:
                continue
            try:
                c.proc.wait(timeout=max(0.1, deadline - time.time()))
            except subprocess.TimeoutExpired:
                c.proc.kill()

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    last_status = 0.0
    while not stopping.is_set():
        for c in children:
            code = c.reap()
            if code is not None and c.critical:
                log(f"{c.name} is critical — stopping container")
                shutdown()
                return code if code else 1
            c.maybe_restart()
        if time.time() - last_status >= 10:
            _write_status(children, roles)
            last_status = time.time()
        time.sleep(0.5)
    return 0


if __name__ == "__main__":
    sys.exit(main())
