"""Skill-match flows end to end on the fake WhatsApp adapter (3 buttons, 10
list rows, one CTA per message: every outbound message is validated), plus
the same flows on the Telegram renderer and the legacy Telegram handlers."""
from __future__ import annotations

import asyncio
import re
from decimal import Decimal

from gaming.src.channels.core import ids
from gaming.src.channels.fake.adapter import FakeChannel, NotOffered, options_of, text_of
from tests.channels_fixtures import PLAY_ADDR, world  # noqa: F401
from tests.channels_match_fixtures import mworld, tg_player, wa_player  # noqa: F401

ADA = "2348011112222"
BOLA = "2348033334444"
PNG = b"\x89PNG\r\n\x1a\nfake-final-screen"


def run(coro):
    return asyncio.run(coro)


def labels(ch, user):
    return [label for _, label in ch.offered(user)]


def create_challenge(wa, world, *, opponent: str = "@bola", stake: str = "$5"):
    """ada challenges someone to FC Mobile; returns the challenge row."""
    run(wa.text(ADA, "challenge"))
    assert "Where do you play?" in wa.last_text(ADA)
    run(wa.tap(ADA, "Mobile"))
    # more than 10 mobile games: a paged list of 9 + "More…"
    offered = labels(wa, ADA)
    assert len(offered) == 10 and offered[-1] == "More…"
    run(wa.tap(ADA, "More…"))
    assert labels(wa, ADA)[0] != offered[0]
    from gaming.src.backend.services.game_catalog import list_games

    pos = [g["game_id"] for g in list_games(category="mobile")].index("mobile.fc_mobile") + 1
    run(wa.text(ADA, str(pos)))  # a numbered reply picks from the whole list
    assert "FC Mobile" in wa.last_text(ADA)
    assert labels(wa, ADA) == ["$2", "$5", "$10"]
    run(wa.tap(ADA, stake))
    assert labels(wa, ADA) == ["By @tag", "By phone number", "Invite link"]
    if opponent == "link":
        run(wa.tap(ADA, "Invite link"))
    else:
        run(wa.text(ADA, opponent))
    assert "Confirm challenge" in wa.last_text(ADA)
    run(wa.tap(ADA, "Send it"))
    rows = world.sb.challenges()
    return rows[-1] if rows else None


def accepted_match(wa, world):
    ada = wa_player(world, ADA, "ada", in_window=True)
    bola = wa_player(world, BOLA, "bola")
    ch = create_challenge(wa, world)
    run(wa.tap_id(BOLA, ids.encode("match", "accept", ch["id"])))
    assert world.sb.challenge(ch["id"])["status"] == "accepted"
    return ada, bola, ch


# ── the whole match on WhatsApp ──────────────────────────────────────────────


