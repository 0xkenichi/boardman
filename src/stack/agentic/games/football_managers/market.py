"""Transfer market — free agents + agent-to-agent bids (v0)."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Optional

from gaming.src.stack.agentic.games.football_managers.catalog import (
    get_player,
    is_available,
    list_players,
    set_owner,
)
from gaming.src.stack.agentic.games.football_managers.club import Club
from gaming.src.stack.agentic.games.football_managers.rules import MAX_SQUAD_SIZE


class MarketError(Exception):
    pass


@dataclass
class Bid:
    bid_id: str
    from_agent_id: str
    to_agent_id: str
    player_id: str
    price_usdc: str
    status: str = "open"  # open | accepted | rejected | expired


@dataclass
class Market:
    """In-memory market for a season process (v0)."""

    window_open: bool = True
    listings: dict[str, str] = field(default_factory=dict)  # player_id -> ask price
    bids: dict[str, Bid] = field(default_factory=dict)
    clubs: dict[str, Club] = field(default_factory=dict)

    def register_club(self, club: Club) -> None:
        self.clubs[club.agent_id] = club

    def buy_free_agent(self, agent_id: str, player_id: str) -> dict[str, Any]:
        if not self.window_open:
            raise MarketError("transfer_window_closed")
        club = self.clubs.get(agent_id)
        if not club:
            raise MarketError("club_not_registered")
        player = get_player(player_id)
        if not player:
            raise MarketError("player_not_found")
        if player.get("owner_agent_id"):
            raise MarketError("player_not_free")
        if not is_available(player):
            raise MarketError("player_licence_pending")  # before any budget moves
        if len(club.roster) >= MAX_SQUAD_SIZE:
            raise MarketError("squad_full")
        price = Decimal(str(player["game_price_usdc"]))
        if not club.can_afford(price):
            raise MarketError("insufficient_budget_or_wage_runway")
        club.set_budget(club.budget() - price)
        club.roster.append(player_id)
        set_owner(player_id, agent_id)
        return {
            "ok": True,
            "player_id": player_id,
            "price_usdc": str(price),
            "budget_usdc": club.budget_usdc,
            "roster": list(club.roster),
        }

    def list_player(self, agent_id: str, player_id: str, ask_usdc: Decimal | str) -> dict[str, Any]:
        if not self.window_open:
            raise MarketError("transfer_window_closed")
        club = self.clubs.get(agent_id)
        if not club or player_id not in club.roster:
            raise MarketError("not_owner")
        ask = Decimal(str(ask_usdc))
        if ask <= 0:
            raise MarketError("invalid_ask")
        self.listings[player_id] = str(ask)
        return {"ok": True, "player_id": player_id, "ask_usdc": str(ask)}

    def bid(
        self,
        from_agent_id: str,
        to_agent_id: str,
        player_id: str,
        price_usdc: Decimal | str,
    ) -> Bid:
        if not self.window_open:
            raise MarketError("transfer_window_closed")
        buyer = self.clubs.get(from_agent_id)
        seller = self.clubs.get(to_agent_id)
        if not buyer or not seller:
            raise MarketError("club_not_registered")
        if player_id not in seller.roster:
            raise MarketError("seller_not_owner")
        price = Decimal(str(price_usdc))
        if price <= 0:
            raise MarketError("invalid_price")
        if not buyer.can_afford(price):
            raise MarketError("insufficient_budget_or_wage_runway")
        if len(buyer.roster) >= MAX_SQUAD_SIZE:
            raise MarketError("squad_full")
        b = Bid(
            bid_id=f"bid_{uuid.uuid4().hex[:10]}",
            from_agent_id=from_agent_id,
            to_agent_id=to_agent_id,
            player_id=player_id,
            price_usdc=str(price),
        )
        self.bids[b.bid_id] = b
        return b

    def respond_bid(self, bid_id: str, agent_id: str, accept: bool) -> dict[str, Any]:
        if not self.window_open:
            raise MarketError("transfer_window_closed")
        b = self.bids.get(bid_id)
        if not b or b.status != "open":
            raise MarketError("bid_not_open")
        if b.to_agent_id != agent_id:
            raise MarketError("not_seller")
        if not accept:
            b.status = "rejected"
            return {"ok": True, "status": "rejected", "bid_id": bid_id}

        buyer = self.clubs[b.from_agent_id]
        seller = self.clubs[b.to_agent_id]
        price = Decimal(b.price_usdc)
        if b.player_id not in seller.roster:
            raise MarketError("seller_not_owner")
        if not buyer.can_afford(price):
            raise MarketError("buyer_cannot_afford")
        if len(buyer.roster) >= MAX_SQUAD_SIZE:
            raise MarketError("buyer_squad_full")

        seller.roster.remove(b.player_id)
        buyer.roster.append(b.player_id)
        buyer.set_budget(buyer.budget() - price)
        seller.set_budget(seller.budget() + price)
        set_owner(b.player_id, buyer.agent_id)
        self.listings.pop(b.player_id, None)
        b.status = "accepted"
        return {
            "ok": True,
            "status": "accepted",
            "bid_id": bid_id,
            "player_id": b.player_id,
            "price_usdc": b.price_usdc,
        }


# ===========================================================================
# v1 — the twice-per-season transfer window (mid-season + between seasons)
# ===========================================================================
# Sphera's offer-queue shape, ported: clubs list players (1% of the ask,
# charged up front, non-refundable), other clubs place bids into the queue,
# and the seller accepts or rejects. On acceptance the House re-validates
# everything, then moves the money on the ledger (seller nets price − 3.5%
# transfer tax; the tax goes to the House) and moves the player. Offers not
# answered by window close expire. Free agents are an instant buy.
#
# Agents see the window through the matchday ask ("transfer_window" payload)
# and act by adding market actions to their plan reply under "transfers".

import threading
from datetime import datetime, timezone

from gaming.src.stack.agentic import ledger as L
from gaming.src.stack.agentic.games.football_managers.rules import (
    LISTING_FEE_BPS,
    MIN_SQUAD_SIZE,
    TRANSFER_TAX_BPS,
    WAGE_RUNWAY_MATCHDAYS,
)
from gaming.src.stack.agentic.store import load_json, save_json

HOUSE_MARKET_WALLET = "afm_house_market"
_WINDOW_FILE = "afm_transfer_window.json"
# Tags buy/sale log entries settled under the cost-basis authority model, so
# scripts/repair_afm_transfer_authority.py only replays older entries (which
# debited the price from the budget on top of the squad commitment).
AUTHORITY_MODEL = "basis_v1"

_market_lock = threading.RLock()


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _mload() -> dict[str, Any]:
    d = load_json(_WINDOW_FILE, {}) or {}
    d.setdefault("windows", {})
    d.setdefault("listings", {})
    d.setdefault("offers", {})
    d.setdefault("log", [])
    return d


def _msave(d: dict[str, Any]) -> None:
    save_json(_WINDOW_FILE, d)


def _wallet_of(agent_id: str) -> str:
    from gaming.src.stack.agentic.games.football_managers.fillers import (
        is_filler,
        synthetic_wallet,
    )
    from gaming.src.stack.agentic.registry import get_registry

    if is_filler(agent_id):
        return synthetic_wallet(agent_id)
    try:
        a = get_registry().get_agent(agent_id) or {}
    except Exception:
        return ""
    return str(a.get("wallet_address") or "")


def _market_wallet(agent_id: str) -> str:
    """A wallet the club can pay market fees from; fail-closed without one."""
    w = _wallet_of(agent_id)
    if not w:
        raise MarketError("no_wallet")
    return w


def _open_window_of(d: dict[str, Any]) -> Optional[dict[str, Any]]:
    for w in d["windows"].values():
        if w.get("status") == "open":
            return w
    return None


def open_window(
    season_no: int,
    phase: str,
    *,
    closes_at: Optional[str] = None,
) -> dict[str, Any]:
    """Open (or keep) a transfer window: phase 'mid' or 'end'."""
    if phase not in ("mid", "end"):
        raise ValueError("phase must be 'mid' or 'end'")
    with _market_lock:
        d = _mload()
        cur = _open_window_of(d)
        key = f"{int(season_no)}:{phase}"
        if cur and cur.get("key") == key:
            return cur
        if cur:
            _expire_and_close(d, cur, reason=f"superseded by {key}")
        win = {
            "key": key,
            "season_no": int(season_no),
            "phase": phase,
            "status": "open",
            "opened_at": _now_iso(),
            "closes_at": closes_at,
            "closed_at": None,
            "closed_reason": None,
        }
        d["windows"][key] = win
        d["log"].append({"at": _now_iso(), "kind": "window_open", "key": key, "phase": phase})
        _msave(d)
        return win


def _expire_and_close(d: dict[str, Any], win: dict[str, Any], *, reason: str) -> None:
    for o in d["offers"].values():
        if o.get("window") == win["key"] and o.get("status") == "open":
            o["status"] = "expired"
            o["resolved_at"] = _now_iso()
    win["status"] = "closed"
    win["closed_at"] = _now_iso()
    win["closed_reason"] = reason
    d["log"].append({"at": _now_iso(), "kind": "window_close", "key": win["key"], "reason": reason})


def close_window(
    season_no: Optional[int] = None,
    phase: Optional[str] = None,
    *,
    reason: str = "window_closed",
) -> Optional[dict[str, Any]]:
    with _market_lock:
        d = _mload()
        win = _open_window_of(d)
        if not win:
            return None
        if season_no is not None and int(win["season_no"]) != int(season_no):
            return None
        if phase is not None and win["phase"] != phase:
            return None
        _expire_and_close(d, win, reason=reason)
        _msave(d)
        return win


def close_all_open(*, reason: str = "window_closed") -> int:
    n = 0
    with _market_lock:
        d = _mload()
        while True:
            win = _open_window_of(d)
            if not win:
                break
            _expire_and_close(d, win, reason=reason)
            n += 1
        _msave(d)
    return n


def window_status() -> dict[str, Any]:
    with _market_lock:
        d = _mload()
        win = _open_window_of(d)
        open_offers = sum(1 for o in d["offers"].values() if o.get("status") == "open")
        return {
            "open": bool(win),
            "phase": (win or {}).get("phase"),
            "season_no": (win or {}).get("season_no"),
            "closes_at": (win or {}).get("closes_at"),
            "listings": len(d["listings"]),
            "open_offers": open_offers,
        }


def _mid_matchday(season: dict[str, Any]) -> int:
    total = int(season.get("matchdays_total") or 0)
    return max(1, (total + 1) // 2)


def open_window_for_matchday(season: dict[str, Any], matchday: int) -> None:
    """Season clock hook: the mid-season matchday opens the window."""
    if int(matchday) != _mid_matchday(season):
        return
    no = int(season.get("season_no") or 0)
    info = (season.get("matchdays") or {}).get(str(matchday)) or {}
    open_window(no, "mid", closes_at=info.get("deadline_at"))


def close_window_for_matchday(season: dict[str, Any], matchday: int) -> None:
    """Season clock hook: the mid-season window shuts at the deadline."""
    if int(matchday) != _mid_matchday(season):
        return
    close_window(int(season.get("season_no") or 0), "mid", reason="mid_window_deadline")


def list_player(agent_id: str, player_id: str, ask_usdc: Decimal | str) -> dict[str, Any]:
    """Put a squad player on the transfer list (1% of ask, non-refundable)."""
    from gaming.src.stack.agentic.games.football_managers import club_store as CS

    with _market_lock:
        d = _mload()
        win = _open_window_of(d)
        if not win:
            raise MarketError("transfer_window_closed")
        if player_id not in CS.roster_ids(agent_id):
            raise MarketError("not_owner")
        if player_id in d["listings"]:
            raise MarketError("already_listed")
        player = get_player(player_id)
        if not player:
            raise MarketError("player_not_found")
        if not is_available(player):
            raise MarketError("player_licence_pending")  # no listing fee for an unsellable player
        ask = Decimal(str(ask_usdc))
        if ask <= 0:
            raise MarketError("invalid_ask")
        fee = (ask * Decimal(LISTING_FEE_BPS) / Decimal(10000)).quantize(Decimal("0.01"))
        wallet = _market_wallet(agent_id)
        if L.balance(wallet) < fee:
            raise MarketError("listing_fee_unaffordable")
        L.debit(wallet, fee, reason="afm_listing_fee", ref=player_id)
        L.credit(HOUSE_MARKET_WALLET, fee, reason="afm_listing_fee", ref=player_id)
        d["listings"][player_id] = {
            "player_id": player_id,
            "seller": agent_id,
            "ask_usdc": str(ask),
            "fee_usdc": str(fee),
            "listed_at": _now_iso(),
            "window": win["key"],
        }
        d["log"].append(
            {"at": _now_iso(), "kind": "list", "player_id": player_id, "seller": agent_id, "ask_usdc": str(ask), "fee_usdc": str(fee)}
        )
        _msave(d)
        return {"ok": True, "player_id": player_id, "ask_usdc": str(ask), "fee_usdc": str(fee)}


def _require_affordable(agent_id: str, price: Decimal, *, player_id: Optional[str] = None) -> None:
    """Balance authority covers the price plus the new wage's runway."""
    from gaming.src.stack.agentic.games.football_managers import club_store as CS

    balance = CS.transfer_balance(agent_id)
    runway = Decimal("0")
    if player_id:
        p = get_player(player_id) or {}
        runway = Decimal(str(p.get("wage_per_matchday_usdc") or "0")) * WAGE_RUNWAY_MATCHDAYS
    if balance < price + runway:
        raise MarketError("insufficient_budget_or_wage_runway")


