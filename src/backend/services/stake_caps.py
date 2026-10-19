"""Real-money stake caps for human challenges (humans realm only).

Founder decision (2026-10-19), until an external audit of BoardmanEscrow v2:

* at most ``BOARDMAN_HUMANS_MAX_STAKE_USDC`` per player per match (default $25)
* at most ``BOARDMAN_HUMANS_DAILY_STAKE_USDC`` staked per player in any rolling
  24 hours (default $100)

Practice (arena-chain) challenges are not capped here; the existing
``safety.validate_stake`` limits still apply to every stake.

Enforcement is server-side at the escrow chokepoints (custodial lock in
``clawstation_escrow``, passkey lock in ``self_custody.intents``) through
``reserve``: the check and the write happen in one transaction, so two locks
racing cannot both squeeze under the daily cap. A reservation is keyed by
(challenge, player), so retrying a lock never counts twice; ``release`` gives
it back only when the lock failed before any money moved.

``realm_stakes`` is also the per-row, chain-tagged record of every real-money
stake, so stakes reconcile per realm (``totals_by_chain``).
"""
from __future__ import annotations

import logging
import os
import textwrap
import threading
import time
import weakref
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

from gaming.src.stack.agentic.db.engine import Database, get_db

logger = logging.getLogger(__name__)

DEFAULT_MAX_STAKE = Decimal("25")
DEFAULT_DAILY_STAKE = Decimal("100")
WINDOW_MS = 24 * 3600 * 1000
MICRO = Decimal("1000000")

TEMPLATE = [
    """
    CREATE TABLE IF NOT EXISTS realm_stakes (
      challenge_id TEXT NOT NULL,
      profile_id TEXT NOT NULL,
      realm TEXT NOT NULL,
      chain TEXT NOT NULL,
      amount_micro BIGINT NOT NULL CHECK (amount_micro > 0),
      status TEXT NOT NULL,
      path TEXT,
      created_at_ms BIGINT NOT NULL,
      updated_at_ms BIGINT NOT NULL,
      PRIMARY KEY (challenge_id, profile_id)
    )
    """,
    "CREATE INDEX IF NOT EXISTS realm_stakes_profile_idx ON realm_stakes (profile_id, realm, created_at_ms)",
    "CREATE INDEX IF NOT EXISTS realm_stakes_chain_idx ON realm_stakes (chain, status)",
]
TABLES = ("realm_stakes",)
RESERVED, RELEASED = "reserved", "released"


class StakeCapExceeded(ValueError):
    """A real-money stake over the per-match or daily cap. Nothing moved."""

    def __init__(self, message: str, *, kind: str, limit: Decimal, used: Decimal = Decimal("0")) -> None:
        super().__init__(message)
        self.kind = kind
        self.limit = limit
        self.used = used


# ── config ───────────────────────────────────────────────────────────────────


def _env_amount(name: str, default: Decimal) -> Decimal:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        v = Decimal(raw)
    except InvalidOperation:
        logger.error("[stake_caps] %s=%r is not a number; using %s", name, raw, default)
        return default
    if not v.is_finite() or v <= 0:
        logger.error("[stake_caps] %s=%r must be positive; using %s", name, raw, default)
        return default
    return v


def max_stake_usdc() -> Decimal:
    """Per player per match (also never above the global safety cap)."""
    from gaming.src.backend.services.safety import MAX_STAKE_USDC

    return min(_env_amount("BOARDMAN_HUMANS_MAX_STAKE_USDC", DEFAULT_MAX_STAKE), MAX_STAKE_USDC)


def daily_stake_usdc() -> Decimal:
    return _env_amount("BOARDMAN_HUMANS_DAILY_STAKE_USDC", DEFAULT_DAILY_STAKE)


def applies(chain_id: Optional[str]) -> bool:
    from gaming.src.backend.services.realms import is_real_chain

    return bool(chain_id) and is_real_chain(chain_id)


