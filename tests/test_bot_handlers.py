"""
gaming/tests/test_bot_handlers.py — Unit tests for the ClawStation Telegram bot handlers.

Covers:
    - /start onboarding (profile + wallet + welcome)
    - /balance reply formatting
    - /profile self and tag lookup
    - /challenge creation and insufficient balance
    - Accept / decline challenge callbacks
    - Expiry job query shape
"""
from __future__ import annotations

import sys
import uuid
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from gaming.src.bot.handlers.balance import cmd_balance  # noqa: E402
from gaming.src.bot.handlers.challenge import (  # noqa: E402
    cb_accept,
    cb_decline,
    cmd_challenge,
)
from gaming.src.bot.handlers.profile import cmd_profile  # noqa: E402
from gaming.src.bot.handlers.send import (  # noqa: E402
    SendState,
    cmd_send,
    send_address_input,
    send_confirm_password,
    send_tag_input,
)
from gaming.src.bot.handlers.start import cmd_start  # noqa: E402
from gaming.src.bot.handlers.tx_password import (  # noqa: E402
    TxPasswordResetState,
    TxPasswordState,
    cmd_reset_tx_password,
    cmd_set_tx_password,
    tx_reset_confirm_new_password,
    tx_reset_enter_code,
    tx_reset_set_new_password,
    tx_password_confirm,
    tx_password_enter,
)
from gaming.src.bot.handlers.profile_links import (  # noqa: E402
    cmd_link_email,
    cmd_link_psn,
    cmd_link_xbox,
    cmd_set_bio,
)
from gaming.src.bot.handlers.lock_stake import (  # noqa: E402
    cmd_lock_stake,
)
from gaming.src.bot.handlers.submit_score import (  # noqa: E402
    cmd_submit_score,
)
from gaming.src.bot.jobs.expiry import expire_challenges  # noqa: E402
from gaming.src.bot.utils.notify import set_bot  # noqa: E402
from gaming.src.bot.utils.security import hash_tx_password, verify_tx_password  # noqa: E402

_TEST_USER_ID = str(uuid.uuid4())
_TEST_OPPONENT_ID = str(uuid.uuid4())


# ── Minimal Supabase mock that supports the fluent chains used by bot code ───
class _MockQuery:
    def __init__(self, sb: "_MockSupabase", table: str):
        self.sb = sb
        self.table = table
        self.operation: str | None = None
        self.data: dict | None = None
        self.filters: list[tuple] = []

    def select(self, columns: str | None = None):
        self.operation = "select"
        return self

    def insert(self, data: dict):
        self.operation = "insert"
        self.data = data
        return self

    def update(self, data: dict):
        self.operation = "update"
        self.data = data
        return self

    def eq(self, col: str, val):
        self.filters.append(("eq", col, val))
        return self

    def neq(self, col: str, val):
        self.filters.append(("neq", col, val))
        return self

    def lt(self, col: str, val):
        self.filters.append(("lt", col, val))
        return self

    def maybe_single(self):
        return self

    @property
    def row_id(self):
        for kind, col, val in self.filters:
            if kind == "eq" and col == "id":
                return val
        return None

    def execute(self):
        sb = self.sb
        if self.table == "profiles":
            if self.operation == "select":
                for kind, col, val in self.filters:
                    if kind == "eq" and col == "telegram_id" and val in sb._profile_by_telegram:
                        return MagicMock(data=sb._profile_by_telegram[val])
                    if kind == "eq" and col == "gaming_tag" and val in sb._profile_by_tag:
                        return MagicMock(data=sb._profile_by_tag[val])
                    if kind == "eq" and col == "id" and val in sb._profile_by_id:
                        return MagicMock(data=sb._profile_by_id[val])
                return MagicMock(data=None)
            if self.operation == "insert":
                data = dict(self.data)
                data.setdefault("id", str(uuid.uuid4()))
                sb.add_profile(data)
                return MagicMock(data=[data])
            if self.operation == "update":
                for kind, col, val in self.filters:
                    if kind == "eq" and col == "id" and val in sb._profile_by_id:
                        sb._profile_by_id[val].update(self.data)
                return MagicMock(data=[])
        if self.table == "challenges":
            if self.operation == "select":
                for kind, col, val in self.filters:
                    if kind == "eq" and col == "id" and val in sb._challenge_by_id:
                        return MagicMock(data=sb._challenge_by_id[val])
                return MagicMock(data=None)
            if self.operation == "insert":
                data = dict(self.data)
                data.setdefault("id", str(uuid.uuid4()))
                sb.add_challenge(data)
                return MagicMock(data=[data])
            if self.operation == "update":
                return MagicMock(data=[])
        if self.table == "bets" and self.operation == "insert":
            data = dict(self.data)
            data.setdefault("id", str(uuid.uuid4()))
            sb._bet_by_id[data["id"]] = data
            return MagicMock(data=[data])
        if self.table == "wallet_debit_audit" and self.operation == "insert":
            data = dict(self.data)
            data.setdefault("id", str(uuid.uuid4()))
            sb._debit_by_id[data["id"]] = data
            return MagicMock(data=[data])
        return MagicMock(data=None)


