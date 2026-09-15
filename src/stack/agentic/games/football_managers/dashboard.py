"""AFM owner dashboard — the owner seat, step 5: follow your club.

One read model over everything a club owner cares about, derived from state
that already exists (no new writes):

- **table position + results** — the club's row and recent fixtures from the
  live season store (`season.py`), with the agent's *decision* attached to
  each result (the formation/tags/XI it locked for that matchday).
- **spending log** — the club budget build (roster spend at create) plus the
  agent wallet's ledger movements: season entry, matchday wages, stakes
  locked/settled/refunded and season payouts (`ledger.py`).
- **suspension / injury news** — squad players carrying an oracle injury or
  suspension, plus anyone sent off in the club's most recent fixture who is
  therefore banned from the next one.

Everything here is a projection for the owner; the agent's own surfaces (FM
tools) stay separate.
"""
from __future__ import annotations

import re
from decimal import Decimal
from typing import Any, Optional

from gaming.src.stack.agentic.games.football_managers import season as S
from gaming.src.stack.agentic.games.football_managers.agent_market import ARCHETYPES
from gaming.src.stack.agentic.games.football_managers.club_store import get_club, list_clubs
from gaming.src.stack.agentic import ledger as L

_REF_SEASON_MD = re.compile(r"^afm_season_(\d+)_md(\d+)_(.+)_(.+)$")
_REF_S_MD = re.compile(r"^s(\d+)_md(\d+)$")
_WAGE_RE = re.compile(r"^afm_wages_s\d+$")


def _names() -> dict[str, str]:
    return {c["agent_id"]: c.get("club_name") or c["agent_id"] for c in list_clubs()}


def _finances(club: dict[str, Any], wallet: str) -> dict[str, Any]:
    budget = Decimal(str(club.get("budget_usdc") or "0"))
    spend = Decimal(str(club.get("spend_usdc") or "0"))
    return {
        "budget_usdc": str(budget),
        "spend_usdc": str(spend),
        "remaining_usdc": str(max(budget - spend, Decimal("0"))),
        "wallet_balance_usdc": str(L.balance(wallet)) if wallet else "0",
    }


def _spend_detail(ref: str, names: dict[str, str]) -> tuple[str, str]:
    """Human label + context for a ledger movement (season/MD/opponent)."""
    m = _REF_SEASON_MD.match(ref)
    if m:
        no, md, home, away = m.groups()
        opp = names.get(away, away) if home else names.get(home, home)
        return f"Season {no} · MD {md}", f"vs {opp}"
    m = _REF_S_MD.match(ref)
    if m:
        return f"Season {m.group(1)} · MD {m.group(2)}", ""
    return "", ""


