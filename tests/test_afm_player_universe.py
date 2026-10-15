"""AFM player universe: licence-pending stars, Nigerian players, originals.

Covers the 2026-10-15 catalog decision:
  - real global stars are listed as "Upcoming · licence pending" and can never
    be owned, signed, listed or auto-picked;
  - real Nigerian players and Boardman's original universe are fully playable;
  - clubs built before the change get their stars swapped out in place;
  - the anime-titled demo clubs are renamed without touching ids or owners.
"""
from __future__ import annotations

from decimal import Decimal

import pytest


@pytest.fixture(autouse=True)
def _isolate_store(tmp_path, monkeypatch):
    monkeypatch.setenv("BOARDMAN_AGENTIC_DATA", str(tmp_path))
    yield
    from gaming.src.stack.agentic.games.football_managers import catalog as cat

    for p in cat.seed_catalog():
        cat.set_owner(p["player_id"], None)


@pytest.fixture()
def _world():
    from gaming.src.stack.agentic.games.football_managers.club_store import seed_demo_clubs
    from gaming.src.stack.agentic.registry import get_registry

    get_registry().ensure_demo_agents()
    seed_demo_clubs()


def _by_name(name):
    from gaming.src.stack.agentic.games.football_managers import catalog as cat

    return next(p for p in cat.list_players() if p["name"] == name)


def test_catalog_origins_and_availability():
    from gaming.src.stack.agentic.games.football_managers import catalog as cat

    meta = cat.catalog_meta()
    assert meta["by_origin"]["global_star"] > 100
    assert meta["by_origin"]["real_ng"] >= 30
    assert meta["by_origin"]["original"] >= 90
    for name in ("Erling Haaland", "Kylian Mbappé", "Mohamed Salah", "Jude Bellingham"):
        star = _by_name(name)
        assert star["origin"] == "global_star"
        assert star["availability"] == "upcoming"
        assert star["availability_label"] == "Upcoming · licence pending"
        assert star["owner_agent_id"] is None
    for name in ("Victor Osimhen", "Ademola Lookman", "Tobi Akanbi"):
        assert cat.is_available(_by_name(name))
    assert _by_name("Victor Osimhen")["origin"] == "real_ng"  # legacy row, nation NG
    free = cat.list_players(free_only=True)
    assert free and all(p["availability"] == "available" for p in free)


def test_stars_can_never_be_owned():
    from gaming.src.stack.agentic.games.football_managers import catalog as cat

    star = _by_name("Erling Haaland")["player_id"]
    with pytest.raises(cat.PlayerUnavailable):
        cat.set_owner(star, "agent_bluelock_demo")
    cat.set_owner(star, None)  # releasing is always fine


def test_icons_have_personas_and_valid_rivals():
    from gaming.src.stack.agentic.games.football_managers import catalog as cat
    from gaming.src.stack.agentic.games.football_managers import universe as U

    ids = {p["player_id"] for p in cat.list_players()}
    icons = [p for p in cat.list_players() if (p.get("persona") or {}).get("tier") == "icon"]
    assert len(icons) == len(U.ICONS) == 16
    for p in icons:
        persona = p["persona"]
        assert persona["weapon"] and persona["archetype"] and persona["backstory"]
        assert persona["rival_id"] in ids and persona["rival_id"] != p["player_id"]
    names = [p["name"] for p in cat.list_players() if p["origin"] == "original"]
    assert len(names) == len(set(names))


def test_universe_file_matches_generator():
    from gaming.src.stack.agentic.games.football_managers import universe as U

    assert U.DATA_FILE.read_text(encoding="utf-8") == U.render(), (
        "regenerate: python -m gaming.src.stack.agentic.games.football_managers.universe --write"
    )


def test_auto_built_clubs_field_no_licence_pending_players(_world):
    from gaming.src.stack.agentic.games.football_managers import catalog as cat
    from gaming.src.stack.agentic.games.football_managers.club_store import list_clubs

    clubs = list_clubs()
    assert clubs
    for club in clubs:
        for p in club["squad"]:
            assert cat.is_available(cat.get_player(p["player_id"])), (club["club_name"], p["name"])
        assert len(club["starters"]) == 11