class _MockSupabase:
    def __init__(self):
        self.calls: list[_MockQuery] = []
        self._profile_by_telegram: dict[int, dict] = {}
        self._profile_by_tag: dict[str, dict] = {}
        self._profile_by_id: dict[str, dict] = {}
        self._challenge_by_id: dict[str, dict] = {}
        self._bet_by_id: dict[str, dict] = {}
        self._debit_by_id: dict[str, dict] = {}

    def table(self, name: str):
        q = _MockQuery(self, name)
        self.calls.append(q)
        return q

    def schema(self, name: str):
        return self

    def add_profile(self, profile: dict) -> None:
        self._profile_by_id[profile["id"]] = profile
        if "telegram_id" in profile:
            self._profile_by_telegram[profile["telegram_id"]] = profile
        if "gaming_tag" in profile:
            self._profile_by_tag[profile["gaming_tag"]] = profile

    def add_challenge(self, challenge: dict) -> None:
        self._challenge_by_id[challenge["id"]] = challenge

    def find_calls(
        self, *, table: str | None = None, operation: str | None = None
    ) -> list[_MockQuery]:
        return [
            c
            for c in self.calls
            if (table is None or c.table == table) and (operation is None or c.operation == operation)
        ]


# ── Fixtures ─────────────────────────────────────────────────────────────────
@pytest.fixture(autouse=True)
def _patch_supabase(monkeypatch):
    """Replace the shared Supabase client with a fresh in-memory mock."""
    sb = _MockSupabase()

    # The bot modules import ``get_supabase`` locally; patch each binding so
    # every code path sees the in-memory mock.
    targets = [
        "backend.supabase_client.get_supabase",
        "gaming.src.bot.utils.db.get_supabase",
        "gaming.src.bot.utils.db._get_supabase",
        "gaming.src.bot.utils.notify.get_supabase",
        "gaming.src.bot.utils.notify._get_supabase",
        "gaming.src.bot.handlers.challenge.get_supabase",
        "gaming.src.bot.handlers.lock_stake.get_supabase",
        "gaming.src.bot.handlers.proof.get_supabase",
        "gaming.src.bot.handlers.send.get_supabase",
        "gaming.src.bot.handlers.submit_score.get_supabase",
        "gaming.src.bot.jobs.expiry.get_supabase",
        "gaming.src.bot.jobs.expiry._get_supabase",
    ]
    for target in targets:
        monkeypatch.setattr(target, lambda _sb=sb: _sb)
    return sb


@pytest.fixture(autouse=True)
def _patch_circle(monkeypatch):
    """Stub Circle wallet helpers so handlers never call the Circle API."""
    async def _ensure(user_id):
        return {
            "wallet_id": f"wallet_{user_id}",
            "address": "0x" + "a" * 40,
            "blockchain": "BASE-SEPOLIA",
        }

    async def _balance(user_id):
        return Decimal("100.00")

    targets = {
        "gaming.src.backend.services.clawstation_circle.ensure_user_wallet": _ensure,
        "gaming.src.backend.services.clawstation_circle.get_usdc_balance": _balance,
        "gaming.src.bot.handlers.start.ensure_user_wallet": _ensure,
        "gaming.src.bot.handlers.balance.get_usdc_balance": _balance,
        "gaming.src.bot.handlers.challenge.get_usdc_balance": _balance,
        "gaming.src.bot.handlers.send.get_usdc_balance": _balance,
    }
    for target, fn in targets.items():
        monkeypatch.setattr(target, fn)


@pytest.fixture(autouse=True)
def _patch_notify_bot(monkeypatch):
    """Provide an async bot stub for outbound notifications."""
    bot = AsyncMock()
    bot.send_message = AsyncMock()
    set_bot(bot)
    return bot


@pytest.fixture
def mock_supabase(_patch_supabase):
    return _patch_supabase


@pytest.fixture
def mock_fsm():
    """Return a fake FSMContext that stores data in memory."""

    class _FakeFSM:
        def __init__(self):
            self._data = {}
            self._state = None

        async def set_state(self, state):
            self._state = state

        async def get_data(self):
            return dict(self._data)

        async def update_data(self, **kwargs):
            self._data.update(kwargs)

        async def clear(self):
            self._data = {}
            self._state = None

    return _FakeFSM()


def _make_user(
    user_id: int = 12345,
    first_name: str = "Test",
    username: str = "testuser",
):
    user = MagicMock()
    user.id = user_id
    user.first_name = first_name
    user.username = username
    user.full_name = first_name
    return user


def _make_message(
    text: str = "",
    user_id: int = 12345,
    first_name: str = "Test",
    username: str = "testuser",
    chat_id: int = 67890,
):
    msg = MagicMock()
    msg.text = text
    msg.from_user = _make_user(user_id, first_name, username)
    msg.chat.id = chat_id
    msg.answer = AsyncMock()
    msg.reply = AsyncMock()
    msg.bot = AsyncMock()
    return msg


