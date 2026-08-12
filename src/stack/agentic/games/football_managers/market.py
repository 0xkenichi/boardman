"""Transfer market — free agents + agent-to-agent bids (v0)."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Optional

from gaming.src.stack.agentic.games.football_managers.catalog import get_player, set_owner
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
