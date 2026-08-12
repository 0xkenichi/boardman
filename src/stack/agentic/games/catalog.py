"""Registry of finite-outcome games available for agents + hackathons."""
from __future__ import annotations

from typing import Any, Optional

from gaming.src.stack.agentic.games.base import GameModule
from gaming.src.stack.agentic.games.tictactoe import TicTacToe, TicTacToe4
from gaming.src.stack.agentic.games.connect4 import ConnectFour
from gaming.src.stack.agentic.games.checkers import Checkers
from gaming.src.stack.agentic.games.go9 import Go9
from gaming.src.stack.agentic.games.shogi_lite import ShogiLite
from gaming.src.stack.agentic.games.xiangqi_lite import XiangqiLite

# Chess stays in chess/ package; catalog points to id only
CHESS_META = {
    "game_id": "agentic.chess_standard",
    "display_name": "Chess",
    "family": "classic",
    "outcome_space": ["p1_win", "p2_win", "draw"],
    "verifier": "chess_engine_v1",
    "hackathon_friendly": True,
    "status": "live",
    "notes": "Full chess via hybrid Stockfish + siloed books",
}


def _meta(mod: GameModule, **extra: Any) -> dict[str, Any]:
    return {
        "game_id": mod.game_id,
        "display_name": mod.display_name,
        "outcome_space": ["p1_win", "p2_win", "draw"],
        "verifier": f"{mod.game_id}_v1",
        "match_formats": ["agent_vs_agent", "human_vs_agent"],
        "hackathon_friendly": True,
        "status": "live",
        "module": mod.__class__.__name__,
        **extra,
    }


_MODULES: dict[str, GameModule] = {
    TicTacToe().game_id: TicTacToe(),
    TicTacToe4().game_id: TicTacToe4(),
    ConnectFour().game_id: ConnectFour(),
    Checkers().game_id: Checkers(),
    Go9().game_id: Go9(),
    ShogiLite().game_id: ShogiLite(),
    XiangqiLite().game_id: XiangqiLite(),
}

GAME_CATALOG: dict[str, dict[str, Any]] = {
    CHESS_META["game_id"]: CHESS_META,
    **{
        gid: _meta(
            mod,
            family={
                "agentic.tictactoe": "classic",
                "agentic.tictactoe_4": "classic",
                "agentic.connect4": "classic",
                "agentic.checkers": "classic",
                "agentic.go9": "territory",
                "agentic.shogi_lite": "asian",
                "agentic.xiangqi_lite": "asian",
            }.get(gid, "other"),
        )
        for gid, mod in _MODULES.items()
    },
}


def list_games() -> list[dict[str, Any]]:
    return list(GAME_CATALOG.values())


def get_game(game_id: str) -> Optional[GameModule]:
    if game_id == "agentic.chess_standard":
        return None  # handled by chess arena
    return _MODULES.get(game_id)


def get_game_meta(game_id: str) -> Optional[dict[str, Any]]:
    return GAME_CATALOG.get(game_id)
