"""
Nero mind — DEFENSE / COUNTERPUNCH. Siloed; no knowledge of Raja's code.

Core directive: WIN. Prefer solid structures, provoke overextension, then
strike. Patient. Does not rush mating attacks without foundation. Still
hates losing — will convert endgames ruthlessly.
"""
from __future__ import annotations

from typing import Any

OPENINGS_WHITE: list[list[str]] = [
    # Classical e4 — Italian / Ruy structures (solid then squeeze)
    ["e4", "e5", "Nf3", "Nc6", "Bc4", "Nf6", "d3", "Bc5", "c3", "d6", "O-O", "O-O", "Re1", "a6", "Bb3"],
    ["e4", "e5", "Nf3", "Nc6", "Bb5", "a6", "Ba4", "Nf6", "O-O", "Be7", "Re1", "b5", "Bb3", "d6", "c3"],
    # vs Sicilian — Closed / Alapin solid
    ["e4", "c5", "c3", "Nf6", "e5", "Nd5", "d4", "cxd4", "Nf3", "Nc6", "cxd4", "d6", "Bc4", "Nb6", "Bb3"],
    ["e4", "c5", "Nc3", "Nc6", "g3", "g6", "Bg2", "Bg7", "d3", "d6", "f4", "e6", "Nf3", "Nge7", "O-O"],
    # Queen's Gambit style if starting d4
    ["d4", "d5", "c4", "e6", "Nc3", "Nf6", "Bg5", "Be7", "e3", "O-O", "Nf3", "h6", "Bh4", "Ne4", "Bxe7"],
]

OPENINGS_BLACK: list[list[str]] = [
    # Sicilian — structural counterpunch
    ["e4", "c5", "Nf3", "d6", "d4", "cxd4", "Nxd4", "Nf6", "Nc3", "a6", "Be2", "e5", "Nb3", "Be7", "O-O", "O-O"],
    ["e4", "c5", "Nf3", "Nc6", "Bb5", "g6", "O-O", "Bg7", "Re1", "e5", "Bxc6", "dxc6", "d3", "Ne7"],
    # French — solid chains
    ["e4", "e6", "d4", "d5", "Nc3", "Nf6", "Bg5", "Be7", "e5", "Nfd7", "Bxe7", "Qxe7", "f4", "a6", "Nf3", "c5"],
    ["e4", "e6", "d4", "d5", "e5", "c5", "c3", "Nc6", "Nf3", "Qb6", "a3", "c4", "Nbd2", "Na5", "g3", "Bd7"],
    # Caro-Kann (user: "Casablanca" → Caro solid defense)
    ["e4", "c6", "d4", "d5", "Nc3", "dxe4", "Nxe4", "Bf5", "Ng3", "Bg6", "h4", "h6", "Nf3", "Nd7", "h5", "Bh7"],
    # vs d4 — Queen's Gambit Declined solid
    ["d4", "d5", "c4", "e6", "Nc3", "Nf6", "Bg5", "Be7", "e3", "O-O", "Nf3", "h6", "Bh4", "b6", "Bd3", "Bb7"],
]

MIND: dict[str, Any] = {
    "directive": "WIN. Stay solid, absorb pressure, counterpunch when overextended.",
    "archetype": "defender_counter",
    "strategy_id": "nero_defense_v2",
    # Fed to ASI/Gemini as strategy_notes — your unique mind, not a global bot
    "strategy_notes": (
        "Solid structures; Sicilian/French/Caro ideas; punish overextension; "
        "convert endgames carefully. Rarely sac without clear regain."
    ),
    "principles": "structure first, then counterpunch; patient not passive",
    "avoid": "speculative sacs without regain; reckless king hunts from worse",
    "aggression": 0.85,
    "king_attack": 0.9,
    "fianchetto": 0.45,
    "hypermodern": 0.55,
    "counterpunch": 1.55,
    "central_pawns": 1.25,
    "mobility": 1.0,
    "development": 1.3,
    "sacrifice_bias": 0.55,  # rarely sacs without clear regain
    "draw_aversion": 0.9,  # will take good endgames even if slow
    "depth": 2,
    "randomness": 0.03,
    # Nero reasons longer — structural calculation
    "think_ms_min": 700,
    "think_ms_max": 2200,
    "book_ids_white": ["nero_white"],
    "book_ids_black": ["nero_black"],
    "black_book_primary": "nero_black",
    "black_book_secondary": "nero_black",
    "blurb": (
        "Defense-first silo. Sicilian, French, Caro-Kann, QGD. "
        "Provokes overextension, then converts. Patient, not passive."
    ),
}
