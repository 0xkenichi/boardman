"""No live-looking credential is committed to the (public) repo.

Infra audit 2026-10 (INF-02): the Circle API key that production still uses
was committed in 4601a32 (docs/api/CIRCLE_ESCROW_SETUP.md) and a Telegram bot
token in the same commit (src/backend/telegram_webhook.py). Both files are
gone from HEAD but remain in public history. This test stops the next one at
review time; it scans every tracked file for high-confidence secret shapes and
reports file:line and pattern name only, never the value.

Allowlisted: well-known public test keys (Hardhat/Anvil default accounts).
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

PATTERNS = {
    "telegram_bot_token": re.compile(r"\b\d{8,10}:AA[A-Za-z0-9_-]{33}\b"),
    "circle_api_key": re.compile(r"\b(TEST|LIVE)_API_KEY:[0-9a-f]{32}:[0-9a-f]{32}\b"),
    "circle_client_key": re.compile(r"\b(TEST|LIVE)_CLIENT_KEY:[0-9a-f]{32}:[0-9a-f]{32}\b"),
    "pem_private_key": re.compile(r"-----BEGIN (RSA |EC |OPENSSH |ENCRYPTED )?PRIVATE KEY-----"),
    "paystack_secret": re.compile(r"\bsk_live_[A-Za-z0-9]{20,}"),
    "openai_or_anthropic_key": re.compile(r"\bsk-(ant-|proj-)[A-Za-z0-9_-]{32,}"),
    "github_token": re.compile(r"\b(gh[pousr]_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]{60,})"),
    "aws_access_key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "supabase_secret_key": re.compile(r"\bsb_secret_[A-Za-z0-9_-]{20,}"),
    "cloudflare_tunnel_token": re.compile(r"\beyJhIjoi[A-Za-z0-9+/=_-]{60,}"),
    "jwt_service_role": re.compile(
        r"\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]*(c2VydmljZV9yb2xl|NlcnZpY2Vfcm9sZ|zZXJ2aWNlX3JvbG)[A-Za-z0-9_-]*\.[A-Za-z0-9_-]{16,}"),
    "evm_private_key_assignment": re.compile(
        r"(?i)(private_?key|_PK|secret|mnemonic|signer_key|resolver_key)[\"']?\s*[:=]\s*[\"']?(0x)?[0-9a-f]{64}\b"),
}

# Public, well-known development keys (Hardhat / Anvil accounts #0-#2).
ALLOW = {
    "ac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80",
    "59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d",
    "5de4111afa1a4b94908f83103eb1f1706367c2e68ca870fc3fb9a804cdab365a",
}

SKIP_SUFFIXES = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".pdf", ".mp4",
                 ".webm", ".woff", ".woff2", ".ttf", ".otf", ".zip", ".gz", ".lock")
SKIP_FILES = {"tests/test_no_secrets_in_tree.py", "frontend/package-lock.json",
              "contracts/package-lock.json"}


def _tracked_files() -> list[str]:
    try:
        out = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True,
                             check=True, timeout=60).stdout
    except (OSError, subprocess.SubprocessError):
        pytest.skip("git not available")
    return [p for p in out.decode().split("\0") if p]


def test_no_secret_shaped_strings_in_tracked_files():
    hits: list[str] = []
    for rel in _tracked_files():
        if rel in SKIP_FILES or rel.endswith(SKIP_SUFFIXES) or rel.endswith("package-lock.json"):
            continue
        path = ROOT / rel
        try:
            if not path.is_file() or path.stat().st_size > 2_000_000:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            for name, rx in PATTERNS.items():
                m = rx.search(line)
                if not m:
                    continue
                if any(a in line.lower() for a in ALLOW):
                    continue
                hits.append(f"{rel}:{lineno} {name}")
    assert not hits, "secret-shaped strings committed (rotate them, then remove):\n" + "\n".join(hits)
