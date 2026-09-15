"""AFM squad view (FM-style) — enriched per-player records for the squad screen.

`squad_view` is a pure read over the club store: derived attributes
(deterministic per player), status from the locked lineup, fitness/morale,
wage + value, and a derived contract projection. It must never mutate state.
"""

from __future__ import annotations

from gaming.src.stack.agentic.games.football_managers import club_store as C

_ATTRS = {
    "pace", "technical", "physicality", "decision_making", "positioning",
    "shooting", "passing", "tackling", "gk", "fitness", "morale",
}


def _any_club_id() -> str:
    clubs = C.seed_demo_clubs()
    assert clubs, "demo clubs must exist for the squad test"
    return clubs[0]["agent_id"]


def test_squad_view_shape_and_statuses():
    aid = _any_club_id()
    squad = C.squad_view(aid)
    assert squad
    starters = [r for r in squad if r["status"] == "starter"]
    bench = [r for r in squad if r["status"] == "bench"]
    assert len(starters) == 11, "a legal XI must be marked starter"
    assert len(bench) <= 5
    assert [r["status"] for r in squad] == sorted(
        (r["status"] for r in squad), key={"starter": 0, "bench": 1, "squad": 2}.get
    ), "squad must be ordered starter → bench → squad"


def test_every_record_carries_fm_columns():
    squad = C.squad_view(_any_club_id())
    for r in squad:
        assert set(r) >= {"player_id", "name", "slot", "primary_pos", "base_rating",
                          "form", "status", "attributes", "fitness", "morale",
                          "injury", "suspension_matches", "contract"}
        assert _ATTRS <= set(r["attributes"])
        # attributes live on the 0-99 skill scale except fitness/morale (0..1)
        for k, v in r["attributes"].items():
            if k in ("fitness", "morale"):
                assert 0.0 <= v <= 1.0
            else:
                assert 20.0 <= v <= 99.0
        assert 0.0 <= r["fitness"] <= 1.0
        assert 0.0 <= r["morale"] <= 1.0
        c = r["contract"]
        assert 2 <= c["years_left"] <= 5
        assert float(c["wage_usdc"]) >= 0.0
        assert float(c["value_usdc"]) >= 0.0
        assert c["runway_matchdays"] == 3


def test_attributes_are_slot_biased():
    """Keepers can keep goal; outfielders cannot (gk attr pinned at 20)."""
    squad = C.squad_view(_any_club_id())
    gk = next(r for r in squad if r["slot"] == "GK")
    outfielder = next(r for r in squad if r["slot"] != "GK")
    assert gk["attributes"]["gk"] >= 50.0
    assert outfielder["attributes"]["gk"] == 20.0


def test_squad_view_is_deterministic_and_read_only():
    aid = _any_club_id()
    a = C.squad_view(aid)
    b = C.squad_view(aid)
    assert a == b, "same club → same squad view (deterministic)"
    # pure read: repeated calls must not change the store
    assert C.squad_view(aid) == a