def _make_callback(data: str, user_id: int = 99999, chat_id: int = 11111):
    cb = MagicMock()
    cb.data = data
    cb.from_user = _make_user(user_id, "Opponent", "opponent")
    cb.answer = AsyncMock()
    cb.message = MagicMock()
    cb.message.answer = AsyncMock()
    cb.message.edit_text = AsyncMock()
    cb.message.chat.id = chat_id
    return cb


# ── /start tests ─────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_start_creates_profile_and_wallet(mock_supabase):
    msg = _make_message(text="/start", user_id=111, username="newgamer")
    await cmd_start(msg)

    insert_calls = mock_supabase.find_calls(table="profiles", operation="insert")
    assert len(insert_calls) == 1
    inserted = insert_calls[0].data
    assert inserted["telegram_id"] == 111
    assert inserted["gaming_tag"] == "newgamer"

    update_calls = mock_supabase.find_calls(table="profiles", operation="update")
    assert any(
        c.data.get("gaming_telegram_chat_id") == 67890 for c in update_calls
    )

    # The inserted profile is assigned an id by the mock execute() path.
    stored_profile = next(iter(mock_supabase._profile_by_id.values()))
    assert stored_profile["gaming_telegram_chat_id"] == 67890
    msg.answer.assert_awaited_once()
    text = msg.answer.await_args.args[0]
    assert "Welcome to ClawStation" in text


# ── /balance tests ───────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_balance_shows_usdc_and_tier(mock_supabase, monkeypatch):
    mock_supabase.add_profile(
        {
            "id": _TEST_USER_ID,
            "telegram_id": 222,
            "display_name": "Rich Gamer",
            "gaming_tag": "sq_rich",
            "gaming_tier": "gold",
            "gaming_reputation_score": 1500,
        }
    )
    async def _fake_balance(user_id, chain_id=None):
        return Decimal("250.50")

    monkeypatch.setattr(
        "gaming.src.bot.handlers.balance.get_usdc_balance",
        _fake_balance,
    )

    msg = _make_message(text="/balance", user_id=222)
    await cmd_balance(msg)

    msg.answer.assert_awaited_once()
    text = msg.answer.await_args.args[0]
    assert "$250.50" in text
    assert "Gold" in text


# ── /profile tests ───────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_profile_self(mock_supabase):
    mock_supabase.add_profile(
        {
            "id": _TEST_USER_ID,
            "telegram_id": 333,
            "display_name": "Self Gamer",
            "gaming_tag": "sq_self",
            "gaming_tier": "silver",
            "gaming_reputation_score": 1200,
        }
    )

    msg = _make_message(text="/profile", user_id=333)
    await cmd_profile(msg)

    msg.answer.assert_awaited_once()
    text = msg.answer.await_args.args[0]
    assert "Self Gamer" in text
    assert "sq_self" in text


@pytest.mark.asyncio
async def test_profile_lookup_by_tag(mock_supabase):
    mock_supabase.add_profile(
        {
            "id": _TEST_USER_ID,
            "telegram_id": 444,
            "display_name": "Lookup Me",
            "gaming_tag": "sq_sometag",
            "gaming_tier": "platinum",
            "gaming_reputation_score": 2000,
        }
    )

    msg = _make_message(text="/profile @sq_sometag", user_id=555)
    await cmd_profile(msg)

    msg.answer.assert_awaited_once()
    text = msg.answer.await_args.args[0]
    assert "Lookup Me" in text
    assert "sq_sometag" in text


# ── /challenge tests ──────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_challenge_creates_row(mock_supabase, monkeypatch):
    mock_supabase.add_profile(
        {
            "id": _TEST_USER_ID,
            "telegram_id": 666,
            "display_name": "Challenger",
            "gaming_tag": "sq_challenger",
            "gaming_tier": "bronze",
        }
    )
    mock_supabase.add_profile(
        {
            "id": _TEST_OPPONENT_ID,
            "telegram_id": 777,
            "display_name": "Opponent",
            "gaming_tag": "sq_opponent",
            "gaming_tier": "bronze",
        }
    )
    async def _fake_balance(user_id, chain_id=None):
        return Decimal("100.00")

    monkeypatch.setattr(
        "gaming.src.bot.handlers.challenge.get_usdc_balance",
        _fake_balance,
    )

    msg = _make_message(text='/challenge @sq_opponent 50 "EA FC" private', user_id=666)
    await cmd_challenge(msg)

    insert_calls = mock_supabase.find_calls(table="challenges", operation="insert")
    assert len(insert_calls) == 1
    record = insert_calls[0].data
    # Live gaming.challenges columns (legacy names + escrow fields).
    assert record["stake_amount"] == 50.0
    assert record["game_type"] == "EA FC"
    assert record["theme"] == "private"
    assert record["issuer_id"] == _TEST_USER_ID
    assert record["target_id"] == _TEST_OPPONENT_ID


