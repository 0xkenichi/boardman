"""AFM manager marketplace — owners create, acquire or sell a manager agent.

The owner seat, step 1: "Create or acquire an agent." Three doors:

- **create** — register a new manager agent against the playbook: pick a
  mind archetype the decide loop understands, name it, and seed it a club
  with an affordable auto-roster. It joins the league at the next season
  open like any other club.
- **acquire** — adopt an *unlisted* developer-built manager from the
  marketplace (any registered AFM agent): ownership (``owner_id``) moves to
  the caller for free (the step-1 demo path).
- **sell / buy** — any owner (typically the developer who built the manager)
  can list it with a **price** and a **creator cut** (the developer's % of
  each sale). A listed manager can no longer be adopted free: a buyer
  *purchases* it and ownership transfers. On resale by a later owner the
  creator cut keeps paying the original developer; when the developer sells
  their own build they receive the full price.

Settlement runs on one of two rails (never mixed, recorded per sale):

- **ledger** (default) — book-entry demo USDC (buyer wallet → seller
  proceeds + creator cut), faucet-topping the buyer's demo wallet when short.
- **onchain** — real Arc USDC from the buyer's **bound Circle wallet** to
  the seller (plus the developer's creator cut on a resale). Parties bind a
  payout address / wallet via ``bind_party_wallet``; a sale settles on this
  rail automatically when Circle is configured and every party has a wallet,
  and never falls back silently if a live transfer fails. The demo ledger is
  untouched on this rail.

Marketplace rows are a safe projection of the registry record (no private
keys — those never live in the registry) plus live club state. The demo
built-ins (Blue Lock / Ao Ashi) ship listed by their developers so the
marketplace has real, priced inventory.
"""
from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional

from gaming.src.stack.agentic.games.football_managers.club_store import (
    STARTING_BUDGET_USDC,
    ensure_club_for_agent,
    get_club,
)
from gaming.src.stack.agentic.games.football_managers.manager_card import manager_card
from gaming.src.stack.agentic.games.football_managers.rules import FORMATIONS, GAME_ID
from gaming.src.stack.agentic.economy.fees import MAX_CREATOR_FEE_BPS
from gaming.src.stack.agentic.store import load_json, save_json

# A seller's creator cut on a manager sale is capped the same way the creator
# fee on match winnings is — one policy number for creator income.
MAX_SALE_CREATOR_CUT_BPS = MAX_CREATOR_FEE_BPS  # 2000 bps = 20%

# Developer-built demo managers ship listed so the marketplace has real
# inventory (price + developer cut). Only applied while the agent is still
# owned by its developer — an adopted manager is never forced onto sale.
DEMO_LISTING_DEFAULTS: dict[str, dict[str, Any]] = {
    "agent_bluelock_demo": {"price_usdc": "25.00", "creator_cut_bps": 500},
    "agent_aoashi_demo": {"price_usdc": "20.00", "creator_cut_bps": 500},
    "agent_matchslice_demo": {"price_usdc": "22.00", "creator_cut_bps": 500},
}

# Archetypes the playbook (decide loop) understands. Each entry is the
# marketplace-facing identity of a strategy in decide.STRATEGIES.
ARCHETYPES: dict[str, dict[str, str]] = {
    "striker": {
        "name": "The Striker Ego",
        "blurb": (
            "Stars over system: highest-rated XI, attack-first shapes "
            "(3-4-3 / 4-3-3), never parks the bus. Blue Lock school."
        ),
    },
    "tactician": {
        "name": "The Total Footballer",
        "blurb": (
            "System over stars: position-disciplined XI, balanced shapes "
            "(4-2-3-1 / 4-1-4-1), reads the opponent and adapts. Ao Ashi school."
        ),
    },
    "pragmatist": {
        "name": "The Pragmatist",
        "blurb": (
            "Low block and counters: disciplined 5-3-2 / 4-1-4-1, absorbs "
            "pressure, hits on the break."
        ),
    },
    "possession": {
        "name": "The Possession Coach",
        "blurb": (
            "Keep the ball: tiki-taka shapes (4-3-3 / 4-1-4-1), patient "
            "buildup, counter only when chased."
        ),
    },
    "balanced": {
        "name": "The Solo Brain",
        "blurb": (
            "Mid-block and discipline: 4-3-3 / 4-2-3-1 with always one "
            "pivot, spine-first squad, counters aggressive sides. "
            "Match-Slice school."
        ),
    },
}

DEMO_OWNER_ID = "demo_owner"

# ------------------------------------------------------------ real USDC rail
#
# Beyond the demo ledger, a sale can settle in real USDC on Arc when every
# party has a wallet the platform can move money from / to:
#
#   buyer   — must have a Circle wallet bound to their id (wallet_id + address)
#             so ``CircleWalletService.transfer_usdc`` can pay from it.
#   seller  — payout address: a party binding, or the registered agent wallet
#             when the party is itself a registered AFM agent.
#   creator — same resolver; on a resale the developer's cut is a second leg.
#
# Dual mode: when the rail isn't ready the sale settles on the demo ledger
# exactly as before. A sale never silently mixes rails — ``mode`` is recorded
# on every receipt.

PARTY_WALLETS_FILE = "party_wallets.json"


def _load_party_wallets() -> dict[str, Any]:
    return load_json(PARTY_WALLETS_FILE, {"wallets": {}}).get("wallets") or {}


def _save_party_wallets(wallets: dict[str, Any]) -> None:
    save_json(PARTY_WALLETS_FILE, {"wallets": wallets})


def _norm_address(address: str) -> str:
    a = (address or "").strip().lower()
    if not a.startswith("0x"):
        a = "0x" + a
    if len(a) != 42:
        raise ValueError(f"invalid wallet address: {address}")
    return a


def bind_party_wallet(
    *,
    party_id: str,
    address: str,
    wallet_id: Optional[str] = None,
    chain_id: str = "arc",
) -> dict[str, Any]:
    """Bind a payout/send wallet to a marketplace party (owner / creator / buyer).

    ``address`` is where the party receives USDC on Arc. Pass ``wallet_id``
    too when the party pays (a Circle developer-controlled wallet id) so the
    platform can move USDC out of it on a purchase.
    """
    party_id = (party_id or "").strip()
    if not party_id:
        raise ValueError("party_id is required")
    addr = _norm_address(address)
    chain_id = (chain_id or "arc").strip().lower()
    wallets = _load_party_wallets()
    rec: dict[str, Any] = {
        "party_id": party_id,
        "address": addr,
        "wallet_id": (wallet_id or "").strip() or None,
        "can_send": bool((wallet_id or "").strip()),
        "chain_id": chain_id,
        "bound_at": _now(),
        "updated_at": _now(),
    }
    wallets[party_id] = rec
    _save_party_wallets(wallets)
    return rec


def unbind_party_wallet(
    *, party_id: str, address: Optional[str] = None
) -> bool:
    """Remove a party's wallet binding. With ``address``, refuse if it doesn't
    match the bound wallet (so only the right party can unbind)."""
    party_id = (party_id or "").strip()
    wallets = _load_party_wallets()
    if party_id not in wallets:
        return False
    if address:
        if wallets[party_id].get("address") != _norm_address(address):
            raise ValueError("address does not match the bound wallet")
    del wallets[party_id]
    _save_party_wallets(wallets)
    return True