def place_bid(buyer_agent_id: str, player_id: str, price_usdc: Decimal | str) -> dict[str, Any]:
    """Join the offer queue for a listed player (validated, not escrowed)."""
    from gaming.src.stack.agentic.games.football_managers import club_store as CS

    with _market_lock:
        d = _mload()
        win = _open_window_of(d)
        if not win:
            raise MarketError("transfer_window_closed")
        listing = d["listings"].get(player_id)
        if not listing:
            raise MarketError("player_not_listed")
        seller = listing["seller"]
        if buyer_agent_id == seller:
            raise MarketError("cannot_bid_on_own_player")
        price = Decimal(str(price_usdc))
        if price <= 0:
            raise MarketError("invalid_price")
        if len(CS.roster_ids(buyer_agent_id)) >= MAX_SQUAD_SIZE:
            raise MarketError("squad_full")
        _require_affordable(buyer_agent_id, price, player_id=player_id)
        offer_id = f"of_{uuid.uuid4().hex[:10]}"
        d["offers"][offer_id] = {
            "offer_id": offer_id,
            "player_id": player_id,
            "from": buyer_agent_id,
            "to": seller,
            "price_usdc": str(price),
            "status": "open",
            "window": win["key"],
            "created_at": _now_iso(),
            "resolved_at": None,
        }
        d["log"].append(
            {"at": _now_iso(), "kind": "bid", "offer_id": offer_id, "player_id": player_id, "from": buyer_agent_id, "price_usdc": str(price)}
        )
        _msave(d)
        return {"ok": True, "offer_id": offer_id, "player_id": player_id, "price_usdc": str(price)}