@pytest.mark.asyncio
async def test_challenge_insufficient_balance(mock_supabase, monkeypatch):
    mock_supabase.add_profile(
        {
            "id": _TEST_USER_ID,
            "telegram_id": 888,
            "display_name": "Poor Gamer",
            "gaming_tag": "sq_poor",
            "gaming_tier": "bronze",
        }
    )
    async def _fake_balance(user_id, chain_id=None):
        return Decimal("10.00")

    monkeypatch.setattr(
        "gaming.src.bot.handlers.challenge.get_usdc_balance",
        _fake_balance,
    )

    msg = _make_message(text='/challenge @sq_opponent 50 "EA FC" private', user_id=888)
    await cmd_challenge(msg)

    insert_calls = mock_supabase.find_calls(table="challenges", operation="insert")
    assert len(insert_calls) == 0

    msg.answer.assert_awaited_once()
    text = msg.answer.await_args.args[0]
    assert "Insufficient balance" in text


# ── Callback tests ───────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_accept_callback_updates_challenge(mock_supabase):
    challenge_id = str(uuid.uuid4())
    mock_supabase.add_profile(
        {
            "id": _TEST_USER_ID,
            "telegram_id": 1000,
            "display_name": "Creator",
            "gaming_tag": "sq_creator",
            "gaming_telegram_chat_id": 1001,
        }
    )
    mock_supabase.add_profile(
        {
            "id": _TEST_OPPONENT_ID,
            "telegram_id": 2000,
            "display_name": "Accepter",
            "gaming_tag": "sq_accepter",
        }
    )
    mock_supabase.add_challenge(
        {
            "id": challenge_id,
            "creator_id": _TEST_USER_ID,
            "opponent_id": _TEST_OPPONENT_ID,
            "amount_usdc": 25.0,
            "game": "EA FC",
            "visibility": "private",
            "status": "open",
        }
    )

    cb = _make_callback(f"challenge:accept:{challenge_id}", user_id=2000)
    await cb_accept(cb)

    update_calls = mock_supabase.find_calls(table="challenges", operation="update")
    assert any(c.data.get("status") == "accepted" for c in update_calls)

    bet_inserts = mock_supabase.find_calls(table="bets", operation="insert")
    assert len(bet_inserts) == 1
    assert bet_inserts[0].data["challenge_id"] == challenge_id
    assert bet_inserts[0].data["opponent_id"] == _TEST_OPPONENT_ID


@pytest.mark.asyncio
async def test_decline_callback_updates_challenge(mock_supabase):
    challenge_id = str(uuid.uuid4())
    mock_supabase.add_profile(
        {
            "id": _TEST_USER_ID,
            "telegram_id": 3000,
            "display_name": "Creator",
            "gaming_tag": "sq_creator2",
            "gaming_telegram_chat_id": 3001,
        }
    )
    mock_supabase.add_profile(
        {
            "id": _TEST_OPPONENT_ID,
            "telegram_id": 4000,
            "display_name": "Decliner",
            "gaming_tag": "sq_decliner",
        }
    )
    mock_supabase.add_challenge(
        {
            "id": challenge_id,
            "creator_id": _TEST_USER_ID,
            "opponent_id": _TEST_OPPONENT_ID,
            "amount_usdc": 25.0,
            "game": "EA FC",
            "visibility": "private",
            "status": "open",
        }
    )

    cb = _make_callback(f"challenge:decline:{challenge_id}", user_id=4000)
    await cb_decline(cb)

    update_calls = mock_supabase.find_calls(table="challenges", operation="update")
    assert any(c.data.get("status") == "declined" for c in update_calls)

    bet_inserts = mock_supabase.find_calls(table="bets", operation="insert")
    assert len(bet_inserts) == 0


# ── Expiry job test ──────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_expiry_job_flips_stale_challenges(mock_supabase, monkeypatch):
    captured = {}
    original_update = _MockQuery.update

    def _tracking_update(self, data: dict):
        captured["update_data"] = data
        return original_update(self, data)

    monkeypatch.setattr(_MockQuery, "update", _tracking_update)

    await expire_challenges()

    update_calls = mock_supabase.find_calls(table="challenges", operation="update")
    assert len(update_calls) == 1
    call = update_calls[0]
    assert captured.get("update_data") == {"status": "expired"}

    eq_filters = {col: val for kind, col, val in call.filters if kind == "eq"}
    lt_filters = {col: val for kind, col, val in call.filters if kind == "lt"}
    assert eq_filters.get("status") == "open"
    assert "expires_at" in lt_filters