def test_existing_squads_swap_stars_out_in_place(_world):
    from gaming.src.stack.agentic.games.football_managers import catalog as cat
    from gaming.src.stack.agentic.games.football_managers import club_store as CS

    aid = "agent_bluelock_demo"
    state = CS._state()
    rec = state["clubs"][aid]
    # a club saved before the change: a star in the XI and the old anime name
    star = _by_name("Erling Haaland")
    old_starter = rec["starters"][-1]
    idx = rec["roster"].index(old_starter)
    cat.set_owner(old_starter, None)
    rec["roster"][idx] = star["player_id"]
    rec["starters"][-1] = star["player_id"]
    rec["club_name"] = "Blue Lock FC"
    CS._save(state)

    CS.seed_demo_clubs()
    rec = CS._state()["clubs"][aid]
    assert rec["club_name"] == "Forge FC"
    assert star["player_id"] not in rec["roster"]
    new = cat.get_player(rec["starters"][-1])
    assert cat.is_available(new) and new["owner_agent_id"] == aid
    assert new["slot"] == star["slot"] or new["primary_pos"] == star["primary_pos"]
    assert len(rec["starters"]) == 11
    CS.seed_demo_clubs()  # idempotent
    assert CS._state()["clubs"][aid]["roster"] == rec["roster"]


def test_market_refuses_stars_before_money_moves(_world):
    import gaming.src.stack.agentic.ledger as L
    from gaming.src.stack.agentic.games.football_managers import club_store as CS
    from gaming.src.stack.agentic.games.football_managers import market as M

    buyer = "agent_aoashi_demo"
    M.open_window(1, "mid", closes_at="soon")
    CS.adjust_budget(buyer, Decimal("500.00"))
    star = _by_name("Kylian Mbappé")["player_id"]
    wallet = M._market_wallet(buyer)
    L.credit(wallet, Decimal("1000"), reason="test", ref="test")
    before, tb0 = L.balance(wallet), CS.transfer_balance(buyer)
    with pytest.raises(M.MarketError, match="player_licence_pending"):
        M.buy_free_agent(buyer, star)
    assert L.balance(wallet) == before and CS.transfer_balance(buyer) == tb0
    assert star not in CS.roster_ids(buyer)


def test_demo_managers_renamed_without_losing_owner():
    from gaming.src.stack.agentic.registry import AGENTS_FILE, get_registry
    from gaming.src.stack.agentic.store import load_json, save_json

    reg = get_registry()
    reg.ensure_demo_agents()
    data = load_json(AGENTS_FILE, {"agents": {}})
    rec = data["agents"]["agent_bluelock_demo"]
    rec["name"] = "Blue Lock"  # as saved before the rename
    rec["owner_id"] = "profile_bought_it"  # a user bought this manager
    rec["stats"]["wins"] = 7
    save_json(AGENTS_FILE, data)

    reg.ensure_demo_agents()
    after = reg.get_agent("agent_bluelock_demo")
    assert after["name"] == "Forge"
    assert after["owner_id"] == "profile_bought_it"
    assert after["stats"]["wins"] == 7


def _originals():
    from gaming.src.stack.agentic.games.football_managers import catalog as cat

    return [p for p in cat.list_players() if p["origin"] == "original"]