def respond_offer(offer_id: str, seller_agent_id: str, accept: bool) -> dict[str, Any]:
    """Seller verdict on a queued offer; acceptance settles through the ledger."""
    with _market_lock:
        d = _mload()
        win = _open_window_of(d)
        if not win:
            raise MarketError("transfer_window_closed")
        o = d["offers"].get(offer_id)
        if not o or o.get("status") != "open":
            raise MarketError("offer_not_open")
        if o.get("to") != seller_agent_id:
            raise MarketError("not_seller")
        if not accept:
            o["status"] = "rejected"
            o["resolved_at"] = _now_iso()
            _msave(d)
            return {"ok": True, "offer_id": offer_id, "status": "rejected"}
        return _settle_offer(d, o)


def _settle_offer(d: dict[str, Any], o: dict[str, Any]) -> dict[str, Any]:
    """Validate everything, then move money, then move the player."""
    from gaming.src.stack.agentic.games.football_managers import club_store as CS

    player_id = o["player_id"]
    buyer, seller = o["from"], o["to"]
    listing = d["listings"].get(player_id)
    if not listing or listing.get("seller") != seller:
        raise MarketError("player_no_longer_listed")
    if player_id not in CS.roster_ids(seller):
        raise MarketError("seller_not_owner")
    price = Decimal(o["price_usdc"])
    seller_roster = CS.roster_ids(seller)
    if len(CS.roster_ids(buyer)) >= MAX_SQUAD_SIZE:
        raise MarketError("buyer_squad_full")
    _require_affordable(buyer, price, player_id=player_id)
    # the seller must still field a legal XI + bench after the sale
    if len(seller_roster) - 1 < MIN_SQUAD_SIZE:
        raise MarketError("seller_below_min_squad")
    p = get_player(player_id)
    if not is_available(p):
        raise MarketError("player_licence_pending")  # before any money moves
    if p and str(p.get("slot") or "").upper() == "GK":
        gks = [
            pid
            for pid in seller_roster
            if str((get_player(pid) or {}).get("slot") or "").upper() == "GK"
        ]
        if len(gks) - 1 < 1:
            raise MarketError("seller_would_lose_only_goalkeeper")
    # ---- money first (fail-closed), then the football
    tax = (price * Decimal(TRANSFER_TAX_BPS) / Decimal(10000)).quantize(Decimal("0.000001"))
    net = price - tax
    bw, sw = _market_wallet(buyer), _market_wallet(seller)
    if L.balance(bw) < price:
        raise MarketError("buyer_wallet_short")
    try:
        L.debit(bw, price, reason="afm_transfer_fee", ref=player_id)
        L.credit(sw, net, reason="afm_transfer_sale", ref=player_id)
        if tax > 0:
            L.credit(HOUSE_MARKET_WALLET, tax, reason="afm_transfer_tax", ref=player_id)
    except Exception as exc:
        raise MarketError(f"ledger_settlement_failed:{exc}") from exc
    # authority: the buyer carries the player at the price paid (consumed
    # once, via its squad commitment); the seller books net − basis
    CS.move_player(
        player_id, from_agent=seller, to_agent=buyer, price=price, seller_net=net
    )
    d["listings"].pop(player_id, None)
    o["status"] = "accepted"
    o["resolved_at"] = _now_iso()
    for other in d["offers"].values():
        if other.get("player_id") == player_id and other.get("status") == "open":
            other["status"] = "rejected"
            other["resolved_at"] = _now_iso()
    d["log"].append(
        {"at": _now_iso(), "kind": "sale", "player_id": player_id, "from": seller, "to": buyer, "price_usdc": str(price), "tax_usdc": str(tax), "authority": AUTHORITY_MODEL}
    )
    _msave(d)
    return {
        "ok": True,
        "offer_id": o["offer_id"],
        "player_id": player_id,
        "status": "accepted",
        "price_usdc": str(price),
        "tax_usdc": str(tax),
        "seller_net_usdc": str(net),
    }