# ── Transaction password tests ───────────────────────────────────────────────
@pytest.mark.asyncio
async def test_set_tx_password_success(mock_supabase, mock_fsm):
    mock_supabase.add_profile(
        {
            "id": _TEST_USER_ID,
            "telegram_id": 5000,
            "display_name": "Password User",
            "gaming_tag": "sq_pwd",
        }
    )
    msg = _make_message(text="/set_tx_password", user_id=5000)
    await cmd_set_tx_password(msg, mock_fsm)
    assert mock_fsm._state == TxPasswordState.enter_password

    msg2 = _make_message(text="SecurePass123", user_id=5000)
    await tx_password_enter(msg2, mock_fsm)
    assert mock_fsm._state == TxPasswordState.confirm_password

    msg3 = _make_message(text="SecurePass123", user_id=5000)
    await tx_password_confirm(msg3, mock_fsm)

    update_calls = mock_supabase.find_calls(table="profiles", operation="update")
    assert any("gaming_tx_password_hash" in (c.data or {}) for c in update_calls)
    stored_hash = next(
        c.data["gaming_tx_password_hash"]
        for c in update_calls
        if "gaming_tx_password_hash" in (c.data or {})
    )
    assert verify_tx_password("SecurePass123", stored_hash)
    assert not verify_tx_password("Wrong", stored_hash)
    assert mock_fsm._state is None


@pytest.mark.asyncio
async def test_set_tx_password_mismatch(mock_supabase, mock_fsm):
    mock_supabase.add_profile(
        {
            "id": _TEST_USER_ID,
            "telegram_id": 5001,
            "display_name": "Mismatch User",
            "gaming_tag": "sq_mismatch",
        }
    )
    msg = _make_message(text="/set_tx_password", user_id=5001)
    await cmd_set_tx_password(msg, mock_fsm)
    msg2 = _make_message(text="SecurePass123", user_id=5001)
    await tx_password_enter(msg2, mock_fsm)
    msg3 = _make_message(text="DifferentPass", user_id=5001)
    await tx_password_confirm(msg3, mock_fsm)
    update_calls = mock_supabase.find_calls(table="profiles", operation="update")
    assert not any("gaming_tx_password_hash" in (c.data or {}) for c in update_calls)


@pytest.mark.asyncio
async def test_set_tx_password_too_short(mock_supabase, mock_fsm):
    mock_supabase.add_profile(
        {
            "id": _TEST_USER_ID,
            "telegram_id": 5002,
            "display_name": "Short User",
            "gaming_tag": "sq_short",
        }
    )
    msg = _make_message(text="/set_tx_password", user_id=5002)
    await cmd_set_tx_password(msg, mock_fsm)
    msg2 = _make_message(text="short", user_id=5002)
    await tx_password_enter(msg2, mock_fsm)
    assert mock_fsm._state == TxPasswordState.enter_password


# ── Send tests ───────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_send_requires_password(mock_supabase, mock_fsm):
    mock_supabase.add_profile(
        {
            "id": _TEST_USER_ID,
            "telegram_id": 6000,
            "display_name": "Sender",
            "gaming_tag": "sq_sender",
        }
    )
    msg = _make_message(text="/send", user_id=6000)
    await cmd_send(msg, mock_fsm)
    text = msg.answer.await_args.args[0]
    assert "/set_tx_password" in text


@pytest.mark.asyncio
async def test_send_to_tag_success(mock_supabase, mock_fsm, monkeypatch):
    sender_id = str(uuid.uuid4())
    recipient_id = str(uuid.uuid4())
    recipient_address = "0x" + "c" * 40

    mock_supabase.add_profile(
        {
            "id": sender_id,
            "telegram_id": 6001,
            "display_name": "Sender",
            "gaming_tag": "sq_sender2",
            "gaming_tx_password_hash": hash_tx_password("SecurePass123"),
            "circle_wallet_id": "wallet_sender",
            "gaming_deposit_address": "0x" + "d" * 40,
        }
    )
    mock_supabase.add_profile(
        {
            "id": recipient_id,
            "telegram_id": 6002,
            "display_name": "Recipient",
            "gaming_tag": "sq_recipient",
            "gaming_deposit_address": recipient_address,
        }
    )

    monkeypatch.setattr(
        "gaming.src.bot.handlers.send.get_usdc_balance",
        AsyncMock(return_value=Decimal("100.00")),
    )

    def _mock_transfer(self, from_wallet_id, to_address, amount_usdc):
        assert from_wallet_id == "wallet_sender"
        return {
            "success": True,
            "transaction_id": "tx_123",
            "status": "PENDING",
            "tx_hash": "0x" + "e" * 64,
        }

    monkeypatch.setattr(
        "backend.circle_wallet_service.CircleWalletService.transfer_usdc",
        _mock_transfer,
    )

    msg1 = _make_message(text="/send", user_id=6001)
    await cmd_send(msg1, mock_fsm)
    msg2 = _make_message(text="@sq_recipient 25", user_id=6001)
    await send_tag_input(msg2, mock_fsm)
    assert mock_fsm._state == SendState.confirm_password
    msg3 = _make_message(text="SecurePass123", user_id=6001)
    await send_confirm_password(msg3, mock_fsm)

    debit_inserts = mock_supabase.find_calls(table="wallet_debit_audit", operation="insert")
    assert len(debit_inserts) == 1
    assert debit_inserts[0].data["recipient_id"] == recipient_id
    assert debit_inserts[0].data["amount_usdc"] == 25.0


