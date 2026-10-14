"""Durable House log: every game + every on-chain hash we recorded.

Tables ``house_log_games`` / ``house_log_txs`` in the agentic database (was a
per-container SQLite file, data/agentic/house_log.db, which separate API
replicas could not share). Source of truth for counts is still the match
rows; this is the append-only book we can query later.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from gaming.src.stack.agentic.db import transaction

EXPLORER = "https://testnet.arcscan.app/tx/"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


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
    with transaction() as tx:
        tx.execute(
            """
            INSERT INTO house_log_games (
              match_id, game_id, status, stake_usdc,
              white_agent_id, black_agent_id, agent_a_id, agent_b_id,
              winner_agent_id, result, settlement_mode,
              created_at, settled_at, updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT (match_id) DO UPDATE SET
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
            tx.execute(
                """
                INSERT INTO house_log_txs
                  (tx_hash, step, match_id, agent_id, explorer, created_at)
                VALUES (?,?,?,?,?,?)
                ON CONFLICT (tx_hash) DO NOTHING
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


def sync_from_matches(matches: dict[str, Any] | None = None) -> dict[str, int]:
    if matches is None:
        from gaming.src.stack.agentic.db.tables import MATCHES

        rows = MATCHES.query("status = ?", ("settled",))
    else:
        rows = list((matches.get("matches") or {}).values())
    for m in rows:
        upsert_match(m)
    return stats()


def stats() -> dict[str, Any]:
    with transaction(readonly=True) as tx:
        games = tx.scalar("SELECT COUNT(*) AS n FROM house_log_games", ())
        settled = tx.scalar("SELECT COUNT(*) AS n FROM house_log_games WHERE status='settled'", ())
        playing = tx.scalar(
            "SELECT COUNT(*) AS n FROM house_log_games WHERE status IN ('playing','locking','locked','open')", ()
        )
        txs = tx.scalar("SELECT COUNT(*) AS n FROM house_log_txs", ())
        by_step = {
            r["step"]: int(r["n"])
            for r in tx.all("SELECT step, COUNT(*) AS n FROM house_log_txs GROUP BY step", ())
        }
    return {
        "games_total": int(games or 0),
        "games_settled": int(settled or 0),
        "games_live": int(playing or 0),
        "transactions": int(txs or 0),
        "tx_by_step": by_step,
    }


def list_transactions(limit: int = 80) -> list[dict[str, Any]]:
    with transaction(readonly=True) as tx:
        return tx.all(
            """
            SELECT tx_hash, step, match_id, agent_id, explorer, created_at
            FROM house_log_txs
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (max(1, min(int(limit), 300)),),
        )
