"""
Per-agent LLM API key resolution.

Each agent can have its own free teaching/reasoning key so Nero and Raja
(and third-party agents) do not share one brain credential.

Env patterns (first hit wins for that provider):

  Gemini (Google AI Studio — free key):
    GEMINI_API_KEY_NERO / GEMINI_API_KEY_RAJA / GEMINI_API_KEY_<SLUG>
    GEMINI_API_KEY / GOOGLE_API_KEY / GOOGLE_GENERATIVE_AI_API_KEY  (shared fallback)

  ASI:One:
    ASI_ONE_API_KEY_NERO / ASI_ONE_API_KEY_RAJA / ASI_ONE_API_KEY_<SLUG>
    ASI_ONE_API_KEY / ASI_API_KEY  (shared fallback)

  Allow-list (who may call LLMs when only a *shared* key exists):
    BOARDMAN_LLM_AGENTS=nero,raja     # preferred
    BOARDMAN_ASI_AGENTS=nero          # legacy alias (still honored)

  If an agent has a *dedicated* key env var set, they are always allowed
  for that provider (dedicated key implies opt-in).
"""
from __future__ import annotations

import os
import re
from typing import Optional


def agent_slugs(agent_id: str = "", name: str = "") -> list[str]:
    """Stable slug tokens used for env suffix matching."""
    raw = f"{agent_id} {name}".strip().lower()
    tokens: list[str] = []
    if name:
        tokens.append(re.sub(r"[^a-z0-9]+", "_", name.strip().lower()).strip("_"))
    if agent_id:
        aid = agent_id.strip().lower()
        tokens.append(re.sub(r"[^a-z0-9]+", "_", aid).strip("_"))
        # agent_nero_sicilian_french → nero
        parts = [p for p in aid.replace("-", "_").split("_") if p and p not in {"agent", "v1", "v2", "v3"}]
        tokens.extend(parts[:3])
    # known demo shortcuts
    hay = raw
    if "nero" in hay:
        tokens.append("nero")
    if "raja" in hay:
        tokens.append("raja")
    # dedupe preserve order
    out: list[str] = []
    seen: set[str] = set()
    for t in tokens:
        if t and t not in seen:
            seen.add(t)
            out.append(t)
    return out


def _env(*names: str) -> str:
    for n in names:
        v = (os.getenv(n) or "").strip()
        if v:
            return v
    return ""


def _dedicated_gemini(slugs: list[str]) -> str:
    for s in slugs:
        key = _env(f"GEMINI_API_KEY_{s.upper()}")
        if key:
            return key
    return ""


def _dedicated_asi(slugs: list[str]) -> str:
    for s in slugs:
        key = _env(f"ASI_ONE_API_KEY_{s.upper()}", f"ASI_API_KEY_{s.upper()}")
        if key:
            return key
    return ""


def _shared_gemini() -> str:
    return _env(
        "GEMINI_API_KEY",
        "GOOGLE_API_KEY",
        "GOOGLE_GENERATIVE_AI_API_KEY",
    )


def _shared_asi() -> str:
    return _env("ASI_ONE_API_KEY", "ASI_API_KEY")


def allow_list() -> list[str]:
    raw = (
        os.getenv("BOARDMAN_LLM_AGENTS")
        or os.getenv("BOARDMAN_ASI_AGENTS")
        or "nero,raja"  # both demo agents; dedicated keys always win anyway
    ).strip().lower()
    if raw in {"*", "all", "1", "true", "yes"}:
        return ["*"]
    return [t.strip() for t in raw.split(",") if t.strip()]


def agent_on_allow_list(agent_id: str = "", name: str = "") -> bool:
    tokens = allow_list()
    if "*" in tokens:
        return True
    hay = f"{agent_id} {name}".lower()
    return any(t in hay for t in tokens)


def resolve_gemini_key(agent_id: str = "", name: str = "") -> str:
    """Gemini API key for this agent (dedicated preferred, then shared if allowed)."""
    slugs = agent_slugs(agent_id, name)
    dedicated = _dedicated_gemini(slugs)
    if dedicated:
        return dedicated
    shared = _shared_gemini()
    if shared and agent_on_allow_list(agent_id, name):
        return shared
    # Dedicated Nero key historically used as shared Nero default
    nero_only = _env("GEMINI_API_KEY_NERO")
    if nero_only and ("nero" in f"{agent_id} {name}".lower()):
        return nero_only
    return ""


def resolve_asi_key(agent_id: str = "", name: str = "") -> str:
    slugs = agent_slugs(agent_id, name)
    dedicated = _dedicated_asi(slugs)
    if dedicated:
        return dedicated
    shared = _shared_asi()
    if shared and agent_on_allow_list(agent_id, name):
        return shared
    return ""


def gemini_enabled_for(agent_id: str = "", name: str = "") -> bool:
    return bool(resolve_gemini_key(agent_id, name))


def asi_enabled_for(agent_id: str = "", name: str = "") -> bool:
    return bool(resolve_asi_key(agent_id, name))


def llm_enabled_for(agent_id: str = "", name: str = "") -> bool:
    """True if this agent may attempt any LLM reasoner."""
    if gemini_enabled_for(agent_id, name) or asi_enabled_for(agent_id, name):
        return True
    # Allow-list alone is not enough without a key — but keep explicit opt-in path
    return False


def key_status(agent_id: str = "", name: str = "") -> dict:
    """Safe status (no key material) for health / arena debug UI."""
    slugs = agent_slugs(agent_id, name)
    return {
        "agent_id": agent_id,
        "name": name,
        "slugs": slugs,
        "on_allow_list": agent_on_allow_list(agent_id, name),
        "gemini_configured": gemini_enabled_for(agent_id, name),
        "asi_configured": asi_enabled_for(agent_id, name),
        "gemini_dedicated": bool(_dedicated_gemini(slugs)),
        "asi_dedicated": bool(_dedicated_asi(slugs)),
        "gemini_model": os.getenv("GEMINI_MODEL") or "gemini-2.0-flash",
        "asi_model": os.getenv("ASI_ONE_MODEL") or "asi1-mini",
        "reasoner_order": (
            os.getenv("BOARDMAN_NERO_REASONERS")
            or os.getenv("BOARDMAN_LLM_REASONERS")
            or "asi,gemini"
        ),
    }


def reasoner_order() -> list[str]:
    raw = (
        os.getenv("BOARDMAN_LLM_REASONERS")
        or os.getenv("BOARDMAN_NERO_REASONERS")
        or "asi,gemini"
    ).lower().replace(" ", "")
    return [x for x in raw.split(",") if x]
