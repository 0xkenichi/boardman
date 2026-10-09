"""Bot-side bettor outcome notifications: nobody is ever left silent.

When a book settles, every public bettor gets a Telegram DM — winners know
they were paid, losers know their side didn't hit, draw-bettors know the
verdict. Root cause under test: before agm_91dadd7c75f5 the user's $10
loss never surfaced anywhere.
"""

from __future__ import annotations

import threading
import asyncio

import pytest

import gaming.src.bot.utils.notify as notify_mod
from gaming.src.stack.agentic import matches as M


class InlineThread:
    """Thread replacement that runs its target immediately."""

    def __init__(self, target=None, name=None, daemon=None):
        self._target = target

    def start(self):
        if self._target:
            self._target()


def _fake_run(coro):
    """Mirror prod flow: a fresh event loop per call (as asyncio.run does)."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@pytest.fixture()
def capture_notify(monkeypatch):
    calls: list[tuple[str, str]] = []

    async def notify(bid, text):
        calls.append((bid, text))

    monkeypatch.setattr(notify_mod, "notify_user", notify)
    monkeypatch.setattr(threading, "Thread", InlineThread)
    monkeypatch.setattr(asyncio, "run", _fake_run)
    return calls


def test_win_and_loss_both_notified(capture_notify):
    book = {
        "status": "settled",
        "payouts": {
            "mode": "winner_take_side",
            "winner_side": "b",
            "bettors": [
                {"bettor_id": "w1", "amount": "6.5", "reason": "win"},
                {"bettor_id": "w2", "amount": "2.1", "reason": "win"},
            ],
            "creators": [],
            "seed_refunds": [],
        },
        "bets": [
            {"bettor_id": "w1", "side": "b", "amount": "3.0"},
            {"bettor_id": "user_lost", "side": "a", "amount": "10.0"},
            {"bettor_id": "w2", "side": "b", "amount": "1.5"},
        ],
    }
    M._notify_spectator_outcomes(
        "agm_test",
        "b",
        book["payouts"]["bettors"],
        book=book,
        result_code="black_win",
        termination="TIMEOUT",
    )

    got = dict(capture_notify)
    # winners: how much they were paid and why the table ended
    assert "Paid" in got["w1"] and "Nero won" in got["w1"]
    assert "ran out of time" in got["w1"]
    # losers: a plain "didn't hit" with their stake named — never silence
    assert "didn't hit" in got["user_lost"]
    assert "$10.00" in got["user_lost"]
    # every bettor was messaged — nobody left silent
    assert set(got) == {"w1", "w2", "user_lost"}


def test_draw_close_out_notify_everyone(capture_notify):
    book = {
        "status": "settled",
        "payouts": {
            "mode": "draw_hits",
            "winner_side": None,
            "bettors": [],
            "creators": [],
            "seed_refunds": [],
        },
        "bets": [
            {"bettor_id": "u1", "side": "a", "amount": "5.0"},
            {"bettor_id": "u2", "side": "draw", "amount": "2.0"},
        ],
    }
    M._notify_spectator_outcomes("agm_draw", None, [], book=book)

    got = dict(capture_notify)
    assert "didn't hit" in got["u1"]  # side bet on a drawn table
    assert "draw pool" in got["u2"]   # draw ticket still rides the pool
    assert set(got) == {"u1", "u2"}


def test_no_bets_no_crash(capture_notify):
    M._notify_spectator_outcomes("agm_empty", "a", [], book={"bets": []})
    assert capture_notify == []