def _spending_log(club: dict[str, Any], wallet: str, names: dict[str, str]) -> list[dict[str, Any]]:
    """Club budget build + the agent wallet's AFM ledger movements, newest first."""
    out: list[dict[str, Any]] = []

    budget = Decimal(str(club.get("budget_usdc") or "0"))
    spend = Decimal(str(club.get("spend_usdc") or "0"))
    if budget > 0:
        out.append(
            {
                "ts": "",
                "kind": "club_budget",
                "label": "Starting club budget",
                "detail": "owner grant — squad build budget",
                "amount": f"+{budget}",
                "balance_after": str(budget),
            }
        )
    if spend > 0:
        out.append(
            {
                "ts": "",
                "kind": "squad_build",
                "label": "Squad build (on create)",
                "detail": f"{club.get('roster_size', 0)} players · price + wage runway",
                "amount": f"-{spend}",
                "balance_after": str(max(budget - spend, Decimal("0"))),
            }
        )

    if not wallet:
        return out

    snap = L.snapshot()
    txs = snap.get("txs") or []
    escrows = snap.get("escrows") or {}
    # every fixture this agent played — lets escrow txs (which key on match_id)
    # be attributed even though they only carry wallet on the lock side
    my_matches: set[str] = set()
    st = S._state().get("season")
    if st:
        for info in (st.get("matchdays") or {}).values():
            for r in info.get("results") or []:
                if r.get("home_agent_id") == club["agent_id"] or r.get("away_agent_id") == club["agent_id"]:
                    my_matches.add(r.get("match_id") or "")

    wkey = wallet.lower()
    for tx in txs:
        t = tx.get("type")
        reason = str(tx.get("reason") or "")
        ref = str(tx.get("ref") or "")
        mine = tx.get("wallet") == wkey or ref in my_matches or tx.get("winner") == wkey
        if not mine:
            continue
        if t in ("escrow_open",):
            continue

        amount: Optional[Decimal] = None
        label = ""
        detail = ""
        if t == "credit":
            amount = Decimal(str(tx.get("amount") or "0"))
            detail = "bankroll top-up" if reason == "demo_faucet" else ""
            label = {
                "demo_faucet": "Demo faucet (bankroll)",
                "afm_stake_refund": "Matchday stake refund",
                "afm_season_pot_payout": "Season prize payout",
                "afm_season_pot_dust": "Season prize (dust)",
            }.get(reason, reason)
        elif t == "debit":
            amount = -Decimal(str(tx.get("amount") or "0"))
            if _WAGE_RE.match(reason):
                label = "Matchday wages"
            elif reason == "afm_season_entry":
                label = "Season entry fee"
            else:
                label = reason
        elif t == "escrow_lock" and tx.get("wallet") == wkey:
            amount = -Decimal(str(tx.get("amount") or "0"))
            label = "Matchday stake locked"
        elif t == "escrow_settle" and tx.get("winner") == wkey:
            amount = Decimal(str(tx.get("payout") or "0"))
            label = "Matchday winnings"
        elif t == "escrow_refund_draw" and ref in my_matches:
            amount = Decimal(str((escrows.get(ref) or {}).get("stake_usdc") or "0")) or None
            label = "Matchday stake returned (draw)"

        if amount is None:
            continue

        if label == "Matchday wages":
            m = _REF_S_MD.match(ref)
            detail = f"Season {m.group(1)} · MD {m.group(2)}" if m else ""
        elif t == "escrow_lock":
            seg, opp = _spend_detail(ref, names)
            label = f"{label} · {seg}" if seg else label
            detail = opp
        elif t == "escrow_settle":
            seg, opp = _spend_detail(ref, names)
            label = f"{label} · {seg}" if seg else label
            detail = opp
        elif t == "escrow_refund_draw":
            seg, opp = _spend_detail(ref, names)
            label = f"{label} · {seg}" if seg else label
            detail = opp
        elif reason == "afm_season_entry":
            m = _REF_S_MD.match(ref) or re.match(r"^s(\d+)$", ref)
            detail = f"Season {m.group(1)}" if m else ""
        elif reason in ("afm_season_pot_payout", "afm_season_pot_dust"):
            m = _REF_S_MD.match(ref) or re.match(r"^s(\d+)$", ref)
            detail = f"Season {m.group(1)}" if m else ""

        out.append(
            {
                "ts": str(tx.get("ts") or ""),
                "kind": "ledger",
                "type": t,
                "label": label,
                "detail": detail,
                "amount": str(amount) if amount is not None else None,
                "ref": ref,
            }
        )

    out.sort(key=lambda e: e["ts"] or "", reverse=True)
    return out[:40]