def test_every_nation_has_a_cast_with_one_titled_headliner():
    from gaming.src.stack.agentic.games.football_managers.universe_nations import NATIONS

    originals = _originals()
    by_id = {p["player_id"]: p for p in originals}
    for code, spec in NATIONS.items():
        cast = [p for p in originals if p["player_id"].startswith(f"afm_og_{code.lower()}_")]
        assert len(cast) == spec["count"], code
        assert all(p["nation"] == code for p in cast)
        heads = [p for p in cast if p["persona"]["tier"] == "headliner"]
        assert len(heads) == 1, code
        head = heads[0]["persona"]
        assert head["title"].startswith("the ") and head["hometown"] in head["title"]
        rival = by_id[head["rival_id"]]
        assert rival["nation"] != code and rival["persona"]["tier"] == "headliner"
    ng = sum(1 for p in originals if p["nation"] == "NG")
    assert ng == max(sum(1 for p in originals if p["nation"] == c) for c in NATIONS)  # biggest cast


def test_call_names_and_naming_conventions():
    originals = _originals()
    assert all(p["persona"].get("known_as") for p in originals)
    names = [p["name"].lower() for p in originals]
    assert len(names) == len(set(names))
    br = [p for p in originals if p["player_id"].startswith("afm_og_br_")]
    assert all(" " not in p["name"] and p["persona"]["full_name"] for p in br)  # one-word nickname
    kr = [p for p in originals if p["player_id"].startswith("afm_og_kr_")]
    assert all(p["name"].split()[0] == p["persona"]["known_as"] for p in kr)  # family name first


def test_cast_fills_every_position_in_squad_proportions():
    from collections import Counter

    slots = Counter(p["slot"] for p in _originals())
    for slot in ("GK", "RB", "CB", "LB", "CDM", "CM", "CAM", "RW", "ST", "LW"):
        assert slots[slot] >= 20, (slot, slots)
    assert slots["CB"] > slots["RB"]  # centre-backs come in pairs


def test_originals_never_reuse_a_real_catalog_name():
    from gaming.src.stack.agentic.games.football_managers import catalog as cat

    real = {p["name"].lower() for p in cat.list_players() if p["origin"] in ("global_star", "real_ng")}
    assert not real & {p["name"].lower() for p in _originals()}


def test_legends_are_listed_but_never_ownable(_world):
    from gaming.src.stack.agentic.games.football_managers import catalog as cat
    from gaming.src.stack.agentic.games.football_managers import market as M
    from gaming.src.stack.agentic.games.football_managers.club_store import list_clubs

    legends = [p for p in cat.list_players() if (p.get("persona") or {}).get("tier") == "legend"]
    real = [p for p in legends if p["origin"] == "legend"]
    ours = [p for p in legends if p["origin"] == "original"]
    assert len(real) >= 40 and len(ours) == 12
    assert {p["nation"] for p in real if p["player_id"].startswith("afm_lg_ng_")} == {"NG"}
    for p in real:
        assert p["availability"] == "upcoming" and p["availability_label"] == "Coming soon · licence pending"
        assert isinstance(p["persona"]["passed"], int) and p["owner_agent_id"] is None
    for p in ours:
        assert p["availability_label"] == "Coming soon · Legends era" and p["persona"]["title"]
    assert all(p["persona"].get("tribute") for p in real if p["nation"] == "NG")
    # never in a squad, never a free agent, never signable
    squad_ids = {s["player_id"] for c in list_clubs() for s in c["squad"]}
    free_ids = {p["player_id"] for p in cat.list_players(free_only=True)}
    for p in legends:
        assert p["player_id"] not in squad_ids and p["player_id"] not in free_ids
        with pytest.raises(cat.PlayerUnavailable):
            cat.set_owner(p["player_id"], "agent_aoashi_demo")
    M.open_window(1, "mid", closes_at="soon")
    with pytest.raises(M.MarketError, match="player_licence_pending"):
        M.buy_free_agent("agent_aoashi_demo", _by_name("Pelé")["player_id"])


def test_legend_file_rows_cannot_unlock_themselves():
    """An origin=legend row is pending whatever availability it claims."""
    from gaming.src.stack.agentic.games.football_managers import catalog as cat

    row = cat._normalize_row(0, {"player_id": "x", "name": "X", "nation": "BR", "slot": "ST",
                                 "real_value_usd": 1, "origin": "legend", "availability": "available"})
    assert row["availability"] == "upcoming"