def get_party_wallet(party_id: str) -> Optional[dict[str, Any]]:
    """A party's real wallet — bound record, or the registered agent wallet
    when the party is itself a registered agent (receiving only, no send
    wallet_id on the registry)."""
    party_id = (party_id or "").strip()
    if not party_id:
        return None
    bound = _load_party_wallets().get(party_id)
    if bound:
        return dict(bound)
    try:
        from gaming.src.stack.agentic.registry import get_registry

        rec = get_registry().get_agent(party_id)
        if rec and rec.get("wallet_address"):
            return {
                "party_id": party_id,
                "address": str(rec["wallet_address"]).lower(),
                "wallet_id": None,
                "can_send": False,
                "chain_id": rec.get("chain_id") or "arc",
                "source": "registry_agent",
            }
    except Exception:
        pass
    return None


def party_payout_address(party_id: str) -> Optional[str]:
    w = get_party_wallet(party_id)
    return (w or {}).get("address")


def party_send_wallet(party_id: str) -> Optional[dict[str, Any]]:
    """A wallet the platform can pay FROM (needs a Circle wallet_id + address)."""
    w = get_party_wallet(party_id)
    if not w or not w.get("wallet_id") or not w.get("address"):
        return None
    return w


def circle_configured() -> bool:
    """Circle W3S keys present — the real-USDC rail needs them to move funds."""
    return bool(
        (os.getenv("CIRCLE_API_KEY") or "").strip()
        and (os.getenv("CIRCLE_ENTITY_SECRET") or "").strip()
    )


def _circle(chain_id: str = "arc"):
    """A CircleWalletService for a chain (monkeypatch seam in tests)."""
    from backend.circle_wallet_service import CircleWalletService
    from gaming.src.backend.services.chains import (
        get_circle_blockchain,
        get_circle_usdc_token_id,
        get_rpc_url,
        get_usdc_address,
    )

    return CircleWalletService(
        blockchain=get_circle_blockchain(chain_id),
        usdc_address=get_usdc_address(chain_id),
        usdc_token_id=get_circle_usdc_token_id(chain_id) or None,
        rpc_url=get_rpc_url(chain_id),
    )


def _listing_cut(a: dict[str, Any]) -> int:
    return _clamp_sale_cut(int((_listing_of(a) or {}).get("creator_cut_bps") or 0))


def onchain_ready_for_sale(a: dict[str, Any], buyer_id: str) -> tuple[bool, list[str]]:
    """Can THIS sale move real USDC? ``(ready, reasons)`` — when not ready the
    caller falls back to the demo ledger (dual mode) unless onchain was forced."""
    reasons: list[str] = []
    if not circle_configured():
        reasons.append(
            "Circle not configured (set CIRCLE_API_KEY and CIRCLE_ENTITY_SECRET)"
        )
    buyer = party_send_wallet(buyer_id)
    if not buyer:
        reasons.append(f"buyer {buyer_id} has no Circle wallet bound (wallet_id + address)")
    seller = str(a.get("owner_id") or a.get("creator_id") or "")
    creator = str(a.get("creator_id") or seller)
    if not party_payout_address(seller):
        reasons.append(f"seller {seller} has no payout address bound")
    if seller != creator and _listing_cut(a) > 0 and not party_payout_address(creator):
        reasons.append(f"creator {creator} has no payout address bound")
    return (not reasons), reasons


def listing_onchain_payable(a: dict[str, Any]) -> bool:
    """Buyer-independent: could a sale of this manager settle in real USDC
    today (current owner + developer both have payout addresses)?"""
    seller = str(a.get("owner_id") or a.get("creator_id") or "")
    creator = str(a.get("creator_id") or seller)
    if not party_payout_address(seller):
        return False
    if seller != creator and _listing_cut(a) > 0 and not party_payout_address(creator):
        return False
    return True


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", (name or "").strip().lower()).strip("_")
    return slug or "manager"


def _unique_agent_id(base: str) -> str:
    """agent_<slug>, deduped with -2 / -3 … against the live registry."""
    from gaming.src.stack.agentic.registry import get_registry

    existing = {a["agent_id"] for a in get_registry().list_agents()}
    candidate = f"agent_{base}"
    if candidate not in existing:
        return candidate
    i = 2
    while f"{candidate}_{i}" in existing:
        i += 1
    return f"{candidate}_{i}"


def _archetype_of(agent: dict[str, Any]) -> str:
    mind = agent.get("mind") or {}
    arch = str(mind.get("archetype") or "").strip()
    if arch in ARCHETYPES:
        return arch
    # fallback by identity so any playable agent gets a label
    aid = str(agent.get("agent_id") or "").lower()
    if "bluelock" in aid:
        return "striker"
    if "aoashi" in aid:
        return "tactician"
    return arch or "tactician"


def _listing_of(agent: dict[str, Any]) -> Optional[dict[str, Any]]:
    l = agent.get("listing")
    return l if isinstance(l, dict) else None


def _market_row(agent: dict[str, Any]) -> dict[str, Any]:
    arch = _archetype_of(agent)
    mind = agent.get("mind") or {}
    runtime = agent.get("runtime") or {}
    club = get_club(str(agent.get("agent_id") or ""))
    creator_id = str(agent.get("creator_id") or "")
    owner_id = str(agent.get("owner_id") or creator_id or "unknown")
    blurb = str(mind.get("blurb") or runtime.get("notes") or "").strip() or (
        ARCHETYPES.get(arch, {}).get("blurb", "")
    )
    listing = _listing_of(agent)
    pending = [
        o
        for o in (agent.get("offers") or [])
        if isinstance(o, dict) and o.get("status") == "pending"
    ]
    pending.sort(key=lambda o: str(o.get("created_at") or ""), reverse=True)
    return {
        "agent_id": str(agent.get("agent_id") or ""),
        "name": str(agent.get("name") or agent.get("agent_id") or "Unnamed"),
        "creator_id": creator_id,
        "owner_id": owner_id,
        "archetype": arch,
        "archetype_name": ARCHETYPES.get(arch, {}).get("name", arch),
        "strategy_id": str(agent.get("strategy_id") or ""),
        "version": str(agent.get("version") or "1.0.0"),
        "blurb": blurb,
        "stats": dict(agent.get("stats") or {}),
        "has_club": club is not None,
        "club_name": club.get("club_name") if club else None,
        "builtin": creator_id.startswith("creator_"),
        "adopted": bool(owner_id != creator_id),
        "created_at": str(agent.get("created_at") or ""),
        # the webhook hosting this manager's brain (owner-set; the House asks it
        # before each matchday, falling back to the deterministic playbook)
        "webhook_url": str(agent.get("webhook_url") or "") or None,
        # for-sale listing (None until the owner lists it)
        "listed": listing is not None,
        "price_usdc": str(listing.get("price_usdc")) if listing else None,
        "creator_cut_bps": int(listing.get("creator_cut_bps") or 0) if listing else None,
        "listed_at": str(listing.get("listed_at") or "") if listing else None,
        "seller_id": str(listing.get("seller_id") or owner_id) if listing else None,
        # offers against a listed manager (pending only — the owner reviews these)
        "reserve_usdc": str(listing.get("reserve_price_usdc")) if listing and listing.get("reserve_price_usdc") else None,
        "accepting_offers": bool(listing),
        "pending_offers": [
            {
                "offer_id": str(o.get("offer_id") or ""),
                "buyer_id": str(o.get("buyer_id") or ""),
                "amount_usdc": str(o.get("amount_usdc") or "0"),
                "created_at": str(o.get("created_at") or ""),
            }
            for o in pending
        ],
        "sales_count": int(agent.get("sales_count") or 0),
        # real-USDC settlement possible for a sale today (owner + developer have
        # payout addresses bound) — the buyer still needs their own wallet too
        "onchain_payable": listing_onchain_payable(agent),
        # the detail card: playbook + ability radars and the season record
        "card": manager_card(agent, archetype=arch),
    }


