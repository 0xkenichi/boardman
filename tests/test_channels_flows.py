"""Ported flows end to end through the fake adapter, under WhatsApp limits
(and the same flows on the Telegram renderer)."""
from __future__ import annotations

import asyncio
import re
from decimal import Decimal

import pytest

from gaming.src.channels.core import state as conv_state
from gaming.src.channels.core import withdraw_links
from gaming.src.channels.core.capabilities import WHATSAPP
from gaming.src.channels.core.engine import Engine
from gaming.src.channels.core.identity.repo import Identity, utcnow
from gaming.src.channels.core.messages import Choice, Option
from gaming.src.channels.core.notify import NotificationService
from gaming.src.channels.core.render import plan_choice
from gaming.src.channels.fake.adapter import FakeChannel, NotOffered, RecordingDeliverer
from tests.channels_fixtures import DEST, PLAY_ADDR, tg_user, wa_user, world  # noqa: F401

U = "2348011112222"


def run(coro):
    return asyncio.run(coro)


# ── renderer / degrade ───────────────────────────────────────────────────────


def test_choice_degrades_buttons_list_pages():
    opts = [Option(f"v1|x|o|{i}", f"Option number {i} with a long label") for i in range(15)]
    assert plan_choice(Choice("b", opts[:3]), WHATSAPP).kind == "buttons"
    p = plan_choice(Choice("b", opts[:10]), WHATSAPP)
    assert p.kind == "list" and len(p.options) == 10 and not p.has_more
    p = plan_choice(Choice("b", opts), WHATSAPP)
    assert p.kind == "list" and len(p.options) == 10 and p.options[-1].label == "More…"
    assert all(len(o.label) <= 24 for o in p.options)
    p2 = plan_choice(Choice("b", opts, page=1), WHATSAPP)
    assert [o.id for o in p2.options] == [o.id for o in opts[9:]]
    from gaming.src.channels.core.capabilities import SMS

    assert plan_choice(Choice("b", opts), SMS).kind == "numbered"


# ── onboarding / menu ────────────────────────────────────────────────────────


def test_new_whatsapp_user_onboards_and_sees_menu(world):
    wa = FakeChannel("wa")
    out = run(wa.text(U, "hi", name="Ada"))
    assert "Welcome to *Boardman*" in wa.last_text(U)
    run(wa.tap(U, "I'm new"))
    run(wa.text(U, "x"))
    assert "3 to 20" in wa.last_text(U)
    run(wa.text(U, "Ada_9ja"))
    assert "@ada_9ja" in wa.all_text(U)
    labels = [label for _, label in wa.offered(U)]
    assert labels == ["New challenge", "My matches", "Watch & bet", "Wallet", "Add money", "Withdraw",
                      "Link account"]  # 7 > 3 → a list
    ident = world.repo.get("whatsapp", U)
    assert ident.country_hint == "NG" and ident.opted_in
    assert out  # replies were validated against WhatsApp limits on the way out


def test_numbered_reply_picks_an_option(world):
    wa_user(world.repo)
    wa = FakeChannel("wa")
    run(wa.text(U, "menu"))
    run(wa.text(U, "4"))  # New challenge, My matches, Watch & bet, Wallet, …
    assert "*Wallet*" in wa.last_text(U)


def test_flags_gate_flows(world, monkeypatch):
    monkeypatch.setenv("CHANNELS_CORE_FLOWS", "balance")
    wa_user(world.repo)
    wa = FakeChannel("wa")
    run(wa.text(U, "menu"))
    assert [label for _, label in wa.offered(U)] == ["Wallet"]
    run(wa.text(U, "withdraw"))
    assert "didn't get that" in wa.all_text(U)
    run(wa.tap_id(U, "v1|withdraw|start|"))
    assert "not available here yet" in wa.all_text(U)


# ── balance ──────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("profile", ["wa", "tg"])
def test_balance(world, profile):
    if profile == "wa":
        wa_user(world.repo)
        user = U
    else:
        tg_user(world.repo)
        user = "5001"
    ch = FakeChannel(profile)
    run(ch.text(user, "balance"))
    text = ch.last_text(user)
    assert "40.00" in text and PLAY_ADDR in text
    labels = [label for _, label in ch.offered(user)]
    assert labels == ["Add money", "Withdraw", "Menu"]
    if profile == "tg":
        assert "<b>" in text  # Telegram renders the markup as HTML
        assert dict((label, i) for i, label in ch.offered(user))["Menu"] == "menu:main"


# ── deposit ──────────────────────────────────────────────────────────────────


