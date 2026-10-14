"""Hermetic test harness for Boardman.

Everything in this module runs before any test module is imported, so
import-time configuration in the app (module-level paths, ``load_dotenv()``
calls, env-derived constants) sees the sandboxed values below.

What it guarantees:

* ``gaming.*`` resolves to THIS checkout, never another one on ``sys.path``.
* ``.env`` files are never loaded and secrets/live flags from the developer's
  shell are scrubbed; on-chain, LLM and watcher flags are forced off.
* Every data path (agentic store, partners, tournaments, fiat, wallet watch,
  stellar, match-code secret) points into a throwaway temp dir; each test gets
  its own ``BOARDMAN_AGENTIC_DATA``.
* An audit hook refuses in-process writes to the repo's ``data/`` (and the
  main checkout's ``data/`` when running from a git worktree).
* Outbound network is blocked. Loopback is allowed only to ports this test
  process bound itself, so live builder webhooks (:18761 …) are unreachable.
* Agent think delays are zero and the builder-webhook launcher is a no-op.
"""
from __future__ import annotations

import ipaddress
import os
import re
import shutil
import socket
import sys
import tempfile
import threading
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

# ── 1. Import path: `gaming.*` must be this checkout ─────────────────────────
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Fresh clones / worktrees lack the local import shims (gitignored): a
# `gaming/` dir symlinking src/config/data, and `backend -> src/backend`.
# Alias them as packages so `gaming.src.*` and `backend.*` load THIS tree.
for _name, _target in (("gaming", ROOT), ("backend", ROOT / "src" / "backend")):
    if (ROOT / _name).exists() or _name in sys.modules:
        continue
    _alias = types.ModuleType(_name)
    _alias.__path__ = [str(_target)]  # type: ignore[attr-defined]
    _alias.__file__ = str(_target / "__init__.py")
    sys.modules[_name] = _alias


# ── 2. Environment: no .env, no secrets, no live flags ───────────────────────
_SECRET_RE = re.compile(
    r"(KEY|SECRET|TOKEN|PASSWORD|PASSWD|PRIVATE|MNEMONIC|NPSSO|SESSION_STRING|"
    r"API_HASH|API_ID|DSN|DATABASE_URL|REDIS_URL|RPC_URL|WEBHOOK)"
)
_APP_PREFIXES = (
    "AFRICASTALKING_", "API_FOOTBALL", "ARC_", "ASI_", "AVALANCHE_", "AXIOM_",
    "BASE_", "BIRD_", "BLOCKED_REGIONS", "BOARDMAN_", "CIRCLE_", "CLAW",
    "ESCROW_", "FCM_", "FIAT_", "GEMINI_", "GEO_FENCE", "GOOGLE_", "KOBOX_",
    "LICHESS_", "LIGHTNING_", "LOGTAIL_", "MATCH_", "MAXMIND", "MONITOR_",
    "NERO_", "NEXT_PUBLIC_", "NIM_", "NVIDIA_", "OLLAMA_", "OPENAI_",
    "OPENROUTER_", "ORACLE_", "PARTNER_", "PAYSTACK_", "PLAY_", "RAJA_",
    "RAPIDAPI_", "REMATCH_", "RESEND_", "SETTLEMENT_", "SHEILA_", "SPECTATOR_",
    "STELLAR_", "STOCKFISH", "SUPABASE_", "TELEGRAM_", "TOURNAMENT",
    "WALLET_WATCH_", "XBL_",
)
# Escape hatch for the mtime check only (the audit hook stays strict): set when
# a live Boardman hub is writing to this checkout's data/ during the run.
IGNORE_DATA_MTIME = os.environ.get("HERMETIC_IGNORE_DATA_MTIME", "") == "1"

_KEEP = {"PATH", "HOME", "USER", "LOGNAME", "SHELL", "TMPDIR", "LANG", "TERM", "PWD"}

for _name in list(os.environ):
    if _name in _KEEP:
        continue
    if _SECRET_RE.search(_name) or _name.startswith(_APP_PREFIXES):
        del os.environ[_name]  # never printed

# python-dotenv >= 1.1 honours this; also inherited by test subprocesses.
os.environ["PYTHON_DOTENV_DISABLED"] = "1"
try:  # belt and braces for any import that already grabbed the function
    import dotenv
    import dotenv.main

    def _no_dotenv(*_a, **_k) -> bool:
        return False

    dotenv.load_dotenv = _no_dotenv
    dotenv.main.load_dotenv = _no_dotenv
