"""Backend modules load only their own checkout's .env, never a parent's.

A bare ``load_dotenv()`` walks up from the calling file until it finds a .env.
Worktrees live under the main checkout (.claude/worktrees/<name>/), so from a
worktree that walk lands on the main checkout's .env — live Supabase, Circle,
resolver and admin keys — and any local run or test there quietly talks to
production services.
"""
from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
LOAD_LINE = 'load_dotenv(Path(__file__).resolve().parents[2] / ".env")'


def test_no_bare_load_dotenv_in_src():
    offenders = []
    for path in sorted((REPO_ROOT / "src").rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fn = node.func
            name = fn.id if isinstance(fn, ast.Name) else getattr(fn, "attr", "")
            if name == "find_dotenv" or (name == "load_dotenv" and not node.args and not any(
                k.arg == "dotenv_path" for k in node.keywords
            )):
                offenders.append(f"{path.relative_to(REPO_ROOT)}:{node.lineno}")
    assert offenders == [], f"bare load_dotenv()/find_dotenv() searches parent dirs: {offenders}"


def test_checkout_ignores_a_parent_env(tmp_path):
    (tmp_path / ".env").write_text("BOARDMAN_DOTENV_PROBE=parent\n")
    checkout = tmp_path / ".claude" / "worktrees" / "wt"
    mod = checkout / "src" / "backend" / "probe.py"
    mod.parent.mkdir(parents=True)
    mod.write_text(
        "import os\nfrom pathlib import Path\nfrom dotenv import load_dotenv\n"
        f"{LOAD_LINE}\nprint(os.getenv('BOARDMAN_DOTENV_PROBE', 'unset'))\n"
    )

    def run() -> str:
        env = {"PATH": "/usr/bin:/bin"}
        out = subprocess.run([sys.executable, str(mod)], cwd=checkout, env=env,
                             capture_output=True, text=True, check=True)
        return out.stdout.strip()

    assert run() == "unset"
    (checkout / ".env").write_text("BOARDMAN_DOTENV_PROBE=own\n")
    assert run() == "own"