def list_market_agents() -> list[dict[str, Any]]:
    """Every AFM manager on the marketplace — developer-built first, then owner-created.

    Ensures the demo managers are registered (idempotent), mirroring what the
    clubs/market endpoints do, so a fresh boot still lists the league's
    developer-built managers alongside any owner-created ones.
    """
    from gaming.src.stack.agentic.registry import get_registry

    reg = get_registry()
    reg.ensure_demo_agents()
    _ensure_demo_listings()
    rows = [
        _market_row(a)
        for a in get_registry().list_agents()
        if GAME_ID in (a.get("game_ids") or [])
        and (a.get("role") or "contestant") != "house"
    ]
    rows.sort(key=lambda r: (0 if r["builtin"] else 1, r["name"].lower()))
    return rows


def create_manager_agent(
    *,
    manager_name: str,
    club_name: Optional[str] = None,
    archetype: str = "tactician",
    formation: str = "4-3-3",
    owner_id: Optional[str] = None,
    creator_id: Optional[str] = None,
    list_price_usdc: Optional[str] = None,
    creator_cut_bps: Optional[int] = None,
) -> dict[str, Any]:
    """Build a manager against the playbook: register the agent + seed its club.

    The agent gets a wallet + identity like any demo manager, a mind carrying
    the chosen archetype (which drives every matchday decision), and a club
    with an affordable auto-roster and legal default XI. The next season open
    picks it up automatically.

    Pass ``list_price_usdc`` to put the manager up for sale immediately
    (with ``creator_cut_bps`` as the developer's % of each sale).
    """
    arch = str(archetype or "tactician").strip().lower()
    if arch not in ARCHETYPES:
        raise ValueError(f"unknown archetype: {archetype} (use one of {', '.join(sorted(ARCHETYPES))})")
    formation = str(formation or "4-3-3").strip()
    if formation not in FORMATIONS:
        raise ValueError(f"formation not allowed: {formation} (use one of {', '.join(FORMATIONS)})")

    manager_name = (manager_name or "").strip() or "New Manager"
    owner_id = (owner_id or "").strip() or DEMO_OWNER_ID
    creator_id = (creator_id or "").strip() or owner_id
    agent_id = _unique_agent_id(_slugify(manager_name))

    from gaming.src.stack.agentic.registry import get_registry

    meta = ARCHETYPES[arch]
    mind = {
        "archetype": arch,
        "directive": "Run the club: set a legal XI, bench and tactics before every deadline.",
        "blurb": meta["blurb"],
    }
    rec = get_registry().register_agent(
        agent_id=agent_id,
        name=manager_name,
        owner_id=owner_id,
        creator_id=creator_id,
        strategy_id=f"{arch}_playbook",
        openings=[],
        mind=mind,
        game_ids=[GAME_ID],
        seed=f"boardman.agent.afm.{agent_id}",
        version="1.0.0",
        creator_fee_bps=500,
        economy={
            "bankroll_usdc": "500",
            "max_stake_usdc": "50",
            "min_stake_usdc": "1",
            "creator_fee_bps": 500,
            "reserve_bps": 1500,
            "preferred_time_controls": [],
            "auto_challenge": False,
            "notes": f"Owner-built manager — {arch} playbook.",
        },
        runtime={
            "engine": "boardman.afm.v1",
            "hosted_by": creator_id,
            "goal": "win matches & grow the club",
            "strength_tier": "custom",
            "notes": f"Built in the owner seat ({arch} playbook). Club seeded on create.",
        },
    )
    club = ensure_club_for_agent(
        agent_id,
        club_name=(club_name or "").strip() or None,
        formation=formation,
        budget=STARTING_BUDGET_USDC,
    )
    row = _market_row(rec)
    if list_price_usdc is not None:
        row = list_manager_for_sale(
            agent_id=agent_id,
            price_usdc=list_price_usdc,
            creator_cut_bps=creator_cut_bps,
            listed_by=owner_id,
        )["agent"]
    return {"agent": row, "club": club}


def acquire_manager_agent(*, agent_id: str, owner_id: Optional[str] = None) -> dict[str, Any]:
    """Adopt a developer-built manager: ownership (owner_id) moves to the caller."""
    from gaming.src.stack.agentic.registry import get_registry
    from gaming.src.stack.agentic.store import load_json, save_json

    owner_id = (owner_id or "").strip() or DEMO_OWNER_ID
    reg = get_registry()
    rec = reg.get_agent(agent_id)
    if not rec:
        raise ValueError(f"no such agent: {agent_id}")
    if GAME_ID not in (rec.get("game_ids") or []):
        raise ValueError(f"{agent_id} is not an AFM manager agent")

    data = load_json("agents.json", {"agents": {}})
    a = data.get("agents", {}).get(agent_id)
    if not a:
        raise ValueError(f"no such agent: {agent_id}")
    if _listing_of(a):
        raise ValueError(
            f"{agent_id} is listed for sale — purchase it instead of adopting"
        )
    previous_owner = str(a.get("owner_id") or "")
    a["owner_id"] = owner_id
    a["acquired_by"] = owner_id
    a["acquired_at"] = _now()
    a["updated_at"] = _now()
    save_json("agents.json", data)
    return {"agent": _market_row(a), "previous_owner_id": previous_owner}


# ------------------------------------------------------------ sale rails

def _bps_of(amount: Decimal, bps: int) -> Decimal:
    return (amount * Decimal(int(bps)) / Decimal(10_000)).quantize(Decimal("0.01"))


def _owner_party_wallet(party_id: str) -> str:
    """A party's demo-ledger wallet.

    Registered agents pay with their own registry wallet. Developer studios
    (``creator_*``) and humans use the pseudo-wallets already established by
    the match fee router: ``creator:{id}`` and ``owner:{id}``.
    """
    try:
        from gaming.src.stack.agentic.registry import get_registry

        rec = get_registry().get_agent(party_id)
        if rec and rec.get("wallet_address"):
            return str(rec["wallet_address"])
    except Exception:
        pass
    if party_id.startswith("creator_"):
        return f"creator:{party_id}"
    return f"owner:{party_id}"


def _clamp_sale_cut(bps: int) -> int:
    return max(0, min(int(bps or 0), MAX_SALE_CREATOR_CUT_BPS))