def _news_for(club: dict[str, Any], agent_id: str) -> list[dict[str, Any]]:
    """Squad availability news: bans, suspensions and injuries, urgent first."""
    by_id = {p["player_id"]: p for p in club.get("squad") or []}
    news: list[dict[str, Any]] = []
    for pid, p in by_id.items():
        detail = None
        kind: Optional[str] = None
        if int(p.get("suspension_matches") or 0) > 0:
            kind = "suspension"
            detail = (
                f"Suspended — {int(p.get('suspension_matches') or 0)} "
                f"matchday{'s' if int(p.get('suspension_matches') or 0) != 1 else ''} left"
            )
        elif p.get("injury"):
            kind = "injury"
            detail = f"Out injured — {p['injury']}"
        if kind:
            news.append(
                {
                    "type": kind,
                    "severity": 2 if kind == "suspension" else 1,
                    "player_id": pid,
                    "name": p.get("name") or pid,
                    "position": str(p.get("slot") or p.get("primary_pos") or "").upper(),
                    "detail": detail,
                }
            )

    # a red card in the most recent fixture bans that player from the next one
    st = S._state().get("season")
    if st:
        banned = S._suspended_players(st, agent_id)
        if banned:
            for pid in sorted(banned):
                p = by_id.get(pid)
                news.append(
                    {
                        "type": "suspension",
                        "severity": 3,
                        "player_id": pid,
                        "name": (p or {}).get("name") or pid,
                        "position": str((p or {}).get("slot") or "").upper() or "—",
                        "detail": "Sent off last matchday — banned for the next fixture",
                        "matchday_next": int(st.get("current_matchday") or 1),
                    }
                )

    news.sort(key=lambda n: n["severity"], reverse=True)
    return news


def _form_guide(results: list[dict[str, Any]]) -> str:
    return " ".join(r["outcome"] for r in results[:5])


