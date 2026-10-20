"""Public match / PNL aggregation over every match (hot matches.json + archive).

No secrets. Skill escrow PNL + on-chain lock/join/settle proofs.
Spectator bets publish SpectatorPool deposit/resolve hashes when present.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Optional

from gaming.src.stack.agentic.store import load_json

RAJA_ID = "agent_raja_kia_alekhine"
NERO_ID = "agent_nero_sicilian_french"
KNOWN_NAMES = {
    RAJA_ID: "Raja",
    NERO_ID: "Nero",
}
EXPLORER_TX = "https://explorer.testnet.arc.io/tx/"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _d(x: Any) -> Decimal:
    try:
        return Decimal(str(x if x is not None else "0"))
    except Exception:
        return Decimal("0")


def _q(x: Decimal) -> str:
    return str(x.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP))


def _name(agent_id: Optional[str], agents: dict[str, Any]) -> str:
    if not agent_id:
        return "—"
    rec = agents.get(agent_id) or {}
    return rec.get("name") or KNOWN_NAMES.get(agent_id) or agent_id


def _wallet(agent_id: Optional[str], match: dict[str, Any], agents: dict[str, Any]) -> str:
    if not agent_id:
        return ""
    if agent_id == match.get("agent_a_id"):
        return (match.get("agent_a_wallet") or "") or ""
    if agent_id == match.get("agent_b_id"):
        return (match.get("agent_b_wallet") or "") or ""
    rec = agents.get(agent_id) or {}
    return rec.get("wallet_address") or ""


def _explorer(tx: Optional[str]) -> str:
    if not tx:
        return ""
    if str(tx).startswith("http"):
        return str(tx)
    return EXPLORER_TX + str(tx)


def _empty_card(agent_id: str, name: str, wallet: str) -> dict[str, Any]:
    return {
        "agent_id": agent_id,
        "name": name,
        "wallet": wallet,
        "played": 0,
        "wins": 0,
        "losses": 0,
        "draws": 0,
        "white_games": 0,
        "black_games": 0,
        "skill_pnl_usdc": "0.000000",
        "stake_volume_usdc": "0.000000",
        "seed_spent_usdc": "0.000000",
        "lp_realized_pnl_usdc": "0.000000",
        "onchain_locks": 0,
    }


def _skill_pnl(match: dict[str, Any], agent_id: str) -> Decimal:
    """Net skill-escrow PNL for one agent on one settled match.

    Winner: owner_payout − stake (fees already taken).
    Loser: −stake.
    Draw / unsettled: 0.
    """
    if match.get("status") != "settled":
        return Decimal("0")
    stake = _d(match.get("stake_usdc"))
    result = (match.get("result") or "").lower()
    winner = match.get("winner_agent_id")
    if result in {"draw", "1/2-1/2"} or not winner:
        return Decimal("0")
    if agent_id == winner:
        split = match.get("fee_split") or (match.get("escrow") or {}).get("fee_split") or {}
        payout = _d(split.get("owner_payout"))
        if payout > 0:
            return payout - stake
        # fallback if fee_split missing: pot minus 3% platform, ignore creator cut
        pot = stake * 2
        platform = (pot * Decimal("300") / Decimal("10000")).quantize(Decimal("0.000001"))
        return (pot - platform) - stake
    if agent_id in {match.get("agent_a_id"), match.get("agent_b_id")}:
        return -stake
    return Decimal("0")


def _seed_spent(match: dict[str, Any], agent_id: str) -> Decimal:
    """Spectator seed consumed (not refunded) when the book settles a winner."""
    book = match.get("spectator_book") or {}
    payouts = book.get("payouts") or {}
    if payouts.get("mode") == "refund":
        return Decimal("0")
    eco = match.get("economy") or {}
    if agent_id == match.get("agent_a_id"):
        return _d(eco.get("spectator_seed_a") or book.get("seed_a"))
    if agent_id == match.get("agent_b_id"):
        return _d(eco.get("spectator_seed_b") or book.get("seed_b"))
    return Decimal("0")


def _proofs(match: dict[str, Any]) -> dict[str, Any]:
    onchain = match.get("onchain") or {}
    settle = match.get("onchain_settle") or (match.get("escrow") or {}).get("onchain_settle") or {}
    txs = []
    for t in onchain.get("txs") or []:
        txh = t.get("tx_hash") or ""
        if not txh:
            continue
        txs.append(
            {
                "step": t.get("step") or "",
                "tx_hash": txh,
                "explorer": t.get("explorer") or _explorer(txh),
            }
        )
    settle_hash = settle.get("tx_hash") or ""
    if settle_hash and not any(t["tx_hash"] == settle_hash for t in txs):
        txs.append(
            {
                "step": "resolveMatch",
                "tx_hash": settle_hash,
                "explorer": settle.get("explorer") or _explorer(settle_hash),
            }
        )
    create_h = onchain.get("create_tx_hash") or ""
    join_h = onchain.get("join_tx_hash") or ""
    return {
        "chain_id": match.get("chain_id") or onchain.get("chain_id") or "arc",
        "settlement_mode": match.get("settlement_mode") or ("onchain" if onchain else "demo_ledger"),
        "escrow": onchain.get("escrow") or "",
        "match_id_bytes32": match.get("match_id_bytes32") or onchain.get("match_id_bytes32") or "",
        "create_tx_hash": create_h,
        "join_tx_hash": join_h,
        "settle_tx_hash": settle_hash,
        "explorer_create": onchain.get("explorer_create") or _explorer(create_h),
        "explorer_join": onchain.get("explorer_join") or _explorer(join_h),
        "explorer_settle": settle.get("explorer") or _explorer(settle_hash),
        "txs": txs,
        "settle_error": match.get("onchain_settle_error") or "",
    }


def _spectator_txs(book: dict[str, Any]) -> list[dict[str, str]]:
    txs: list[dict[str, str]] = []
    seen: set[str] = set()

    def _add(step: str, txh: Optional[str], href: Optional[str] = None) -> None:
        h = (txh or "").strip()
        if not h or h in seen:
            return
        seen.add(h)
        txs.append({"step": step, "tx_hash": h, "explorer": href or _explorer(h)})

    _add("openBook", book.get("open_tx_hash"), book.get("open_explorer"))
    for b in book.get("bets") or []:
        _add("deposit", b.get("tx_hash"), b.get("explorer"))
    for t in book.get("deposit_txs") or []:
        _add("deposit", t.get("tx_hash"), t.get("explorer"))
    _add("resolve", book.get("resolve_tx_hash"), book.get("resolve_explorer"))
    return txs


def _public_row(
    match: dict[str, Any],
    agents: dict[str, Any],
    live_book: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    white_id = match.get("white_agent_id")
    black_id = match.get("black_agent_id")
    winner_id = match.get("winner_agent_id")
    book = dict(match.get("spectator_book") or {})
    if live_book:
        book = {**book, **{k: v for k, v in live_book.items() if v not in (None, "", [], {})}}
    totals = book.get("totals") or {}
    pot = _d(totals.get("a")) + _d(totals.get("b"))
    spec_txs = _spectator_txs(book)
    pgn = match.get("pgn") or ""
    return {
        "match_id": match.get("match_id"),
        "game_id": match.get("game_id") or "agentic.chess_standard",
        "status": match.get("status"),
        "result": match.get("result"),
        "termination": match.get("termination"),
        "stake_usdc": _q(_d(match.get("stake_usdc"))),
        "created_at": match.get("created_at"),
        "settled_at": match.get("settled_at") or (match.get("escrow") or {}).get("settled_at"),
        "white": {
            "agent_id": white_id,
            "name": _name(white_id, agents),
            "wallet": _wallet(white_id, match, agents),
        },
        "black": {
            "agent_id": black_id,
            "name": _name(black_id, agents),
            "wallet": _wallet(black_id, match, agents),
        },
        "winner": (
            {
                "agent_id": winner_id,
                "name": _name(winner_id, agents),
            }
            if winner_id
            else None
        ),
        "proofs": _proofs(match),
        "spectator": {
            "status": book.get("status"),
            "pot_usdc": _q(pot),
            "mode": (book.get("payouts") or {}).get("mode"),
            "ledger_only": not spec_txs,
            "pool": book.get("pool") or "",
            "open_tx_hash": book.get("open_tx_hash") or "",
            "resolve_tx_hash": book.get("resolve_tx_hash") or "",
            "txs": spec_txs,
        },
        "skill_pnl": {
            "a": _q(_skill_pnl(match, match.get("agent_a_id") or "")),
            "b": _q(_skill_pnl(match, match.get("agent_b_id") or "")),
        },
        "pgn_preview": (pgn[:160] + "…") if len(pgn) > 160 else pgn,
    }


# ---------------------------------------------------------------- data source
#
# The hot matches.json only keeps live tables plus the last few settled games
# (AgentMatchService._archive_cold moves the rest to matches_archive.json), so
# metrics read from it alone only ever described a handful of recent games.
# Every metrics read now goes through `metric_matches()`.
#
# Matches live in the agentic database now (one row each); metric_matches()
# reads every row through an incremental, version-keyed projection cache.

MATCHES_FILE = "matches.json"
ARCHIVE_FILE = "matches_archive.json"
# Fields metrics never read and that dominate the archive's size (~190MB,
# mostly move lists): dropped from the cached projection.
_HEAVY_FIELDS = ("moves", "clock", "live_odds", "odds_history", "disbursement")


def _slim_match(m: dict[str, Any]) -> dict[str, Any]:
    out = {k: v for k, v in m.items() if k not in _HEAVY_FIELDS}
    pgn = out.get("pgn")
    if isinstance(pgn, str) and len(pgn) > 161:
        out["pgn"] = pgn[:161]  # enough for pgn_preview's "> 160 → …" check
    return out


def _slim_archive(raw: Any) -> dict[str, Any]:
    ms = (raw or {}).get("matches") or {}
    return {"matches": {mid: _slim_match(m) for mid, m in ms.items() if isinstance(m, dict)}}


def _archived_matches() -> dict[str, Any]:
    """Settled matches, slimmed (kept for callers; all matches live in the DB)."""
    return {mid: m for mid, m in metric_matches()["matches"].items() if m.get("status") == "settled"}


def metric_matches() -> dict[str, Any]:
    """Every match metrics should count — live and long-settled — from the
    agentic database; settled matches outside the hot set are slimmed of
    move lists.

    Same shape as matches.json ({"matches": {id: record}}); records are
    read-only cached views and must not be mutated. Only rows whose version
    changed since the previous call are re-read (db.tables.all_matches_projected).
    """
    from gaming.src.stack.agentic.db.tables import all_matches_projected, hot_matches
    from gaming.src.stack.agentic.json_cache import freeze

    merged = dict(all_matches_projected(_slim_match))
    # Live tables + the newest settled ones pass through untouched (as the
    # hot file did); only the long tail is slimmed.
    merged.update({m["match_id"]: freeze(m) for m in hot_matches() if m.get("match_id")})
    return {"matches": merged}


def _parse_ts(ts: Any) -> Optional[datetime]:
    try:
        dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except Exception:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _settled_at(m: dict[str, Any]) -> Optional[str]:
    return m.get("settled_at") or (m.get("escrow") or {}).get("settled_at")


def house_activity(*, now: Optional[datetime] = None, matches: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """Counts for the operator desk, over every match (hot + archive).

    games_24h       settled in the last 24h (uncapped)
    games_live      tables open / locking / locked / playing
    last_settled    the most recently settled match (public row)
    """
    from datetime import timedelta

    now = now or datetime.now(timezone.utc)
    store = matches if matches is not None else metric_matches()
    rows = list((store.get("matches") or {}).values())
    since = now - timedelta(hours=24)
    games_24h = 0
    last: Optional[dict[str, Any]] = None
    last_dt: Optional[datetime] = None
    for m in rows:
        if m.get("status") != "settled":
            continue
        dt = _parse_ts(_settled_at(m))
        if dt is None:
            continue
        if dt >= since:
            games_24h += 1
        if last_dt is None or dt > last_dt:
            last, last_dt = m, dt
    live = sum(1 for m in rows if m.get("status") in {"playing", "locking", "locked", "open"})
    last_row: dict[str, Any] = {}
    if last is not None:
        agents = (load_json("agents.json", {"agents": {}}).get("agents") or {})
        last_row = _public_row(last, agents)
    return {"games_24h": games_24h, "games_live": live, "last_settled": last_row}


def _lp_realized(agent_id: str, lp_pools: dict[str, Any]) -> Decimal:
    pool = (lp_pools.get("pools") or {}).get(agent_id) or {}
    total = Decimal("0")
    for pos in (pool.get("positions") or {}).values():
        total += _d(pos.get("realized_pnl"))
    return total


def build_public_metrics(
    *,
    matches: Optional[dict[str, Any]] = None,
    agents: Optional[dict[str, Any]] = None,
    lp_pools: Optional[dict[str, Any]] = None,
    limit: int = 100,
) -> dict[str, Any]:
    store = matches if matches is not None else metric_matches()
    agent_store = agents if agents is not None else load_json("agents.json", {"agents": {}})
    lp_store = lp_pools if lp_pools is not None else load_json("agent_lp_pools.json", {"pools": {}})
    from gaming.src.stack.agentic.economy.spectator import all_books

    spec_books = all_books()

    agent_map: dict[str, Any] = dict(agent_store.get("agents") or {})
    rows_src = list((store.get("matches") or {}).values())
    rows_src.sort(key=lambda m: m.get("created_at") or "", reverse=True)

    cards: dict[str, dict[str, Any]] = {}
    for aid, default_name in ((RAJA_ID, "Raja"), (NERO_ID, "Nero")):
        rec = agent_map.get(aid) or {}
        cards[aid] = _empty_card(aid, rec.get("name") or default_name, rec.get("wallet_address") or "")

    skill_volume = Decimal("0")
    spectator_volume = Decimal("0")
    settled_n = 0
    onchain_n = 0
    locked_n = 0
    # 30-day windows + on-chain-only volume
    from datetime import datetime as _dt, timedelta as _td, timezone as _tz

    cutoff_30d = _dt.now(_tz.utc) - _td(days=30)

    def _created_30d(m: dict[str, Any]) -> bool:
        ts = m.get("created_at") or ""
        try:
            return _dt.fromisoformat(ts).replace(tzinfo=_tz.utc) >= cutoff_30d
        except Exception:
            return False

    def _is_onchain(m: dict[str, Any]) -> bool:
        return bool(
            (m.get("onchain") or {}).get("create_tx_hash")
            or (m.get("spectator_book") or {}).get("open_tx_hash")
        )

    skill_volume_30d = Decimal("0")
    spectator_volume_30d = Decimal("0")
    onchain_skill_volume = Decimal("0")
    onchain_spectator_volume = Decimal("0")
    onchain_skill_volume_30d = Decimal("0")
    onchain_spectator_volume_30d = Decimal("0")

    public_rows: list[dict[str, Any]] = []
    for m in rows_src:
        status = m.get("status")
        stake = _d(m.get("stake_usdc"))
        in_30d = _created_30d(m)
        onchain = _is_onchain(m)
        if status in {"settled", "locked"}:
            skill_volume += stake * 2
            if in_30d:
                skill_volume_30d += stake * 2
            if onchain:
                onchain_skill_volume += stake * 2
                if in_30d:
                    onchain_skill_volume_30d += stake * 2
        if status == "settled":
            settled_n += 1
        if status == "locked":
            locked_n += 1
        if m.get("settlement_mode") == "onchain" or (m.get("onchain") or {}).get("create_tx_hash"):
            onchain_n += 1
        book = m.get("spectator_book") or {}
        totals = book.get("totals") or {}
        spec_pot = _d(totals.get("a")) + _d(totals.get("b")) + _d(totals.get("draw"))
        spectator_volume += spec_pot
        if in_30d:
            spectator_volume_30d += spec_pot
        if onchain and spec_pot > 0:
            onchain_spectator_volume += spec_pot
            if in_30d:
                onchain_spectator_volume_30d += spec_pot

        for aid in (m.get("agent_a_id"), m.get("agent_b_id")):
            if not aid:
                continue
            if aid not in cards:
                cards[aid] = _empty_card(aid, _name(aid, agent_map), _wallet(aid, m, agent_map))
            card = cards[aid]
            if status in {"settled", "locked"}:
                card["_stake"] = _d(card.get("_stake")) + stake
                if in_30d:
                    card["_stake_30d"] = _d(card.get("_stake_30d")) + stake
                if onchain:
                    card["_stake_onchain"] = _d(card.get("_stake_onchain")) + stake
                    if in_30d:
                        card["_stake_onchain_30d"] = _d(card.get("_stake_onchain_30d")) + stake
            if spec_pot > 0:
                card["_spec"] = _d(card.get("_spec")) + spec_pot
                if in_30d:
                    card["_spec_30d"] = _d(card.get("_spec_30d")) + spec_pot
                if onchain:
                    card["_spec_onchain"] = _d(card.get("_spec_onchain")) + spec_pot
                    if in_30d:
                        card["_spec_onchain_30d"] = _d(card.get("_spec_onchain_30d")) + spec_pot
            # creator earnings from settled spectator books
            full_book = spec_books.get(m.get("match_id") or "") or {}
            payouts = full_book.get("payouts") or {}
            for c in payouts.get("creators") or []:
                if str(c.get("creator_id") or "") != aid:
                    continue
                c_amt = _d(c.get("amount") or "0")
                card["_fees"] = _d(card.get("_fees")) + c_amt
                if in_30d:
                    card["_fees_30d"] = _d(card.get("_fees_30d")) + c_amt
            if status == "settled":
                card["played"] += 1
                winner = m.get("winner_agent_id")
                result = (m.get("result") or "").lower()
                if result in {"draw", "1/2-1/2"} or not winner:
                    card["draws"] += 1
                elif winner == aid:
                    card["wins"] += 1
                else:
                    card["losses"] += 1
                if m.get("white_agent_id") == aid:
                    card["white_games"] += 1
                if m.get("black_agent_id") == aid:
                    card["black_games"] += 1
                card["_pnl"] = _d(card.get("_pnl")) + _skill_pnl(m, aid)
                card["_seed"] = _d(card.get("_seed")) + _seed_spent(m, aid)
            if (m.get("onchain") or {}).get("create_tx_hash"):
                card["onchain_locks"] += 1

        if len(public_rows) < max(1, int(limit)):
            public_rows.append(
                _public_row(m, agent_map, spec_books.get(m.get("match_id") or ""))
            )

    out_cards = []
    for aid, card in cards.items():
        rec = agent_map.get(aid) or {}
        _stake_30d = _d(card.pop("_stake_30d", 0))
        _stake_on_30d = _d(card.pop("_stake_onchain_30d", 0))
        _stake_on = _d(card.pop("_stake_onchain", 0))
        _spec = _d(card.pop("_spec", 0))
        _spec_30d = _d(card.pop("_spec_30d", 0))
        _spec_on_30d = _d(card.pop("_spec_onchain_30d", 0))
        _spec_on = _d(card.pop("_spec_onchain", 0))
        card["skill_pnl_usdc"] = _q(_d(card.pop("_pnl", 0)))
        card["stake_volume_usdc"] = _q(_d(card.pop("_stake", 0)))
        card["stake_volume_30d_usdc"] = _q(_stake_30d)
        card["onchain_stake_volume_30d_usdc"] = _q(_stake_on_30d)
        card["onchain_stake_volume_usdc"] = _q(_stake_on)
        card["spectator_volume_usdc"] = _q(_spec)
        card["spectator_volume_30d_usdc"] = _q(_spec_30d)
        card["onchain_spectator_volume_30d_usdc"] = _q(_spec_on_30d)
        card["onchain_volume_30d_usdc"] = _q(_stake_on_30d + _spec_on_30d)
        card["fees_earned_usdc"] = _q(_d(card.pop("_fees", 0)))
        card["fees_earned_30d_usdc"] = _q(_d(card.pop("_fees_30d", 0)))
        card["seed_spent_usdc"] = _q(_d(card.pop("_seed", 0)))
        card["lp_realized_pnl_usdc"] = _q(_lp_realized(aid, lp_store))
        eco = rec.get("economy") or {}
        card["bankroll_usdc"] = eco.get("bankroll_usdc")
        card["wallet"] = card["wallet"] or rec.get("wallet_address") or ""
        out_cards.append(card)

    # Raja / Nero first, then anyone else
    order = {RAJA_ID: 0, NERO_ID: 1}
    out_cards.sort(key=lambda c: (order.get(c["agent_id"], 9), c["name"]))

    playing_n = sum(
        1
        for m in rows_src
        if m.get("status") in {"playing", "locking", "locked", "open"}
    )

    # Count hashes in memory — never block this request on sqlite.
    tx_seen: set[str] = set()
    tx_by_step: dict[str, int] = {}
    tx_rows: list[dict[str, Any]] = []
    tx_by_match: dict[str, int] = {}

    def _add_tx(h: Any, step: str, match_id: str, agent_id: str = "") -> None:
        txh = str(h or "").strip()
        if not txh or txh in tx_seen:
            return
        tx_seen.add(txh)
        tx_by_step[step or "tx"] = tx_by_step.get(step or "tx", 0) + 1
        tx_by_match[match_id] = tx_by_match.get(match_id, 0) + 1
        tx_rows.append(
            {
                "tx_hash": txh,
                "step": step or "tx",
                "match_id": match_id,
                "agent_id": agent_id,
                "explorer": _explorer(txh),
                "created_at": "",
            }
        )

    for m in rows_src:
        mid = str(m.get("match_id") or "")
        p = _proofs(m)
        _add_tx(p.get("create_tx_hash"), "lock", mid, m.get("agent_a_id") or "")
        _add_tx(p.get("join_tx_hash"), "join", mid, m.get("agent_b_id") or "")
        _add_tx(p.get("settle_tx_hash"), "settle", mid, m.get("winner_agent_id") or "")
        for t in p.get("txs") or []:
            _add_tx(t.get("tx_hash"), t.get("step") or "tx", mid)
        book = m.get("spectator_book") or {}
        _add_tx(book.get("open_tx_hash"), "openBook", mid)
        _add_tx(book.get("resolve_tx_hash"), "resolveBook", mid)
        for b in book.get("bets") or []:
            _add_tx(b.get("tx_hash"), "deposit", mid)
        for t in book.get("deposit_txs") or []:
            _add_tx(t.get("tx_hash"), t.get("step") or "deposit", mid)

    for card in out_cards:
        mids = {
            m.get("match_id")
            for m in rows_src
            if card["agent_id"] in {m.get("agent_a_id"), m.get("agent_b_id")}
        }
        card["tx_count"] = sum(tx_by_match.get(mid, 0) for mid in mids if mid)
        card["games_played"] = card["played"]

    return {
        "success": True,
        "generated_at": _now(),
        "source": "matches.json+matches_archive.json",
        "log": "data/agentic/house_log.db",
        "note": (
            "Games and on-chain hashes are stored in house_log.db. "
            "A lock hash on Arc testnet means that stake was real. "
            "Transaction count is unique hashes we recorded (lock/join/approve/settle/bets)."
        ),
        "volume": {
            "matches_total": len(rows_src),
            "matches_settled": settled_n,
            "matches_locked": locked_n,
            "matches_onchain": onchain_n,
            "games_played": settled_n + playing_n,
            "games_settled": settled_n,
            "games_live": playing_n,
            "transactions": len(tx_seen),
            "tx_by_step": tx_by_step,
            "skill_volume_usdc": _q(skill_volume),
            "spectator_volume_usdc": _q(spectator_volume),
            "volume_30d_usdc": _q(skill_volume_30d + spectator_volume_30d),
            "onchain_skill_volume_usdc": _q(onchain_skill_volume),
            "onchain_spectator_volume_usdc": _q(onchain_spectator_volume),
            "total_onchain_volume_usdc": _q(onchain_skill_volume + onchain_spectator_volume),
            "onchain_volume_30d_usdc": _q(
                onchain_skill_volume_30d + onchain_spectator_volume_30d
            ),
        },
        "agents": out_cards,
        "matches": public_rows,
        "transactions": tx_rows[: min(200, max(40, int(limit) * 3))],
    }


def public_metrics(limit: int = 100) -> dict[str, Any]:
    return build_public_metrics(limit=limit)