except ImportError:  # pragma: no cover
    pass

SANDBOX = Path(tempfile.mkdtemp(prefix="boardman-tests-")).resolve()
_SESSION_AGENTIC = SANDBOX / "agentic"
_SESSION_AGENTIC.mkdir()

_FORCED_ENV = {
    # data paths (several are read once at import into module constants)
    "BOARDMAN_AGENTIC_DATA": str(_SESSION_AGENTIC),
    "PARTNER_ATTR_PATH": str(SANDBOX / "partner_attributions.json"),
    "PARTNER_LEDGER_PATH": str(SANDBOX / "partner_ledger.json"),
    "WALLET_WATCH_SNAPSHOT_PATH": str(SANDBOX / "wallet_watch_snapshots.json"),
    "TOURNAMENT_STORE_PATH": str(SANDBOX / "tournaments.json"),
    "FIAT_TOPUP_STORE": str(SANDBOX / "fiat_topups.json"),
    "STELLAR_WATCH_STATE_FILE": str(SANDBOX / "stellar_watch_state.json"),
    # otherwise match_codes persists a fresh secret under repo data/
    "MATCH_CODE_SECRET": "boardman-tests-not-a-secret",
    # on-chain / money / watchers off
    "BOARDMAN_AGENTIC_ONCHAIN": "0",
    "SPECTATOR_ONCHAIN": "0",
    "TOURNAMENTS_MONEY_LIVE": "0",
    "STELLAR_WATCH_ENABLED": "0",
    "AVALANCHE_WATCH_ENABLED": "0",
    "ORACLE_DRY_RUN": "1",
    # fast, deterministic agents: no bet window, no remote/local engines
    "BOARDMAN_BET_WINDOW_SEC": "0",
    "BOARDMAN_USE_STOCKFISH": "0",
    "BOARDMAN_AGENT_THINK_MS": "50",
    "BOARDMAN_SF_THINK_MS": "50",
}
os.environ.update(_FORCED_ENV)


# ── 3. Write guard on data/ directories ──────────────────────────────────────
def _main_checkout_root(root: Path) -> Path | None:
    """If ROOT is a git worktree, return the main checkout it belongs to."""
    git = root / ".git"
    if not git.is_file():
        return None
    try:
        text = git.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if not text.startswith("gitdir:"):
        return None
    gitdir = Path(text.split(":", 1)[1].strip())
    common = gitdir / "commondir"
    try:
        common_dir = (gitdir / common.read_text(encoding="utf-8").strip()).resolve()
    except OSError:
        common_dir = gitdir.parents[1]
    return common_dir.parent if common_dir.name == ".git" else None


def _real_dirs(dirs: list[Path], exclude: list[Path] = ()) -> list[Path]:
    out: list[Path] = []
    for d in dirs:
        r = Path(os.path.realpath(d))
        if r not in out and r not in exclude:
            out.append(r)
    return out


# data/ of the checkout under test: writes refused AND mtimes compared.
CHECKOUT_DATA_DIRS = _real_dirs([ROOT / "data", ROOT / "gaming" / "data"])
# data/ of the main checkout when running from a git worktree: writes refused.
# Not mtime-compared — a live hub there writes it while tests run.
_MAIN = _main_checkout_root(ROOT)
MAIN_DATA_DIRS = (
    _real_dirs([_MAIN / "data", _MAIN / "gaming" / "data"], CHECKOUT_DATA_DIRS)
    if _MAIN is not None
    else []
)
PROTECTED_DIRS = CHECKOUT_DATA_DIRS + MAIN_DATA_DIRS
_PROTECTED_STRS = tuple(str(d) + os.sep for d in PROTECTED_DIRS) + tuple(
    str(d) for d in PROTECTED_DIRS
)
DATA_WRITE_VIOLATIONS: list[str] = []
_guard_on = True

_WRITE_FLAGS = os.O_WRONLY | os.O_RDWR | os.O_APPEND | os.O_CREAT | os.O_TRUNC
_PATH_EVENTS = {
    "os.mkdir": (0,),
    "os.remove": (0,),
    "os.rmdir": (0,),
    "os.rename": (0, 1),
    "os.truncate": (0,),
    "os.chmod": (0,),
    "os.utime": (0,),
    "os.symlink": (1,),
    "os.link": (1,),
    "shutil.rmtree": (0,),
    "shutil.copyfile": (1,),
    "shutil.move": (1,),
    "sqlite3.connect": (0,),
}