@pytest.mark.asyncio
async def test_send_self_not_allowed(mock_supabase, mock_fsm, monkeypatch):
    sender_id = str(uuid.uuid4())
    sender_address = "0x" + "f" * 40

    mock_supabase.add_profile(
        {
            "id": sender_id,
            "telegram_id": 6003,
            "display_name": "Self Sender",
            "gaming_tag": "sq_selfsender",
            "gaming_tx_password_hash": hash_tx_password("SecurePass123"),
            "circle_wallet_id": "wallet_self",
            "gaming_deposit_address": sender_address,
        }
    )

    monkeypatch.setattr(
        "gaming.src.bot.handlers.send.get_usdc_balance",
        AsyncMock(return_value=Decimal("100.00")),
    )

    msg1 = _make_message(text="/send", user_id=6003)
    await cmd_send(msg1, mock_fsm)
    msg2 = _make_message(text="@sq_selfsender 25", user_id=6003)
    await send_tag_input(msg2, mock_fsm)
    assert mock_fsm._state == SendState.confirm_password

    msg3 = _make_message(text="SecurePass123", user_id=6003)
    await send_confirm_password(msg3, mock_fsm)

    text = msg3.answer.await_args.args[0]
    assert "cannot send to yourself" in text.lower()


@pytest.mark.asyncio
async def test_send_to_address_success(mock_supabase, mock_fsm, monkeypatch):
    sender_id = str(uuid.uuid4())
    recipient_address = "0x" + "a" * 40

    mock_supabase.add_profile(
        {
            "id": sender_id,
            "telegram_id": 6004,
            "display_name": "Address Sender",
            "gaming_tag": "sq_addr_sender",
            "gaming_tx_password_hash": hash_tx_password("SecurePass123"),
            "circle_wallet_id": "wallet_addr_sender",
            "gaming_deposit_address": "0x" + "b" * 40,
        }
    )

    monkeypatch.setattr(
        "gaming.src.bot.handlers.send.get_usdc_balance",
        AsyncMock(return_value=Decimal("100.00")),
    )

    def _mock_transfer(self, from_wallet_id, to_address, amount_usdc):
        return {
            "success": True,
            "transaction_id": "tx_456",
            "status": "PENDING",
            "tx_hash": "0x" + "c" * 64,
        }

    monkeypatch.setattr(
        "backend.circle_wallet_service.CircleWalletService.transfer_usdc",
        _mock_transfer,
    )

    msg1 = _make_message(text="/send", user_id=6004)
    await cmd_send(msg1, mock_fsm)
    msg2 = _make_message(text=f"{recipient_address} 10", user_id=6004)
    await send_address_input(msg2, mock_fsm)
    assert mock_fsm._state == SendState.confirm_password
    msg3 = _make_message(text="SecurePass123", user_id=6004)
    await send_confirm_password(msg3, mock_fsm)

    debit_inserts = mock_supabase.find_calls(table="wallet_debit_audit", operation="insert")
    assert len(debit_inserts) == 1
    assert debit_inserts[0].data["recipient_address"].lower() == recipient_address.lower()
    assert debit_inserts[0].data["recipient_id"] is None


# ── Profile linking tests ────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_link_psn_stores_id(mock_supabase, monkeypatch):
    mock_supabase.add_profile(
        {
            "id": _TEST_USER_ID,
            "telegram_id": 7000,
            "display_name": "PSN User",
            "gaming_tag": "sq_psn",
        }
    )

    msg = _make_message(text="/link_psn my_psn_id", user_id=7000)
    await cmd_link_psn(msg)

    update_calls = mock_supabase.find_calls(table="profiles", operation="update")
    assert any(c.data.get("gaming_psn_id") == "my_psn_id" for c in update_calls)


@pytest.mark.asyncio
async def test_link_xbox_stores_tag(mock_supabase, monkeypatch):
    mock_supabase.add_profile(
        {
            "id": _TEST_USER_ID,
            "telegram_id": 7001,
            "display_name": "Xbox User",
            "gaming_tag": "sq_xbox",
        }
    )

    msg = _make_message(text="/link_xbox MyGamertag123", user_id=7001)
    await cmd_link_xbox(msg)

    update_calls = mock_supabase.find_calls(table="profiles", operation="update")
    assert any(c.data.get("gaming_xbox_id") == "MyGamertag123" for c in update_calls)


@pytest.mark.asyncio
async def test_link_email_validates_format(mock_supabase, monkeypatch):
    mock_supabase.add_profile(
        {
            "id": _TEST_USER_ID,
            "telegram_id": 7002,
            "display_name": "Email User",
            "gaming_tag": "sq_email",
        }
    )

    msg = _make_message(text="/link_email invalid-email", user_id=7002)
    await cmd_link_email(msg)

    update_calls = mock_supabase.find_calls(table="profiles", operation="update")
    assert not any("gaming_backup_email" in (c.data or {}) for c in update_calls)
    msg.answer.assert_awaited_once()
    text = msg.answer.await_args.args[0]
    assert "Invalid email" in text


