"""AFM FM-style role suitability (roles.py).

Suitability is a pure function of (slot, attribute profile): the same player
always gets the same roles, players only ever see roles from their own
position family, and the attribute weights genuinely re-rank roles between
different kinds of player (a pace+shooting striker favours an Advanced
Forward; a physical target-man profile favours a Target Man).
"""

from __future__ import annotations

from gaming.src.stack.agentic.games.football_managers import club_store as C
from gaming.src.stack.agentic.games.football_managers.roles import role_suitability


def _attrs(**over) -> dict:
    base = {k: 70.0 for k in ("pace", "technical", "physicality", "decision_making",
                              "positioning", "shooting", "passing", "tackling", "gk")}
    base.update(over)
    return base


def test_deterministic_same_inputs():
    a = role_suitability("ST", _attrs())
    b = role_suitability("ST", _attrs())
    assert a == b
    assert a, "a striker must have striker roles"


def test_only_own_position_family():
    """GK, CB and ST players only ever see roles from their own family."""
    gk = {r["name"] for r in role_suitability("GK", _attrs(gk=90))}
    cb = {r["name"] for r in role_suitability("CB", _attrs(tackling=90, positioning=90))}
    st = {r["name"] for r in role_suitability("ST", _attrs(shooting=90))}
    assert "Goalkeeper (Defend)" in gk and "Sweeper Keeper (Support)" in gk
    assert "Advanced Forward" not in gk
    assert "Centre-Back (Defend)" in cb and "Ball-Playing Defender" in cb
    assert "Centre-Back (Defend)" not in st
    assert any("Forward" in n or "Nine" in n or "Man" in n or "Poacher" in n for n in st)
    assert all(1 <= r["stars"] <= 5 for r in role_suitability("CM", _attrs()))


def test_attribute_weights_rank_roles():
    """A pacy finisher prefers Advanced Forward; a battering ram prefers Target Man."""
    pacy = role_suitability("ST", _attrs(pace=95, shooting=95, technical=85,
                                         physicality=60, passing=50, positioning=88))
    beast = role_suitability("ST", _attrs(pace=55, shooting=80, technical=55,
                                          physicality=95, passing=75, positioning=75))
    score = {r["name"]: r["score"] for r in pacy}
    score2 = {r["name"]: r["score"] for r in beast}
    assert score["Advanced Forward"] > score["Target Man (Support)"]
    assert score2["Target Man (Support)"] > score2["Advanced Forward"]
    # the pacy forward's top pick must not be a target man, and vice versa
    assert pacy[0]["name"] != "Target Man (Support)"
    assert beast[0]["name"] == "Target Man (Support)"


def test_squad_view_includes_roles():
    clubs = C.seed_demo_clubs()
    assert clubs
    squad = C.squad_view(clubs[0]["agent_id"])
    assert squad
    for r in squad:
        assert "roles" in r
        fam = {"GK", "FB", "CB", "DM", "CM", "AM", "W", "ST"}.intersection(
            {x["name"] for x in r["roles"]}
        )
        assert r["roles"], f"{r['name']} should have role options"
        for role in r["roles"]:
            assert 1 <= role["stars"] <= 5
            assert 1.0 <= role["score"] <= 99.0
    # GK sees only keeper roles; striker sees no keeper roles
    gk = next(r for r in squad if r["slot"] == "GK")
    st = next(r for r in squad if r["slot"] == "ST")
    assert all("Goalkeeper" in x["name"] or "Keeper" in x["name"] for x in gk["roles"])
    assert not any("Keeper" in x["name"] for x in st["roles"])