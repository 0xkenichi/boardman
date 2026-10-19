"""A fake world for the skill-match flows: an in-memory Supabase (profiles,
gaming.challenges, bets), a fake escrow, a fake score verifier, and the
core notifier recording what each player would receive."""
from __future__ import annotations

import itertools
import sys
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

import backend.supabase_client as _sc

# Import every module that binds ``get_supabase`` at import time NOW, so they
# hold the real factory (the fixture patches them and monkeypatch restores).
import gaming.src.backend.services.clawstation_escrow  # noqa: F401,E402
import gaming.src.backend.services.clawstation_settlement  # noqa: F401,E402
import gaming.src.backend.services.match_report  # noqa: F401,E402
import gaming.src.backend.services.play_points  # noqa: F401,E402
import gaming.src.backend.services.rematch_cancel  # noqa: F401,E402
import gaming.src.bot.handlers.dispute  # noqa: F401,E402
import gaming.src.bot.handlers.simple_ui  # noqa: F401,E402
import gaming.src.bot.jobs.expiry  # noqa: F401,E402
import gaming.src.bot.utils.db  # noqa: F401,E402
import gaming.src.bot.utils.notify  # noqa: F401,E402

from gaming.src.channels.core.identity import service as ids_svc  # noqa: E402
from gaming.src.channels.core.identity.repo import Identity  # noqa: E402
from tests.channels_fixtures import PLAY_ADDR, world  # noqa: F401,E402

_REAL = _sc.get_supabase
_clock = itertools.count(1)


def _now_iso(offset_us: int = 0) -> str:
    return (datetime.now(timezone.utc) + timedelta(microseconds=offset_us)).isoformat()


class _Q:
    def __init__(self, sb: "FakeSB", table: str) -> None:
        self.sb, self.table = sb, table
        self.op, self.payload, self.filters = "select", None, []
        self._order, self._limit, self._single = None, None, False

    # builders
    def select(self, *_a, **_k):
        if self.op not in ("insert", "update", "upsert"):
            self.op = "select"
        return self

    def insert(self, data):
        self.op, self.payload = "insert", data
        return self

    def update(self, data):
        self.op, self.payload = "update", data
        return self

    def eq(self, c, v):
        self.filters.append(lambda r: str(r.get(c)) == str(v))
        return self

    def neq(self, c, v):
        self.filters.append(lambda r: str(r.get(c)) != str(v))
        return self

    def in_(self, c, vals):
        vals = {str(v) for v in vals}
        self.filters.append(lambda r: str(r.get(c)) in vals)
        return self

    def lt(self, c, v):
        self.filters.append(lambda r: r.get(c) is not None and str(r.get(c)) < str(v))
        return self

    def gt(self, c, v):
        self.filters.append(lambda r: r.get(c) is not None and str(r.get(c)) > str(v))
        return self

    def gte(self, c, v):
        self.filters.append(lambda r: r.get(c) is not None and str(r.get(c)) >= str(v))
        return self

    def is_(self, c, v):
        self.filters.append(lambda r: r.get(c) is None if v == "null" else r.get(c) == v)
        return self

    def order(self, c, desc=False):
        self._order = (c, desc)
        return self

    def limit(self, n):
        self._limit = n
        return self

    def maybe_single(self):
        self._single = True
        return self

    single = maybe_single

    def __getattr__(self, name):  # ilike, or_, … are not used by these flows
        return lambda *a, **k: self

    def execute(self):
        rows = self.sb.tables.setdefault(self.table, [])
        if self.op == "insert":
            new = self.payload if isinstance(self.payload, list) else [self.payload]
            out = []
            for r in new:
                r = dict(r)
                r.setdefault("id", str(uuid.uuid4()))
                stamp = _now_iso(next(_clock))
                r.setdefault("created_at", stamp)
                r.setdefault("updated_at", stamp)
                rows.append(r)
                out.append(dict(r))
            return SimpleNamespace(data=out)
        hit = [r for r in rows if all(f(r) for f in self.filters)]
        if self.op == "update":
            for r in hit:
                r.update(self.payload)
                r["updated_at"] = _now_iso(next(_clock))
            return SimpleNamespace(data=[dict(r) for r in hit])
        if self._order:
            c, desc = self._order
            hit = sorted(hit, key=lambda r: str(r.get(c) or ""), reverse=desc)
        if self._limit is not None:
            hit = hit[: self._limit]
        if self._single:
            return SimpleNamespace(data=dict(hit[0]) if hit else None)
        return SimpleNamespace(data=[dict(r) for r in hit])


class FakeSB:
    def __init__(self) -> None:
        self.tables: dict[str, list[dict]] = {}

    def table(self, name: str) -> _Q:
        return _Q(self, name)

    def schema(self, _name: str) -> "FakeSB":
        return self

    @property
    def storage(self):  # pragma: no cover - local evidence store is used
        raise RuntimeError("no storage in tests")

    def challenge(self, cid: str) -> dict:
        return next(r for r in self.tables.get("challenges", []) if r["id"] == cid)

    def challenges(self) -> list[dict]:
        return self.tables.get("challenges", [])


