"""Optional LLM brain for AFM managers — builders bring the key.

A third-party manager is just: a mind (archetype + persona) and, if the
builder wants language-model judgement, an API key. When a supported key is
present the manager asks the model to pick the plan from the same observable
ask the deterministic brain sees; the House validates the reply with the
same hard rules it applies to every webhook plan (legal XI, whitelisted
formations/tags, bench caps) and any failure falls back to the deterministic
mind — a club can never be defaulted by a hallucination.

Env:
  BOARDMAN_AFM_LLM_KEY      — explicit key (any provider below)
  OPENAI_API_KEY            — OpenAI-compatible /chat/completions
  ANTHROPIC_API_KEY         — Anthropic /v1/messages
  BOARDMAN_AFM_LLM_MODEL    — model override (per provider default otherwise)
  BOARDMAN_AFM_LLM_BASE_URL — OpenAI-compatible base URL (proxies/OSS runtimes)
  BOARDMAN_AFM_LLM          — "0" disables the seam entirely
"""
from __future__ import annotations

import json
import logging
import os
import urllib.request
from typing import Any, Optional

logger = logging.getLogger(__name__)

TIMEOUT_SEC = 12.0

_OPENAI_MODEL = "gpt-4o-mini"
_ANTHROPIC_MODEL = "claude-3-5-haiku-latest"


def llm_available() -> bool:
    """True when the seam is on and any supported key is configured."""
    if os.getenv("BOARDMAN_AFM_LLM", "1").strip().lower() in ("0", "false", "off"):
        return False
    return bool(
        os.getenv("BOARDMAN_AFM_LLM_KEY")
        or os.getenv("OPENAI_API_KEY")
        or os.getenv("ANTHROPIC_API_KEY")
    )


def _prompt(mind: dict[str, Any], ask: dict[str, Any]) -> str:
    arch = str(mind.get("archetype") or "balanced")
    directive = str(mind.get("directive") or "").strip()
    notes = str(mind.get("strategy_notes") or "").strip()
    return (
        "You are the manager of a football club in the Agentic Football "
        "Managers league. Pick your matchday plan from the context below.\n\n"
        f"Your managerial identity — archetype: {arch}.\n"
        + (f"Directive: {directive}\n" if directive else "")
        + (f"Tactics notes: {notes}\n" if notes else "")
        + "\nMatchday context (JSON):\n"
        + json.dumps(ask, ensure_ascii=False, separators=(",", ":"))
        + "\n\nRules: pick `formation` from ask.legal.formations; pick "
        "`tactical_tags` from ask.legal.tactical_tags (1-2 tags); `xi` must "
        "be exactly 11 player_ids from your squad (one of them a goalkeeper "
        "— position GK); `bench` at most "
        + str(5)
        + " other squad ids, no overlap with xi. Tired players (low "
        "`condition`) may need resting. Reply with STRICT JSON only, no "
        "prose, shaped exactly like:\n"
        '{"formation": "...", "xi": ["id", ...], "bench": ["id", ...], '
        '"tactical_tags": ["..."], "instructions": "one short line"}'
    )


def _parse_plan(raw: str) -> Optional[dict[str, Any]]:
    """Extract the plan JSON from a model reply (tolerates code fences)."""
    if not raw:
        return None
    text = raw.strip()
    if "```" in text:
        for chunk in text.split("```"):
            chunk = chunk.strip()
            if chunk.startswith("{"):
                text = chunk
                break
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        plan = json.loads(text[start : end + 1])
    except Exception:
        return None
    if not isinstance(plan, dict):
        return None
    # light sanity only — the House's validate_matchday_plan is the real gate
    if not str(plan.get("formation") or ""):
        return None
    if not isinstance(plan.get("xi"), list) or len(plan["xi"]) != 11:
        return None
    return plan


def _post(url: str, headers: dict[str, str], body: dict[str, Any]) -> Optional[str]:
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", **headers},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SEC) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        logger.warning("[afm-llm] brain call failed: %s", exc)
        return None
    # OpenAI-compatible shape
    try:
        choices = data.get("choices")
        if isinstance(choices, list) and choices:
            return str(((choices[0] or {}).get("message") or {}).get("content") or "")
    except Exception:
        pass
    # Anthropic shape
    try:
        content = data.get("content")
        if isinstance(content, list) and content:
            return str(content[0].get("text") or "")
    except Exception:
        pass
    return None


def plan_from_ask(mind: dict[str, Any], ask: dict[str, Any]) -> Optional[dict[str, Any]]:
    """The LLM manager's plan for an ask payload — None on any failure.

    The caller (agent runtime) falls back to its deterministic mind when this
    returns None, and the House validates whatever comes back either way.
    """
    if not llm_available():
        return None
    prompt = _prompt(mind, ask or {})
    model = (os.getenv("BOARDMAN_AFM_LLM_MODEL") or "").strip()
    key = (
        os.getenv("BOARDMAN_AFM_LLM_KEY")
        or os.getenv("OPENAI_API_KEY")
        or ""
    ).strip()
    anthropic_key = os.getenv("ANTHROPIC_API_KEY") or ""

    if key:
        base = (os.getenv("BOARDMAN_AFM_LLM_BASE_URL") or "https://api.openai.com/v1").rstrip("/")
        text = _post(
            f"{base}/chat/completions",
            {"Authorization": f"Bearer {key}"},
            {
                "model": model or _OPENAI_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.7,
                "max_tokens": 900,
            },
        )
    elif anthropic_key:
        text = _post(
            "https://api.anthropic.com/v1/messages",
            {"x-api-key": anthropic_key, "anthropic-version": "2023-06-01"},
            {
                "model": model or _ANTHROPIC_MODEL,
                "max_tokens": 900,
                "messages": [{"role": "user", "content": prompt}],
            },
        )
    else:
        return None

    plan = _parse_plan(text or "")
    if plan:
        plan.setdefault("instructions", "Picked by the manager's language-model brain.")
    return plan