@pytest.mark.asyncio
async def test_link_email_stores_valid_email(mock_supabase, monkeypatch):
    mock_supabase.add_profile(
        {
            "id": _TEST_USER_ID,
            "telegram_id": 7003,
            "display_name": "Email User",
            "gaming_tag": "sq_email2",
        }
    )

    msg = _make_message(text="/link_email gamer@example.com", user_id=7003)
    await cmd_link_email(msg)

    update_calls = mock_supabase.find_calls(table="profiles", operation="update")
    assert any(c.data.get("gaming_backup_email") == "gamer@example.com" for c in update_calls)


@pytest.mark.asyncio
async def test_set_bio_stores_text(mock_supabase, monkeypatch):
    mock_supabase.add_profile(
        {
            "id": _TEST_USER_ID,
            "telegram_id": 7004,
            "display_name": "Bio User",
            "gaming_tag": "sq_bio",
        }
    )

    msg = _make_message(text="/set_bio Competitive FIFA player", user_id=7004)
    await cmd_set_bio(msg)

    update_calls = mock_supabase.find_calls(table="profiles", operation="update")
    assert any(c.data.get("gaming_bio") == "Competitive FIFA player" for c in update_calls)


# ── Transaction password reset tests ─────────────────────────────────────────
@pytest.mark.asyncio
async def test_reset_tx_password_success(mock_supabase, mock_fsm, monkeypatch):
    mock_supabase.add_profile(
        {
            "id": _TEST_USER_ID,
            "telegram_id": 8000,
            "display_name": "Reset User",
            "gaming_tag": "sq_reset",
            "gaming_tx_password_hash": hash_tx_password("OldPass123"),
        }
    )

    msg = _make_message(text="/reset_tx_password", user_id=8000)
    await cmd_reset_tx_password(msg, mock_fsm)
    assert mock_fsm._state == TxPasswordResetState.enter_code

    # Get the generated code from FSM
    data = await mock_fsm.get_data()
    reset_code = data.get("reset_code")
    assert reset_code is not None

    msg2 = _make_message(text=reset_code, user_id=8000)
    await tx_reset_enter_code(msg2, mock_fsm)
    assert mock_fsm._state == TxPasswordResetState.set_new_password

    msg3 = _make_message(text="NewPass123", user_id=8000)
    await tx_reset_set_new_password(msg3, mock_fsm)
    assert mock_fsm._state == TxPasswordResetState.confirm_new_password

    msg4 = _make_message(text="NewPass123", user_id=8000)
    await tx_reset_confirm_new_password(msg4, mock_fsm)

    update_calls = mock_supabase.find_calls(table="profiles", operation="update")
    assert any("gaming_tx_password_hash" in (c.data or {}) for c in update_calls)
    stored_hash = next(
        c.data["gaming_tx_password_hash"]
        for c in update_calls
        if "gaming_tx_password_hash" in (c.data or {})
    )
    assert verify_tx_password("NewPass123", stored_hash)
    assert not verify_tx_password("OldPass123", stored_hash)


# ── Lock stake tests ─────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_lock_stake_creator_calls_create_match(mock_supabase, monkeypatch):
    challenge_id = str(uuid.uuid4())
    opponent_id = str(uuid.uuid4())
    mock_supabase.add_profile(
        {
            "id": _TEST_USER_ID,
            "telegram_id": 9000,
            "display_name": "Creator",
            "gaming_tag": "sq_creator",
            "circle_wallet_id": "wallet_creator",
        }
    )
    mock_supabase.add_profile(
        {
            "id": opponent_id,
            "telegram_id": 9001,
            "display_name": "Opponent",
            "gaming_tag": "sq_opponent",
            "circle_wallet_id": "wallet_opponent",
        }
    )
    mock_supabase.add_challenge(
        {
            "id": challenge_id,
            "creator_id": _TEST_USER_ID,
            "opponent_id": opponent_id,
            "amount_usdc": 5.0,
            "game": "EAFC",
            "visibility": "private",
            "status": "accepted",
        }
    )

    async def fake_ensure(uid, chain_id=None):
        return {"wallet_id": f"wallet_{uid[:8]}", "address": "0x1234"}

    monkeypatch.setattr(
        "gaming.src.bot.handlers.lock_stake.ensure_user_wallet", fake_ensure
    )

    create_called = {}

    async def fake_create(uid, cid, amount):
        create_called["called"] = True
        create_called["amount"] = amount
        return {
            "success": True,
            "create_tx_id": "tx_create",
            "tx_hash": "0xabc123",
            "match_id": "0xmatch",
        }

    monkeypatch.setattr(
        "gaming.src.bot.handlers.lock_stake.approve_and_create_match", fake_create
    )

    msg = _make_message(text=f"/lock_stake {challenge_id}", user_id=9000)
    await cmd_lock_stake(msg)

    assert create_called.get("called")
    assert create_called["amount"] == Decimal("5.0")
    # DB status is updated inside approve_and_create_match (mocked here).
    assert msg.answer.await_count >= 1
    texts = " ".join(str(c.args[0]) for c in msg.answer.await_args_list if c.args)
    assert "Stake locked" in texts or "lock" in texts.lower()