def _is_protected(p) -> bool:
    if isinstance(p, int) or p is None:
        return False
    try:
        s = os.path.realpath(os.fsdecode(p))
    except (TypeError, ValueError):
        return False
    return any(s == d or s.startswith(d) for d in _PROTECTED_STRS)


def _audit(event: str, args: tuple) -> None:
    if not _guard_on:
        return
    if event == "open":
        path, mode, flags = (tuple(args) + (None, None, None))[:3]
        writing = False
        if isinstance(mode, str):
            writing = any(c in mode for c in "wax+")
        elif isinstance(flags, int):
            writing = bool(flags & _WRITE_FLAGS)
        if writing and _is_protected(path):
            DATA_WRITE_VIOLATIONS.append(f"{event} {path!r} mode={mode!r}")
            raise PermissionError(f"tests must not write to repo data/: {path}")
        return
    idx = _PATH_EVENTS.get(event)
    if idx is None:
        return
    for i in idx:
        if i < len(args) and _is_protected(args[i]):
            DATA_WRITE_VIOLATIONS.append(f"{event} {args[i]!r}")
            raise PermissionError(f"tests must not write to repo data/: {args[i]}")


sys.addaudithook(_audit)


def _snapshot(dirs: list[Path]) -> dict[str, tuple[int, int]]:
    snap: dict[str, tuple[int, int]] = {}
    for d in dirs:
        if not d.exists():
            continue
        snap[str(d)] = (d.stat().st_mtime_ns, -1)
        for dirpath, dirnames, filenames in os.walk(d):
            for n in dirnames + filenames:
                p = os.path.join(dirpath, n)
                try:
                    st = os.lstat(p)
                except OSError:
                    continue
                snap[p] = (st.st_mtime_ns, st.st_size)
    return snap


DATA_SNAPSHOT_BEFORE = _snapshot(CHECKOUT_DATA_DIRS)


def data_dir_changes() -> list[str]:
    """Paths under this checkout's data/ created/changed/removed so far."""
    after = _snapshot(CHECKOUT_DATA_DIRS)
    changed = [p for p, v in after.items() if DATA_SNAPSHOT_BEFORE.get(p) != v]
    removed = [p for p in DATA_SNAPSHOT_BEFORE if p not in after]
    return sorted(changed + removed)


# ── 4. Network guard ─────────────────────────────────────────────────────────
class NetworkBlocked(ConnectionRefusedError):
    """Raised for any connection a hermetic test is not allowed to make."""


# address -> [attempts, first test that tried it]
BLOCKED_CONNECTIONS: dict[str, list] = {}
_current_test = "<collection>"
_bound_ports: set[int] = set()
_bound_lock = threading.Lock()
_real_connect = socket.socket.connect
_real_connect_ex = socket.socket.connect_ex
_real_bind = socket.socket.bind
_real_getaddrinfo = socket.getaddrinfo
_LOCAL_NAMES = {"localhost", "127.0.0.1", "::1", "0.0.0.0", "::", "", "testserver"}


def _is_loopback(host) -> bool:
    if isinstance(host, bytes):
        host = host.decode()
    if host in _LOCAL_NAMES:
        return True
    try:
        return ipaddress.ip_address(str(host).split("%")[0]).is_loopback
    except ValueError:
        return False


def _record_block(addr: str) -> None:
    entry = BLOCKED_CONNECTIONS.setdefault(addr, [0, _current_test])
    entry[0] += 1


def _check_addr(sock: socket.socket, address) -> None:
    if sock.family not in (socket.AF_INET, socket.AF_INET6):
        return  # AF_UNIX etc.
    host, port = address[0], address[1]
    if _is_loopback(host):
        with _bound_lock:
            if port in _bound_ports:
                return
    _record_block(f"{host}:{port}")
    raise NetworkBlocked(f"network blocked in tests: {host}:{port}")


def _guarded_connect(self, address):
    _check_addr(self, address)
    return _real_connect(self, address)


def _guarded_connect_ex(self, address):
    _check_addr(self, address)
    return _real_connect_ex(self, address)


def _tracking_bind(self, address):
    out = _real_bind(self, address)
    if self.family in (socket.AF_INET, socket.AF_INET6):
        try:
            port = self.getsockname()[1]
        except OSError:
            port = None
        if port:
            with _bound_lock:
                _bound_ports.add(port)
    return out