def test_whatsapp_challenge_lock_report_settle(mworld):
    world = mworld
    wa = FakeChannel("wa")
    ada = wa_player(world, ADA, "ada", in_window=True)
    bola = wa_player(world, BOLA, "bola")  # never messaged us: outside the 24 h window

    ch = create_challenge(wa, world)
    assert (ch["issuer_id"], ch["target_id"], ch["stake_amount"], ch["game_type"], ch["status"]) == (
        ada["id"], bola["id"], 5.0, "mobile.fc_mobile", "open")
    assert "Challenge sent to *@bola*" in wa.all_text(ADA)

    # bola is outside the window: the approved template, with Accept/Decline payloads
    to, msg = world.wa_dv.templates[-1]
    assert to == BOLA and msg["template"]["name"] == "challenge_received"
    payloads = [c["parameters"][0]["payload"] for c in msg["template"]["components"] if c["type"] == "button"]
    assert payloads == [ids.encode("match", "accept", ch["id"]), ids.encode("match", "decline", ch["id"])]

    # tapping the template's Accept quick reply
    run(wa.tap_id(BOLA, payloads[0]))
    assert "Accepted" in wa.last_text(BOLA)
    assert world.sb.challenge(ch["id"])["status"] == "accepted"
    assert any(b["challenge_id"] == ch["id"] for b in world.sb.tables["bets"])
    # ada (inside the window) gets a session message with Lock my stake
    to, outs = world.wa_dv.session[-1]
    assert to == ADA and "accepted your challenge" in outs[0].body
    assert [o.label for o in outs[0].options][0] == "Lock my stake"

    # ada locks behind an approval prompt
    run(wa.text(ADA, "matches"))
    assert "Lock my stake" in labels(wa, ADA)
    run(wa.tap(ADA, "Lock my stake"))
    assert "Lock $5.00 USDC?" in wa.last_text(ADA)
    assert not world.escrow
    run(wa.tap(ADA, "Yes, lock it"))
    assert world.escrow[-1][:3] == ("create", ada["id"], ch["id"])
    assert "Waiting for your opponent" in wa.last_text(ADA)
    to, outs = world.wa_dv.session[-1]  # bola messaged us: now inside the window
    assert to == BOLA and "Your turn" in outs[0].body

    # bola locks: both locked, ada told to play
    run(wa.tap_id(BOLA, ids.encode("match", "lock", ch["id"])))
    run(wa.tap(BOLA, "Yes, lock it"))
    assert world.escrow[-1][:3] == ("join", bola["id"], ch["id"])
    assert world.sb.challenge(ch["id"])["status"] == "locked"
    assert "Both stakes locked" in wa.last_text(BOLA)
    to, outs = world.wa_dv.session[-1]
    assert to == ADA and "Both stakes locked" in outs[0].body

    # ada reports: photo → side → score → confirm
    run(wa.text(ADA, "report"))
    assert "Send a photo" in wa.last_text(ADA)
    run(wa.image(ADA, PNG))
    assert labels(wa, ADA) == ["I was HOME", "I was AWAY"]
    run(wa.tap(ADA, "I was HOME"))
    assert "HOME-AWAY" in wa.last_text(ADA)
    run(wa.text(ADA, "2-1"))
    assert "Confirm your report" in wa.last_text(ADA)
    run(wa.tap(ADA, "Submit"))
    row = world.sb.challenge(ch["id"])
    assert row["screenshot_creator_url"].startswith("evidence://local/whatsapp/")
    assert (row["creator_reported_home"], row["creator_reported_away"]) == (2, 1)
    assert "Waiting for your opponent" in wa.last_text(ADA)
    to, outs = world.wa_dv.session[-1]
    assert to == BOLA and "Report result" in [o.label for o in outs[0].options]

    # bola reports the same score (side already set to AWAY), settlement pays ada
    run(wa.tap(BOLA, "Report result"))
    run(wa.image(BOLA, PNG + b"2"))
    assert "HOME-AWAY" in wa.last_text(BOLA)
    run(wa.text(BOLA, "2-1"))
    run(wa.tap(BOLA, "Submit"))
    row = world.sb.challenge(ch["id"])
    assert row["status"] == "resolved" and row["winner_id"] == ada["id"]
    assert ("resolve", ch["id"], PLAY_ADDR) in world.escrow
    # the score verifier read both screenshots from OUR storage
    call = world.verifier.calls[-1]
    assert call["p1"].startswith("data:image/png;base64,") and call["p2"].startswith("data:image/png;base64,")
    results = {to: outs[0].body for to, outs in world.wa_dv.session if "Balance" in outs[0].body}
    assert "You won" in results[ADA] and "You lost" in results[BOLA]
    assert not world.bot.send_message.called  # nobody here is on Telegram


def test_invite_link_and_join_for_a_new_player(mworld):
    world = mworld
    wa = FakeChannel("wa")
    wa_player(world, ADA, "ada", in_window=True)
    ch = create_challenge(wa, world, opponent="link")
    assert ch["target_id"] is None and ch["theme"] == "private"
    from gaming.src.backend.services.match_codes import derived_code

    code = derived_code(ch["id"])
    text = wa.all_text(ADA)
    assert f"https://wa.me/2348000000000?text=JOIN%20{code}" in text
    assert f"https://boardman.test/app/match/{code}" in text
    assert f"https://t.me/BoardmanTestBot?start=m_{code}" in text
    share = wa.links(ADA)[-1]
    assert share.startswith("https://wa.me/?text=")

    newbie = "2348055556666"
    run(wa.text(newbie, f"JOIN {code}", name="Chi"))
    assert "Welcome to *Boardman*" in wa.last_text(newbie)
    run(wa.tap(newbie, "I'm new"))
    run(wa.text(newbie, "chi_9ja"))
    assert "Challenge from @ada" in wa.last_text(newbie)
    run(wa.tap(newbie, "Accept"))
    row = world.sb.challenge(ch["id"])
    chi = world.repo.get("whatsapp", newbie)
    assert row["status"] == "accepted" and row["target_id"] == chi.profile_id