def buy_free_agent(agent_id: str, player_id: str) -> dict[str, Any]:
    """Instant purchase of an unowned catalog player while the window is open."""
    from gaming.src.stack.agentic.games.football_managers import club_store as CS

    with _market_lock:
        d = _mload()
        win = _open_window_of(d)
        if not win:
            raise MarketError("transfer_window_closed")
        player = get_player(player_id)
        if not player:
            raise MarketError("player_not_found")
        if (
            player.get("owner_agent_id")
            or player_id in d["listings"]
            or CS.club_of_player(player_id)  # catalog owners reset on restart
        ):
            raise MarketError("player_not_free")
        if not is_available(player):
            raise MarketError("player_licence_pending")  # before any money moves
        if len(CS.roster_ids(agent_id)) >= MAX_SQUAD_SIZE:
            raise MarketError("squad_full")
        price = Decimal(str(player["game_price_usdc"]))
        _require_affordable(agent_id, price, player_id=player_id)
        wallet = _market_wallet(agent_id)
        if L.balance(wallet) < price:
            raise MarketError("buyer_wallet_short")
        L.debit(wallet, price, reason="afm_free_agent_fee", ref=player_id)
        L.credit(HOUSE_MARKET_WALLET, price, reason="afm_free_agent_fee", ref=player_id)
        # the squad commitment (basis = price) consumes the price once
        CS.move_player(player_id, from_agent=None, to_agent=agent_id, price=price)
        d["log"].append(
            {"at": _now_iso(), "kind": "free_agent", "player_id": player_id, "club": agent_id, "price_usdc": str(price), "authority": AUTHORITY_MODEL}
        )
        _msave(d)
        return {"ok": True, "player_id": player_id, "price_usdc": str(price)}


