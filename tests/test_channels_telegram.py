"""Telegram adapter: nothing changes with the flags off; flagged entry points
run through the core and answer in Telegram HTML."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

from gaming.src.channels.core import state as conv_state
from gaming.src.channels.telegram import adapter
from tests.channels_fixtures import tg_user, world  # noqa: F401


def run(coro):
    return asyncio.run(coro)


class _FSM:
    def __init__(self, st=None):
        self.st = st

    async def get_state(self):
        return self.st

    async def clear(self):
        self.st = None


def _message(uid=5001, text=""):
    m = MagicMock()
    m.text = text
    m.from_user = MagicMock(id=uid, username="tobi", full_name="Tobi")
    m.chat.id = uid
    m.answer = AsyncMock()
    return m


def test_filters_match_nothing_with_flags_off(world, monkeypatch):
    monkeypatch.delenv("CHANNELS_CORE_FLOWS")
    for flow in ("balance", "deposit", "withdraw", "link"):
        assert run(adapter.CoreFlow(flow)(None)) is False
    st = conv_state.load("telegram", "5001")
    st.set("withdraw", "dest")
    conv_state.save(st)
    assert run(adapter.ActiveCoreConversation()(_message(), _FSM())) is False


def test_core_text_never_steals_from_a_legacy_wizard(world):
    st = conv_state.load("telegram", "5001")
    st.set("withdraw", "dest")
    conv_state.save(st)
    assert run(adapter.ActiveCoreConversation()(_message(), _FSM())) is True
    assert run(adapter.ActiveCoreConversation()(_message(), _FSM("FiatTopupWizard:amount"))) is False


def test_per_channel_override(world, monkeypatch):
    monkeypatch.setenv("CHANNELS_CORE_FLOWS", "")
    monkeypatch.setenv("CHANNELS_CORE_FLOWS_WHATSAPP", "all")
    assert run(adapter.CoreFlow("balance")(None)) is False
    from gaming.src.channels import config

    assert config.flow_enabled("whatsapp", "withdraw")


def test_balance_command_runs_through_core(world, monkeypatch):
    prof = tg_user(world.repo)

    async def legacy_profile(user):
        return world.repo.get_profile(prof["id"])

    monkeypatch.setattr("gaming.src.bot.utils.db.get_or_create_profile", legacy_profile)
    msg = _message()
    fsm = _FSM("SomeLegacyWizard:step")
    run(adapter.core_balance(msg, fsm))
    assert fsm.st is None  # the legacy wizard was left
    text = msg.answer.await_args.args[0]
    assert "<b>Wallet</b>" in text and "$40.00" in text
    kb = msg.answer.await_args.kwargs["reply_markup"].inline_keyboard
    assert [row[0].text for row in kb] == ["Add money", "Withdraw", "Menu"]
    assert kb[-1][0].callback_data == "menu:main"
    assert all(len(row[0].callback_data.encode()) <= 64 for row in kb)


def test_link_deep_link_redeems(world, monkeypatch):
    from gaming.src.channels.core.identity import service as ids

    wa_prof = world.repo.create_profile({"gaming_tag": "wa_first"})
    from gaming.src.channels.core.identity.repo import Identity

    world.repo.upsert(Identity("whatsapp", "2348011112222", wa_prof["id"]))
    code, _ = ids.issue_link_code(ids.resolve("whatsapp", "2348011112222"))

    async def legacy_profile(user):  # /start would have created this empty profile
        for p in world.repo.profiles.values():
            if p.get("telegram_id") == user.id:
                return p
        p = world.repo.create_profile({"gaming_tag": "sq_new", "telegram_id": user.id})
        ids.ensure_telegram_identity(p["id"], user.id)
        return p

    monkeypatch.setattr("gaming.src.bot.utils.db.get_or_create_profile", legacy_profile)

    async def empty(pid):
        return True, []

    monkeypatch.setattr("gaming.src.channels.core.flows.link.profile_is_empty", empty)
    msg = _message(uid=7777, text=f"/start link_{code}")
    cmd = MagicMock(args=f"link_{code}")
    run(adapter.core_link_deeplink(msg, cmd, _FSM()))
    # the deep link alone links nothing: it names the target account and asks
    ask = msg.answer.await_args_list[0]
    assert "<b>@wa_first</b>?" in ask.args[0]
    assert world.repo.get("telegram", "7777").profile_id != wa_prof["id"]
    yes = [b for row in ask.kwargs["reply_markup"].inline_keyboard for b in row if b.text == "Yes, link it"][0]
    cb = MagicMock(data=yes.callback_data, from_user=msg.from_user, message=msg)
    cb.answer = AsyncMock()
    run(adapter.core_button(cb, _FSM()))
    assert "Linked to <b>@wa_first</b>" in msg.answer.await_args_list[1].args[0]
    assert world.repo.get("telegram", "7777").profile_id == wa_prof["id"]
    assert world.repo.profiles[wa_prof["id"]]["telegram_id"] == 7777
