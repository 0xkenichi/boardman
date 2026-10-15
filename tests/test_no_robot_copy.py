"""User-facing copy says "AI agent" / "AI manager", never "robot".

Founder call: "robot" scares people. This scans the site (pages, components,
public text) and the bot / channel message code, and fails on any "robot"
wording outside the few technical names that must keep it: Next's ``robots``
metadata key and ``robots.ts`` (search-engine crawlers), ``robots.txt``, and
the Roboto font.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

SCAN = [
    ("frontend/app", {".ts", ".tsx", ".css", ".md", ".json"}),
    ("frontend/components", {".ts", ".tsx", ".css"}),
    ("frontend/lib", {".ts", ".tsx"}),
    ("frontend/public", {".txt", ".json", ".html", ".js", ".css", ".md"}),
    ("src/bot", {".py"}),
    ("src/channels", {".py"}),
]
SKIP_FILES = {"frontend/app/robots.ts"}  # the crawler rules file itself

# Technical names that legitimately contain the letters.
ALLOWED = [
    re.compile(r"\brobots\s*:"),  # Next metadata key: robots: { index, follow }
    re.compile(r"MetadataRoute\.Robots"),
    re.compile(r"\brobots\(\)"),
    re.compile(r"robots\.txt", re.I),
    re.compile(r"Roboto"),
]
ROBOT = re.compile(r"robot", re.I)


def _offenders() -> list[str]:
    hits: list[str] = []
    for rel, exts in SCAN:
        base = ROOT / rel
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if not path.is_file() or path.suffix not in exts:
                continue
            if "node_modules" in path.parts or ".next" in path.parts:
                continue
            relpath = path.relative_to(ROOT).as_posix()
            if relpath in SKIP_FILES:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            for n, line in enumerate(text.splitlines(), 1):
                cleaned = line
                for pat in ALLOWED:
                    cleaned = pat.sub("", cleaned)
                if ROBOT.search(cleaned):
                    hits.append(f"{relpath}:{n}: {line.strip()[:120]}")
    return hits


def test_user_facing_copy_never_says_robot():
    hits = _offenders()
    assert not hits, "Say 'AI agent' / 'AI manager', not 'robot':\n" + "\n".join(hits)


def test_allowlist_still_catches_robot_copy():
    line = "robots: { index: false }, font: Roboto — and a robot manager"
    cleaned = line
    for pat in ALLOWED:
        cleaned = pat.sub("", cleaned)
    assert ROBOT.search(cleaned)