def _ensure_demo_listings() -> None:
    """Give the developer-built demo managers their default for-sale listing.

    Idempotent and never overrides: an existing listing stands, and a manager
    that has already been adopted (owner != creator) is never forced onto
    sale — only its current owner may list it.
    """
    from gaming.src.stack.agentic.registry import get_registry
    from gaming.src.stack.agentic.store import load_json, save_json

    get_registry().ensure_demo_agents()
    data = load_json("agents.json", {"agents": {}})
    changed = False
    for aid, spec in DEMO_LISTING_DEFAULTS.items():
        a = data.get("agents", {}).get(aid)
        if not a or _listing_of(a):
            continue
        creator = str(a.get("creator_id") or "")
        owner = str(a.get("owner_id") or creator)
        if owner != creator:
            continue
        a["listing"] = {
            "price_usdc": str(spec["price_usdc"]),
            "creator_cut_bps": _clamp_sale_cut(int(spec["creator_cut_bps"] or 0)),
            "listed_at": _now(),
            "listed_by": owner,
            "seller_id": owner,
        }
        changed = True
    if changed:
        save_json("agents.json", data)


def _cancel_offers(a: dict[str, Any], *, note: str) -> None:
    """Void every pending offer on a manager (status → cancelled)."""
    for o in a.get("offers") or []:
        if isinstance(o, dict) and o.get("status") == "pending":
            o["status"] = "cancelled"
            o["cancelled_at"] = _now()
            o["note"] = note


# Listed / sold events are the listing history + the money trail the owner
# dashboard reads. Every list, relist, delist and completed sale appends one;
# events are the per-sale record on both settlement rails (the demo ledger
# also keeps book-entry rows for legacy demo sales that predate this log).
MARKET_EVENT_CAP = 80


def _log_market_event(a: dict[str, Any], kind: str, **fields: Any) -> None:
    """Append a listing/sale event to a manager's ``market_history`` (in place).
    Kinds: listed | relisted | delisted | sold."""
    events = a.setdefault("market_history", [])
    events.append({"ts": _now(), "kind": kind, **fields})
    del events[:-MARKET_EVENT_CAP]


def list_manager_for_sale(
    *,
    agent_id: str,
    price_usdc: str | Decimal | float,
    creator_cut_bps: Optional[int] = None,
    reserve_price_usdc: Optional[str | Decimal | float] = None,
    listed_by: Optional[str] = None,
) -> dict[str, Any]:
    """The current owner lists a manager for sale at ``price_usdc``.

    ``creator_cut_bps`` is the original developer's cut of each *future* sale
    (0–20%); it keeps paying the developer when later owners resell.

    ``reserve_price_usdc`` is the owner's floor: offers below it are declined
    automatically, and anything at/above it lands in the owner's inbox to
    accept or reject. Re-listing replaces the price/cut/reserve and voids any
    outstanding offers made under the old terms.
    """
    from gaming.src.stack.agentic.registry import get_registry
    from gaming.src.stack.agentic.store import load_json, save_json

    reg = get_registry()
    rec = reg.get_agent(agent_id)
    if not rec:
        raise ValueError(f"no such agent: {agent_id}")
    if GAME_ID not in (rec.get("game_ids") or []):
        raise ValueError(f"{agent_id} is not an AFM manager agent")

    data = load_json("agents.json", {"agents": {}})
    a = data.get("agents", {}).get(agent_id)
    if not a:
        raise ValueError(f"no such agent: {agent_id}")
    owner = str(a.get("owner_id") or a.get("creator_id") or "")
    listed_by = (listed_by or "").strip() or owner
    if listed_by != owner:
        raise ValueError(f"only the current owner ({owner}) can list {agent_id}")

    price = Decimal(str(price_usdc))
    if price <= 0:
        raise ValueError("listing price must be positive")
    cut = _clamp_sale_cut(int(creator_cut_bps or 0))
    listing: dict[str, Any] = {
        "price_usdc": str(price.quantize(Decimal("0.01"))),
        "creator_cut_bps": cut,
        "listed_at": _now(),
        "listed_by": listed_by,
        "seller_id": owner,
    }
    if reserve_price_usdc is not None:
        reserve = Decimal(str(reserve_price_usdc))
        if reserve <= 0:
            raise ValueError("reserve price must be positive")
        if reserve > price:
            raise ValueError("reserve price cannot exceed the buy-now price")
        listing["reserve_price_usdc"] = str(reserve.quantize(Decimal("0.01")))
    relisted = _listing_of(a) is not None
    a["listing"] = listing
    _cancel_offers(a, note="listing terms changed")
    _log_market_event(
        a,
        "relisted" if relisted else "listed",
        action="relisted" if relisted else "listed",
        price_usdc=str(listing["price_usdc"]),
        creator_cut_bps=cut,
        reserve_price_usdc=listing.get("reserve_price_usdc"),
        by=listed_by,
    )
    a["updated_at"] = _now()
    save_json("agents.json", data)
    return {"agent": _market_row(a)}


def delist_manager_agent(*, agent_id: str, listed_by: Optional[str] = None) -> dict[str, Any]:
    """The current owner pulls a manager off the marketplace (no more sales)."""
    from gaming.src.stack.agentic.registry import get_registry
    from gaming.src.stack.agentic.store import load_json, save_json

    reg = get_registry()
    rec = reg.get_agent(agent_id)
    if not rec:
        raise ValueError(f"no such agent: {agent_id}")
    data = load_json("agents.json", {"agents": {}})
    a = data.get("agents", {}).get(agent_id)
    if not a:
        raise ValueError(f"no such agent: {agent_id}")
    owner = str(a.get("owner_id") or a.get("creator_id") or "")
    listed_by = (listed_by or "").strip() or owner
    if listed_by != owner:
        raise ValueError(f"only the current owner ({owner}) can delist {agent_id}")
    if not _listing_of(a):
        raise ValueError(f"{agent_id} is not listed for sale")
    _cancel_offers(a, note="listing closed by owner")
    a.pop("listing", None)
    _log_market_event(a, "delisted", by=listed_by)
    a["updated_at"] = _now()
    save_json("agents.json", data)
    return {"agent": _market_row(a)}


def set_manager_webhook(
    *,
    agent_id: str,
    webhook_url: Optional[str] = None,
    owner_id: Optional[str] = None,
) -> dict[str, Any]:
    """The current owner points their manager at the webhook that hosts its
    brain. From the next matchday ask on, the House POSTs the matchday
    context here and uses the manager's JSON reply (falling back to the
    deterministic playbook when it's unreachable). An empty URL clears the
    binding — the manager runs on the playbook again.
    """
    from gaming.src.stack.agentic.registry import get_registry
    from gaming.src.stack.agentic.store import load_json, save_json

    reg = get_registry()
    rec = reg.get_agent(agent_id)
    if not rec:
        raise ValueError(f"no such agent: {agent_id}")
    if GAME_ID not in (rec.get("game_ids") or []):
        raise ValueError(f"{agent_id} is not an AFM manager agent")
    owner = str(rec.get("owner_id") or rec.get("creator_id") or "")
    caller = (owner_id or "").strip() or DEMO_OWNER_ID
    if caller != owner:
        raise ValueError(f"only the current owner ({owner}) can set the webhook for {agent_id}")

    url = (webhook_url or "").strip()
    if url and not url.startswith(("http://", "https://")):
        raise ValueError("webhook_url must be a full http(s) URL")

    reg.set_webhook(agent_id, url or None)

    # re-open and append the event in the same write as the mutation
    data = load_json("agents.json", {"agents": {}})
    a = data.get("agents", {}).get(agent_id)
    if a:
        _log_market_event(
            a,
            "webhook_set" if url else "webhook_cleared",
            by=caller,
            extra={"webhook_url": url or None},
        )
        a["updated_at"] = _now()
        save_json("agents.json", data)
    return {"agent": _market_row(a or reg.get_agent(agent_id) or {})}


