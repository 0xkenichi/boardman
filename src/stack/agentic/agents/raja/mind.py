"""
Raja mind — MATE-HUNGRY ATTACKER. Siloed; no knowledge of Nero's code.

Philosophy: Attack is the best defence.
Core directive: WIN by initiative, king hunts, and finishing mates.
Never play for a dry draw when an attack exists.
"""
from __future__ import annotations

from typing import Any

# Aggressive white systems — storm the king, open lines early
OPENINGS_WHITE: list[list[str]] = [
    # KIA → kingside bayonet
    ["Nf3", "d5", "g3", "Nf6", "Bg2", "e6", "O-O", "Be7", "d3", "O-O", "Nbd2", "c5", "e4", "Nc6", "Re1", "Qc7", "e5", "Nd7", "Nf1", "b5", "h4"],
    ["Nf3", "c5", "g3", "Nc6", "Bg2", "g6", "O-O", "Bg7", "d3", "d6", "e4", "Nf6", "Nbd2", "O-O", "a4", "a6", "Re1", "Rb8", "Nf1", "b5", "h4"],
    ["Nf3", "Nf6", "g3", "g6", "Bg2", "Bg7", "O-O", "O-O", "d3", "d6", "e4", "e5", "Nbd2", "Nc6", "c3", "a5", "a4", "h6", "Re1", "Be6", "Nf1"],
    # Open Sicilian Yugoslav-style aggression as White
    ["e4", "c5", "Nf3", "d6", "d4", "cxd4", "Nxd4", "Nf6", "Nc3", "g6", "Be3", "Bg7", "f3", "O-O", "Qd2", "Nc6", "O-O-O", "Bd7", "g4", "Rc8", "h4"],
    ["e4", "c5", "Nf3", "d6", "d4", "cxd4", "Nxd4", "Nf6", "Nc3", "a6", "Be3", "e5", "Nb3", "Be6", "f3", "Be7", "Qd2", "O-O", "O-O-O", "Nbd7", "g4"],
    # Italian / Fried Liver pressure
    ["e4", "e5", "Nf3", "Nc6", "Bc4", "Nf6", "Ng5", "d5", "exd5", "Na5", "Bb5+", "c6", "dxc6", "bxc6", "Be2", "h6", "Nf3", "e4", "Ne5"],
    ["e4", "e5", "Nf3", "Nc6", "Bc4", "Bc5", "c3", "Nf6", "d4", "exd4", "cxd4", "Bb4+", "Nc3", "Nxe4", "O-O", "Bxc3", "d5"],
    # Four Knights → aggressive pin
    ["e4", "e5", "Nf3", "Nc6", "Nc3", "Nf6", "Bb5", "Bb4", "O-O", "O-O", "d3", "Bxc3", "bxc3", "d6", "Bg5", "h6", "Bh4", "Qe7", "Re1"],
]

# Black: dynamic counter-attacks (Alekhine, KID, Dutch-ish aggression)
OPENINGS_BLACK: list[list[str]] = [
    ["e4", "Nf6", "e5", "Nd5", "d4", "d6", "Nf3", "Bg4", "Be2", "e6", "O-O", "Be7", "c4", "Nb6", "h3", "Bh5", "Nc3", "O-O", "Be3", "d5"],
    ["e4", "Nf6", "e5", "Nd5", "c4", "Nb6", "d4", "d6", "f4", "dxe5", "fxe5", "Nc6", "Be3", "Bf5", "Nc3", "e6", "Nf3", "Be7", "Be2", "O-O"],
    ["d4", "Nf6", "c4", "g6", "Nc3", "Bg7", "e4", "d6", "Nf3", "O-O", "Be2", "e5", "O-O", "Nc6", "d5", "Ne7", "b4", "Nh5", "Re1", "f5"],
    ["d4", "Nf6", "c4", "g6", "Nc3", "Bg7", "e4", "d6", "f3", "O-O", "Be3", "e5", "d5", "c6", "Qd2", "cxd5", "cxd5", "a6", "Bd3", "Nbd7"],
    ["Nf3", "Nf6", "c4", "g6", "Nc3", "Bg7", "e4", "d6", "d4", "O-O", "Be2", "e5", "O-O", "Nc6", "d5", "Ne7", "b4", "a5", "Ba3", "axb4"],
    # vs e4 — sharper than pure solid
    ["e4", "c5", "Nf3", "d6", "d4", "cxd4", "Nxd4", "Nf6", "Nc3", "g6", "Be3", "Bg7", "f3", "O-O", "Qd2", "Nc6", "O-O-O", "d5"],
]

MIND: dict[str, Any] = {
    "directive": (
        "WIN by attack. Attack is the best defence. "
        "Hunt the king, force mates, refuse quiet equality."
    ),
    "archetype": "attacker",
    "strategy_id": "raja_mate_hunter_v3",
    # If a builder enables LLM for Raja, this mind is what gets amplified
    "strategy_notes": (
        "Initiative first; king hunts; refuse quiet equality when an attack exists. "
        "KIA storms, Yugoslav, Italian pressure; Alekhine & KID as Black."
    ),
    "principles": "attack is the best defence; finish when the king is weak",
    "avoid": "passive equality when a forcing attack exists",
    "mate_hunger": 1.8,  # drives hybrid engine forcing bias
    "aggression": 1.85,
    "king_attack": 1.9,
    "fianchetto": 1.25,
    "hypermodern": 1.35,
    "counterpunch": 0.55,  # still counter when needed, but from initiative
    "central_pawns": 0.75,
    "mobility": 1.35,
    "development": 1.2,
    "sacrifice_bias": 1.55,
    "draw_aversion": 1.7,
    "depth_bonus": 0,  # both agents at GM max depth; personality = openings only
    "think_ms_min": 280,
    "think_ms_max": 1200,  # snappy attacker
    "randomness": 0.02,
    "book_ids_white": ["raja_white"],
    "book_ids_black": ["raja_black"],
    "black_book_primary": "raja_black",
    "black_book_secondary": "raja_black",
    "blurb": (
        "Mate-hungry attacker. KIA storms, Open Sicilian Yugoslav, Italian pressure, "
        "Alekhine & KID as Black. Attack is the best defence — finishes games."
    ),
}
