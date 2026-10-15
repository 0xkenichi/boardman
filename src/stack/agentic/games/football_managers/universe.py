"""Boardman's own player universe — original characters, owned outright.

Real global stars sit in the catalog as "Upcoming · licence pending" until a
licence lands, so the league is carried by players we invent, the way Blue
Lock and Ao Ashi built casts of original footballers people care about. Every
one carries a persona: an archetype, a signature "weapon", a temperament, a
backstory and, for the Icons, a named rival.

  ICONS   — 16 hand-written leads, rated 82-88, each with a rival.
  depth   — 80 deterministic originals (68-81) so every position has cover.

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

# Depth: slot counts so a 20-club division always finds cover.
_DEPTH_SLOTS = (("GK", 8), ("CB", 14), ("RB", 6), ("LB", 6), ("CDM", 8), ("CM", 12),
                ("CAM", 6), ("RW", 6), ("LW", 6), ("ST", 8))

_GIVEN = {
    "NG": ("Tunde", "Chinedu", "Obinna", "Segun", "Kelechi", "Musa", "Babatunde", "Ifeanyi", "Damilare", "Nnamdi",
           "Abdullahi", "Olamide", "Ebuka", "Kayode", "Somto", "Usman", "Gbenga", "Chukwudi", "Bayo", "Tochukwu"),
    "GH": ("Kwabena", "Yaw", "Kojo", "Kweku", "Nana"),
    "SN": ("Mamadou", "Ousmane", "Cheikh", "Babacar"),
    "BR": ("Thiago", "Caio", "Renan", "Davi"),
    "AR": ("Facundo", "Tomás", "Lautaro", "Bautista"),
    "ES": ("Iker", "Álvaro", "Unai", "Marc"),
    "FR": ("Yanis", "Lucas", "Mathis", "Noé"),
    "JP": ("Sora", "Kaito", "Ren", "Yuto"),
    "KR": ("Ji-ho", "Min-jun", "Seo-jun"),
    "EN": ("Callum", "Reece", "Harvey", "Mason"),
    "DE": ("Jonas", "Finn", "Lennart"),
    "MA": ("Ayoub", "Ilyas", "Zakaria"),
}
_FAMILY = {
    "NG": ("Okonkwo", "Adewale", "Eze", "Balogun", "Nwachukwu", "Ogunleye", "Abubakar", "Uzor", "Afolabi", "Ibekwe",
           "Olaniyan", "Chukwuma", "Bello", "Onyekachi", "Adeleke", "Ekwueme", "Lawal", "Oyelaran", "Anozie", "Babangida"),
    "GH": ("Owusu-Ansah", "Boakye-Dankwa", "Agyemang-Fosu", "Sarpong-Kyei"),
    "SN": ("Ndour-Faye", "Sy-Diatta", "Gueye-Badji", "Mbodj"),
    "BR": ("Albuquerque-Ramos", "Teixeira Lobo", "Vasconcelos", "Barreto Neto"),
    "AR": ("Etcheverría", "Quiroga Paz", "Villafañe", "Ledesma Sur"),
    "ES": ("Garmendia", "Urquiza", "Olabarrieta", "Ferrán Vidal"),
    "FR": ("Delacroix-Ba", "Marchetti-Roux", "Ambroise", "Lefevre-Diop"),
    "JP": ("Hayashida", "Komatsuzaki", "Torigoe", "Nishikata"),
    "KR": ("Baek-Yoon", "Seo-Hwan", "Gil-Ra"),
    "EN": ("Ashworth", "Pendlebury", "Thackeray", "Whitlock"),
    "DE": ("Kranzbühler", "Oberhaus", "Steinmetz-Ahn"),
    "MA": ("El Amrani-Saidi", "Benhaddou", "Zerrouki"),
}
# Nigeria first — the visibility we want — then a spread of football nations.
_NATION_WEIGHTS = (("NG", 40), ("GH", 6), ("SN", 6), ("BR", 7), ("AR", 6), ("ES", 6), ("FR", 7),
                   ("JP", 6), ("KR", 4), ("EN", 6), ("DE", 3), ("MA", 3))

_ARCHETYPES = {
    "GK": ("Shot Stopper", "Sweeper Keeper"),
    "CB": ("Stopper", "Ball-Playing Centre-Back", "Aerial Dominator"),
    "RB": ("Overlap Engine", "Inverted Full-Back"),
    "LB": ("Wing-Back Runner", "Inverted Full-Back"),
    "CDM": ("Destroyer", "Deep-Lying Playmaker"),
    "CM": ("Box-to-Box", "Metronome", "Pressing Machine"),
    "CAM": ("Shadow Striker", "Field Commander", "Trequartista"),
    "RW": ("Speed Demon", "Inverted Winger"),
    "LW": ("Dribble Artist", "Inverted Winger"),
    "ST": ("Egoist Finisher", "Target Man", "Predator", "False Nine"),
}
_WEAPONS = {
    "GK": ("One-on-one smother", "Quick distribution", "Penalty instinct"),
    "DEF": ("Interception read", "Recovery sprint", "Header in both boxes", "Switch of play"),
    "MID": ("Line-breaking pass", "Press resistance", "Late run into the box", "Long-range strike"),
    "FWD": ("First-time finish", "Step-over burst", "Curled finish to the far post", "Run in behind"),
}
_TEMPERS = ("Calm under pressure", "Fiery competitor", "Quiet leader", "Joker in the dressing room",
            "Perfectionist", "Big-game player", "Streaky but brilliant", "Workhorse")
_ORIGINS = ("Came through an academy nobody had heard of.", "Spotted at a street tournament.",
            "Late bloomer released twice before breaking through.", "Child prodigy still learning to be patient.",
            "Converted from another position as a teenager.", "Played futsal until 17.",
            "Grew up idolising the Icons and now wants their place.")


def _h(key: str) -> int:
    return int(hashlib.sha256(f"boardman-universe-v1:{key}".encode()).hexdigest(), 16)


def _pick(seq: tuple, key: str):
    return seq[_h(key) % len(seq)]


def _weighted_nation(key: str) -> str:
    total = sum(w for _, w in _NATION_WEIGHTS)
    roll = _h(key) % total
    for nation, w in _NATION_WEIGHTS:
        if roll < w:
            return nation
        roll -= w
    return "NG"


def _group(slot: str) -> str:
    return {"GK": "GK", "CB": "DEF", "RB": "DEF", "LB": "DEF", "CDM": "MID", "CM": "MID", "CAM": "MID"}.get(slot, "FWD")


def build(real_names: set[str] | None = None) -> list[dict[str, Any]]:
    """The whole original roster, Icons first. `real_names` (lower-case) are
    names already in the catalog; generated players never reuse one."""
    taken = {n.lower() for n in (real_names or set())}
    rows: list[dict[str, Any]] = []
    for i, (slot, name, nation, rating, arche, weapon, temper, story, rival) in enumerate(ICONS, start=1):
        taken.add(name.lower())
        rows.append({
            "player_id": f"{ID_PREFIX}{i:03d}", "origin": "original", "name": name, "nation": nation, "slot": slot,
            "base_rating": rating, "real_value_usd": value_for_rating(rating),
            "persona": {"tier": "icon", "archetype": arche, "weapon": weapon, "temperament": temper,
                        "backstory": story, "rival_id": f"{ID_PREFIX}{rival:03d}"},
        })
    n = len(ICONS)
    for slot, count in _DEPTH_SLOTS:
        for k in range(count):
            n += 1
            pid = f"{ID_PREFIX}{n:03d}"
            for attempt in range(50):
                key = f"{slot}:{k}:{attempt}"
                nation = _weighted_nation(f"nation:{key}")
                name = f"{_pick(_GIVEN[nation], 'given:' + key)} {_pick(_FAMILY[nation], 'family:' + key)}"
                if name.lower() not in taken:
                    break
            taken.add(name.lower())
            rating = 68 + _h(f"rating:{pid}") % 14  # 68..81
            rows.append({
                "player_id": pid, "origin": "original", "name": name, "nation": nation, "slot": slot,
                "base_rating": rating, "real_value_usd": value_for_rating(rating),
                "persona": {"tier": "prospect", "archetype": _pick(_ARCHETYPES[slot], f"arch:{pid}"),
                            "weapon": _pick(_WEAPONS[_group(slot)], f"weapon:{pid}"),
                            "temperament": _pick(_TEMPERS, f"temper:{pid}"),
                            "backstory": _pick(_ORIGINS, f"story:{pid}")},
            })
    return rows


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
