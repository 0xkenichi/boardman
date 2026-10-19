"""The mainnet setup scripts: dry runs touch nothing, secrets are never printed."""
from __future__ import annotations

import importlib.util
import os
import stat
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
LIVE_KEY = "LIVE_API_KEY:id:shh"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


@pytest.fixture()
def setup_mod():
    return _load("circle_mainnet_setup")


@pytest.fixture()
def vm(tmp_path):
    env = tmp_path / ".env"
    env.write_text(f"CIRCLE_API_KEY=TEST_API_KEY:x:y\nCIRCLE_API_KEY_LIVE={LIVE_KEY}\n")
    os.chmod(env, 0o600)
    out = tmp_path / "secrets"
    out.mkdir()
    return env, out


def test_dry_run_changes_nothing_and_calls_nobody(setup_mod, vm, capsys, monkeypatch):
    env, out = vm
    before = env.read_text()
    monkeypatch.setattr(setup_mod, "Circle", lambda *a, **k: pytest.fail("no Circle call in a dry run"))
    assert setup_mod.main(["--env-file", str(env), "--recovery-dir", str(out)]) == 0
    assert env.read_text() == before and not list(out.iterdir())
    text = capsys.readouterr().out
    assert "DRY RUN" in text and LIVE_KEY not in text


def test_refuses_a_test_key_or_a_live_key_in_the_testnet_slot(setup_mod, vm, capsys):
    env, out = vm
    env.write_text("CIRCLE_API_KEY_LIVE=TEST_API_KEY:a:b\n")
    assert setup_mod.main(["--env-file", str(env), "--recovery-dir", str(out)]) == 2
    env.write_text(f"CIRCLE_API_KEY={LIVE_KEY}\nCIRCLE_API_KEY_LIVE={LIVE_KEY}\n")
    assert setup_mod.main(["--env-file", str(env), "--recovery-dir", str(out)]) == 2
    assert "testnet realm" in capsys.readouterr().err


def test_apply_generates_the_secret_in_place_and_prints_only_addresses(setup_mod, vm, capsys, monkeypatch):
    env, out = vm
    calls: list[str] = []

    class FakeCircle:
        def __init__(self, key, secret_hex):
            assert key == LIVE_KEY and len(secret_hex) == 64
            self.secret = secret_hex

        def register(self):
            calls.append("register")
            return {"recoveryFile": "RECOVERY-BLOB"}

        def wallet_set(self):
            calls.append("set")
            return {"id": "ws-live-1"}

        def wallet(self, ws, chain, acct, step):
            calls.append(f"wallet:{chain}:{acct}")
            return {"id": f"w-{chain}", "address": f"0x{chain.lower()}addr"}

        def get_wallet(self, wid):
            return {"address": "0xexisting"}

    monkeypatch.setattr(setup_mod, "Circle", FakeCircle)
    assert setup_mod.main(["--env-file", str(env), "--recovery-dir", str(out), "--apply"]) == 0
    vals = setup_mod.read_env(env)
    secret = vals["CIRCLE_ENTITY_SECRET_LIVE"]
    assert len(secret) == 64 and int(secret, 16) >= 0
    assert vals["CIRCLE_WALLET_SET_ID_LIVE"] == "ws-live-1"
    assert vals["PAYCREST_ARC_RELAYER_WALLET_ID"] == "w-ARC"
    assert vals["PAYCREST_BASE_RELAYER_WALLET_ID"] == "w-BASE"
    assert calls == ["register", "set", "wallet:ARC:EOA", "wallet:BASE:SCA"]
    printed = capsys.readouterr()
    assert secret not in printed.out + printed.err and LIVE_KEY not in printed.out + printed.err
    assert "0xarcaddr" in printed.out
    rec = list(out.glob("circle_entity_recovery_*.dat"))
    assert rec and rec[0].read_text() == "RECOVERY-BLOB"
    assert stat.S_IMODE(rec[0].stat().st_mode) == 0o600 and stat.S_IMODE(env.stat().st_mode) == 0o600

    # a rerun replaces nothing and creates nothing new
    calls.clear()
    assert setup_mod.main(["--env-file", str(env), "--recovery-dir", str(out), "--apply"]) == 0
    assert calls == [] and setup_mod.read_env(env)["CIRCLE_ENTITY_SECRET_LIVE"] == secret


def test_resolver_script_prints_the_address_only(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("BOARDMAN_KEYSTORE_SECRET", "k" * 40)
    monkeypatch.setenv("BOARDMAN_KEYSTORE_DIR", str(tmp_path / "ks"))
    mod = _load("create_mainnet_resolver")
    assert mod.main([]) == 0 and "DRY RUN" in capsys.readouterr().out
    assert mod.main(["--apply"]) == 0
    text = capsys.readouterr().out
    from gaming.src.stack.agentic.keystore import get_keystore

    ks = get_keystore()
    addr = ks.address("resolver_arc_mainnet")
    assert addr and addr in text
    assert ks.private_key("resolver_arc_mainnet")[2:] not in text
    assert mod.main(["--apply"]) == 0 and "not replaced" in capsys.readouterr().out
