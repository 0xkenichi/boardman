"""Shared fixtures for the channels tests: a fake world of money services."""
from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest

from gaming.src.channels.core.identity import repo as repo_mod
from gaming.src.channels.core.identity import service as ids
from gaming.src.channels.core.identity.repo import Identity, MemoryIdentityRepo

PLAY_ADDR = "0x" + "a" * 40
DEST = "0x" + "b" * 40


class _EmptySB:
    """get_supabase() stand-in: every query returns no rows."""

    def table(self, name):
        return self

    def schema(self, name):
        return self

    def __getattr__(self, name):
        return lambda *a, **k: self

    def execute(self):
        return SimpleNamespace(data=[])


@pytest.fixture
def world(monkeypatch):
    repo = MemoryIdentityRepo()
    repo_mod.set_repo(repo)
    ids.reset_dual_write_memo()
    monkeypatch.setenv("CHANNELS_CORE_FLOWS", "all")
    monkeypatch.setenv("CHANNELS_SITE_URL", "https://boardman.test")
    monkeypatch.setenv("WHATSAPP_DISPLAY_NUMBER", "+234 800 000 0000")
    monkeypatch.setenv("TELEGRAM_BOT_USERNAME_BOARDMAN", "BoardmanTestBot")
    monkeypatch.setattr("backend.supabase_client.get_supabase", lambda: _EmptySB())

    state = SimpleNamespace(repo=repo, balance=Decimal("40"), paystack_inits=[], transfers=[],
                            paystack_paid=True, tags={})

    async def summary(user_id, chain_id=None):
        return {"spendable_usdc": state.balance, "other_usdc": 0, "other_address": "",
                "ledger_usdc": 0, "address": PLAY_ADDR, "chain_id": "arc", "balance_error": None}

    async def ensure_wallet(user_id, chain_id=None):
        return {"wallet_id": f"w_{user_id}", "address": PLAY_ADDR, "chain_id": chain_id or "arc"}

    async def balance(user_id, chain_id=None):
        return state.balance

    async def pref(user_id):
        return "arc"

    async def strict(user_id, chain_id=None):
        return state.balance, None

    c = "gaming.src.backend.services.clawstation_circle"
    monkeypatch.setattr(f"{c}.get_balance_summary", summary)
    monkeypatch.setattr(f"{c}.ensure_user_wallet", ensure_wallet)
    monkeypatch.setattr(f"{c}.get_usdc_balance", balance)
    monkeypatch.setattr(f"{c}.get_preferred_chain", pref)
    monkeypatch.setattr(f"{c}.get_usdc_balance_strict", strict)

    p = "gaming.src.backend.services.paystack"
    monkeypatch.setattr(f"{p}.paystack_configured", lambda: True)

    def init(**kw):
        state.paystack_inits.append(kw)
        return {"authorization_url": f"https://checkout.paystack.com/{kw['reference']}", "access_code": "ac"}

    def verify(ref):
        return {"paid": state.paystack_paid, "status": "success" if state.paystack_paid else "abandoned",
                "amount_ngn": 10000, "channel": "card", "paid_at": "now"}

    monkeypatch.setattr(f"{p}.initialize_transaction", init)
    monkeypatch.setattr(f"{p}.verify_transaction", verify)
    monkeypatch.setattr("gaming.src.bot.utils.db._get_profile_by_tag_sync",
                        lambda tag: state.tags.get(tag.lstrip("@").lower()))

    def transfer(sender_id, wallet_id, address, amount, recipient_id, chain_id):
        state.transfers.append((sender_id, address, amount, recipient_id))
        return {"success": True, "transaction_id": "tx1", "tx_hash": "0x" + "e" * 64, "status": "PENDING"}

    monkeypatch.setattr("gaming.src.backend.services.withdrawals.execute_transfer_sync", transfer)

    # the in-memory safety windows are process-wide: start each test clean
    from gaming.src.backend.services import safety

    monkeypatch.setattr(safety, "_rate", type(safety._rate)(safety._rate.default_factory))
    monkeypatch.setattr(safety, "_daily_withdraw", {})
    yield state
    repo_mod.set_repo(None)


def wa_user(repo, number="2348011112222", tag="ada", **ident):
    prof = repo.create_profile({"gaming_tag": tag, "display_name": tag})
    repo.upsert(Identity("whatsapp", number, prof["id"], address=number, country_hint="NG",
                         opted_in_at=ids.utcnow(), **ident))
    return prof


def tg_user(repo, tid=5001, tag="tobi"):
    prof = repo.create_profile({"gaming_tag": tag, "telegram_id": tid})
    ids.ensure_telegram_identity(prof["id"], tid, chat_id=tid, username=tag)
    return prof
