"""Identity: resolve, Telegram dual-write, backfill, link codes, merge policy, geo."""
from __future__ import annotations

import asyncio
import importlib.util
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from gaming.src.channels.core import geo
from gaming.src.channels.core.identity import repo as repo_mod
from gaming.src.channels.core.identity import service as ids
from gaming.src.channels.core.identity.repo import Identity, MemoryIdentityRepo, utcnow
from gaming.src.channels.core.principal import CountrySignal, Principal

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def repo():
    r = MemoryIdentityRepo()
    repo_mod.set_repo(r)
    ids.reset_dual_write_memo()
    yield r
    repo_mod.set_repo(None)


def _empty(result=True, reasons=()):
    async def check(pid):
        return result, list(reasons)
    return check


def _tg_user(repo, tid=111, tag="alice"):
    p = repo.create_profile({"gaming_tag": tag, "telegram_id": tid})
    ids.ensure_telegram_identity(p["id"], tid, chat_id=tid, username=tag)
    return p, ids.resolve("telegram", str(tid))


def run(coro):
    return asyncio.run(coro)


# ── dual-write / resolve / backfill ─────────────────────────────────────────


def test_dual_write_creates_identity_once(repo):
    p, principal = _tg_user(repo)
    assert principal.profile_id == p["id"]
    ident = repo.get("telegram", "111")
    assert ident.verify_method == "tg_login" and ident.address == "111"
    ids.ensure_telegram_identity(p["id"], 111, chat_id=111, username="alice")
    assert len(repo.identities) == 1


def test_dual_write_never_raises(monkeypatch):
    class Boom:
        def get(self, *a):
            raise RuntimeError("table missing")
    repo_mod.set_repo(Boom())
    ids.reset_dual_write_memo()
    try:
        assert ids.ensure_telegram_identity("p", 1) is None
    finally:
        repo_mod.set_repo(None)


def test_bot_profile_lookup_dual_writes(repo, monkeypatch):
    from gaming.src.bot.utils import db

    monkeypatch.setattr(db, "_get_or_create_profile_core", lambda user: {"id": "p-9", "gaming_telegram_chat_id": 55})
    user = SimpleNamespace(id=909, username="bob", full_name="Bob")
    assert db._get_or_create_profile_sync(user)["id"] == "p-9"
    assert repo.get("telegram", "909").profile_id == "p-9"


def test_resolve_whatsapp_records_country_and_window(repo):
    p = repo.create_profile({"gaming_tag": "ada"})
    repo.upsert(Identity("whatsapp", "2348011112222", p["id"], country_hint="NG"))
    pr = ids.resolve("whatsapp", "2348011112222", phone="2348011112222", inbound=True)
    assert pr.profile_id == p["id"]
    assert CountrySignal("phone_cc", "NG") in pr.country_signals
    assert repo.get("whatsapp", "2348011112222").last_inbound_at is not None


def test_backfill_dry_run_then_apply(repo):
    spec = importlib.util.spec_from_file_location("bf", ROOT / "scripts" / "backfill_channel_identities.py")
    bf = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bf)
    a = repo.create_profile({"telegram_id": 1, "linked_wallet": "0xABC"})
    repo.create_profile({"telegram_id": 2})
    repo.create_profile({"gaming_tag": "wa_only"})
    repo.upsert(Identity("telegram", "2", "someone-else"))

    dry = bf.backfill(repo, apply=False, page=1)
    assert dry["telegram_new"] == 1 and dry["wallet_new"] == 1 and dry["conflicts"] == 1
    assert repo.get("telegram", "1") is None

    out = bf.backfill(repo, apply=True)
    assert out["telegram_new"] == 1
    assert repo.get("telegram", "1").profile_id == a["id"]
    assert repo.get("web_wallet", "0xabc").verify_method == "backfill"
    assert bf.backfill(repo, apply=True)["telegram_new"] == 0


# ── link codes ───────────────────────────────────────────────────────────────


def test_code_is_hashed_at_rest(repo):
    _, tg = _tg_user(repo)
    code, _ = ids.issue_link_code(tg)
    assert len(ids.normalize_code(code)) == 8
    assert all(code not in h for h in repo.codes)
    assert ids.hash_code(code) in repo.codes
    assert ids.hash_code(ids.format_code(code).lower()) == ids.hash_code(code)


def test_link_new_whatsapp_number(repo):
    p, tg = _tg_user(repo)
    code, _ = ids.issue_link_code(tg)
    res = run(ids.redeem_link_code("whatsapp", "2348011112222", ids.format_code(code),
                                   profile_is_empty=_empty(), phone="2348011112222"))
    assert res.status == "linked" and res.profile_id == p["id"]
    ident = repo.get("whatsapp", "2348011112222")
    assert ident.profile_id == p["id"] and ident.country_hint == "NG"
    assert ident.withdraw_hold_until > utcnow() + timedelta(hours=71)
    assert ident.opted_in


def test_link_code_single_use(repo):
    _, tg = _tg_user(repo)
    code, _ = ids.issue_link_code(tg)
    assert run(ids.redeem_link_code("whatsapp", "2341", code, profile_is_empty=_empty())).ok
    again = run(ids.redeem_link_code("whatsapp", "2342", code, profile_is_empty=_empty()))
    assert again.status == "invalid"
    assert repo.get("whatsapp", "2342") is None


def test_link_code_expires(repo):
    _, tg = _tg_user(repo)
    code, expires = ids.issue_link_code(tg)
    res = run(ids.redeem_link_code("whatsapp", "2341", code, profile_is_empty=_empty(),
                                   now=expires + timedelta(seconds=1)))
    assert res.status == "invalid"


