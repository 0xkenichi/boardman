"""requirements-lock.txt pins every direct dependency and agrees with requirements.txt.

Infra audit 2026-10 (INF-11): requirements.txt is floors only (>=), so every
image build resolved whatever PyPI served that day. The Dockerfiles and CI now
install with `-c src/backend/requirements-lock.txt`; this test keeps the two files
consistent so a constraint can never silently fail to apply.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

packaging = pytest.importorskip("packaging")
from packaging.requirements import Requirement  # noqa: E402
from packaging.utils import canonicalize_name  # noqa: E402
from packaging.version import Version  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
REQS = ROOT / "src" / "backend" / "requirements.txt"
LOCK = ROOT / "src" / "backend" / "requirements-lock.txt"


def _lines(path: Path) -> list[str]:
    out = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if line:
            out.append(line)
    return out


def _lock() -> dict[str, Version]:
    pins: dict[str, Version] = {}
    for line in _lines(LOCK):
        m = re.fullmatch(r"([A-Za-z0-9_.\-]+)==([A-Za-z0-9_.+\-]+)", line)
        assert m, f"requirements-lock.txt line is not an exact pin: {line!r}"
        name = canonicalize_name(m.group(1))
        assert name not in pins, f"duplicate pin for {name}"
        pins[name] = Version(m.group(2))
    return pins


def test_lock_is_exact_pins_only():
    assert _lock()


def test_every_direct_dependency_is_pinned_and_satisfies_requirements():
    pins = _lock()
    problems = []
    for line in _lines(REQS):
        req = Requirement(line)
        name = canonicalize_name(req.name)
        if name not in pins:
            problems.append(f"{req.name}: not pinned in requirements-lock.txt")
        elif req.specifier and not req.specifier.contains(pins[name], prereleases=True):
            problems.append(f"{req.name}: lock {pins[name]} violates {req.specifier}")
    assert not problems, "\n".join(problems)


@pytest.mark.parametrize("dockerfile", ["Dockerfile", "Dockerfile.akash"])
def test_dockerfiles_install_with_the_lock(dockerfile):
    text = (ROOT / dockerfile).read_text(encoding="utf-8")
    assert "requirements-lock.txt" in text and "-c /app/requirements-lock.txt" in text, (
        f"{dockerfile} must install with -c /app/requirements-lock.txt"
    )
