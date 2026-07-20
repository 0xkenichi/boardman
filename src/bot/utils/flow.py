"""Simple player-facing flow copy for Rematch (button-first)."""
from __future__ import annotations

from typing import Any, Optional


def how_to_play() -> str:
    return (
        "🎮 <b>Rematch — how to play</b> (testnet)\n\n"
        "Buttons only. No long IDs needed.\n\n"
        "<b>1. Pick Arc (recommended)</b>\n"
        "Switch network → <b>Arc Testnet</b> — gas in USDC, best PLAY points.\n"
        "Wallet → copy address → send <b>testnet USDC</b> on that network.\n\n"
        "<b>2. Challenge a friend</b>\n"
        "New challenge → their @tag → stake → game → network → Send.\n"
        "They Accept in Telegram.\n\n"
        "<b>3. Both lock</b>\n"
        "My match → Lock my stake (you first if you challenged).\n\n"
        "<b>4. HOME / AWAY → play console → Submit FT photo</b>\n"
        "Caption like <code>5-3</code>. AI reads the score. Winner paid in USDC.\n\n"
        "<b>Testnet mission</b>\n"
        "We need real matches + volume on testnets (esp. <b>Arc</b>) for grants & mainnet.\n"
        "PLAY points: <b>Arc 1.5×</b> · Avalanche 1.25× · Base 1.0×\n"
        "New rivals / new Telegram users → higher mult than endless rematches.\n"
        "Multi-chain players (all three) get noted for seasons.\n\n"
        "<b>Rules</b>\n"
        "• One match at a time\n"
        "• Ghosting = −PLAY (no reward)\n"
        "• Test tokens only — see /playbook disclaimer"
    )


def short_help() -> str:
    return (
        "📋 <b>Rematch</b> · sideQuest\n\n"
        "🎮 My match · ⚔️ New challenge · 💰 Wallet · 🌐 Network · 👤 Profile\n\n"
        "Prefer <b>Arc</b> for max PLAY. Bring new players for higher mults.\n"
        "/howto · /playbook · /balance · /support_id"
    )


def testnet_push_banner() -> str:
    return (
        "🧪 <b>Testnet season</b>\n"
        "Play real locks on <b>Arc</b> (best), Avalanche, Base.\n"
        "Settled volume helps us qualify for chain grants & mainnet.\n"
        "PLAY points ≠ money — see /playbook."
    )


def report_status(challenge: dict) -> str:
    """Human summary of who reported what."""
    from gaming.src.backend.services.match_codes import display_code, ensure_public_code

    try:
        match_code = ensure_public_code(challenge)
    except Exception:
        match_code = display_code(challenge)
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
        f"Code: <code>{match_code}</code>",
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
        lines.append(
            f"If support asks to confirm: "
            f"<code>/support_id {match_code}</code>"
        )
    elif status == "resolved":
        lines.append("Done. Check Wallet for USDC + PLAY. Rematch?")
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
    from gaming.src.backend.services.match_codes import display_code

    match_code = display_code(None, challenge_id=challenge_id)
    return (
        f"⚠️ <b>Reports don't match</b>\n"
        f"Match: <code>{match_code}</code>\n"
        f"{reason}\n\n"
        f"Match disputed. Send clearer FT photos via <b>Submit result</b>.\n"
        f"If support asks to confirm: <code>/support_id {match_code}</code>"
    )