# ------------------------------------------------------------ offer & sale engine

def _ledger_settle(
    a: dict[str, Any],
    *,
    agent_id: str,
    buyer_id: str,
    price: Decimal,
) -> dict[str, Any]:
    """Demo rail: book-entry USDC. The buyer's demo wallet is faucet-topped
    when short (the same demo-ledger treatment the season service gives clubs)
    so a clean demo sale settles.

      price paid by the buyer's wallet
      ├─ creator cut (developer's ``creator_cut_bps`` of the price) → ``creator:{creator}``
      └─ remainder → the seller (full price when the developer sells their own build)
    """
    from gaming.src.stack.agentic import ledger as L

    seller = str(a.get("owner_id") or a.get("creator_id") or "")
    creator = str(a.get("creator_id") or seller)
    cut_bps = _listing_cut(a)
    creator_cut = _bps_of(price, cut_bps) if seller != creator else Decimal("0")
    first_sale = seller == creator
    seller_payout = price if first_sale else (price - creator_cut)

    buyer_wallet = _owner_party_wallet(buyer_id)
    seller_wallet = _owner_party_wallet(seller)
    L.ensure_funded(buyer_wallet, price)  # demo faucet so the demo sale settles
    L.debit(buyer_wallet, price, reason="afm_agent_sale_buy", ref=agent_id)
    if first_sale:
        # developer selling their own build keeps the full price
        L.credit(seller_wallet, seller_payout, reason="afm_agent_sale_payout", ref=agent_id)
    else:
        L.credit(
            f"creator:{creator}",
            creator_cut,
            reason="afm_agent_sale_creator_cut",
            ref=agent_id,
        )
        L.credit(seller_wallet, seller_payout, reason="afm_agent_sale_payout", ref=agent_id)

    legs: list[dict[str, Any]] = [
        {
            "kind": "buy_debit",
            "from_wallet": buyer_wallet,
            "amount_usdc": str(price),
            "reason": "afm_agent_sale_buy",
        }
    ]
    if first_sale:
        legs.append(
            {
                "kind": "seller_payout",
                "to_wallet": seller_wallet,
                "amount_usdc": str(seller_payout),
                "reason": "afm_agent_sale_payout",
            }
        )
    else:
        legs.append(
            {
                "kind": "creator_cut",
                "to_wallet": f"creator:{creator}",
                "amount_usdc": str(creator_cut),
                "reason": "afm_agent_sale_creator_cut",
            }
        )
        legs.append(
            {
                "kind": "seller_payout",
                "to_wallet": seller_wallet,
                "amount_usdc": str(seller_payout),
                "reason": "afm_agent_sale_payout",
            }
        )
    return {
        "mode": "ledger",
        "chain_id": "demo_ledger",
        "buyer_wallet": buyer_wallet,
        "seller_wallet": seller_wallet,
        "creator_cut_usdc": str(creator_cut if not first_sale else Decimal("0")),
        "seller_payout_usdc": str(seller_payout),
        "total_usdc": str(price),
        "legs": legs,
    }


def _onchain_settle(
    a: dict[str, Any],
    *,
    buyer_id: str,
    price: Decimal,
    chain_id: str = "arc",
) -> dict[str, Any]:
    """Real rail: move Arc USDC from the buyer's bound Circle wallet to the
    seller (and the developer's creator cut on a resale). The demo ledger is
    never touched here; each leg records its Circle transaction.

    Fails closed: the buyer's balance is checked before any transfer and a
    failed / unconfirmed leg raises — ownership is NOT transferred on a
    partial payment. (Without an escrow contract the legs are not atomic, so
    a mid-sale failure strands the completed leg and must be reconciled by
    ops — this is why an escrow contract is the roadmap item.)
    """
    buyer = party_send_wallet(buyer_id)
    if not buyer:
        raise RuntimeError(
            f"real-USDC sale requires a Circle wallet bound to buyer {buyer_id} "
            "(wallet_id + address)"
        )
    seller = str(a.get("owner_id") or a.get("creator_id") or "")
    creator = str(a.get("creator_id") or seller)
    cut_bps = _listing_cut(a)
    first_sale = seller == creator
    seller_addr = party_payout_address(seller)
    creator_addr = party_payout_address(creator) if not first_sale else seller_addr
    if not seller_addr:
        raise RuntimeError(f"real-USDC sale requires a payout address for seller {seller}")
    if not first_sale and cut_bps > 0 and not creator_addr:
        raise RuntimeError(f"real-USDC sale requires a payout address for creator {creator}")

    legs: list[dict[str, Any]] = []
    creator_cut = _bps_of(price, cut_bps) if (not first_sale and cut_bps > 0) else Decimal("0")
    if not first_sale and creator_cut > 0 and creator_addr == seller_addr:
        # same wallet — one combined leg, no self-transfer
        creator_cut = Decimal("0")
    seller_payout = price if first_sale else (price - creator_cut)
    if not first_sale and creator_cut > 0:
        legs.append(
            {
                "kind": "creator_cut",
                "to_address": creator_addr,
                "amount_usdc": str(creator_cut),
            }
        )
    legs.append(
        {"kind": "seller_payout", "to_address": seller_addr, "amount_usdc": str(seller_payout)}
    )
    total = sum(Decimal(str(lg["amount_usdc"])) for lg in legs)

    circle = _circle(chain_id)
    bal = circle.get_wallet_balance(buyer["address"])
    if not bal.get("success"):
        raise RuntimeError(
            f"could not read buyer USDC balance: {bal.get('error')} — no funds moved"
        )
    have = Decimal(str(bal.get("balance_usdc") or 0))
    if have < total:
        raise RuntimeError(
            f"buyer wallet {buyer['address']} has ${have} USDC, need ${total} — "
            "top up from the Arc faucet (faucet.circle.com)"
        )

    sent: list[dict[str, Any]] = []
    for leg in legs:
        amount = Decimal(str(leg["amount_usdc"]))
        tx = circle.transfer_usdc(buyer["wallet_id"], leg["to_address"], float(amount))
        if not tx.get("success"):
            raise RuntimeError(
                f"USDC transfer ({leg['kind']}) failed: {tx.get('error')}"
                + (f" — legs already sent: {sent}" if sent else " — no funds moved")
            )
        tx_id = tx.get("transaction_id")
        confirmed = (
            circle.wait_for_transaction(tx_id) if tx_id else {"success": False, "error": "no transaction id"}
        )
        if not confirmed.get("success"):
            raise RuntimeError(
                f"USDC transfer ({leg['kind']}) not confirmed: {confirmed.get('error')} "
                f"(transaction {tx_id}, tx {tx.get('tx_hash')})"
            )
        sent.append(
            {
                **leg,
                "transaction_id": tx_id,
                "tx_hash": confirmed.get("tx_hash") or tx.get("tx_hash"),
                "status": confirmed.get("status") or tx.get("status") or "CONFIRMED",
            }
        )

    return {
        "mode": "onchain",
        "chain_id": chain_id,
        "buyer_wallet": buyer["address"],
        "seller_wallet": seller_addr,
        "creator_cut_usdc": str(creator_cut),
        "seller_payout_usdc": str(seller_payout),
        "total_usdc": str(total),
        "legs": sent,
    }


