"""Stack API keys: the ``platform`` label is reserved for the master key."""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _keys(monkeypatch):
    for name in ("BOARDMAN_API_KEY", "REMATCH_API_KEY", "STACK_API_KEY", "BOARDMAN_STACK_API_KEYS_FILE"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("BOARDMAN_API_KEY", "sk_master")


def test_master_key_is_master(monkeypatch):
    from gaming.src.backend.rematch_auth import resolve_api_key

    p = resolve_api_key("sk_master")
    assert p is not None and p.is_master and p.builder_id == "platform"


@pytest.mark.parametrize("label", ["platform", "Platform", " PLATFORM "])
def test_builder_key_labelled_platform_is_refused(monkeypatch, label):
    from gaming.src.backend.rematch_auth import load_api_key_map, resolve_api_key

    monkeypatch.setenv("BOARDMAN_STACK_API_KEYS", f"sk_sneaky:{label},sk_alice:alice_lab")
    assert "sk_sneaky" not in load_api_key_map()
    assert resolve_api_key("sk_sneaky") is None
    alice = resolve_api_key("sk_alice")
    assert alice is not None and not alice.is_master and alice.builder_id == "alice_lab"


def test_builder_entry_cannot_relabel_master(monkeypatch):
    from gaming.src.backend.rematch_auth import resolve_api_key

    monkeypatch.setenv("BOARDMAN_STACK_API_KEYS", "sk_master:alice_lab")
    p = resolve_api_key("sk_master")
    assert p is not None and p.is_master and p.builder_id == "platform"


def test_key_file_platform_label_refused(monkeypatch, tmp_path):
    from gaming.src.backend.rematch_auth import resolve_api_key

    f = tmp_path / "keys.txt"
    f.write_text("sk_file:platform\nsk_bob:bob_forge\n", encoding="utf-8")
    monkeypatch.setenv("BOARDMAN_STACK_API_KEYS_FILE", str(f))
    assert resolve_api_key("sk_file") is None
    bob = resolve_api_key("sk_bob")
    assert bob is not None and not bob.is_master