@pytest.mark.asyncio
async def test_lock_stake_opponent_calls_join_match(mock_supabase, monkeypatch):
    challenge_id = str(uuid.uuid4())
    opponent_id = str(uuid.uuid4())
    mock_supabase.add_profile(
        {
            "id": _TEST_USER_ID,
            "telegram_id": 9100,
            "display_name": "Creator",
            "gaming_tag": "sq_creator",
            "circle_wallet_id": "wallet_creator",
        }
    )
    mock_supabase.add_profile(
        {
            "id": opponent_id,
            "telegram_id": 9101,
            "display_name": "Opponent",
            "gaming_tag": "sq_opponent",
            "circle_wallet_id": "wallet_opponent",
        }
    )
    mock_supabase.add_challenge(
        {
            "id": challenge_id,
            "creator_id": _TEST_USER_ID,
            "opponent_id": opponent_id,
            "amount_usdc": 10.0,
            "game": "EAFC",
            "visibility": "private",
            "status": "creator_locked",
            "creator_lock_tx_id": "tx_create",
        }
    )

    async def fake_ensure(uid, chain_id=None):
        return {"wallet_id": f"wallet_{uid[:8]}", "address": "0x1234"}

    monkeypatch.setattr(
        "gaming.src.bot.handlers.lock_stake.ensure_user_wallet", fake_ensure
    )

    join_called = {}

    async def fake_join(uid, cid, amount):
        join_called["called"] = True
        join_called["amount"] = amount
        return {
            "success": True,
            "join_tx_id": "tx_join",
            "tx_hash": "0xdef456",
            "match_id": "0xmatch",
        }

    monkeypatch.setattr(
        "gaming.src.bot.handlers.lock_stake.approve_and_join_match", fake_join
    )

    msg = _make_message(text=f"/lock_stake {challenge_id}", user_id=9101)
    await cmd_lock_stake(msg)

    assert join_called.get("called")
    assert join_called["amount"] == Decimal("10.0")
    # DB status is updated inside approve_and_join_match (mocked here).
    assert msg.answer.await_count >= 1
    texts = " ".join(str(c.args[0]) for c in msg.answer.await_args_list if c.args)
    assert "Stake locked" in texts or "lock" in texts.lower()


# ── Submit score tests ───────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_submit_score_stores_creator_score(mock_supabase):
    challenge_id = str(uuid.uuid4())
    opponent_id = str(uuid.uuid4())
    mock_supabase.add_profile(
        {
            "id": _TEST_USER_ID,
            "telegram_id": 9200,
            "display_name": "Creator",
            "gaming_tag": "sq_creator",
        }
    )
    mock_supabase.add_profile(
        {
            "id": opponent_id,
            "telegram_id": 9201,
            "display_name": "Opponent",
            "gaming_tag": "sq_opponent",
        }
    )
    mock_supabase.add_challenge(
        {
            "id": challenge_id,
            "creator_id": _TEST_USER_ID,
            "opponent_id": opponent_id,
            "amount_usdc": 5.0,
            "game": "EAFC",
            "visibility": "private",
            "status": "locked",
        }
    )

    msg = _make_message(text=f"/submit_score {challenge_id} 3", user_id=9200)
    await cmd_submit_score(msg)

    update_calls = mock_supabase.find_calls(table="challenges", operation="update")
    update = next((c for c in update_calls if c.row_id == challenge_id), None)
    assert update is not None
    assert update.data["creator_score"] == 3


@pytest.mark.asyncio
async def test_submit_score_transitions_to_submitted_when_both_scores_present(mock_supabase):
    challenge_id = str(uuid.uuid4())
    opponent_id = str(uuid.uuid4())
    mock_supabase.add_profile(
        {
            "id": _TEST_USER_ID,
            "telegram_id": 9300,
            "display_name": "Creator",
            "gaming_tag": "sq_creator",
        }
    )
    mock_supabase.add_profile(
        {
            "id": opponent_id,
            "telegram_id": 9301,
            "display_name": "Opponent",
            "gaming_tag": "sq_opponent",
        }
    )
    mock_supabase.add_challenge(
        {
            "id": challenge_id,
            "creator_id": _TEST_USER_ID,
            "opponent_id": opponent_id,
            "amount_usdc": 5.0,
            "game": "EAFC",
            "visibility": "private",
            "status": "locked",
            "creator_score": 3,
        }
    )

    msg = _make_message(text=f"/submit_score {challenge_id} 1", user_id=9301)
    await cmd_submit_score(msg)

    update_calls = mock_supabase.find_calls(table="challenges", operation="update")
    update = next((c for c in update_calls if c.row_id == challenge_id), None)
    assert update is not None
    assert update.data["opponent_score"] == 1
    assert update.data["status"] == "submitted"
