"""Route handlers must not be `async def` unless they await something.

FastAPI runs plain `def` handlers in its threadpool, but an `async def` that
never awaits runs on the event loop — so a single slow database read (the
house floor scanning the matches table) froze every request, health checks
included, right after the storage cutover.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
API_FILES = [
    "src/stack/agentic/api.py",
    "src/stack/api_v1.py",
    "src/stack/api.py",
    "src/backend/api/rematch_web.py",
]
_ROUTE_VERBS = {"get", "post", "put", "delete", "patch"}


def _blocking_async_routes(path: Path) -> list[str]:
    tree = ast.parse(path.read_text())
    bad = []
    for node in tree.body:
        if not isinstance(node, ast.AsyncFunctionDef):
            continue
        routed = any(
            isinstance(d, ast.Call) and getattr(d.func, "attr", "") in _ROUTE_VERBS
            for d in node.decorator_list
        )
        awaits = any(isinstance(x, (ast.Await, ast.AsyncFor, ast.AsyncWith)) for x in ast.walk(node))
        if routed and not awaits:
            bad.append(f"{path.name}:{node.lineno} {node.name}")
    return bad


@pytest.mark.parametrize("rel", API_FILES)
def test_async_routes_await_something(rel):
    assert _blocking_async_routes(ROOT / rel) == []
