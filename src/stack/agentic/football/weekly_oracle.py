"""Weekly API-Football oracle for Agentic Football Managers.

Patches form / injury / suspension on the AFM catalog. Never writes match scores.

Usage (laptop hub):
  export API_FOOTBALL_KEY=...
  python -m gaming.src.stack.agentic.football.weekly_oracle

Free plan is 100 req/day. Default path is 5 league injury calls (EPL, La Liga,
Serie A, Bundesliga, Ligue 1) plus optional name search for unmatched stars.

Oracle fields written onto catalog_v0.json:
  form, injury, suspension_matches, oracle_updated_at, oracle_source
"""
from __future__ import annotations

import json
import logging
import os
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_p = Path(__file__).resolve()
search_p = _p
while search_p.name != "gaming" and search_p.parent != search_p:
    search_p = search_p.parent
if search_p.name == "gaming":
    sys.path.insert(0, str(search_p.parent))

from gaming.src.stack.agentic.football.api_client import configured, injuries  # noqa: E402

logger = logging.getLogger(__name__)

# API-Football league ids
DEFAULT_LEAGUES = (
    (39, "EPL"),
    (140, "La Liga"),
    (135, "Serie A"),
    (78, "Bundesliga"),
    (61, "Ligue 1"),
)

CATALOG_PATH = (
    Path(__file__).resolve().parent.parent
    / "games"
    / "football_managers"
    / "data"
    / "catalog_v0.json"
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _norm(name: str) -> str:
    s = unicodedata.normalize("NFKD", name or "")
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return " ".join(s.lower().replace(".", " ").split())


def _last_token(name: str) -> str:
    parts = _norm(name).split()
    return parts[-1] if parts else ""


def apply_injuries(
    catalog: list[dict[str, Any]],
    reports: list[dict[str, Any]],
) -> dict[str, Any]:
    """Match injury reports onto catalog rows by normalized name / surname."""
    by_full = {_norm(p.get("name") or ""): p for p in catalog}
    by_last: dict[str, list[dict[str, Any]]] = {}
    for p in catalog:
        by_last.setdefault(_last_token(p.get("name") or ""), []).append(p)

    patched = 0
    unmatched = 0
    # Clear stale injury flags first so recovered players come off the list
    for p in catalog:
        p["injury"] = None

    for rep in reports:
        name = rep.get("name") or ""
        key = _norm(name)
        row = by_full.get(key)
        if not row:
            cands = by_last.get(_last_token(name)) or []
            row = cands[0] if len(cands) == 1 else None
        if not row:
            unmatched += 1
            continue
        reason = (rep.get("reason") or rep.get("type") or "injured").strip()
        kind = (rep.get("type") or "").lower()
        if "susp" in kind or "red" in reason.lower() or "yellow" in reason.lower():
            row["suspension_matches"] = max(int(row.get("suspension_matches") or 0), 1)
            row["injury"] = None
        else:
            row["injury"] = reason[:80] or "injured"
        row["form"] = min(float(row.get("form") or 6.5), 5.0)
        row["oracle_updated_at"] = _now()
        row["oracle_source"] = "api-football"
        patched += 1

    return {"patched": patched, "unmatched": unmatched, "reports": len(reports)}


def apply_weekly_stats(
    catalog: list[dict[str, Any]],
    stats: list[dict[str, Any]],
) -> dict[str, Any]:
    """Attach weekly goals / assists / rating. Bumps in-game price slightly on form."""
    by_full = {_norm(p.get("name") or ""): p for p in catalog}
    patched = 0
    for row in stats:
        name = row.get("name") or ""
        rec = by_full.get(_norm(name))
        if not rec:
            continue
        goals = int(row.get("goals") or 0)
        assists = int(row.get("assists") or 0)
        rating = row.get("rating")
        apps = int(row.get("appearances") or row.get("apps") or 0)
        rec["weekly_goals"] = goals
        rec["weekly_assists"] = assists
        rec["weekly_apps"] = apps
        if rating is not None:
            rec["weekly_rating"] = float(rating)
            rec["form"] = max(3.0, min(10.0, float(rating)))
        # Context only: 0.05 USDC per goal+assist this week, capped.
        bump = min(0.50, 0.05 * (goals + assists))
        try:
            price = float(rec.get("game_price_usdc") or 0)
            rec["game_price_usdc"] = f"{price + bump:.2f}"
        except (TypeError, ValueError):
            pass
        rec["oracle_updated_at"] = _now()
        rec["oracle_source"] = rec.get("oracle_source") or "api-football"
        patched += 1
    return {"patched": patched, "rows": len(stats)}


def run(
    *,
    season: int | None = None,
    leagues: list[tuple[int, str]] | None = None,
    catalog_path: Path | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    if not configured():
        raise SystemExit("Set API_FOOTBALL_KEY (or RAPIDAPI_KEY + RAPIDAPI_HOST)")

    year = season or int(os.getenv("API_FOOTBALL_SEASON") or datetime.now(timezone.utc).year)
    path = catalog_path or CATALOG_PATH
    if not path.exists():
        raise SystemExit(f"catalog missing: {path}")
    catalog = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(catalog, list):
        raise SystemExit("catalog_v0.json must be a JSON array")

    all_reports: list[dict[str, Any]] = []
    per_league: list[dict[str, Any]] = []
    for lid, label in leagues or list(DEFAULT_LEAGUES):
        reps = injuries(lid, year)
        per_league.append({"league": label, "id": lid, "count": len(reps)})
        all_reports.extend(reps)

    stats = apply_injuries(catalog, all_reports)
    stats["season"] = year
    stats["leagues"] = per_league
    stats["catalog_path"] = str(path)
    stats["dry_run"] = dry_run

    if not dry_run:
        path.write_text(json.dumps(catalog, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return stats


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    dry = os.getenv("ORACLE_DRY_RUN", "").strip().lower() in {"1", "true", "yes"}
    stats = run(dry_run=dry)
    print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    main()