def test_lock_approval_nonce_is_bound_single_use_and_owned(mworld):
    world = mworld
    wa = FakeChannel("wa")
    ada, bola, ch = accepted_match(wa, world)
    lock_id = ids.encode("match", "lock", ch["id"])

    run(wa.tap_id(ADA, lock_id))
    run(wa.tap(ADA, "No"))
    assert "nothing was locked" in wa.last_text(ADA) and not world.escrow

    run(wa.tap_id(ADA, lock_id))
    yes = dict((label, i) for i, label in wa.offered(ADA))["Yes, lock it"]
    assert len(yes.split("|")[3]) >= 22  # a 128-bit nonce, not the match id
    prompt_wamid = wa.last_wamid(ADA)

    # a reply to another message (a copied/forwarded prompt) is refused
    run(wa.tap_id(ADA, yes, context_id="wamid.SOMETHING_ELSE"))
    assert "latest prompt" in wa.last_text(ADA) and not world.escrow
    # someone else tapping ada's prompt is refused
    run(wa.tap_id(BOLA, yes, context_id=prompt_wamid))
    assert "isn't yours" in wa.last_text(BOLA) and not world.escrow
    # the real tap locks once; a replay does nothing
    run(wa.tap_id(ADA, yes, context_id=prompt_wamid))
    assert [e[0] for e in world.escrow] == ["create"]
    run(wa.tap_id(ADA, yes, context_id=prompt_wamid))
    assert "already answered" in wa.last_text(ADA)
    assert [e[0] for e in world.escrow] == ["create"]

    # a newer prompt supersedes an older one
    run(wa.tap_id(BOLA, lock_id))
    old = dict((label, i) for i, label in wa.offered(BOLA))["Yes, lock it"]
    old_wamid = wa.last_wamid(BOLA)
    run(wa.tap_id(BOLA, lock_id))
    run(wa.tap_id(BOLA, old, context_id=old_wamid))
    assert "already answered" in wa.last_text(BOLA)
    assert [e[0] for e in world.escrow] == ["create"]


def test_expired_approval_is_refused(mworld, monkeypatch):
    world = mworld
    wa = FakeChannel("wa")
    accepted_match(wa, world)
    run(wa.text(ADA, "matches"))
    run(wa.tap(ADA, "Lock my stake"))
    from gaming.src.channels.core import store

    real = store.now_ms
    monkeypatch.setattr(store, "now_ms", lambda: real() + 10 * 60 * 1000)
    run(wa.tap(ADA, "Yes, lock it"))
    assert "expired" in wa.last_text(ADA) and not world.escrow


def test_screenshot_is_copied_to_our_storage(mworld):
    import hashlib

    from gaming.src.channels.core.evidence import read_evidence

    world = mworld
    wa = FakeChannel("wa")
    _, _, ch = accepted_match(wa, world)
    world.sb.challenge(ch["id"]).update(status="locked")
    run(wa.image(ADA, PNG))  # a bare photo starts the report for the waiting match
    assert labels(wa, ADA) == ["I was HOME", "I was AWAY"]
    run(wa.tap(ADA, "I was AWAY"))
    run(wa.text(ADA, "0-3"))
    run(wa.tap(ADA, "Submit"))
    ref = world.sb.challenge(ch["id"])["screenshot_creator_url"]
    digest = hashlib.sha256(PNG).hexdigest()
    assert ref.startswith("evidence://local/whatsapp/") and digest in ref
    data, mime = read_evidence(ref)
    assert data == PNG and mime == "image/png"
    # Meta's media URL is never what we store
    assert "media.example" not in ref


