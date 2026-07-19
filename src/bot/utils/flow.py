"""Simple player-facing flow copy for ClawStation (button-first)."""
from __future__ import annotations

from typing import Any, Optional


def how_to_play() -> str:
    return (
        "🎮 <b>How to play</b> (easy mode)\n\n"
        "You mostly use <b>buttons</b>. No need to copy long IDs.\n\n"
        "<b>1. Network + fund</b>\n"
        "Tap <b>Switch network</b> → pick <b>Arc Testnet</b> (USDC gas, no test ETH).\n"
        "Open Wallet → send USDC on that network to your address "
        "(same address on Base / Arc / Avalanche — balances are separate).\n\n"
        "<b>2. Challenge</b>\n"
        "Tap <b>New challenge</b> → @tag → stake → game → network (Arc recommended) → Send.\n"
        "They tap <b>Accept</b>.\n\n"
        "<b>3. Lock money</b>\n"
        "Tap <b>My match</b> → <b>Lock my stake</b> (challenger first, then you).\n\n"
        "<b>4. Pick side</b>\n"
        "Tap <b>I am HOME</b> or <b>I am AWAY</b>.\n\n"
        "<b>5. Play</b> on console.\n\n"
        "<b>6. Report</b>\n"
        "Tap <b>Submit result</b> → send FT <b>photo</b> with caption like:\n"
        "<code>5-3</code>  (home goals – away goals)\n\n"
        "When both report the same score, the winner is paid automatically.\n\n"
        "<b>$PLAY points</b>\n"
        "Win +100 (streak bonus) · Loss +40 · No-show −50\n"
        "Tier = Bronze→Diamond from total $PLAY\n"
        "Tap <b>$PLAY playbook</b> for details.\n\n"
        "<b>Rules</b>\n"
        "• One match at a time\n"
        "• Loser who never reports can lose by no-show if you sent a photo\n"
        "• Ghosting costs $PLAY (not rewarded)"
    )


def short_help() -> str:
    return (
        "📋 <b>Simple mode</b>\n\n"
        "Use the buttons on the main menu:\n"
        "🎮 My match · ⚔️ New challenge · 💰 Wallet · 👤 Profile\n\n"
        "Advanced commands still work if you want them:\n"
        "/challenge /lock_stake /set_side /submit_score /match_info\n"
        "/playbook /balance /profile /howto /withdraw /safety\n"
    )


def report_status(challenge: dict) -> str:
    """Human summary of who reported what."""
    cid = challenge.get("id", "?")
    status = challenge.get("status", "?")
    c_score = challenge.get("creator_score")
    o_score = challenge.get("opponent_score")
    c_line = challenge.get("creator_reported_home")
    o_line = challenge.get("opponent_reported_home")
    c_shot = bool(challenge.get("screenshot_creator_url"))
    o_shot = bool(challenge.get("screenshot_opponent_url"))
    cs = challenge.get("creator_side") or "?"
    os_ = challenge.get("opponent_side") or "?"
    ht = challenge.get("home_team") or "?"
    at = challenge.get("away_team") or "?"
    ai = challenge.get("ai_verified_score") or "—"
    conf = challenge.get("ai_confidence")

    def _mark(ok: bool) -> str:
        return "✅" if ok else "⏳"

    creator_rep = _mark(c_score is not None or c_line is not None)
    opp_rep = _mark(o_score is not None or o_line is not None)
    creator_ph = _mark(c_shot)
    opp_ph = _mark(o_shot)

    stake = challenge.get("amount_usdc") or challenge.get("stake_amount") or "?"
    chain = challenge.get("settlement_chain") or "base"

    lines = [
        f"⚔️ <b>Your match</b>",
        f"Status: <b>{status}</b> · Stake ${stake} · {chain}",
        f"Sides: creator=<b>{cs}</b> · opponent=<b>{os_}</b>",
        f"Clubs: <b>{ht}</b> (H) vs <b>{at}</b> (A)",
        "",
        f"Creator report {creator_rep}  photo {creator_ph}",
        f"Opponent report {opp_rep}  photo {opp_ph}",
        f"AI: <b>{ai}</b>" + (f" ({float(conf):.0%})" if conf is not None else ""),
        "",
        "<b>What to do</b>",
    ]

    if status in ("open",):
        lines.append("Waiting for accept.")
    elif status in ("accepted", "creator_locked"):
        lines.append("Tap <b>Lock my stake</b> (challenger first).")
    elif status in ("locked", "playing"):
        if cs == "?" or os_ == "?":
            lines.append("Tap <b>I am HOME</b> or <b>I am AWAY</b>.")
        lines.append("Play, then <b>Submit result</b> + photo caption <code>5-3</code>.")
        if (c_score is not None or c_line is not None) and not (
            o_score is not None or o_line is not None
        ):
            lines.append("⏳ Waiting on opponent.")
        if (o_score is not None or o_line is not None) and not (
            c_score is not None or c_line is not None
        ):
            lines.append("⏳ Waiting on creator.")
    elif status == "submitted":
        lines.append("Both reported — payout should run if scores match.")
    elif status == "disputed":
        lines.append("Disputed — admin will review.")
    elif status == "resolved":
        lines.append("Done. Check Wallet for USDC + $PLAY.")
    elif status in ("cancelled", "expired", "declined"):
        lines.append("Match closed.")

    return "\n".join(lines)


def next_steps_after_lock(challenge_id: str) -> str:
    return (
        f"🎮 <b>Both stakes locked</b>\n\n"
        f"1. Tap <b>My match</b>\n"
        f"2. Choose HOME or AWAY\n"
        f"3. Play\n"
        f"4. <b>Submit result</b> → photo caption <code>5-3</code>"
    )


def waiting_on_opponent(challenge_id: str, who: str = "opponent") -> str:
    return (
        f"⏳ Your report is in.\n"
        f"Waiting on the {who}.\n"
        f"If they stay silent after a photo proof, you can still win by no-show."
    )


def conflict_message(challenge_id: str, reason: str) -> str:
    return (
        f"⚠️ <b>Reports don't match</b>\n"
        f"{reason}\n\n"
        f"Match disputed. Send clearer FT photos via <b>Submit result</b>."
    )
