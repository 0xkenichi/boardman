"""Naira on-ramps take real money, so they stay off until there is a licence.

config/funding_rails.yaml ships paystack_ngn and bank_ngn disabled; every
entry point (Telegram menu, intro copy, the channels deposit flow, and old
buttons still sitting in chat history) must respect that, even when Paystack
keys are configured.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from gaming.src.backend.services import funding_rails as fr


def _buttons(markup) -> list[tuple[str, str]]:
    return [
        (b.text, b.callback_data or b.url or "")
        for row in markup.inline_keyboard
        for b in row
    ]


@pytest.fixture
def paystack_keys(monkeypatch):
    monkeypatch.setattr("gaming.src.backend.services.paystack.paystack_configured", lambda: True)


def test_shipped_config_turns_both_naira_rails_off():
    assert fr.naira_paystack_enabled() is False
    assert fr.naira_bank_enabled() is False
    assert fr.funding_rail_enabled("arc") is True


def test_telegram_menu_hides_naira_even_with_paystack_keys(paystack_keys):
    from gaming.src.bot.keyboards import get_money_menu

    datas = [d for _t, d in _buttons(get_money_menu())]
    assert "ui:topup:paystack" not in datas
    assert "ui:topup:ngn" not in datas
    assert "ui:topup:crypto" in datas


def test_intro_copy_does_not_advertise_naira(paystack_keys):
    from gaming.src.backend.services.kobox_partner import get_money_intro_html

    html = get_money_intro_html(1600)
    assert "Paystack" not in html
    assert "₦" not in html


def test_channels_deposit_offers_no_naira_option(paystack_keys):
    from gaming.src.channels.core.actions import deposit

    assert deposit.paystack_ready() is False


def test_naira_comes_back_when_the_rail_is_enabled(monkeypatch, paystack_keys):
    from gaming.src.bot.keyboards import get_money_menu

    real = fr.get_rail

    def rail(rail_id):
        r = real(rail_id)
        return {**r, "enabled": True} if rail_id in ("paystack_ngn", "bank_ngn") and r else r

    monkeypatch.setattr(fr, "get_rail", rail)
    datas = [d for _t, d in _buttons(get_money_menu())]
    assert "ui:topup:paystack" in datas and "ui:topup:ngn" in datas


@pytest.mark.parametrize("handler", ["ui_topup_paystack_start", "ui_topup_ngn_start"])
def test_old_naira_buttons_are_refused(handler, paystack_keys):
    from gaming.src.bot.handlers import fiat_topup

    message = SimpleNamespace(answer=AsyncMock())
    callback = SimpleNamespace(answer=AsyncMock(), message=message, from_user=SimpleNamespace(id=1))
    state = SimpleNamespace(clear=AsyncMock(), set_state=AsyncMock(), update_data=AsyncMock())

    asyncio.run(getattr(fiat_topup, handler)(callback, state))

    text = message.answer.await_args.args[0]
    assert text == fr.NAIRA_PAUSED_TEXT
    state.set_state.assert_not_awaited()
    state.clear.assert_awaited()