def test_conflicting_reports_open_a_dispute(mworld):
    world = mworld
    wa = FakeChannel("wa")
    _, _, ch = accepted_match(wa, world)
    world.sb.challenge(ch["id"]).update(status="locked", game_type="mobile.8_ball_pool")
    world.verifier.resolved = False
    for user, name in ((ADA, "AdaPool"), (BOLA, "BolaPool")):
        run(wa.text(user, "report"))
        run(wa.image(user, PNG + user.encode()))
        assert "in-game name" in wa.last_text(user)
        run(wa.text(user, name))
        assert labels(wa, user) == ["I won", "I lost"]
        run(wa.tap(user, "I won"))
        run(wa.tap(user, "Submit"))
    assert world.sb.challenge(ch["id"])["status"] == "disputed"
    assert ("dispute", ch["id"]) in world.escrow
    assert "support will review" in wa.last_text(BOLA)
    disputed = [to for to, outs in world.wa_dv.session if "Reports don't match" in outs[0].body]
    assert set(disputed) == {ADA, BOLA}


def test_dispute_button_alerts_admins(mworld):
    world = mworld
    wa = FakeChannel("wa")
    _, _, ch = accepted_match(wa, world)
    world.sb.challenge(ch["id"]).update(status="locked")
    run(wa.text(ADA, "matches"))
    run(wa.tap(ADA, "Dispute"))
    run(wa.tap(ADA, "Open dispute"))
    assert world.sb.challenge(ch["id"])["status"] == "disputed"
    assert "Dispute opened" in wa.last_text(ADA)
    assert world.admin_alerts and ch["id"] in world.admin_alerts[-1]


def test_my_matches_lists_with_actions(mworld):
    world = mworld
    wa = FakeChannel("wa")
    wa_player(world, ADA, "ada", in_window=True)
    wa_player(world, BOLA, "bola")
    run(wa.text(ADA, "matches"))
    assert "No open matches" in wa.last_text(ADA)
    ch = create_challenge(wa, world)
    run(wa.text(ADA, "matches"))
    assert "Waiting for your opponent to accept" in wa.last_text(ADA)
    assert labels(wa, ADA) == ["Cancel challenge", "Menu"]
    run(wa.text(BOLA, "matches"))
    assert labels(wa, BOLA) == ["Accept", "Decline", "Menu"]
    run(wa.tap(BOLA, "Decline"))
    assert world.sb.challenge(ch["id"])["status"] == "declined"
    to, outs = world.wa_dv.session[-1]
    assert to == ADA and "declined" in outs[0].body


def test_cannot_challenge_while_a_match_is_open(mworld):
    world = mworld
    wa = FakeChannel("wa")
    accepted_match(wa, world)
    run(wa.text(ADA, "challenge"))
    assert "already have an open match" in wa.last_text(ADA)


def test_insufficient_balance_offers_add_money(mworld):
    world = mworld
    world.balance = Decimal("1")
    wa = FakeChannel("wa")
    wa_player(world, ADA, "ada", in_window=True)
    wa_player(world, BOLA, "bola")
    create_challenge(wa, world)
    assert "Not enough USDC" in wa.last_text(ADA)
    assert labels(wa, ADA) == ["Add money", "Menu"]
    assert not world.sb.challenges()


def test_challenge_by_phone_number(mworld):
    world = mworld
    wa = FakeChannel("wa")
    wa_player(world, ADA, "ada", in_window=True)
    bola = wa_player(world, BOLA, "bola")
    ch = create_challenge(wa, world, opponent="+234 803 333 4444")
    assert ch["target_id"] == bola["id"]
    create_unknown = FakeChannel("wa")
    run(create_unknown.text(ADA, "cancel"))


def test_geo_blocked_number_cannot_stake_accept_or_lock(mworld):
    world = mworld
    wa = FakeChannel("wa")
    gb = "447700900123"
    wa_player(world, gb, "londoner")
    wa_player(world, ADA, "ada", in_window=True)
    run(wa.text(gb, "challenge"))
    assert "not available for your region" in wa.last_text(gb)
    ch = create_challenge(wa, world, opponent="link")
    from gaming.src.backend.services.match_codes import derived_code

    run(wa.text(gb, f"JOIN {derived_code(ch['id'])}"))
    run(wa.tap(gb, "Accept"))
    assert "not available for your region" in wa.last_text(gb)
    assert world.sb.challenge(ch["id"])["status"] == "open"
    run(wa.tap_id(gb, ids.encode("match", "lock", ch["id"])))
    assert not world.escrow