def test_deposit_paystack_naira(world):
    prof = wa_user(world.repo)
    wa = FakeChannel("wa")
    run(wa.text(U, "deposit"))
    run(wa.tap(U, "Pay with Naira"))
    run(wa.tap(U, "₦10,000"))
    url = wa.links(U)[-1]
    assert url.startswith("https://checkout.paystack.com/")
    init = world.paystack_inits[-1]
    assert init["email"].startswith("wa") and U not in init["email"]
    assert init["metadata"]["channel"] == "whatsapp"
    run(wa.tap(U, "I've paid"))
    assert "Payment confirmed" in wa.last_text(U)
    from gaming.src.backend.services.fiat_topup import list_topups

    row = list_topups(limit=1)[0]
    assert row["profile_id"] == prof["id"] and row["status"] == "paystack_paid"


def test_deposit_typed_amount_and_validation(world):
    wa_user(world.repo)
    wa = FakeChannel("wa")
    run(wa.text(U, "deposit"))
    run(wa.tap(U, "Pay with Naira"))
    run(wa.text(U, "100"))
    assert "Minimum" in wa.last_text(U)
    run(wa.text(U, "15k"))
    assert world.paystack_inits[-1]["amount_ngn"] == Decimal("15000")


def test_deposit_check_is_owner_only(world):
    wa_user(world.repo)
    wa_user(world.repo, number="2348099999999", tag="mallory")
    wa = FakeChannel("wa")
    run(wa.text(U, "deposit"))
    run(wa.tap(U, "Pay with Naira"))
    run(wa.tap(U, "₦10,000"))
    check_id = dict((label, i) for i, label in wa.offered(U))["I've paid"]
    run(wa.tap_id("2348099999999", check_id))  # someone else's (forged) button
    assert "can't find that top-up" in wa.last_text("2348099999999")


def test_deposit_crypto_address(world):
    wa_user(world.repo)
    wa = FakeChannel("wa")
    run(wa.text(U, "deposit"))
    run(wa.tap(U, "Send USDC"))
    assert PLAY_ADDR in wa.last_text(U)


def test_blocked_phone_country_cannot_deposit(world):
    gb = "447700900123"
    wa_user(world.repo, number=gb, tag="londoner")
    wa = FakeChannel("wa")
    run(wa.text(gb, "deposit"))
    assert "not available for your region" in wa.last_text(gb)
    assert not world.paystack_inits


# ── link account ─────────────────────────────────────────────────────────────


def test_link_telegram_to_new_whatsapp_number(world):
    tg_prof = tg_user(world.repo)
    deliver_tg = RecordingDeliverer("telegram")
    notifier = NotificationService({"telegram": deliver_tg, "whatsapp": RecordingDeliverer("whatsapp")})
    engine = Engine(notifier=notifier)
    tg = FakeChannel("tg", engine=engine)
    run(tg.text("5001", "link"))
    text = tg.last_text("5001")
    code = re.search(r"<b>([A-Z0-9]{4}-[A-Z0-9]{4})</b>", text).group(1)
    assert tg.links("5001")[-1].startswith("https://wa.me/2348000000000?text=LINK%20")

    wa = FakeChannel("wa", engine=engine)
    run(wa.text(U, f"link {code.lower()}", name="Tobi"))
    assert "Linked to *@tobi*" in wa.all_text(U)
    ident = world.repo.get("whatsapp", U)
    assert ident.profile_id == tg_prof["id"] and ident.country_hint == "NG"
    # security notice on Telegram, not echoed back to WhatsApp
    assert [x for x, _ in deliver_tg.session] == ["5001"]
    assert "linked to your Boardman account" in deliver_tg.session[0][1][0].body

    # the same code cannot be used again
    run(wa.text("2348022223333", f"LINK {code}"))
    assert "wrong, used or expired" in wa.last_text("2348022223333")


def test_link_refuses_funded_profile(world, monkeypatch):
    tg_user(world.repo)
    wa_user(world.repo, tag="rich")  # this number already has its own profile
    tg = FakeChannel("tg")
    run(tg.text("5001", "link"))
    code = re.search(r"<b>([A-Z0-9]{4}-[A-Z0-9]{4})</b>", tg.last_text("5001")).group(1)
    wa = FakeChannel("wa")
    run(wa.text(U, f"LINK {code}"))  # balance is $40 → not empty
    assert "can't merge it automatically" in wa.last_text(U)


# ── withdraw ─────────────────────────────────────────────────────────────────


def _withdraw_to_link(ch, user, *msgs):
    run(ch.text(user, "withdraw"))
    for m in msgs:
        run(ch.text(user, m))
    return ch.links(user)[-1]