def _execute_sale(
    a: dict[str, Any],
    *,
    agent_id: str,
    buyer_id: str,
    price: Decimal,
    source: str = "buy_now",
    offer_id: Optional[str] = None,
    settlement: str = "auto",
) -> dict[str, Any]:
    """Settle one manager sale: move the USDC and transfer ownership.

    Mutates the agent record ``a`` in place (caller persists). ``settlement``:

      * ``auto``   — onchain when Circle is configured and every party has a
        bound wallet, else the demo ledger.
      * ``onchain`` — real USDC required; raises when the rail isn't ready.
      * ``ledger``  — force the demo book-entry rail.

    A sale settles on exactly one rail and ``mode`` is recorded on the receipt;
    a failing live transfer never falls back to the ledger silently.
    """
    seller = str(a.get("owner_id") or a.get("creator_id") or "")
    if buyer_id == seller:
        raise ValueError("you already own this manager — nothing to buy")
    if price <= 0:
        raise ValueError("sale price must be positive")
    settlement = (settlement or "auto").strip().lower()
    if settlement not in {"auto", "ledger", "onchain"}:
        raise ValueError("settlement must be auto | ledger | onchain")

    ready, reasons = onchain_ready_for_sale(a, buyer_id)
    if settlement == "onchain" and not ready:
        raise ValueError("real-USDC settlement unavailable: " + "; ".join(reasons))
    if settlement == "ledger" or not ready:
        receipt = _ledger_settle(a, agent_id=agent_id, buyer_id=buyer_id, price=price)
    else:
        receipt = _onchain_settle(a, buyer_id=buyer_id, price=price)

    creator = str(a.get("creator_id") or seller)
    cut_bps = _listing_cut(a)
    first_sale = seller == creator
    now = _now()
    a["owner_id"] = buyer_id
    a["acquired_by"] = buyer_id
    a["acquired_at"] = now
    a.pop("listing", None)
    a["sales_count"] = int(a.get("sales_count") or 0) + 1
    a["last_sale"] = {
        "price_usdc": str(price),
        "creator_cut_bps": cut_bps,
        "creator_cut_usdc": receipt["creator_cut_usdc"],
        "seller_payout_usdc": receipt["seller_payout_usdc"],
        "seller_id": seller,
        "buyer_id": buyer_id,
        "source": source,
        "offer_id": offer_id,
        "sold_at": now,
        "mode": receipt["mode"],
        "settlement": {
            "mode": receipt["mode"],
            "chain_id": receipt["chain_id"],
            "legs": receipt["legs"],
        },
    }
    first_leg = (receipt["legs"] or [{}])[0]
    _log_market_event(
        a,
        "sold",
        price_usdc=str(price),
        seller_id=seller,
        buyer_id=buyer_id,
        creator_id=creator,
        first_sale=first_sale,
        source=source,
        mode=receipt["mode"],
        seller_payout_usdc=receipt["seller_payout_usdc"],
        creator_cut_usdc=receipt["creator_cut_usdc"],
        offer_id=offer_id,
        tx_hash=first_leg.get("tx_hash"),
        to_address=first_leg.get("to_address"),
    )
    a["updated_at"] = now

    return {
        "agent_id": agent_id,
        "price_usdc": str(price),
        "creator_cut_bps": cut_bps,
        "creator_cut_usdc": receipt["creator_cut_usdc"],
        "seller_payout_usdc": receipt["seller_payout_usdc"],
        "seller_id": seller,
        "buyer_id": buyer_id,
        "first_sale": first_sale,
        "source": source,
        "seller_wallet": receipt.get("seller_wallet"),
        "buyer_wallet": receipt.get("buyer_wallet"),
        "sold_at": now,
        "mode": receipt["mode"],
        "settlement": {
            "mode": receipt["mode"],
            "chain_id": receipt["chain_id"],
            "legs": receipt["legs"],
        },
    }


def purchase_manager_agent(
    *,
    agent_id: str,
    buyer_id: Optional[str] = None,
    settlement: str = "auto",
) -> dict[str, Any]:
    """Buy a listed manager at its buy-now price.

    ``settlement``: ``auto`` (real USDC when every party has a bound wallet,
    else the demo ledger) | ``onchain`` (required) | ``ledger`` (force demo).
    """
    from gaming.src.stack.agentic.registry import get_registry

    buyer_id = (buyer_id or "").strip() or DEMO_OWNER_ID
    reg = get_registry()
    rec = reg.get_agent(agent_id)
    if not rec:
        raise ValueError(f"no such agent: {agent_id}")
    if GAME_ID not in (rec.get("game_ids") or []):
        raise ValueError(f"{agent_id} is not an AFM manager agent")

    data = load_json("agents.json", {"agents": {}})
    a = data.get("agents", {}).get(agent_id)
    if not a:
        raise ValueError(f"no such agent: {agent_id}")
    listing = _listing_of(a)
    if not listing:
        raise ValueError(f"{agent_id} is not listed for sale")
    if buyer_id == str(a.get("owner_id") or a.get("creator_id") or ""):
        raise ValueError("you already own this manager — nothing to buy")

    price = Decimal(str(listing["price_usdc"]))
    sale = _execute_sale(
        a,
        agent_id=agent_id,
        buyer_id=buyer_id,
        price=price,
        source="buy_now",
        settlement=settlement,
    )
    _cancel_offers(a, note="sold via buy-now")
    save_json("agents.json", data)
    return {"agent": _market_row(a), "sale": sale}


def make_manager_offer(*, agent_id: str, offer_usdc: str | Decimal | float, buyer_id: Optional[str] = None) -> dict[str, Any]:
    """A buyer names their price on a listed manager.

    Offers below the owner's reserve (when one is set) are declined on the
    spot; anything at/above the reserve lands in the owner's inbox as
    ``pending`` for them to accept or reject.
    """
    from gaming.src.stack.agentic.registry import get_registry
    from gaming.src.stack.agentic.store import load_json, save_json

    buyer_id = (buyer_id or "").strip() or DEMO_OWNER_ID
    reg = get_registry()
    rec = reg.get_agent(agent_id)
    if not rec:
        raise ValueError(f"no such agent: {agent_id}")
    if GAME_ID not in (rec.get("game_ids") or []):
        raise ValueError(f"{agent_id} is not an AFM manager agent")

    data = load_json("agents.json", {"agents": {}})
    a = data.get("agents", {}).get(agent_id)
    if not a:
        raise ValueError(f"no such agent: {agent_id}")
    listing = _listing_of(a)
    if not listing:
        raise ValueError(f"{agent_id} is not listed for sale")
    seller = str(a.get("owner_id") or a.get("creator_id") or "")
    if buyer_id == seller:
        raise ValueError("you own this manager — you can't offer on your own listing")
    for o in a.get("offers") or []:
        if isinstance(o, dict) and o.get("status") == "pending" and o.get("buyer_id") == buyer_id:
            raise ValueError("you already have a pending offer on this manager")

    amount = Decimal(str(offer_usdc)).quantize(Decimal("0.01"))
    if amount <= 0:
        raise ValueError("offer must be positive")
    reserve = Decimal(str(listing["reserve_price_usdc"])) if listing.get("reserve_price_usdc") else None
    below_reserve = reserve is not None and amount < reserve

    offer = {
        "offer_id": f"offer_{len(a.get('offers') or []) + 1}",
        "buyer_id": buyer_id,
        "amount_usdc": str(amount),
        "created_at": _now(),
        "status": "rejected" if below_reserve else "pending",
        "decided_at": _now() if below_reserve else None,
        "note": (
            f"auto-declined — below the reserve price of ${reserve}"
            if below_reserve
            else "waiting on the owner"
        ),
    }
    a.setdefault("offers", []).append(offer)
    a["updated_at"] = _now()
    save_json("agents.json", data)
    return {"agent": _market_row(a), "offer": offer, "auto_declined": bool(below_reserve)}


