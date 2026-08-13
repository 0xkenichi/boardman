"""API-Football weekly oracle applies injuries without hitting the network."""
from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from gaming.src.stack.agentic.football.weekly_oracle import (  # noqa: E402
    apply_injuries,
    apply_weekly_stats,
)


def test_apply_injuries_matches_name_and_clears_stale():
    catalog = [
        {"name": "Erling Haaland", "form": 7.0, "injury": "old knock", "suspension_matches": 0},
        {"name": "Kylian Mbappé", "form": 7.5, "injury": "hamstring", "suspension_matches": 0},
        {"name": "Rodri", "form": 6.5, "injury": None, "suspension_matches": 0},
    ]
    reports = [
        {"name": "E. Haaland", "type": "Missing Fixture", "reason": "Knee Injury"},
        {"name": "Rodri", "type": "Suspended", "reason": "Red Card"},
    ]
    stats = apply_injuries(catalog, reports)
    assert stats["patched"] == 2
    by_name = {p["name"]: p for p in catalog}
    assert by_name["Erling Haaland"]["injury"] == "Knee Injury"
    assert by_name["Erling Haaland"]["form"] <= 5.0
    # recovered player cleared
    assert by_name["Kylian Mbappé"]["injury"] is None
    assert by_name["Rodri"]["suspension_matches"] >= 1
    assert by_name["Rodri"]["oracle_source"] == "api-football"


def test_weekly_stats_bump_price_without_writing_scores():
    catalog = [
        {"name": "Erling Haaland", "game_price_usdc": "18.00", "form": 6.5},
    ]
    out = apply_weekly_stats(
        catalog,
        [{"name": "Erling Haaland", "goals": 2, "assists": 1, "rating": 8.4, "appearances": 1}],
    )
    assert out["patched"] == 1
    p = catalog[0]
    assert p["weekly_goals"] == 2
    assert p["weekly_assists"] == 1
    assert p["form"] == 8.4
    assert float(p["game_price_usdc"]) > 18.0
