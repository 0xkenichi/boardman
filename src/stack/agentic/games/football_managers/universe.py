"""Boardman's own player universe — original characters, owned outright.

Real global stars sit in the catalog as "Upcoming · licence pending" until a
licence lands, so the league is carried by players we invent, the way Blue
Lock and Ao Ashi built casts of original footballers people care about. Every
one carries a persona: an archetype, a signature "weapon", a temperament, a
backstory and, for the Icons, a named rival.

  ICONS       — 16 hand-written leads, rated 82-88, each with a rival.
  world cast  — every football nation in universe_nations.py gets its own
                originals: one headliner (79-85) with a title ("the Kumasi
                Engine") and a rival from another nation, then prospects
                (66-79). Nigeria has the biggest cast.

Every player has a call name (persona.known_as) — what fans chant, the way
Blue Lock's cast are known by one word. Brazilians get a one-word nickname;
Korean, Chinese and Vietnamese names are written family name first. Ids are
stable per nation (afm_og_gh_01), so adding a nation never renumbers anyone.

The data ships as data/catalog_v3_originals_extension.json (picked up by
catalog.seed_catalog like any other extension). Regenerate it with:

    PYTHONPATH=. python -m gaming.src.stack.agentic.games.football_managers.universe --write

Output is fully deterministic: same code, same file.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

DATA_FILE = Path(__file__).resolve().parent / "data" / "catalog_v3_originals_extension.json"
ID_PREFIX = "afm_og_"


def value_for_rating(rating: int) -> int:
    """Market value that tracks rating: ~3M at 70, ~22M at 80, ~108M at 88."""
    return int(round(3_000_000 * 1.22 ** (rating - 70), -5))


# (slot, name, nation, rating, archetype, weapon, temperament, backstory, rival#)
ICONS: tuple[tuple[str, str, str, int, str, str, str, str, int], ...] = (
    ("ST", "Tobi Akanbi", "NG", 88, "Egoist Finisher", "Blind-side volley",
     "Ice-cold and selfish in the box", "Street-football king of Surulere who has never passed in the final third and never apologised for it.", 2),
    ("ST", "Rei Kurosawa", "JP", 87, "Predator", "Near-post ghost run",
     "Quiet, obsessive, studies every keeper", "Watched a decade of goals frame by frame and now arrives where the ball will be before anyone else knows.", 1),
    ("CAM", "Chidi Nwosu-Hale", "NG", 86, "Field Commander", "No-look switch of play",
     "Calm; sees the pitch from above", "Started as a full-back; a coach moved him inside after noticing he talked more than he ran, and was right.", 14),
    ("CM", "Matteo Vianelli", "IT", 84, "Metronome", "Two-touch tempo control",
     "Patient, never rushed", "Grew up in his father's café counting the beats of a restaurant rush. Plays the same way.", 15),
    ("CB", "Emeka Okafor-Lind", "NG", 85, "The Wall", "Last-ditch recovery sprint",
     "Proud, loud, impossible to bully", "Split his youth between Enugu and Malmö and learned to defend in both snow and dust.", 11),
    ("LW", "Yusuf Danjuma", "NG", 86, "Dribble Artist", "Elastico into the cut-in",
     "Showman who lives for the crowd", "Kano's most-filmed teenager; his skill videos had more views than his club's matches.", 9),
    ("GK", "Lukas Brenner", "DE", 84, "Sweeper Keeper", "Long throw to start the counter",
     "Composed, borderline arrogant", "A failed striker who went in goal for one match and never came back out.", 16),
    ("RB", "Ikenna Obi", "NG", 83, "Overlap Engine", "Underlapping cut-back",
     "Relentless, never stops running", "Ran 10km to training every day for three years because the bus fare went on boots.", 13),
    ("RW", "Dario Montelongo", "AR", 85, "Speed Demon", "First-touch burst past the full-back",
     "Hot-headed, chases every lost ball", "Rosario sprint champion at 14 who picked football because track had no crowds.", 6),
    ("CDM", "Haruto Senda", "JP", 83, "Destroyer", "Tackle, turn and release",
     "Says nothing, misses nothing", "Raised on judo before football; still wins the ball like he is throwing someone.", 12),
    ("ST", "Femi Adeyinka", "NG", 83, "Target Man", "Hold-up and lay-off",
     "Gentle giant until the ball is in the air", "Lagos beach-football legend who learned to control any ball on sand, so grass is easy.", 5),
    ("CB", "Mateus Arrebola", "BR", 84, "Ball-Playing Centre-Back", "Line-breaking pass through midfield",
     "Elegant, occasionally reckless", "Futsal-trained in São Paulo; would rather risk a pass than clear it.", 10),
    ("LB", "Kojo Ampofo-Lyle", "GH", 82, "Wing-Back Runner", "Early cross on the run",
     "Cheerful, endless energy", "Kumasi-born, Leeds-raised, still argues about which city taught him more.", 8),
    ("CAM", "Ibrahim Sule", "NG", 84, "Shadow Striker", "Late arrival into the box",
     "Unseen until it's too late", "Abuja's quiet kid who scores from positions nobody marks because nobody notices him.", 3),
    ("CM", "Aiden Calloway", "IE", 82, "Box-to-Box", "Pressing trigger that wins it high",
     "Never knows when to stop", "Gaelic football convert from Cork who tackles like the ball owes him money.", 4),
    ("GK", "Uche Nnamdi-Faro", "NG", 83, "Shot Stopper", "Reads the penalty taker's hips",
     "Unflappable; smiles at strikers", "Saved seven penalties in a single youth tournament and has been smiling since.", 7),
)

# ── the world cast ────────────────────────────────────────────────────────
# One 16-man squad's worth of positions. Each nation enters the cycle at a
# different point (stride 5, coprime with 16), so across the world the
# positions come out in squad proportions and headliners play everywhere,
# not just up front.
_SLOT_CYCLE = ("GK", "CB", "CM", "ST", "RB", "LB", "CDM", "CB", "CAM", "RW", "LW", "CM", "ST", "CB", "GK", "CB")
_NATION_STRIDE = 5

_ARCHETYPES = {
    "GK": ("Shot Stopper", "Sweeper Keeper", "Penalty Specialist"),
    "CB": ("Stopper", "Ball-Playing Centre-Back", "Aerial Dominator", "Libero"),
    "RB": ("Overlap Engine", "Inverted Full-Back", "Defensive Full-Back"),
    "LB": ("Wing-Back Runner", "Inverted Full-Back", "Defensive Full-Back"),
    "CDM": ("Destroyer", "Deep-Lying Playmaker", "Anchor"),
    "CM": ("Box-to-Box", "Metronome", "Pressing Machine", "Mezzala"),
    "CAM": ("Shadow Striker", "Field Commander", "Trequartista", "Enganche"),
    "RW": ("Speed Demon", "Inverted Winger", "Touchline Winger"),
    "LW": ("Dribble Artist", "Inverted Winger", "Touchline Winger"),
    "ST": ("Egoist Finisher", "Target Man", "Predator", "False Nine", "Poacher"),
}
_WEAPONS = {
    "GK": ("One-on-one smother", "Quick distribution", "Penalty instinct", "Reflex double save",
           "Punt that starts the counter", "Commands the six-yard box"),
    "DEF": ("Interception read", "Recovery sprint", "Header in both boxes", "Switch of play",
            "Sliding block", "Line-breaking carry", "Shadow-marks the striker", "Long diagonal"),
    "MID": ("Line-breaking pass", "Press resistance", "Late run into the box", "Long-range strike",
            "Half-turn on the half-space", "Third-man combination", "Set-piece delivery", "Ball-winning lunge"),
    "FWD": ("First-time finish", "Step-over burst", "Curled finish to the far post", "Run in behind",
            "Near-post flick", "Chip over the keeper", "Rabona cross", "Hold-up spin and shoot"),
}
_TEMPERS = ("Calm under pressure", "Fiery competitor", "Quiet leader", "Joker in the dressing room",
            "Perfectionist", "Big-game player", "Streaky but brilliant", "Workhorse", "Lone wolf",
            "Born captain", "Trash-talker", "Shy off the pitch, ruthless on it", "Superstitious", "Showman")
_ORIGINS = ("Came through an academy nobody had heard of", "Spotted at a street tournament",
            "Late bloomer released twice before breaking through", "Child prodigy still learning patience",
            "Converted from another position as a teenager", "Played futsal until 17",
            "Grew up idolising the Icons and wants their place", "Paid for boots by selling match tickets",
            "Learned the game on a dirt pitch behind the market", "Was a sprinter before football found him")
# Headliner titles: "the {city} {noun}" — one per nation, the face of its cast.
_TITLE_NOUNS = {"GK": ("Wall", "Keeper of the Gates", "Last Line"), "DEF": ("Fortress", "Anchor", "Iron Gate"),
                "MID": ("Engine", "Maestro", "Conductor"), "FWD": ("Lightning", "Ghost", "Hammer", "Arrow")}


def _h(key: str) -> int:
    return int(hashlib.sha256(f"boardman-universe-v2:{key}".encode()).hexdigest(), 16)


def _pick(seq: tuple, key: str):
    return seq[_h(key) % len(seq)]


def _group(slot: str) -> str:
    return {"GK": "GK", "CB": "DEF", "RB": "DEF", "LB": "DEF", "CDM": "MID", "CM": "MID", "CAM": "MID"}.get(slot, "FWD")


def _icon_rows(taken: set[str]) -> list[dict[str, Any]]:
    rows = []
    for i, (slot, name, nation, rating, arche, weapon, temper, story, rival) in enumerate(ICONS, start=1):
        taken.add(name.lower())
        rows.append({
            "player_id": f"{ID_PREFIX}{i:03d}", "origin": "original", "name": name, "nation": nation, "slot": slot,
            "base_rating": rating, "real_value_usd": value_for_rating(rating),
            "persona": {"tier": "icon", "known_as": name.split()[-1].split("-")[0], "archetype": arche,
                        "weapon": weapon, "temperament": temper, "backstory": story,
                        "rival_id": f"{ID_PREFIX}{rival:03d}"},
        })
    return rows


def _name_for(code: str, spec: dict[str, Any], key: str, taken: set[str]) -> tuple[str, str, str]:
    """(display name, call name, legal name) — unique across the universe and
    the real catalog. Brazilians play under a one-word nickname, like real
    Brazilian footballers, so their display name is the nickname."""
    for attempt in range(80):
        k = f"{key}:{attempt}"
        given = _pick(spec["given"], f"given:{k}")
        family = _pick(spec["family"], f"family:{k}")
        full = f"{family} {given}" if spec.get("order") == "family_given" else f"{given} {family}"
        if spec.get("call") == "nickname":
            call = _pick(spec["nicks"], f"nick:{k}")
            if call.lower() not in taken and full.lower() not in taken:
                taken.update({call.lower(), full.lower()})  # one Tatá per universe
                return call, call, full
            continue
        if full.lower() not in taken:
            taken.add(full.lower())
            return full, family, full
    raise RuntimeError(f"name pool for {code} exhausted")


def _nation_rows(taken: set[str]) -> list[dict[str, Any]]:
    from gaming.src.stack.agentic.games.football_managers.universe_nations import NATIONS

    rows: list[dict[str, Any]] = []
    headliners: list[str] = []
    for n, (code, spec) in enumerate(NATIONS.items()):
        for k in range(int(spec["count"])):
            pid = f"{ID_PREFIX}{code.lower()}_{k + 1:02d}"
            slot = _SLOT_CYCLE[(n * _NATION_STRIDE + k) % len(_SLOT_CYCLE)]
            group = _group(slot)
            display, call, legal = _name_for(code, spec, f"{code}:{k}", taken)
            city = _pick(spec["cities"], f"city:{pid}")
            headliner = k == 0
            rating = 79 + _h(f"rating:{pid}") % 7 if headliner else 66 + _h(f"rating:{pid}") % 14
            persona: dict[str, Any] = {
                "tier": "headliner" if headliner else "prospect",
                "known_as": call,
                "archetype": _pick(_ARCHETYPES[slot], f"arch:{pid}"),
                "weapon": _pick(_WEAPONS[group], f"weapon:{pid}"),
                "temperament": _pick(_TEMPERS, f"temper:{pid}"),
                "backstory": f"{_pick(_ORIGINS, f'story:{pid}')}, in {city}.",
                "hometown": city,
            }
            if legal != display:
                persona["full_name"] = legal
            if headliner:
                persona["title"] = f"the {city} {_pick(_TITLE_NOUNS[group], f'title:{pid}')}"
                headliners.append(pid)
            rows.append({"player_id": pid, "origin": "original", "name": display, "nation": code, "slot": slot,
                         "base_rating": rating, "real_value_usd": value_for_rating(rating), "persona": persona})
    # Headliner rivalries pair neighbouring nations (an odd one out joins the last pair's ring).
    by_id = {r["player_id"]: r for r in rows}
    for i in range(0, len(headliners) - 1, 2):
        a, b = headliners[i], headliners[i + 1]
        by_id[a]["persona"]["rival_id"], by_id[b]["persona"]["rival_id"] = b, a
    if len(headliners) % 2:
        by_id[headliners[-1]]["persona"]["rival_id"] = headliners[-2]
    return rows


def build(real_names: set[str] | None = None) -> list[dict[str, Any]]:
    """The whole original roster: Icons first, then every nation's cast.
    `real_names` (lower-case) are names in the real catalog; never reused."""
    taken = {n.lower() for n in (real_names or set())}
    return _icon_rows(taken) + _nation_rows(taken)


def _real_catalog_names() -> set[str]:
    data = Path(__file__).resolve().parent / "data"
    names: set[str] = set()
    for f in sorted(data.glob("catalog_v*.json")):
        if f.name == DATA_FILE.name:
            continue
        names.update(str(r.get("name") or "").lower() for r in json.loads(f.read_text(encoding="utf-8")))
    return names


def render() -> str:
    return json.dumps(build(_real_catalog_names()), indent=1, ensure_ascii=False) + "\n"


if __name__ == "__main__":
    if "--write" in sys.argv:
        DATA_FILE.write_text(render(), encoding="utf-8")
        print(f"wrote {DATA_FILE}")
    else:
        sys.stdout.write(render())