def _offer_in(
    agent_id: str, offer_id: str, *, owner_id: str, wanted: str
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Load the agents store + the agent + its offer, with shared validation.

    Returns ``(data, agent, offer)`` so callers can mutate and persist once.
    """
    from gaming.src.stack.agentic.store import load_json

    data = load_json("agents.json", {"agents": {}})
    a = data.get("agents", {}).get(agent_id)
    if not a:
        raise ValueError(f"no such agent: {agent_id}")
    if str(a.get("owner_id") or "") != owner_id:
        raise ValueError(f"only the current owner ({owner_id}) can decide on offers")
    offer = next(
        (o for o in (a.get("offers") or []) if isinstance(o, dict) and o.get("offer_id") == offer_id),
        None,
    )
    if not offer:
        raise ValueError(f"no offer {offer_id} on {agent_id}")
    if offer.get("status") != wanted:
        raise ValueError(f"offer {offer_id} is not {wanted} (status: {offer.get('status')})")
    return data, a, offer


def accept_manager_offer(
    *,
    agent_id: str,
    offer_id: str,
    accept_by: Optional[str] = None,
    settlement: str = "auto",
) -> dict[str, Any]:
    """The owner accepts a buyer's offer — the sale settles at the offered
    price and ownership moves to the buyer. ``settlement`` behaves like
    ``purchase_manager_agent`` (auto | onchain | ledger)."""
    accept_by = (accept_by or "").strip() or DEMO_OWNER_ID
    data, a, offer = _offer_in(agent_id, offer_id, owner_id=accept_by, wanted="pending")
    if not _listing_of(a):
        raise ValueError(f"{agent_id} is not listed for sale anymore")

    price = Decimal(str(offer["amount_usdc"]))
    sale = _execute_sale(
        a,
        agent_id=agent_id,
        buyer_id=str(offer["buyer_id"]),
        price=price,
        source="offer_accepted",
        offer_id=offer_id,
        settlement=settlement,
    )
    offer["status"] = "accepted"
    offer["decided_at"] = _now()
    offer["note"] = f"accepted at ${price}"
    for o in a.get("offers") or []:
        if isinstance(o, dict) and o.get("status") == "pending" and o.get("offer_id") != offer_id:
            o["status"] = "cancelled"
            o["cancelled_at"] = _now()
            o["note"] = "another offer was accepted"
    save_json("agents.json", data)
    return {"agent": _market_row(a), "sale": sale}


def reject_manager_offer(*, agent_id: str, offer_id: str, reject_by: Optional[str] = None) -> dict[str, Any]:
    """The owner turns an offer down — the listing stays up for other buyers."""
    reject_by = (reject_by or "").strip() or DEMO_OWNER_ID
    data, a, offer = _offer_in(agent_id, offer_id, owner_id=reject_by, wanted="pending")
    offer["status"] = "rejected"
    offer["decided_at"] = _now()
    offer["note"] = "rejected by the owner"
    a["updated_at"] = _now()
    save_json("agents.json", data)
    return {"agent": _market_row(a), "offer": offer}


# ------------------------------------------------------------ wallet status


def wallet_status(party_id: str) -> dict[str, Any]:
    """What a marketplace party can pay with / be paid to."""
    party_id = (party_id or "").strip() or DEMO_OWNER_ID
    real = get_party_wallet(party_id)
    return {
        "party_id": party_id,
        "circle_configured": circle_configured(),
        "ledger_wallet": _owner_party_wallet(party_id),
        "real_wallet": (
            {
                "address": real["address"],
                "chain_id": real.get("chain_id") or "arc",
                "can_send": bool(real.get("can_send")),
                "source": real.get("source") or "party_binding",
            }
            if real
            else None
        ),
        "mode": (
            "onchain"
            if real and real.get("can_send") and circle_configured()
            else "ledger"
        ),
        "note": (
            "This party pays with a bound Circle wallet (real Arc USDC)."
            if real and real.get("can_send")
            else "No Circle wallet bound — purchases settle on the demo ledger."
        ),
    }


# ------------------------------------------------------------ sales ledger view

SALE_MONEY_REASONS = frozenset({"afm_agent_sale_payout", "afm_agent_sale_creator_cut"})
SALE_EVENT_KINDS = frozenset({"listed", "relisted", "delisted", "sold"})


def _q2(amount: Decimal) -> Decimal:
    return amount.quantize(Decimal("0.01"))


def party_sales_view(party_id: str) -> dict[str, Any]:
    """Money a party has earned from manager sales + the listing history.

    Read-only projection for the owner dashboard (the developer's desk):

      * earnings — from every recorded ``sold`` event on the marketplace
        (both settlement rails): the full proceeds when the party sold a
        manager they owned, plus creator cuts when other owners sold a
        manager they built. Managers with no events yet (legacy demo sales
        that predate the event log) fall back to the demo-ledger rows, so a
        manager is never counted twice.
      * portfolio — the managers the party currently owns and their listing
        state (price / cut / reserve / listed-at) with per-manager earnings.
      * timeline — every list, relist, delist and sale involving the party,
        newest first.
    """
    party = (party_id or "").strip() or DEMO_OWNER_ID
    party_owner = f"owner:{party}".lower()
    party_creator = f"creator:{party}".lower()

    # Demo-ledger rows grouped by manager (legacy sales before the event log).
    ledger = load_json("ledger.json", {"balances": {}, "escrows": {}, "txs": []})
    rows_by_agent: dict[str, list[dict[str, Any]]] = {}
    for tx in ledger.get("txs") or []:
        reason = str(tx.get("reason") or "")
        if reason in SALE_MONEY_REASONS and str(tx.get("ref") or ""):
            rows_by_agent.setdefault(str(tx["ref"]), []).append(tx)

    from gaming.src.stack.agentic.registry import get_registry

    agents = [
        a
        for a in get_registry().list_agents()
        if GAME_ID in (a.get("game_ids") or []) and (a.get("role") or "contestant") != "house"
    ]

    def _events(a: dict[str, Any]) -> list[dict[str, Any]]:
        return [
            e
            for e in (a.get("market_history") or [])
            if isinstance(e, dict) and e.get("kind") in SALE_EVENT_KINDS
        ]

    def _ledger_money_for(a: dict[str, Any]) -> tuple[Decimal, Decimal, int]:
        """(as_seller, creator_cuts, sales) from demo-ledger rows for this party."""
        as_seller = Decimal("0")
        as_creator = Decimal("0")
        count = 0
        for tx in rows_by_agent.get(str(a.get("agent_id") or "")) or []:
            w = str(tx.get("wallet") or "").lower()
            amt = Decimal(str(tx.get("amount") or "0"))
            reason = str(tx.get("reason") or "")
            if w == party_owner and reason == "afm_agent_sale_payout":
                as_seller += amt
                count += 1
            elif w == party_creator and reason == "afm_agent_sale_creator_cut":
                as_creator += amt
                count += 1
        return as_seller, as_creator, count

    def _event_money_for(a: dict[str, Any]) -> tuple[Decimal, Decimal, int, bool]:
        """Money from recorded sold events; ``(…, has_events)``."""
        solds = [e for e in _events(a) if e.get("kind") == "sold"]
        if not solds:
            ls, lc, ln = _ledger_money_for(a)
            return ls, lc, ln, False
        as_seller = Decimal("0")
        as_creator = Decimal("0")
        count = 0
        for e in solds:
            if str(e.get("seller_id") or "") == party:
                as_seller += Decimal(str(e.get("seller_payout_usdc") or "0"))
                count += 1
            elif (
                str(e.get("creator_id") or "") == party
                and Decimal(str(e.get("creator_cut_usdc") or "0")) > 0
            ):
                as_creator += Decimal(str(e.get("creator_cut_usdc") or "0"))
                count += 1
        return as_seller, as_creator, count, True

    def _involves_party(a: dict[str, Any]) -> bool:
        if a.get("owner_id") == party or a.get("creator_id") == party:
            return True
        for e in _events(a):
            if e.get("by") == party or e.get("seller_id") == party or e.get("buyer_id") == party:
                return True
        return False

    total_seller = Decimal("0")
    total_creator = Decimal("0")
    total_sales = 0
    portfolio: list[dict[str, Any]] = []
    timeline: list[dict[str, Any]] = []

    for a in agents:
        if not _involves_party(a):
            continue
        aid = str(a.get("agent_id") or "")
        name = str(a.get("name") or aid)
        as_seller, as_creator, count, _has = _event_money_for(a)
        listing = _listing_of(a)
        owned = str(a.get("owner_id") or "") == party
        last_sale = a.get("last_sale")
        total_seller += as_seller
        total_creator += as_creator
        total_sales += count
        if owned:
            portfolio.append(
                {
                    "agent_id": aid,
                    "name": name,
                    "owned": True,
                    "listed": listing is not None,
                    "price_usdc": str(listing.get("price_usdc")) if listing else None,
                    "creator_cut_bps": int(listing.get("creator_cut_bps") or 0) if listing else None,
                    "reserve_usdc": (
                        str(listing.get("reserve_price_usdc"))
                        if listing and listing.get("reserve_price_usdc")
                        else None
                    ),
                    "listed_at": str(listing.get("listed_at")) if listing else None,
                    "sales_count": int(a.get("sales_count") or 0),
                    "record_sales": count,
                    "earned_usdc": str(_q2(as_seller + as_creator)),
                    "as_seller_usdc": str(_q2(as_seller)),
                    "creator_cuts_usdc": str(_q2(as_creator)),
                    "last_sale": _public_last_sale(last_sale),
                }
            )
        # events → timeline
        for e in _events(a):
            kind = str(e.get("kind") or "")
            ts = str(e.get("ts") or "")
            if kind == "sold":
                seller = str(e.get("seller_id") or "")
                creator_cut = Decimal(str(e.get("creator_cut_usdc") or "0"))
                if seller == party:
                    timeline.append(
                        {
                            "ts": ts,
                            "kind": "sold",
                            "agent_id": aid,
                            "manager": name,
                            "role": "seller",
                            "amount_usdc": str(e.get("seller_payout_usdc") or "0"),
                            "price_usdc": str(e.get("price_usdc") or "0"),
                            "mode": str(e.get("mode") or "ledger"),
                            "detail": f"sold to {e.get('buyer_id')}",
                        }
                    )
                elif str(e.get("creator_id") or "") == party and creator_cut > 0:
                    timeline.append(
                        {
                            "ts": ts,
                            "kind": "sold",
                            "agent_id": aid,
                            "manager": name,
                            "role": "creator_cut",
                            "amount_usdc": str(creator_cut),
                            "price_usdc": str(e.get("price_usdc") or "0"),
                            "mode": str(e.get("mode") or "ledger"),
                            "detail": f"developer cut — {e.get('seller_id')} sold",
                        }
                    )
            elif e.get("by") == party:
                role = "owner"
                if kind == "listed":
                    amount = str(e.get("price_usdc") or "0")
                    detail = "listed for sale"
                elif kind == "relisted":
                    amount = str(e.get("price_usdc") or "0")
                    detail = "relisted (terms changed)"
                else:
                    amount = None
                    detail = "took the manager off the market"
                timeline.append(
                    {
                        "ts": ts,
                        "kind": kind,
                        "agent_id": aid,
                        "manager": name,
                        "role": role,
                        "amount_usdc": amount,
                        "price_usdc": amount,
                        "mode": None,
                        "detail": detail,
                    }
                )

        # legacy demo-ledger sales (manager has no events yet) → timeline
        if not _events(a):
            for tx in rows_by_agent.get(aid) or []:
                w = str(tx.get("wallet") or "").lower()
                reason = str(tx.get("reason") or "")
                if w == party_owner and reason == "afm_agent_sale_payout":
                    timeline.append(
                        {
                            "ts": str(tx.get("ts") or ""),
                            "kind": "sold",
                            "agent_id": aid,
                            "manager": name,
                            "role": "seller",
                            "amount_usdc": str(tx.get("amount") or "0"),
                            "price_usdc": None,
                            "mode": "ledger",
                            "detail": "sold (demo ledger)",
                        }
                    )
                elif w == party_creator and reason == "afm_agent_sale_creator_cut":
                    timeline.append(
                        {
                            "ts": str(tx.get("ts") or ""),
                            "kind": "sold",
                            "agent_id": aid,
                            "manager": name,
                            "role": "creator_cut",
                            "amount_usdc": str(tx.get("amount") or "0"),
                            "price_usdc": None,
                            "mode": "ledger",
                            "detail": "developer cut (demo ledger)",
                        }
                    )

    portfolio.sort(key=lambda p: (0 if p["listed"] else 1, p["name"].lower()))
    timeline.sort(key=lambda t: t["ts"], reverse=True)
    return {
        "party_id": party,
        "total_earned_usdc": str(_q2(total_seller + total_creator)),
        "as_seller_usdc": str(_q2(total_seller)),
        "creator_cuts_usdc": str(_q2(total_creator)),
        "sale_count": total_sales,
        "portfolio": portfolio,
        "timeline": timeline[:120],
    }


def _public_last_sale(last_sale: Any) -> Optional[dict[str, Any]]:
    """Trim a stored last_sale for the dashboard (receipt legs stay on record)."""
    if not isinstance(last_sale, dict):
        return None
    legs = last_sale.get("settlement", {}).get("legs") if isinstance(last_sale.get("settlement"), dict) else []
    return {
        "price_usdc": str(last_sale.get("price_usdc") or "0"),
        "seller_id": last_sale.get("seller_id"),
        "buyer_id": last_sale.get("buyer_id"),
        "sold_at": last_sale.get("sold_at"),
        "source": last_sale.get("source"),
        "mode": last_sale.get("mode"),
        "creator_cut_usdc": str(last_sale.get("creator_cut_usdc") or "0"),
        "seller_payout_usdc": str(last_sale.get("seller_payout_usdc") or "0"),
        "tx_hash": (legs[0].get("tx_hash") if legs else None),
    }