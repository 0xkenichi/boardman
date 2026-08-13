"""Raja and Nero are two builder-shipped chess agents, not one shared bot."""
from __future__ import annotations

import ast
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
RAJA = _REPO / "src/stack/agentic/agents/raja"
NERO = _REPO / "src/stack/agentic/agents/nero"


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            out.add(node.module)
    return out


def test_silos_do_not_import_each_other():
    for p in RAJA.glob("*.py"):
        mods = _imports(p)
        assert not any("nero" in m for m in mods), p
    for p in NERO.glob("*.py"):
        mods = _imports(p)
        assert not any("raja" in m for m in mods), p


def test_each_builder_ships_chess_only():
    from gaming.src.stack.agentic.agents.raja.manifest import MANIFEST as R
    from gaming.src.stack.agentic.agents.nero.manifest import MANIFEST as N

    assert R["game_ids"] == ["agentic.chess_standard"]
    assert N["game_ids"] == ["agentic.chess_standard"]
    assert R["creator_id"] != N["creator_id"]
    assert R["runtime"]["engine"] == "webhook"
    assert N["runtime"]["engine"] == "webhook"
    assert R["runtime"]["webhook_url"] != N["runtime"]["webhook_url"]


def test_raja_refuses_other_games():
    from gaming.src.stack.agentic.agents.raja.runtime import pick_move

    try:
        pick_move(game_id="agentic.connect4", fen="8/8/8/8/8/8/8/8 w - - 0 1", legal_moves=[])
        assert False
    except ValueError as e:
        assert "chess-only" in str(e)


def test_nero_refuses_other_games():
    from gaming.src.stack.agentic.agents.nero.runtime import pick_move

    try:
        pick_move(game_id="agentic.connect4", fen="8/8/8/8/8/8/8/8 w - - 0 1", legal_moves=[])
        assert False
    except ValueError as e:
        assert "chess-only" in str(e)


def test_each_silo_returns_a_legal_chess_move():
    import chess
    from gaming.src.stack.agentic.agents.raja.runtime import pick_move as raja_pick
    from gaming.src.stack.agentic.agents.nero.runtime import pick_move as nero_pick

    board = chess.Board()
    legal = [m.uci() for m in board.legal_moves]
    r = raja_pick(fen=board.fen(), legal_moves=legal)
    n = nero_pick(fen=board.fen(), legal_moves=legal)
    assert r in legal
    assert n in legal


def test_house_rejects_game_builder_did_not_ship(tmp_path, monkeypatch):
    import sys

    sys.path.insert(0, str(_REPO))
    monkeypatch.setenv("BOARDMAN_AGENTIC_DATA", str(tmp_path))
    monkeypatch.setenv("BOARDMAN_AGENTIC_ONCHAIN", "0")
    monkeypatch.setattr("gaming.src.stack.agentic.onchain.onchain_enabled", lambda: False)
    from gaming.src.stack.agentic.registry import get_registry
    from gaming.src.stack.agentic.matches import get_match_service

    get_registry.cache_clear()
    get_match_service.cache_clear()
    from gaming.src.stack.agentic.house import get_house

    reg = get_registry()
    agents = {a["agent_id"]: a for a in reg.ensure_demo_agents()}
    rt = get_house()
    try:
        rt.open_match(
            agent_a_id=agents["agent_raja_kia_alekhine"]["agent_id"],
            agent_b_id=agents["agent_nero_sicilian_french"]["agent_id"],
            game_id="agentic.connect4",
            stake_usdc=1,
        )
        assert False
    except ValueError as e:
        assert "has not shipped" in str(e) or "does not play" in str(e)