def release_player(agent_id: str, player_id: str) -> dict[str, Any]:
    """Release a squad player to the free market while the window is open.

    No fee comes back: the cost basis is written off and only the wage runway
    returns to the club's transfer balance. The same squad floor as a sale
    applies (XI + bench depth, never the only keeper).
    """
    from gaming.src.stack.agentic.games.football_managers import club_store as CS

    with _market_lock:
        d = _mload()
        win = _open_window_of(d)
        if not win:
            raise MarketError("transfer_window_closed")
        roster = CS.roster_ids(agent_id)
        if player_id not in roster:
            raise MarketError("not_owner")
        if len(roster) - 1 < MIN_SQUAD_SIZE:
            raise MarketError("below_min_squad")
        p = get_player(player_id) or {}
        if str(p.get("slot") or "").upper() == "GK":
            gks = [
                pid
                for pid in roster
                if str((get_player(pid) or {}).get("slot") or "").upper() == "GK"
            ]
            if len(gks) - 1 < 1:
                raise MarketError("would_lose_only_goalkeeper")
        written_off = CS.release_player(agent_id, player_id)
        # a released player is off the transfer list and out of every offer
        d["listings"].pop(player_id, None)
        for o in d["offers"].values():
            if o.get("player_id") == player_id and o.get("status") == "open":
                o["status"] = "rejected"
                o["resolved_at"] = _now_iso()
        d["log"].append(
            {"at": _now_iso(), "kind": "release", "player_id": player_id, "club": agent_id, "basis_usdc": str(written_off)}
        )
        _msave(d)
        return {"ok": True, "player_id": player_id, "written_off_usdc": str(written_off)}


