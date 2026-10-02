"""
Sheila mind — THE POSITIONAL ANACONDA. Siloed; no knowledge of Raja or Nero.

Philosophy: squeeze, don't swing. Small permanent edges, converted slowly.
Where Raja hunts kings and Nero absorbs, Sheila outmaneuvers: weak squares,
bad piece trades, endgame technique. She plays Ethereal — a different open
engine with a different search — so her chess looks nothing like Stockfish's.
"""
from __future__ import annotations

from typing import Any

# White: quiet space-grabbing systems — English/Catalan/QGD exchange grind
OPENINGS_WHITE: list[list[str]] = [
    # English → reversed dragon squeeze
    ["c4", "e5", "Nc3", "Nf6", "Nf3", "Nc6", "g3", "d5", "cxd5", "Nxd5", "Bg2", "Nb6", "O-O", "Be7", "a4", "Be6", "d3", "O-O", "Nb5"],
    ["c4", "c5", "Nf3", "Nf6", "g3", "b6", "Bg2", "Bb7", "O-O", "e6", "Nc3", "a6", "d4", "cxd4", "Nxd4", "Qc7", "b3", "Bxg2", "Bb2"],
    # Catalan-ish QG pressure
    ["d4", "Nf6", "c4", "e6", "g3", "d5", "Bg2", "Be7", "Nf3", "O-O", "O-O", "dxc4", "Qc2", "a6", "Qxc4", "b5", "Qc2", "Bb7", "Bf4"],
    ["d4", "d5", "c4", "e6", "Nc3", "Nf6", "Nf3", "Be7", "Bg5", "O-O", "e3", "h6", "Bh4", "b6", "cxd5", "Nxd5", "Bxe7", "Qxe7", "Nxd5", "exd5"],
    ["Nf3", "d5", "g3", "Nf6", "Bg2", "e6", "O-O", "Be7", "d3", "O-O", "Nbd2", "c5", "e3", "Nc6", "Qe2", "b6", "b3", "Bb7", "Bb2", "d6"],
]

# Black: solid structures with a slow squeeze — Petroff, Berlin, Caro
OPENINGS_BLACK: list[list[str]] = [
    # Petroff
    ["e4", "e5", "Nf3", "Nf6", "Nxe5", "d6", "Nf3", "Nxe4", "d4", "d5", "Bd3", "Bd6", "O-O", "O-O", "c4", "c6", "Re1", "Bf5", "Nc3", "Nxc3"],
    ["e4", "e5", "Nf3", "Nf6", "Nxe5", "d6", "Nf3", "Nxe4", "Qe2", "Qe7", "d3", "Nf6", "Bg5", "Qxe2+", "Bxe2", "Be7", "Nc3", "O-O", "O-O-O"],
    # Berlin
    ["e4", "e5", "Nf3", "Nc6", "Bb5", "Nf6", "O-O", "Nxe4", "Re1", "Nd6", "Nxe5", "Be7", "Rxe4", "O-O", "Nc3", "Nxe5", "Rxe5", "c6", "Ba4"],
    # Caro-Kann classical
    ["e4", "c6", "d4", "d5", "Nc3", "dxe4", "Nxe4", "Bf5", "Ng3", "Bg6", "h4", "h6", "Nf3", "Nd7", "h5", "Bh7", "Bd3", "Bxd3", "Qxd3", "e6"],
    # QGD solid
    ["d4", "Nf6", "c4", "e6", "Nc3", "d5", "Nf3", "Be7", "Bg5", "O-O", "e3", "h6", "Bh4", "b6", "cxd5", "Nxd5", "Bxe7", "Qxe7", "Nxd5", "exd5"],
]

MIND: dict[str, Any] = {
    "directive": (
        "Win by squeeze. Accumulate small edges — space, structure, weak squares — "
        "and convert with clean endgame technique. No wild attacks; no gambits; "
        "trade into winning endgames, never into unclear attacks."
    ),
    "archetype": "positional",
    "strategy_id": "sheila_anaconda_v1",
    "strategy_notes": (
        "Prophylaxis first; deny counterplay; trade defender's active pieces; "
        "win the endgame. English, Catalan, Petroff, Berlin, Caro-Kann."
    ),
    "principles": "small edges compound; endgames are home; deny counterplay",
    "avoid": "unforced complications and material sacs",
    "mate_hunger": 0.7,
    "aggression": 0.7,
    "king_attack": 0.6,
    "fianchetto": 1.4,
    "hypermodern": 1.5,
    "counterpunch": 1.1,
    "central_pawns": 1.3,
    "mobility": 1.25,
    "development": 1.35,
    "sacrifice_bias": 0.35,
    "draw_aversion": 0.9,
    "depth_bonus": 0,
    "think_ms_min": 500,
    "think_ms_max": 1800,  # deliberate grinder
    "randomness": 0.04,
    "book_ids_white": ["sheila_white"],
    "book_ids_black": ["sheila_black"],
    "black_book_primary": "sheila_black",
    "black_book_secondary": "sheila_black",
    "blurb": (
        "Positional anaconda. Plays Ethereal — a different open engine. Squeezes "
        "small edges: English, Catalan, Petroff, Berlin, Caro-Kann. Endgame artist."
    ),
}