def _guarded_getaddrinfo(host, *args, **kwargs):
    if host is not None and not _is_loopback(host):
        _record_block(f"dns:{host}")
        raise socket.gaierror(socket.EAI_NONAME, f"DNS blocked in tests: {host}")
    return _real_getaddrinfo(host, *args, **kwargs)


socket.socket.connect = _guarded_connect  # type: ignore[method-assign]
socket.socket.connect_ex = _guarded_connect_ex  # type: ignore[method-assign]
socket.socket.bind = _tracking_bind  # type: ignore[method-assign]
socket.getaddrinfo = _guarded_getaddrinfo


# ── 5. Fixtures ──────────────────────────────────────────────────────────────
def pytest_configure(config):
    config.addinivalue_line(
        "markers", "real_think_delay: keep the agents' real per-move think delay"
    )
    config.addinivalue_line(
        "markers", "builder_webhooks: allow house.ensure_builder_webhooks to run"
    )


@pytest.fixture(autouse=True)
def _hermetic(request, tmp_path_factory, monkeypatch):
    global _current_test
    _current_test = request.node.nodeid
    # Fresh agentic store per test; tests may still override with their own.
    monkeypatch.setenv("BOARDMAN_AGENTIC_DATA", str(tmp_path_factory.mktemp("agentic")))
    for k, v in _FORCED_ENV.items():
        if k != "BOARDMAN_AGENTIC_DATA":
            monkeypatch.setenv(k, v)

    # Process-wide singletons must not carry one test's store into the next.
    for mod_name, fn_name in (
        ("gaming.src.stack.agentic.registry", "get_registry"),
        ("gaming.src.stack.agentic.matches", "get_match_service"),
    ):
        mod = sys.modules.get(mod_name)
        fn = getattr(mod, fn_name, None) if mod is not None else None
        if fn is not None and hasattr(fn, "cache_clear"):
            fn.cache_clear()

    if "real_think_delay" not in request.keywords:
        from gaming.src.stack.agentic import clock

        monkeypatch.setattr(clock, "reasoning_delay_sec", lambda *a, **k: 0.0)

    if "builder_webhooks" not in request.keywords:
        house = sys.modules.get("gaming.src.stack.agentic.house")
        if house is None:
            from gaming.src.stack.agentic import house
        monkeypatch.setattr(house, "ensure_builder_webhooks", lambda *a, **k: None)
    yield


@pytest.fixture
def hermetic():
    """Handles on the harness, for the guard tests."""
    return types.SimpleNamespace(
        root=ROOT,
        sandbox=SANDBOX,
        protected_dirs=PROTECTED_DIRS,
        data_write_violations=DATA_WRITE_VIOLATIONS,
        data_dir_changes=data_dir_changes,
        ignore_data_mtime=IGNORE_DATA_MTIME,
        blocked=BLOCKED_CONNECTIONS,
        NetworkBlocked=NetworkBlocked,
    )


# ── 6. Session sanity + teardown ─────────────────────────────────────────────
def pytest_sessionstart(session):
    from gaming.src.stack.agentic import store

    store_file = Path(store.__file__).resolve()
    if ROOT not in store_file.parents:
        pytest.exit(
            f"`gaming` resolves to {store_file}, not this checkout ({ROOT}). "
            "Refusing to run against another checkout's code and data.",
            returncode=4,
        )


def pytest_terminal_summary(terminalreporter):
    if BLOCKED_CONNECTIONS:
        total = sum(n for n, _ in BLOCKED_CONNECTIONS.values())
        terminalreporter.write_line(f"hermetic: blocked {total} network attempt(s):")
        for addr, (n, first) in sorted(BLOCKED_CONNECTIONS.items()):
            terminalreporter.write_line(f"  {addr} x{n} (first: {first})")
    if DATA_WRITE_VIOLATIONS:
        terminalreporter.write_line(
            "hermetic: refused writes to data/: " + "; ".join(DATA_WRITE_VIOLATIONS[:10]),
            red=True,
        )


def pytest_sessionfinish(session, exitstatus):
    # Catch anything that touched data/ after the guard test ran.
    problems = list(DATA_WRITE_VIOLATIONS)
    if not IGNORE_DATA_MTIME:
        problems += [f"changed: {p}" for p in data_dir_changes()]
    if problems and session.exitstatus == 0:
        sys.stderr.write("hermetic: repo data/ was touched:\n  " + "\n  ".join(problems[:20]) + "\n")
        session.exitstatus = 1


def pytest_unconfigure(config):
    global _guard_on
    _guard_on = False
    shutil.rmtree(SANDBOX, ignore_errors=True)