def test_watch_and_bet_links_out_never_bets_in_chat(mworld):
    world = mworld
    wa = FakeChannel("wa")
    wa_player(world, ADA, "ada", in_window=True)
    out = run(wa.text(ADA, "bet"))
    assert len(out) == 1 and out[0]["interactive"]["type"] == "cta_url"
    assert wa.links(ADA) == ["https://boardman.test/arena"]
    assert "not in this chat" in wa.last_text(ADA)


def test_menu_and_unknown_input(mworld):
    world = mworld
    wa = FakeChannel("wa")
    wa_player(world, ADA, "ada", in_window=True)
    run(wa.text(ADA, "hi"))
    assert labels(wa, ADA) == ["New challenge", "My matches", "Watch & bet", "Wallet", "Add money",
                               "Withdraw", "Link account"]
    run(wa.text(ADA, "what is this"))
    assert "didn't get that" in wa.all_text(ADA)
    assert labels(wa, ADA)[0] == "New challenge"
    run(wa.text(ADA, "JOIN NOPE1234"))
    assert "no longer open" in wa.last_text(ADA)


def test_every_whatsapp_message_respects_limits(mworld):
    """The fake validated each message on send; check the shapes we rely on."""
    world = mworld
    wa = FakeChannel("wa")
    accepted_match(wa, world)
    for user in (ADA, BOLA):
        for m in wa.messages(user):
            if m["type"] == "interactive":
                it = m["interactive"]
                if it["type"] == "button":
                    assert len(it["action"]["buttons"]) <= 3
                if it["type"] == "list":
                    assert sum(len(s["rows"]) for s in it["action"]["sections"]) <= 10
            assert "<b>" not in text_of(m)


# ── notifications: window, templates, Telegram unchanged ─────────────────────


def test_notify_user_routes_whatsapp_players_and_keeps_telegram(mworld):
    from gaming.src.bot.utils.notify import notify_user
    from gaming.src.channels.core import bridge, match_notices

    world = mworld
    wa_only = wa_player(world, BOLA, "bola")
    tg = tg_player(world, 5001, "tobi")
    assert bridge.preferred_channel(wa_only["id"]) == "whatsapp"
    assert bridge.preferred_channel(tg["id"]) is None

    ch = {"id": "11111111-2222-3333-4444-555555555555", "amount_usdc": 5, "game": "mobile.fc_mobile"}
    # outside the window: the template for the notice kind
    assert run(notify_user(wa_only["id"], "<b>x</b>", notice=match_notices.match_ready(ch)))
    assert world.wa_dv.templates[-1][1]["template"]["name"] == "match_ready"
    # a legacy message with no template is skipped outside the window
    assert not run(notify_user(wa_only["id"], "<b>Hello</b> there"))
    # inside the window: a free-form session message, HTML converted, legacy buttons mapped
    world.repo.update("whatsapp", BOLA, last_inbound_at=world.repo.get("whatsapp", BOLA).opted_in_at)
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(
        text="✅ Accept", callback_data=f"challenge:accept:{ch['id']}")]])
    assert run(notify_user(wa_only["id"], "⚔️ <b>Challenge</b> <code>K7</code>", buttons=kb))
    to, outs = world.wa_dv.session[-1]
    assert to == BOLA and outs[0].body.startswith("⚔️ *Challenge* `K7`")
    assert [(o.id, o.label) for o in outs[0].options] == [(ids.encode("match", "accept", ch["id"]), "Accept")]
    # Telegram players: exactly the legacy DM
    assert run(notify_user(tg["id"], "<b>hi</b>", buttons=kb, notice=match_notices.match_ready(ch)))
    kw = world.bot.send_message.call_args.kwargs
    assert kw["chat_id"] == 5001 and kw["text"] == "<b>hi</b>" and kw["reply_markup"] is kb


def test_whatsapp_off_means_telegram_only(mworld, monkeypatch):
    from gaming.src.channels.core import bridge

    monkeypatch.setenv("WHATSAPP_ENABLED", "0")
    wa_only = wa_player(mworld, BOLA, "bola")
    assert bridge.preferred_channel(wa_only["id"]) is None


