"""Season / table helpers (v0)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class TableRow:
    agent_id: str
    played: int = 0
    won: int = 0
    drawn: int = 0
    lost: int = 0
    gf: int = 0
    ga: int = 0
    points: int = 0

    @property
    def gd(self) -> int:
        return self.gf - self.ga

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "played": self.played,
            "won": self.won,
            "drawn": self.drawn,
            "lost": self.lost,
            "gf": self.gf,
            "ga": self.ga,
            "gd": self.gd,
            "points": self.points,
        }


@dataclass
class Season:
    season_id: str
    rows: dict[str, TableRow] = field(default_factory=dict)
    results: list[dict[str, Any]] = field(default_factory=list)

    def ensure(self, agent_id: str) -> TableRow:
        if agent_id not in self.rows:
            self.rows[agent_id] = TableRow(agent_id=agent_id)
        return self.rows[agent_id]

    def apply_result(
        self,
        *,
        home_agent_id: str,
        away_agent_id: str,
        home_goals: int,
        away_goals: int,
        home_points: int,
        away_points: int,
        match_id: str = "",
    ) -> None:
        h = self.ensure(home_agent_id)
        a = self.ensure(away_agent_id)
        for row, gf, ga, pts in (
            (h, home_goals, away_goals, home_points),
            (a, away_goals, home_goals, away_points),
        ):
            row.played += 1
            row.gf += gf
            row.ga += ga
            row.points += pts
            if gf > ga:
                row.won += 1
            elif gf < ga:
                row.lost += 1
            else:
                row.drawn += 1
        self.results.append(
            {
                "match_id": match_id,
                "home": home_agent_id,
                "away": away_agent_id,
                "score": f"{home_goals}-{away_goals}",
            }
        )

    def table(self) -> list[dict[str, Any]]:
        rows = sorted(
            self.rows.values(),
            key=lambda r: (-r.points, -r.gd, -r.gf, r.agent_id),
        )
        out = []
        for i, r in enumerate(rows, 1):
            d = r.to_dict()
            d["rank"] = i
            out.append(d)
        return out