def execute_transfers(agent_id: str, actions: Any) -> list[dict[str, Any]]:
    """Run a manager's market actions (from a plan reply); never raises."""
    out: list[dict[str, Any]] = []
    for t in actions or []:
        if not isinstance(t, dict):
            out.append({"action": "?", "ok": False, "error": "action_not_an_object"})
            continue
        action = str(t.get("action") or "")
        try:
            if action == "list":
                r = list_player(agent_id, str(t.get("player_id") or ""), t.get("ask_usdc") or 0)
            elif action == "bid":
                r = place_bid(agent_id, str(t.get("player_id") or ""), t.get("price_usdc") or 0)
            elif action == "respond":
                r = respond_offer(str(t.get("offer_id") or ""), agent_id, bool(t.get("accept")))
            elif action == "buy_free_agent":
                r = buy_free_agent(agent_id, str(t.get("player_id") or ""))
            else:
                r = {"ok": False, "error": f"unknown_action_{action or 'none'}"}
        except MarketError as exc:
            r = {"ok": False, "error": str(exc)}
        except Exception as exc:  # a bad action never kills the matchday
            r = {"ok": False, "error": f"market_error:{exc}"}
        out.append({"action": action, **r})
    return out


def _free_agents(agent_id: str, *, cap: int = 40) -> list[dict[str, Any]]:
    """Cheapest free agents the club could actually afford, catalog order."""
    from gaming.src.stack.agentic.games.football_managers import club_store as CS

    balance = CS.transfer_balance(agent_id)
    CS.sync_catalog_owners()  # never offer a rostered player as free after a restart
    out: list[dict[str, Any]] = []
    for p in list_players(free_only=True):
        price = Decimal(str(p["game_price_usdc"]))
        runway = Decimal(str(p.get("wage_per_matchday_usdc") or "0")) * WAGE_RUNWAY_MATCHDAYS
        if price + runway <= balance:
            out.append(p)
        if len(out) >= cap:
            break
    return out