def test_linked_player_prefers_whatsapp_only_by_priority(mworld):
    from gaming.src.channels.core import bridge
    from gaming.src.channels.core.identity.repo import Identity, utcnow

    world = mworld
    tg = tg_player(world, 5002, "both")
    world.repo.upsert(Identity("whatsapp", BOLA, tg["id"], address=BOLA, opted_in_at=utcnow()))
    assert bridge.preferred_channel(tg["id"]) is None
    world.repo.update("whatsapp", BOLA, notify_priority=10)
    assert bridge.preferred_channel(tg["id"]) == "whatsapp"


def test_expiry_jobs_notify_whatsapp_players_with_templates(mworld):
    from gaming.src.bot.jobs.expiry import nudge_and_timeout_reports, sweep_stale_creator_locks

    world = mworld
    wa = FakeChannel("wa")
    ada, bola, ch = accepted_match(wa, world)
    row = world.sb.challenge(ch["id"])
    row.update(status="creator_locked", creator_lock_tx_id="tx-c", expires_at="2000-01-01T00:00:00+00:00")
    world.wa_dv.templates.clear()
    world.repo.update("whatsapp", ADA, last_inbound_at=None)
    assert run(sweep_stale_creator_locks()) == 1
    names = [m["template"]["name"] for _, m in world.wa_dv.templates]
    assert "match_refunded" in names

    # report nudge: bola reported an hour ago (past the 30 min nudge, before the
    # 6 h no-show), ada is silent and outside the window → the template
    from datetime import datetime, timedelta, timezone

    hour_ago = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    ch2 = {"id": "22222222-2222-3333-4444-555555555555", "issuer_id": ada["id"], "target_id": bola["id"],
           "stake_amount": 5, "game_type": "mobile.fc_mobile", "status": "playing", "theme": "private",
           "opponent_score": 1, "opponent_reported_home": 2, "opponent_reported_away": 1,
           "screenshot_opponent_url": "evidence://local/x.png",
           "created_at": hour_ago, "updated_at": hour_ago}
    world.sb.tables["challenges"].append(ch2)
    world.wa_dv.templates.clear()
    run(nudge_and_timeout_reports())
    sent = [(to, m["template"]["name"]) for to, m in world.wa_dv.templates]
    assert sent == [(ADA, "report_reminder")]
    payload = world.wa_dv.templates[0][1]["template"]["components"][-1]["parameters"][0]["payload"]
    assert payload == ids.encode("report", "start", ch2["id"])


# ── Telegram: core flows on the Telegram renderer, and the legacy handlers ───


def test_core_challenge_flow_on_telegram_renderer(mworld):
    world = mworld
    tg = FakeChannel("tg")
    tg_player(world, 5001, "tobi")
    bola = tg_player(world, 5002, "bola")
    run(tg.text("5001", "challenge"))
    run(tg.tap("5001", "Mobile"))
    # Telegram has no list primitive: more than 12 games degrade to numbered text
    assert "Reply with a number (1-" in tg.last_text("5001")
    from gaming.src.backend.services.game_catalog import list_games

    pos = [g["game_id"] for g in list_games(category="mobile")].index("mobile.fc_mobile") + 1
    run(tg.text("5001", str(pos)))
    run(tg.tap("5001", "$10"))
    run(tg.text("5001", "@bola"))
    run(tg.tap("5001", "Send it"))
    ch = world.sb.challenges()[-1]
    assert ch["target_id"] == bola["id"] and ch["stake_amount"] == 10.0
    assert "<b>@bola</b>" in tg.last_text("5001")
    # the Telegram opponent gets the legacy DM with legacy Accept/Decline callbacks
    kw = world.bot.send_message.call_args.kwargs
    assert kw["chat_id"] == 5002 and "Challenge from @tobi" in kw["text"]
    cbs = [b.callback_data for row in kw["reply_markup"].inline_keyboard for b in row]
    assert f"challenge:accept:{ch['id']}" in cbs