def limits_text() -> str:
    return f"Real-money limits: ${max_stake_usdc():,.0f} per match, ${daily_stake_usdc():,.0f} a day."


# ── storage ──────────────────────────────────────────────────────────────────

_ready: "weakref.WeakSet[Database]" = weakref.WeakSet()
_ready_lock = threading.Lock()


def render(dialect: Any, *, pretty: bool = False) -> list[str]:
    out = []
    for stmt in TEMPLATE:
        text = textwrap.dedent(stmt).strip() if pretty else " ".join(stmt.split())
        out.append(text.replace("{JSON}", dialect.json_type))
    return out


def _ensure(db: Database) -> None:
    if db in _ready:
        return
    with _ready_lock:
        if db in _ready:
            return
        with db.transaction() as tx:
            if db.is_postgres:
                tx.execute("SELECT pg_advisory_xact_lock(724101019)")
            for stmt in render(db.dialect):
                tx.execute(stmt)
            if db.is_postgres:
                for t in TABLES:
                    tx.execute(f"ALTER TABLE {t} ENABLE ROW LEVEL SECURITY")
        _ready.add(db)


def db() -> Database:
    d = get_db()
    _ensure(d)
    return d


def now_ms() -> int:
    return int(time.time() * 1000)


def _micro(amount: Decimal) -> int:
    return int((Decimal(str(amount)) * MICRO).to_integral_value())


def _usd(micro: int) -> Decimal:
    return (Decimal(int(micro or 0)) / MICRO).quantize(Decimal("0.01"))


def _used_micro(tx: Any, profile_id: str, since_ms: int, *, exclude_challenge: str = "") -> int:
    row = tx.one(
        "SELECT COALESCE(SUM(amount_micro), 0) AS total FROM realm_stakes "
        "WHERE profile_id = ? AND realm = 'humans' AND status = ? AND created_at_ms >= ? "
        "AND challenge_id <> ?",
        (profile_id, RESERVED, since_ms, exclude_challenge),
    )
    return int((row or {}).get("total") or 0)


def used_today(profile_id: str, *, now: Optional[int] = None) -> Decimal:
    """Real money this player staked in the last 24 hours."""
    t = now if now is not None else now_ms()
    with db().transaction(readonly=True) as tx:
        return _usd(_used_micro(tx, str(profile_id), t - WINDOW_MS))


# ── checks ───────────────────────────────────────────────────────────────────


def _per_match_problem(amount: Decimal) -> Optional[StakeCapExceeded]:
    cap = max_stake_usdc()
    if Decimal(str(amount)) > cap:
        return StakeCapExceeded(
            f"Real-money matches are capped at ${cap:,.2f} per player for now. "
            f"Pick ${cap:,.0f} or less.",
            kind="per_match", limit=cap,
        )
    return None


def _daily_problem(amount: Decimal, used: Decimal) -> Optional[StakeCapExceeded]:
    cap = daily_stake_usdc()
    if used + Decimal(str(amount)) > cap:
        left = max(Decimal("0"), cap - used)
        return StakeCapExceeded(
            f"Daily real-money limit is ${cap:,.2f}. You've staked ${used:,.2f} in the last 24 hours, "
            f"so ${left:,.2f} is left right now.",
            kind="daily", limit=cap, used=used,
        )
    return None


def check(profile_id: str, chain_id: Optional[str], amount: Decimal, *, challenge_id: str = "",
          now: Optional[int] = None) -> Optional[str]:
    """Peek (no write): the player-facing refusal, or None. Practice chains: None."""
    if not applies(chain_id):
        return None
    err = _per_match_problem(amount)
    if err:
        return str(err)
    t = now if now is not None else now_ms()
    with db().transaction(readonly=True) as tx:
        used = _usd(_used_micro(tx, str(profile_id), t - WINDOW_MS, exclude_challenge=challenge_id))
    err = _daily_problem(amount, used)
    return str(err) if err else None