def test_wrong_code_is_rate_limited(repo):
    _tg_user(repo)
    outs = [run(ids.redeem_link_code("whatsapp", "2341", "AAAA-AAAA", profile_is_empty=_empty())).status
            for _ in range(6)]
    assert outs[:5] == ["invalid"] * 5 and outs[5] == "rate_limited"


def test_issue_is_rate_limited(repo):
    _, tg = _tg_user(repo)
    for _ in range(5):
        ids.issue_link_code(tg)
    with pytest.raises(ids.LinkError) as e:
        ids.issue_link_code(tg)
    assert e.value.kind == "rate_limited"


def test_funded_profile_is_never_merged(repo):
    target, tg = _tg_user(repo)
    other = repo.create_profile({"gaming_tag": "wa_rich"})
    repo.upsert(Identity("whatsapp", "2349", other["id"]))
    code, _ = ids.issue_link_code(tg)
    res = run(ids.redeem_link_code("whatsapp", "2349", code,
                                   profile_is_empty=_empty(False, ["balance:spendable_usdc"])))
    assert res.status == "refused_funded"
    assert repo.get("whatsapp", "2349").profile_id == other["id"]
    assert "merged_into" not in repo.profiles[other["id"]]
    # the refused code is dead too
    assert run(ids.redeem_link_code("whatsapp", "2349", code, profile_is_empty=_empty())).status == "invalid"


def test_empty_profile_merges_and_tombstones(repo):
    target = repo.create_profile({"gaming_tag": "wa_main"})
    repo.upsert(Identity("whatsapp", "2348", target["id"]))
    wa = ids.resolve("whatsapp", "2348")
    stray = repo.create_profile({"gaming_tag": "sq_x", "telegram_id": 777})
    repo.upsert(Identity("telegram", "777", stray["id"]))
    code, _ = ids.issue_link_code(wa)
    res = run(ids.redeem_link_code("telegram", "777", code, profile_is_empty=_empty(), address="777"))
    assert res.status == "merged" and res.merged_from == stray["id"]
    assert repo.get("telegram", "777").profile_id == target["id"]
    assert repo.profiles[stray["id"]]["merged_into"] == target["id"]
    assert repo.profiles[stray["id"]]["telegram_id"] is None
    assert repo.profiles[target["id"]]["telegram_id"] == 777


def test_second_number_on_same_channel_conflicts(repo):
    p, tg = _tg_user(repo)
    repo.upsert(Identity("whatsapp", "2341", p["id"]))
    code, _ = ids.issue_link_code(tg)
    assert run(ids.redeem_link_code("whatsapp", "2342", code, profile_is_empty=_empty())).status == "conflict"


def test_profile_is_empty_fails_closed(repo, monkeypatch):
    from gaming.src.channels.core.identity import emptiness

    async def boom(*a, **k):
        raise RuntimeError("rpc down")
    monkeypatch.setattr("gaming.src.backend.services.clawstation_circle.get_balance_summary", boom)
    p = repo.create_profile({"gaming_tag": "x"})
    empty, reasons = run(emptiness.profile_is_empty(p["id"]))
    assert not empty and "balance:unknown" in reasons


def test_create_profile_for_whatsapp(repo):
    ident = ids.create_profile_for_channel("whatsapp", "2348011112222", "@Ada_9", phone="2348011112222", display_name="Ada")
    assert repo.profiles[ident.profile_id]["gaming_tag"] == "ada_9"
    assert ident.opted_in and ident.country_hint == "NG"
    with pytest.raises(ids.LinkError):
        ids.create_profile_for_channel("whatsapp", "2349", "ada_9")
    with pytest.raises(ids.LinkError):
        ids.create_profile_for_channel("whatsapp", "2340", "no spaces!")


# ── geo ──────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("phone,cc", [
    ("+2348012345678", "NG"), ("233201234567", "GH"), ("+447700900123", "GB"),
    ("+12025550123", "US"), ("+14165550123", "CA"), ("+254712345678", "KE"), ("12", None),
])
def test_country_from_phone(phone, cc):
    assert geo.country_from_phone(phone) == cc


def _principal(channel, *signals):
    return Principal(channel, "x", profile_id="p", country_signals=list(signals))


def test_blocked_phone_country_denies_whatsapp_money():
    d = geo.check_money(_principal("whatsapp", CountrySignal("phone_cc", "GB")), "withdraw")
    assert d is not None and d.reason == "blocked"
    assert geo.check_money(_principal("whatsapp", CountrySignal("phone_cc", "NG")), "withdraw") is None


def test_strict_mode_needs_a_money_signal(monkeypatch):
    monkeypatch.setenv("GEO_FENCE_STRICT", "1")
    d = geo.check_money(_principal("whatsapp", CountrySignal("phone_cc", None)), "deposit")
    assert d is not None and d.reason == "country_unknown"
    assert geo.check_money(_principal("whatsapp", CountrySignal("phone_cc", "NG")), "deposit") is None


def test_telegram_is_observe_only(monkeypatch):
    monkeypatch.setenv("GEO_FENCE_STRICT", "1")
    # would be refused (no signal) but Telegram does not enforce yet
    assert geo.check_money(_principal("telegram"), "withdraw") is None
    assert geo.check_money(_principal("telegram", CountrySignal("phone_cc", "US")), "withdraw") is None


def test_policy_file_carries_channel_signals():
    from gaming.src.backend.middleware import geo_fence

    geo_fence.reset_blocked_cache()
    pol = geo_fence.load_policy()
    assert pol["channel_signals"]["whatsapp"]["source"] == "phone_cc"
    assert geo_fence.money_route_kind("POST", "/api/channels/withdraw/abc") == "withdraw"
