"""Withdraw links: single use, expiry, wrong profile, amount tampering, PIN rules,
and the backend route the web page calls."""
from __future__ import annotations

import asyncio
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from gaming.src.bot.utils.security import hash_tx_password
from gaming.src.channels.core import withdraw_links as wl
from gaming.src.channels.core.withdraw_links import LinkRefused
from tests.channels_fixtures import DEST, wa_user, world  # noqa: F401

MASTER = "test-channels-master"


def run(coro):
    return asyncio.run(coro)


def _issue(prof, amount="20", **kw):
    return wl.issue(prof["id"], channel="whatsapp", external_id="234801", amount=Decimal(amount),
                    address=DEST, **kw)


def _with_pin(world, pin="135790"):
    prof = wa_user(world.repo)
    world.repo.update_profile(prof["id"], {"gaming_tx_password_hash": hash_tx_password(pin)})
    return prof


def test_token_is_hashed_at_rest(world):
    prof = wa_user(world.repo)
    link = _issue(prof)
    from gaming.src.channels.core import store

    with store.db().transaction(readonly=True) as tx:
        rows = tx.all("SELECT token_hash FROM channel_tokens")
    assert rows == [{"token_hash": wl.token_hash(link.token)}]
    assert link.token not in rows[0]["token_hash"]


def test_single_use(world):
    prof = _with_pin(world)
    link = _issue(prof)
    assert run(wl.confirm(link.token, pin="135790", amount="20"))["ok"]
    with pytest.raises(LinkRefused) as e:
        run(wl.confirm(link.token, pin="135790", amount="20"))
    assert e.value.kind == "used"
    assert len(world.transfers) == 1


def test_concurrent_double_submit_pays_once(world):
    prof = _with_pin(world)
    link = _issue(prof)

    async def both():
        return await asyncio.gather(
            wl.confirm(link.token, pin="135790", amount="20"),
            wl.confirm(link.token, pin="135790", amount="20"),
            return_exceptions=True,
        )

    results = run(both())
    assert sum(1 for r in results if isinstance(r, dict) and r.get("ok")) == 1
    assert len(world.transfers) == 1


def test_expiry(world):
    prof = _with_pin(world)
    link = wl.issue(prof["id"], channel="whatsapp", external_id="1", amount=Decimal("5"), address=DEST,
                    now_ms=1_000)
    with pytest.raises(LinkRefused) as e:
        wl.view(link.token)
    assert e.value.kind == "expired"
    with pytest.raises(LinkRefused):
        run(wl.confirm(link.token, pin="135790", amount="5"))
    assert not world.transfers


def test_wrong_profile_session_is_refused(world):
    prof = _with_pin(world)
    link = _issue(prof)
    with pytest.raises(LinkRefused) as e:
        run(wl.confirm(link.token, pin="135790", amount="20", session_profile_id="someone-else"))
    assert e.value.kind == "wrong_profile"
    # not burned: the right person can still use it
    assert run(wl.confirm(link.token, pin="135790", amount="20", session_profile_id=prof["id"]))["ok"]


def test_amount_tampering_burns_the_link(world):
    prof = _with_pin(world)
    link = _issue(prof, amount="20")
    with pytest.raises(LinkRefused) as e:
        run(wl.confirm(link.token, pin="135790", amount="50"))
    assert e.value.kind == "amount_mismatch"
    with pytest.raises(LinkRefused) as e:
        run(wl.confirm(link.token, pin="135790", amount="20"))
    assert e.value.kind == "used"
    assert not world.transfers


def test_wrong_pin_locks_after_five(world):
    prof = _with_pin(world)
    link = _issue(prof)
    kinds = []
    for _ in range(5):
        with pytest.raises(LinkRefused) as e:
            run(wl.confirm(link.token, pin="000001", amount="20"))
        kinds.append(e.value.kind)
    assert kinds == ["bad_pin"] * 4 + ["locked"]
    with pytest.raises(LinkRefused):
        run(wl.confirm(link.token, pin="135790", amount="20"))
    assert not world.transfers