class FakeVerifier:
    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.winner = "player1"
        self.confidence = 0.95
        self.resolved = True

    async def verify_dispute(self, screenshot_p1, screenshot_p2, reported_p1, reported_p2, **kw):
        self.calls.append({"p1": screenshot_p1, "p2": screenshot_p2})
        conf = SimpleNamespace(confidence=self.confidence)
        return {"resolved": self.resolved, "winner": self.winner, "verified_score": "2-1",
                "reason": "fake", "p1_result": conf, "p2_result": conf}

    async def verify_screenshot(self, src):
        self.calls.append({"single": src})
        return SimpleNamespace(is_valid=True, player1_score=2, player2_score=1, confidence=self.confidence,
                               error=None)


@pytest.fixture
def mworld(world, monkeypatch):  # noqa: F811
    """``world`` plus the match services, faked."""
    from gaming.src.backend.services import safety
    from gaming.src.channels.core import notify
    from gaming.src.channels.fake.adapter import RecordingDeliverer

    sb = FakeSB()
    fake = lambda: sb  # noqa: E731
    monkeypatch.setattr("backend.supabase_client.get_supabase", fake)
    for name, mod in list(sys.modules.items()):
        if mod is None or not name.startswith(("gaming.", "backend.")):
            continue
        for attr in ("get_supabase", "_get_supabase"):
            if getattr(mod, attr, None) is _REAL:
                monkeypatch.setattr(mod, attr, fake)

    monkeypatch.setattr(safety, "_recent_actions", {})
    monkeypatch.setenv("WHATSAPP_ENABLED", "1")
    monkeypatch.setenv("CHANNELS_CORE_FLOWS_TELEGRAM", "all,challenge,match,report,watch")

    escrow: list[tuple] = []

    async def create(pid, cid, amount):
        escrow.append(("create", pid, cid, str(amount)))
        sb.challenge(cid).update(status="creator_locked", creator_lock_tx_id="tx-c")
        return {"tx_hash": "0x" + "c" * 64}

    async def join(pid, cid, amount):
        escrow.append(("join", pid, cid, str(amount)))
        sb.challenge(cid).update(status="locked", opponent_lock_tx_id="tx-o")
        return {"tx_hash": "0x" + "d" * 64}

    async def resolve(cid, winner_address):
        escrow.append(("resolve", cid, winner_address))
        return {"tx_hash": "0x" + "f" * 64}

    async def cancel(cid):
        escrow.append(("cancel", cid))
        sb.challenge(cid).update(status="cancelled")
        return {"tx_hash": "0x" + "a" * 64}

    async def flag(cid):
        escrow.append(("dispute", cid))
        return {}

    e = "gaming.src.backend.services.clawstation_escrow"
    s = "gaming.src.backend.services.clawstation_settlement"
    for target, fn in {
        f"{e}.approve_and_create_match": create, f"{e}.approve_and_join_match": join,
        f"{e}.resolve_match": resolve, f"{e}.cancel_match": cancel, f"{e}.flag_dispute": flag,
        f"{s}.resolve_match": resolve, f"{s}.flag_dispute": flag,
        "gaming.src.backend.services.rematch_cancel.cancel_match": cancel,
        "gaming.src.bot.handlers.dispute.flag_dispute": flag,
    }.items():
        monkeypatch.setattr(target, fn)

    async def _noop(*a, **k):
        return None

    monkeypatch.setattr(f"{s}._award_play_points", _noop)
    monkeypatch.setattr(f"{s}._credit_onile_partner", lambda *a, **k: None)
    verifier = FakeVerifier()
    monkeypatch.setattr("gaming.src.backend.score_verifier.get_score_verifier", lambda: verifier)

    admin_alerts: list[str] = []

    async def alert(text):
        admin_alerts.append(text)

    monkeypatch.setattr("gaming.src.channels.core.actions.deposit.alert_admins", alert)

    wa_dv, tg_dv = RecordingDeliverer("whatsapp"), RecordingDeliverer("telegram")
    notify.set_default_service(notify.NotificationService({"whatsapp": wa_dv, "telegram": tg_dv}))
    bot = AsyncMock()
    from gaming.src.bot.utils import notify as bot_notify

    monkeypatch.setattr(bot_notify, "_bot", bot)

    world.sb = sb
    world.escrow = escrow
    world.verifier = verifier
    world.wa_dv = wa_dv
    world.tg_dv = tg_dv
    world.bot = bot
    world.admin_alerts = admin_alerts
    yield world
    notify.set_default_service(None)


def sb_profile(world, prof: dict, **extra: Any) -> dict:
    """Mirror a repo profile into the fake ``profiles`` table (tag lookups,
    Telegram chat ids) and the tag index."""
    row = {**prof, **extra}
    world.sb.tables.setdefault("profiles", []).append(row)
    if row.get("gaming_tag"):
        world.tags[str(row["gaming_tag"]).lower()] = row
    return row


def wa_player(world, number: str, tag: str, *, in_window: bool = False) -> dict:
    prof = world.repo.create_profile({"gaming_tag": tag, "display_name": tag})
    world.repo.upsert(Identity("whatsapp", number, prof["id"], address=number, country_hint="NG",
                               opted_in_at=ids_svc.utcnow(),
                               last_inbound_at=ids_svc.utcnow() if in_window else None))
    return sb_profile(world, prof)


def tg_player(world, tid: int, tag: str) -> dict:
    prof = world.repo.create_profile({"gaming_tag": tag, "telegram_id": tid})
    ids_svc.ensure_telegram_identity(prof["id"], tid, chat_id=tid, username=tag)
    return sb_profile(world, prof, gaming_telegram_chat_id=tid)