def test_telegram_all_flag_never_takes_over_match_handlers(monkeypatch):
    from gaming.src.channels import config

    monkeypatch.delenv("CHANNELS_CORE_FLOWS_TELEGRAM", raising=False)
    monkeypatch.setenv("CHANNELS_CORE_FLOWS", "all")
    assert "challenge" not in config.enabled_flows("telegram")
    assert {"challenge", "match", "report", "watch"} <= config.enabled_flows("whatsapp")
    monkeypatch.setenv("CHANNELS_CORE_FLOWS_TELEGRAM", "all,match")
    assert "match" in config.enabled_flows("telegram") and "challenge" not in config.enabled_flows("telegram")


def _cb(data: str, user_id: int):
    from unittest.mock import AsyncMock, MagicMock

    cb = MagicMock()
    cb.data = data
    cb.from_user = MagicMock(id=user_id, username=f"u{user_id}", first_name="T", last_name=None)
    cb.answer = AsyncMock()
    cb.message = MagicMock()
    cb.message.answer = AsyncMock()
    cb.message.chat = MagicMock(id=user_id)
    cb.bot = AsyncMock()
    return cb


def test_legacy_telegram_lock_uses_the_shared_service(mworld, monkeypatch):
    """Telegram's Lock button: same escrow call, same wording, and a WhatsApp
    opponent now gets a nudge (Telegram opponents still don't)."""
    from gaming.src.bot.handlers import simple_ui

    world = mworld
    tobi = tg_player(world, 5001, "tobi")
    bola = wa_player(world, BOLA, "bola")

    async def profile(user):
        return tobi

    monkeypatch.setattr(simple_ui, "get_or_create_profile", profile)
    from gaming.src.channels.core.actions.matches import insert_challenge

    ch = insert_challenge(creator_id=tobi["id"], opponent_id=bola["id"], amount=Decimal("5"),
                          game="mobile.fc_mobile", visibility="private")
    world.sb.challenge(ch["id"]).update(status="accepted")
    cb = _cb(f"ui:lock:{ch['id']}", 5001)
    run(simple_ui.ui_lock(cb))
    texts = [c.args[0] for c in cb.message.answer.call_args_list]
    assert texts[0] == "⏳ Locking <b>$5.00</b> USDC…"
    assert texts[1].startswith("✅ Stake locked (you).\nWaiting for opponent.")
    assert world.escrow[-1][:3] == ("create", tobi["id"], ch["id"])
    to, msg = world.wa_dv.templates[-1]
    assert to == BOLA and msg["template"]["name"] == "stake_locked"

    # double tap inside the idempotency window: refused, no second escrow call
    world.sb.challenge(ch["id"]).update(status="accepted")
    cb2 = _cb(f"ui:lock:{ch['id']}", 5001)
    run(simple_ui.ui_lock(cb2))
    assert "already in progress" in cb2.message.answer.call_args.args[0]
    assert [e[0] for e in world.escrow] == ["create"]


def test_legacy_telegram_report_finalize_uses_the_shared_service(mworld, monkeypatch):
    from unittest.mock import AsyncMock

    from gaming.src.bot.handlers import simple_ui

    world = mworld
    tobi = tg_player(world, 5001, "tobi")
    bola = tg_player(world, 5002, "bola")

    async def profile(user):
        return tobi

    monkeypatch.setattr(simple_ui, "get_or_create_profile", profile)
    from gaming.src.channels.core.actions.matches import insert_challenge

    ch = insert_challenge(creator_id=tobi["id"], opponent_id=bola["id"], amount=Decimal("5"),
                          game="mobile.fc_mobile", visibility="private")
    world.sb.challenge(ch["id"]).update(status="locked", creator_side="home", opponent_side="away")
    state = AsyncMock()
    state.get_data = AsyncMock(return_value={"file_id": "AgACtelegramfileid", "home": 3, "away": 1,
                                             "binary_won": None, "screen_name": ""})
    cb = _cb(f"ui:reportask:go:{ch['id']}", 5001)
    run(simple_ui.ui_report_finalize(cb, state))
    row = world.sb.challenge(ch["id"])
    assert row["screenshot_creator_url"] == "AgACtelegramfileid"
    assert (row["creator_reported_home"], row["creator_reported_away"], row["status"]) == (3, 1, "playing")
    assert "Report submitted for fair ruling" in cb.message.answer.call_args_list[-1].args[0]
    sent = [c.kwargs["text"] for c in world.bot.send_message.call_args_list]
    assert any("Opponent reported" in t for t in sent)