def window_ask_payload(agent_id: str) -> Optional[dict[str, Any]]:
    """The 'transfer_window' block of the matchday ask (None when closed)."""
    from gaming.src.stack.agentic.games.football_managers import club_store as CS
    from gaming.src.stack.agentic.games.football_managers.club_store import (
        _formation_slots,
    )

    with _market_lock:
        d = _mload()
        win = _open_window_of(d)
        if not win:
            return None
        club = CS.get_club(agent_id) or {}
        roster = CS.roster_ids(agent_id)
        # squad needs: formation slots the roster does not cover, plus depth to 16
        needs: dict[str, int] = {}
        for slot in _formation_slots(str(club.get("formation") or "4-3-3")):
            covered = [
                pid
                for pid in roster
                if str((get_player(pid) or {}).get("slot") or "") == slot
            ]
            shortfall = 1 - len(covered)
            if shortfall > 0:
                needs[slot] = needs.get(slot, 0) + shortfall
        if len(roster) < MIN_SQUAD_SIZE:
            needs["BENCH"] = MIN_SQUAD_SIZE - len(roster)
        open_offers = sorted(
            (o for o in d["offers"].values() if o.get("status") == "open"),
            key=lambda o: str(o.get("created_at") or ""),
        )
        mine_in = [o for o in open_offers if o.get("to") == agent_id]
        mine_out = [o for o in open_offers if o.get("from") == agent_id]
        listings = sorted(d["listings"].values(), key=lambda l: Decimal(l["ask_usdc"]))
        return {
            "open": True,
            "phase": win["phase"],
            "season_no": win["season_no"],
            "closes_at": win.get("closes_at"),
            "transfer_balance_usdc": str(CS.transfer_balance(agent_id)),
            "squad_size": len(roster),
            "min_squad": MIN_SQUAD_SIZE,
            "max_squad": MAX_SQUAD_SIZE,
            "needs": needs,
            "my_listings": [
                {
                    "player_id": l["player_id"],
                    "ask_usdc": l["ask_usdc"],
                    "open_offers": sum(1 for o in mine_in if o["player_id"] == l["player_id"]),
                }
                for l in listings
                if l.get("seller") == agent_id
            ],
            "incoming_offers": [
                {"offer_id": o["offer_id"], "player_id": o["player_id"], "price_usdc": o["price_usdc"]}
                for o in mine_in
            ],
            "outgoing_offers": [
                {"offer_id": o["offer_id"], "player_id": o["player_id"], "price_usdc": o["price_usdc"]}
                for o in mine_out
            ],
            "transfer_list": [
                {"player_id": l["player_id"], "ask_usdc": l["ask_usdc"], "seller": l["seller"]}
                for l in listings[:40]
            ],
            "free_agents": [
                {"player_id": p["player_id"], "price_usdc": str(p["game_price_usdc"]), "slot": p["slot"]}
                for p in _free_agents(agent_id, cap=40)
            ],
            "rules": {
                "listing_fee_bps": LISTING_FEE_BPS,
                "transfer_tax_bps": TRANSFER_TAX_BPS,
                "note": "list: 1% of ask charged now; sale: seller nets price − 3.5% tax; unanswered offers expire at close",
            },
        }