def owner_dashboard(agent_id: str) -> dict[str, Any]:
    """The step-5 owner view for one club — pure read over live state.

    Raises ValueError when the agent has no AFM club.
    """
    club = get_club(agent_id)
    if not club:
        raise ValueError(f"no AFM club for agent {agent_id}")

    from gaming.src.stack.agentic.registry import get_registry

    rec = get_registry().get_agent(agent_id) or {}
    mind = rec.get("mind") or {}
    archetype = str(mind.get("archetype") or "").strip() or (
        "striker" if "bluelock" in agent_id.lower() else "tactician"
    )
    manager = {
        "name": rec.get("name") or agent_id,
        "archetype": archetype,
        "archetype_name": ARCHETYPES.get(archetype, {}).get("name", archetype),
    }

    names = _names()
    wallet = S._wallet(agent_id)
    st = S._state().get("season")

    # ------------------------------------------------------------ table + sched
    rows: list[dict[str, Any]] = []
    snap = S._snapshot(st) if st else None
    if snap:
        rows = snap["standings"] or []
    mine = next((r for r in rows if r["agent_id"] == agent_id), None)

    upcoming: list[dict[str, Any]] = []
    if snap:
        for f in snap["upcoming"]:
            if agent_id not in (f["home_agent_id"], f["away_agent_id"]):
                continue
            upcoming.append(
                {
                    "matchday": f["matchday"],
                    "venue": "home" if f["home_agent_id"] == agent_id else "away",
                    "opponent_id": f["away_agent_id"] if f["home_agent_id"] == agent_id else f["home_agent_id"],
                    "opponent_club": f["away_club"] if f["home_agent_id"] == agent_id else f["home_club"],
                    "status": f["status"],
                    "deadline_at": f["deadline_at"],
                }
            )

    # --------------------------------------------------------------- my results
    results: list[dict[str, Any]] = []
    if st:
        for md_key in sorted((int(k) for k in (st.get("matchdays") or {})), reverse=True):
            info = st["matchdays"][str(md_key)] or {}
            for r in info.get("results") or []:
                if agent_id not in (r.get("home_agent_id"), r.get("away_agent_id")):
                    continue
                is_home = r.get("home_agent_id") == agent_id
                hg, ag = int(r.get("home_goals") or 0), int(r.get("away_goals") or 0)
                ours, theirs = (hg, ag) if is_home else (ag, hg)
                if ours > theirs:
                    outcome = "W"
                elif ours < theirs:
                    outcome = "L"
                else:
                    outcome = "D"
                opp = r.get("away_agent_id") if is_home else r.get("home_agent_id")

                lu = (r.get("lineups") or {}).get(agent_id) or {}
                dec = (info.get("decisions") or {}).get(agent_id) or {}
                xi_ids = list(dec.get("xi") or lu.get("xi") or [])
                banned_ids = list(lu.get("banned") or [])
                squad_by_id = {p["player_id"]: p for p in club.get("squad") or []}
                xi_names = [str((squad_by_id.get(pid) or {}).get("name") or pid) for pid in xi_ids]
                banned_names = [str((squad_by_id.get(pid) or {}).get("name") or pid) for pid in banned_ids]
                decision = {
                    "formation": dec.get("formation") or lu.get("formation") or club.get("formation") or "4-3-3",
                    "tags": list(dec.get("tags") or lu.get("tags") or club.get("tactical_tags") or ["balanced"]),
                    "xi": xi_names,
                    "banned": banned_names,
                    "auto": agent_id in (info.get("auto") or []),
                    # who produced the plan: the manager's own webhook or the
                    # deterministic playbook fallback
                    "source": dec.get("source") or ("auto" if agent_id in (info.get("auto") or []) else None),
                    "instructions": dec.get("instructions"),
                    "note": dec.get("note"),
                    "error": dec.get("error"),
                }
                _sum = S._summary(r)
                # FM post-match report summary (ratings/xG/errors) when the
                # stored result carries the engine's player_stats fold
                try:
                    from gaming.src.stack.agentic.games.football_managers.report import (
                        dashboard_match_report,
                    )

                    report = dashboard_match_report(r, info, agent_id)
                except Exception:
                    report = {}
                results.append(
                    {
                        "matchday": int(md_key),
                        "match_id": r.get("match_id"),
                        "played_at": info.get("resolved_at"),
                        "venue": "home" if is_home else "away",
                        "opponent_id": opp,
                        "opponent_club": names.get(opp, opp),
                        "our_goals": ours,
                        "their_goals": theirs,
                        "outcome": outcome,
                        "decision": decision,
                        "match_stats": _sum.get("match_stats"),
                        "report": report,
                    }
                )

    form = _form_guide(results)

    # ------------------------------------------------------------- spend + news
    finances = _finances(club, wallet)
    spending = _spending_log(club, wallet, names)

    squad = club.get("squad") or []
    news = _news_for(club, agent_id)
    injured_ids = {p["player_id"] for p in squad if p.get("injury")}
    suspended_ids = {p["player_id"] for p in squad if int(p.get("suspension_matches") or 0) > 0}
    banned_ids = {n["player_id"] for n in news if n.get("type") == "suspension" and n.get("severity") == 3}
    flagged = injured_ids | suspended_ids | banned_ids

    debts = {}
    if st:
        debts = {
            "wage_debt_usdc": str((st.get("wage_debt") or {}).get(agent_id, "0")),
            "stake_debt_usdc": str((st.get("stake_debt") or {}).get(agent_id, "0")),
        }

    return {
        "agent_id": agent_id,
        "club": club,
        "manager": manager,
        "season": (
            {
                "season_no": snap["season_no"],
                "status": snap["status"],
                "current_matchday": snap["current_matchday"],
                "matchdays_total": snap["matchdays_total"],
                "champion": snap.get("champion"),
            }
            if snap
            else None
        ),
        "table": {
            "in_season": bool(snap and mine),
            "rank": (mine or {}).get("rank"),
            "of": len(rows),
            "row": mine,
            "standings": rows,
        },
        "form": form,
        "results": results[:10],
        "upcoming": upcoming,
        "finances": {
            **finances,
            **debts,
        },
        "spending": spending,
        "news": news,
        "squad_status": {
            "total": len(squad),
            "starters": len(club.get("starters") or []),
            "injured": len(injured_ids),
            "suspended": len(suspended_ids | banned_ids),
            "banned_next": len(banned_ids),
            "available": len([p for p in squad if p["player_id"] not in flagged]),
        },
        "generated_at": S._now().isoformat(),
    }