def test_withdraw_sends_one_time_link_never_asks_pin(world):
    prof = wa_user(world.repo)
    wa = FakeChannel("wa")
    url = _withdraw_to_link(wa, U, DEST, "20")
    assert url.startswith("https://boardman.test/app/withdraw/")
    assert "PIN" in wa.last_text(U) and "Never type your PIN" in wa.last_text(U)
    token = url.rsplit("/", 1)[-1]
    view = withdraw_links.view(token)
    assert view["amount"] == "20" and view["destination"]["address"] == DEST
    assert view["needs_pin_setup"] is True
    out = run(withdraw_links.confirm(token, pin="246810", pin_confirm="246810", amount="20"))
    assert out["ok"] and out["pin_set"]
    assert world.transfers == [(prof["id"], DEST, Decimal("20"), None)]
    assert world.repo.profiles[prof["id"]]["gaming_tx_password_hash"].startswith("pbkdf2_sha256$")


def test_withdraw_to_tag_in_one_message(world):
    wa_user(world.repo)
    world.tags["bola"] = {"id": "p-bola", "gaming_deposit_address": DEST}
    wa = FakeChannel("wa")
    url = _withdraw_to_link(wa, U, "@bola 5")
    assert "to @bola" in wa.all_text(U)
    assert withdraw_links.view(url.rsplit("/", 1)[-1])["destination"]["tag"] == "bola"


def test_withdraw_validation_in_chat(world):
    wa_user(world.repo)
    wa = FakeChannel("wa")
    run(wa.text(U, "withdraw"))
    run(wa.text(U, "my bank"))
    assert "wallet address" in wa.last_text(U)
    run(wa.text(U, DEST))
    run(wa.text(U, "500"))
    assert "Max withdraw" in wa.last_text(U)
    assert not wa.links(U)


def test_withdraw_blocked_during_link_hold(world):
    wa_user(world.repo, withdraw_hold_until=utcnow().replace(year=utcnow().year + 1))
    wa = FakeChannel("wa")
    run(wa.text(U, "withdraw"))
    assert "linked recently" in wa.last_text(U)


def test_withdraw_on_telegram_uses_the_same_link(world):
    tg_user(world.repo)
    tg = FakeChannel("tg")
    url = _withdraw_to_link(tg, "5001", DEST, "10")
    assert "/app/withdraw/" in url


def test_wizard_survives_restart(world):
    wa_user(world.repo)
    wa = FakeChannel("wa")
    run(wa.text(U, "withdraw"))
    run(wa.text(U, DEST))
    from gaming.src.stack.agentic.db import engine as db_engine

    db_engine.reset_databases()
    wa2 = FakeChannel("wa")  # a different process, same store
    run(wa2.text(U, "12"))
    assert wa2.links(U)


def test_stale_and_unknown_buttons_are_harmless(world):
    wa_user(world.repo)
    wa = FakeChannel("wa")
    run(wa.tap_id(U, "v1|nope|x|"))
    assert "no longer active" in wa.all_text(U) or "not available" in wa.all_text(U)
    run(wa.tap_id(U, "garbage"))
    assert "no longer active" in wa.all_text(U)
    with pytest.raises(NotOffered):
        run(wa.tap(U, "Delete everything"))


def test_paging_through_a_long_list(world):
    wa_user(world.repo)
    st = conv_state.load("whatsapp", U)
    st.data["_last_choice"] = {"body": "Pick a game", "button_label": "Games",
                               "options": [[f"v1|menu|open|{i}", f"Game {i}", ""] for i in range(14)]}
    conv_state.save(st)
    wa = FakeChannel("wa")
    run(wa.tap_id(U, "v1|nav|more|1"))
    labels = [label for _, label in wa.offered(U)]
    assert labels == [f"Game {i}" for i in range(9, 14)]


def test_stop_opts_out(world):
    wa_user(world.repo)
    wa = FakeChannel("wa")
    run(wa.text(U, "STOP"))
    assert not world.repo.get("whatsapp", U).opted_in
    run(wa.text(U, "start"))
    assert world.repo.get("whatsapp", U).opted_in


def test_media_is_copied_to_our_storage(world):
    wa_user(world.repo)
    wa = FakeChannel("wa")
    run(wa.image(U, b"\x89PNG fake screenshot"))
    assert "match reports" in wa.last_text(U)
    from gaming.src.stack.agentic.store import data_dir

    stored = list((data_dir() / "channels" / "evidence").rglob("*.png"))
    assert len(stored) == 1 and stored[0].read_bytes() == b"\x89PNG fake screenshot"
