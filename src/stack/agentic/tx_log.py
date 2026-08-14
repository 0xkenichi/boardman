"""Durable House log: every game + every on-chain hash we recorded.

SQLite under data/agentic/house_log.db. Source of truth for counts is still
matches.json; this file is the append-only book we can query later.
"""
from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timezone
from typing import Any, Optional

from gaming.src.stack.agentic.store import data_dir

_lock = threading.RLock()
EXPLORER = "https://testnet.arcscan.app/tx/"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def db_path():
    return data_dir() / "house_log.db"


def _conn() -> sqlite3.Connection:
    con = sqlite3.connect(str(db_path()), timeout=10)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS games (
          match_id TEXT PRIMARY KEY,
          game_id TEXT,
          status TEXT,
          stake_usdc TEXT,
          white_agent_id TEXT,
          black_agent_id TEXT,
          agent_a_id TEXT,
          agent_b_id TEXT,
          winner_agent_id TEXT,
          result TEXT,
          settlement_mode TEXT,
          created_at TEXT,
          settled_at TEXT,
          updated_at TEXT
        )
        """
    )
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS transactions (
          tx_hash TEXT PRIMARY KEY,
          step TEXT,
          match_id TEXT,
          agent_id TEXT,
          explorer TEXT,
          created_at TEXT
        )
        """
    )
    con.execute(
        "CREATE INDEX IF NOT EXISTS idx_tx_match ON transactions(match_id)"
    )
    return con


def _explorer(tx: str) -> str:
    if not tx:
        return ""
    if str(tx).startswith("http"):
        return str(tx)
    return EXPLORER + str(tx)


def _iter_match_txs(match: dict[str, Any]) -> list[tuple[str, str, str]]:
    """(tx_hash, step, agent_id) from a stored match."""
    out: list[tuple[str, str, str]] = []
    seen: set[str] = set()

    def add(h: Optional[str], step: str, agent: str = "") -> None:
        tx = (h or "").strip()
        if not tx or tx in seen:
            return
        seen.add(tx)
        out.append((tx, step or "tx", agent or ""))

    on = match.get("onchain") or {}
    settle = match.get("onchain_settle") or (match.get("escrow") or {}).get("onchain_settle") or {}
    add(on.get("create_tx_hash"), "lock", match.get("agent_a_id") or "")
    add(on.get("join_tx_hash"), "join", match.get("agent_b_id") or "")
    add(settle.get("tx_hash"), "settle", match.get("winner_agent_id") or "")
    for t in on.get("txs") or []:
        add(t.get("tx_hash"), t.get("step") or "tx", "")
    book = match.get("spectator_book") or {}
    add(book.get("open_tx_hash"), "openBook", "")
    add(book.get("resolve_tx_hash"), "resolveBook", "")
    for b in book.get("bets") or []:
        add(b.get("tx_hash"), "deposit", "")
    for t in book.get("deposit_txs") or []:
        add(t.get("tx_hash"), t.get("step") or "deposit", "")
    return out


def upsert_match(match: dict[str, Any]) -> None:
    mid = (match.get("match_id") or "").strip()
    if not mid:
        return
    with _lock:
        con = _conn()
        try:
            con.execute(
                """
                INSERT INTO games (
                  match_id, game_id, status, stake_usdc,
                  white_agent_id, black_agent_id, agent_a_id, agent_b_id,
                  winner_agent_id, result, settlement_mode,
                  created_at, settled_at, updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(match_id) DO UPDATE SET
                  status=excluded.status,
                  stake_usdc=excluded.stake_usdc,
                  winner_agent_id=excluded.winner_agent_id,
                  result=excluded.result,
                  settlement_mode=excluded.settlement_mode,
                  settled_at=excluded.settled_at,
                  updated_at=excluded.updated_at
                """,
                (
                    mid,
                    match.get("game_id") or "agentic.chess_standard",
                    match.get("status") or "",
                    str(match.get("stake_usdc") or "0"),
                    match.get("white_agent_id") or "",
                    match.get("black_agent_id") or "",
                    match.get("agent_a_id") or "",
                    match.get("agent_b_id") or "",
                    match.get("winner_agent_id") or "",
                    match.get("result") or "",
                    match.get("settlement_mode") or "",
                    match.get("created_at") or "",
                    match.get("settled_at") or "",
                    _now(),
                ),
            )
            for txh, step, agent in _iter_match_txs(match):
                con.execute(
                    """
                    INSERT OR IGNORE INTO transactions
                      (tx_hash, step, match_id, agent_id, explorer, created_at)
                    VALUES (?,?,?,?,?,?)
                    """,
                    (
                        txh,
                        step,
                        mid,
                        agent,
                        _explorer(txh),
                        match.get("settled_at") or match.get("created_at") or _now(),
                    ),
                )
            con.commit()
        finally:
            con.close()


def sync_from_matches(matches: dict[str, Any] | None = None) -> dict[str, int]:
    from gaming.src.stack.agentic.store import load_json

    store = matches if matches is not None else load_json("matches.json", {"matches": {}})
    rows = list((store.get("matches") or {}).values())
    for m in rows:
        upsert_match(m)
    return stats()


def stats() -> dict[str, Any]:
    with _lock:
        con = _conn()
        try:
            games = con.execute("SELECT COUNT(*) FROM games").fetchone()[0]
            settled = con.execute(
                "SELECT COUNT(*) FROM games WHERE status='settled'"
            ).fetchone()[0]
            playing = con.execute(
                "SELECT COUNT(*) FROM games WHERE status IN ('playing','locking','locked','open')"
            ).fetchone()[0]
            txs = con.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
            by_step = {
                r["step"]: r["n"]
                for r in con.execute(
                    "SELECT step, COUNT(*) AS n FROM transactions GROUP BY step"
                )
            }
            return {
                "games_total": int(games),
                "games_settled": int(settled),
                "games_live": int(playing),
                "transactions": int(txs),
                "tx_by_step": by_step,
            }
        finally:
            con.close()


def list_transactions(limit: int = 80) -> list[dict[str, Any]]:
    with _lock:
        con = _conn()
        try:
            rows = con.execute(
                """
                SELECT tx_hash, step, match_id, agent_id, explorer, created_at
                FROM transactions
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (max(1, min(int(limit), 300)),),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            con.close()