def test_first_pin_must_be_strong_and_confirmed(world):
    prof = wa_user(world.repo)
    link = _issue(prof)
    for pin, confirm, kind in (("1234", "1234", "pin_policy"), ("123456", "123456", "pin_policy"),
                               ("111111", "111111", "pin_policy"), ("482916", "482917", "pin_mismatch")):
        with pytest.raises(LinkRefused) as e:
            run(wl.confirm(link.token, pin=pin, pin_confirm=confirm, amount="20"))
        assert e.value.kind == kind
    assert run(wl.confirm(link.token, pin="482916", pin_confirm="482916", amount="20"))["pin_set"]


def test_newer_link_supersedes_older(world):
    prof = _with_pin(world)
    old = _issue(prof, amount="10")
    _issue(prof, amount="11")
    with pytest.raises(LinkRefused) as e:
        wl.view(old.token)
    assert e.value.kind == "used"


def test_issue_rate_limit(world):
    prof = _with_pin(world)
    for _ in range(5):
        _issue(prof)
    with pytest.raises(LinkRefused) as e:
        _issue(prof)
    assert e.value.kind == "rate_limited"


def test_existing_checks_still_apply_at_payout(world):
    prof = _with_pin(world)
    world.balance = Decimal("3")
    link = _issue(prof, amount="20")
    out = run(wl.confirm(link.token, pin="135790", amount="20"))
    assert not out["ok"] and out["status"] == "insufficient"
    assert not world.transfers


def test_pin_reset_link(world):
    prof = _with_pin(world)
    link = wl.issue_pin_reset(prof["id"], channel="telegram", external_id="5")
    assert wl.view(link.token)["purpose"] == "pin_reset"
    out = run(wl.confirm(link.token, pin="864209", pin_confirm="864209"))
    assert out["status"] == "pin_set"
    w = _issue(prof)
    assert run(wl.confirm(w.token, pin="864209", amount="20"))["ok"]


# ── HTTP: the route the BFF calls ────────────────────────────────────────────


@pytest.fixture
def api(world, monkeypatch):
    for name in ("REMATCH_API_KEY", "STACK_API_KEY", "BOARDMAN_STACK_API_KEYS_FILE", "BOARDMAN_STACK_API_KEYS"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("BOARDMAN_API_KEY", MASTER)
    from gaming.src.backend.main import create_app

    return TestClient(create_app())


def test_route_requires_master_key(api, world):
    prof = _with_pin(world)
    link = _issue(prof)
    assert api.get(f"/api/channels/withdraw/{link.token}").status_code == 401
    r = api.get(f"/api/channels/withdraw/{link.token}", headers={"X-Boardman-Key": MASTER})
    assert r.status_code == 200 and r.json()["amount"] == "20"


def test_route_confirms_once(api, world):
    prof = _with_pin(world)
    link = _issue(prof)
    h = {"X-Boardman-Key": MASTER, "x-boardman-client-country": "NG"}
    r = api.post(f"/api/channels/withdraw/{link.token}", json={"pin": "135790", "amount": "20"}, headers=h)
    assert r.status_code == 200 and r.json()["status"] == "submitted"
    r = api.post(f"/api/channels/withdraw/{link.token}", json={"pin": "135790", "amount": "20"}, headers=h)
    assert r.status_code == 409 and r.json()["error"] == "used"


def test_route_refuses_other_session(api, world):
    prof = _with_pin(world)
    link = _issue(prof)
    h = {"X-Boardman-Key": MASTER, "X-Boardman-Caller": "other-profile"}
    r = api.post(f"/api/channels/withdraw/{link.token}", json={"pin": "135790", "amount": "20"}, headers=h)
    assert r.status_code == 403


def test_route_is_geo_fenced(api, world):
    prof = _with_pin(world)
    link = _issue(prof)
    h = {"X-Boardman-Key": MASTER, "x-boardman-client-country": "US"}
    r = api.post(f"/api/channels/withdraw/{link.token}", json={"pin": "135790", "amount": "20"}, headers=h)
    assert r.status_code == 451
    assert not world.transfers