def reserve(profile_id: str, chain_id: str, challenge_id: str, amount: Decimal, *, path: str = "",
            now: Optional[int] = None) -> bool:
    """Count this stake against the caps (atomic check + write). Returns True
    when newly reserved, False when this (challenge, player) already holds a
    reservation (a retry). Raises StakeCapExceeded. Practice chains: no-op."""
    if not applies(chain_id):
        return False
    from gaming.src.backend.services.realms import realm_of_chain

    pid, cid = str(profile_id), str(challenge_id)
    err = _per_match_problem(amount)
    if err:
        raise err
    t = now if now is not None else now_ms()
    with db().transaction() as tx:
        tx.lock_key("realm_stakes", pid)
        cur = tx.one("SELECT status FROM realm_stakes WHERE challenge_id = ? AND profile_id = ?", (cid, pid))
        if cur is not None and cur["status"] == RESERVED:
            return False
        used = _usd(_used_micro(tx, pid, t - WINDOW_MS, exclude_challenge=cid))
        err = _daily_problem(amount, used)
        if err:
            raise err
        if cur is None:
            tx.execute(
                "INSERT INTO realm_stakes (challenge_id, profile_id, realm, chain, amount_micro, status, path, "
                "created_at_ms, updated_at_ms) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (cid, pid, realm_of_chain(chain_id), str(chain_id), _micro(amount), RESERVED, path[:80], t, t),
            )
        else:  # released earlier (failed lock); this retry counts again, from now
            tx.execute(
                "UPDATE realm_stakes SET status = ?, amount_micro = ?, chain = ?, path = ?, created_at_ms = ?, "
                "updated_at_ms = ? WHERE challenge_id = ? AND profile_id = ?",
                (RESERVED, _micro(amount), str(chain_id), path[:80], t, t, cid, pid),
            )
    logger.info("[stake_caps] reserved %s chain=%s challenge=%s", _usd(_micro(amount)), chain_id, cid)
    return True


def release(profile_id: str, challenge_id: str, *, reason: str = "") -> bool:
    """Give a reservation back (ONLY when the lock failed before money moved)."""
    with db().transaction() as tx:
        n = tx.rowcount(
            "UPDATE realm_stakes SET status = ?, path = COALESCE(path, '') || ?, updated_at_ms = ? "
            "WHERE challenge_id = ? AND profile_id = ? AND status = ?",
            (RELEASED, f" released:{reason[:40]}", now_ms(), str(challenge_id), str(profile_id), RESERVED),
        )
    return n == 1


def totals_by_chain() -> list[dict[str, Any]]:
    """Reserved real-money stakes per (realm, chain), for reconciliation."""
    with db().transaction(readonly=True) as tx:
        rows = tx.all(
            "SELECT realm, chain, COUNT(*) AS n, COALESCE(SUM(amount_micro), 0) AS total FROM realm_stakes "
            "WHERE status = ? GROUP BY realm, chain ORDER BY realm, chain",
            (RESERVED,),
        )
    return [{"realm": r["realm"], "chain": r["chain"], "count": int(r["n"]), "usdc": str(_usd(r["total"]))}
            for r in rows]


def postgres_migration_sql() -> str:
    from gaming.src.stack.agentic.db.engine import PostgresDialect

    head = (
        "-- Boardman money realms: real-money stake caps and the chain-tagged stake record.\n"
        "-- Generated from src/backend/services/stake_caps.py — edit there, then regenerate:\n"
        "-- python -m gaming.src.backend.services.stake_caps > <this file>\n\n"
        "BEGIN;\n\n"
    )
    body = ";\n\n".join(render(PostgresDialect(), pretty=True)) + ";\n\n"
    body += "-- Never reachable with the anon/authenticated keys.\n"
    body += ";\n".join(f"ALTER TABLE {t} ENABLE ROW LEVEL SECURITY" for t in TABLES) + ";\n\n"
    return head + body + "COMMIT;\n"


if __name__ == "__main__":  # pragma: no cover
    print(postgres_migration_sql(), end="")
