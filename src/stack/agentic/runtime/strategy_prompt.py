"""
Build per-agent strategy prompts for LLM reasoners (Gemini, ASI:One, …).

Every builder ships a different mind. The LLM does not replace their strategy —
it *applies* the strategy they declared in the agent manifest / mind / runtime.

Stack only enforces: response must be one of legal_moves.
"""
from __future__ import annotations

from typing import Any, Optional


def strategy_from_mind(
    mind: Any = None,
    *,
    agent_name: str = "Agent",
    agent_id: str = "",
    openings: Optional[list[str]] = None,
    strategy_id: str = "",
    strategy_notes: str = "",
    wallet_address: str = "",
    extra: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Normalize strategy fields from a Mind object, dict, or free-form builder payload."""
    m: dict[str, Any] = {}
    if mind is not None:
        if isinstance(mind, dict):
            m = dict(mind)
        else:
            for k in (
                "directive",
                "archetype",
                "blurb",
                "aggression",
                "king_attack",
                "counterpunch",
                "sacrifice_bias",
                "draw_aversion",
                "strategy",
                "strategy_notes",
                "principles",
                "avoid",
            ):
                if hasattr(mind, k):
                    m[k] = getattr(mind, k)
                elif isinstance(getattr(mind, "__dict__", None), dict) and k in mind.__dict__:
                    m[k] = mind.__dict__[k]

    if extra:
        m.update({k: v for k, v in extra.items() if v is not None})

    principles = m.get("principles") or m.get("strategy") or ""
    if isinstance(principles, list):
        principles = "; ".join(str(x) for x in principles)

    openings = openings or m.get("openings") or []
    if isinstance(openings, str):
        openings = [openings]

    return {
        "agent_name": agent_name or m.get("name") or "Agent",
        "agent_id": agent_id or m.get("agent_id") or "",
        "wallet_address": wallet_address or str(m.get("wallet_address") or m.get("wallet") or ""),
        "directive": str(m.get("directive") or "WIN. Play the strongest move that fits your strategy."),
        "archetype": str(m.get("archetype") or "balanced"),
        "blurb": str(m.get("blurb") or ""),
        "strategy_id": strategy_id or str(m.get("strategy_id") or ""),
        "strategy_notes": strategy_notes or str(m.get("strategy_notes") or principles or ""),
        "principles": str(principles or ""),
        "avoid": str(m.get("avoid") or ""),
        "openings": [str(x) for x in openings][:24],
        "aggression": m.get("aggression"),
        "king_attack": m.get("king_attack"),
        "counterpunch": m.get("counterpunch"),
        "sacrifice_bias": m.get("sacrifice_bias"),
        "draw_aversion": m.get("draw_aversion"),
    }


def build_system_prompt(strategy: dict[str, Any]) -> str:
    """System message: identity + builder strategy + mandatory FIDE rule book."""
    name = strategy.get("agent_name") or "Agent"
    wallet = strategy.get("wallet_address") or strategy.get("wallet") or ""
    lines = [
        f"You are {name}, an autonomous chess agent on Boardman Stack.",
        "You play only legal moves from the provided list.",
        "Your builder defined a unique strategy. Apply it — do not invent a different persona.",
        "You MUST NEVER break the Boardman Chess Rule Book (FIDE Laws). Legality overrides style.",
        "",
        f"Directive: {strategy.get('directive') or 'WIN.'}",
        f"Archetype: {strategy.get('archetype') or 'balanced'}",
    ]
    if wallet:
        lines.append(f"Wallet identity (stakes / settlement): {wallet}")
    if strategy.get("agent_id"):
        lines.append(f"Agent id: {strategy['agent_id']}")
    if strategy.get("blurb"):
        lines.append(f"Scout report: {strategy['blurb']}")
    if strategy.get("strategy_id"):
        lines.append(f"Strategy id: {strategy['strategy_id']}")
    if strategy.get("strategy_notes") or strategy.get("principles"):
        lines.append(f"Strategy notes: {strategy.get('strategy_notes') or strategy.get('principles')}")
    if strategy.get("avoid"):
        lines.append(f"Avoid: {strategy['avoid']}")
    if strategy.get("openings"):
        lines.append("Preferred openings / ideas: " + ", ".join(strategy["openings"]))

    # Soft knobs (builders set these in mind) — LLM guidance only
    knobs = []
    for label, key in (
        ("aggression", "aggression"),
        ("king attack", "king_attack"),
        ("counterpunch", "counterpunch"),
        ("sacrifice bias", "sacrifice_bias"),
        ("draw aversion", "draw_aversion"),
    ):
        v = strategy.get(key)
        if v is not None:
            try:
                knobs.append(f"{label}={float(v):.2f}")
            except (TypeError, ValueError):
                knobs.append(f"{label}={v}")
    if knobs:
        lines.append("Style knobs (1.0 = neutral): " + ", ".join(knobs))

    lines.extend(
        [
            "",
            "When choosing a move:",
            "1) Prefer lines that fit the strategy notes over generic engine chess.",
            "2) Still refuse blunders that clearly hang heavy material when avoidable.",
            "3) Never leave your king in check; never play illegal castling / en passant / promotion.",
            "4) Reply with JSON only: {\"move\":\"<UCI or SAN from the legal list>\"}.",
            "No commentary outside JSON.",
        ]
    )
    from gaming.src.stack.agentic.chess.rule_book import rule_book_system_suffix

    return "\n".join(lines) + rule_book_system_suffix()


def build_user_prompt(
    *,
    fen: str,
    side: str,
    legal_uci: list[str],
    legal_san: list[str],
    ply_hint: str = "",
) -> str:
    parts = [
        f"FEN: {fen}",
        f"Side to move: {side}",
    ]
    if ply_hint:
        parts.append(ply_hint)
    parts.append(
        "Legal UCI: "
        + ", ".join(legal_uci[:80])
        + (f" (+{len(legal_uci) - 80} more)" if len(legal_uci) > 80 else "")
    )
    parts.append("Legal SAN sample: " + ", ".join(legal_san[:40]))
    parts.append("Pick one legal move that best executes YOUR strategy.")
    return "\n".join(parts)
