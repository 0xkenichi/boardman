"""Simple player-facing flow copy for Rematch (button-first)."""
from __future__ import annotations

from typing import Any, Optional

# Public faucet — Arc USDC only (keep in one place)
ARC_FAUCET_URL = "https://faucet.circle.com/"
ARC_FAUCET_HINT = "Circle Faucet → Arc Testnet → USDC"


def how_to_play() -> str:
    return (
        "🎮 <b>How to play Rematch</b>\n\n"
        "<b>1. Get money</b>\n"
        "Wallet → <b>Get money</b> → fund the address shown.\n"
        "Balance = what you can stake (not old account credits).\n\n"
        "<b>2. Challenge a friend</b>\n"
        "Challenge → their @tag → stake → game → Send.\n"
        "They Accept in Telegram.\n\n"
        "<b>3. Both lock</b>\n"
        "My match → Lock my stake.\n\n"
        "<b>4. Play &amp; settle</b>\n"
        "HOME or AWAY (if needed) → play → <b>Submit result</b>\n"
        "The bot tells you <b>exactly what photo + caption</b> for that game:\n"
        "• Score games: <code>5-3</code> · Win/lose games: <code>W</code> / <code>L</code>\n"
        "Winner gets paid.\n\n"
        "<b>Rules</b>\n"
        "• One match at a time\n"
        "• Fair play — no ghosting\n"
        "• Skill matches with proof"
    )


def short_help() -> str:
    return (
        "📋 <b>Rematch</b> · sideQuest\n\n"
        "🎮 My match · ⚔️ Challenge · 💰 Wallet · 👤 Profile\n\n"
        "/howto · /balance · /support_id"
    )


def rules_short() -> str:
    return (
        "📜 <b>Rules</b>\n\n"
        "• Skill match with proof — play fair\n"
        "• One match at a time\n"
        "• Cancel free before both lock; after lock both must agree\n"
        "• Dispute: /dispute CODE\n"
        "• Support: /support_id CODE\n"
        "• Only stake what you can afford to lose"
    )


def play_points_short() -> str:
    return (
        "🎮 <b>PLAY points</b>\n\n"
        "Score for competing on Rematch.\n"
        "• Win <b>+100</b> · Loss <b>+40</b> · Draw <b>+50</b>\n"
        "• No-show <b>−50</b>\n"
        "• New rivals earn more than endless rematches\n"
        "• Tiers: Bronze → Diamond\n\n"
        "PLAY is a score — not cash."
    )


def get_usdc_copy(address: str) -> str:
    addr = address or "—"
    return (
        "💧 <b>Get money</b>\n\n"
        f"Your address (tap to copy):\n<code>{addr}</code>\n\n"
        "1. Tap <b>Fund page</b> or open the faucet\n"
        "2. Choose <b>Arc Testnet</b> → <b>USDC</b>\n"
        "3. Paste address → request\n"
        "4. Wallet → Refresh\n\n"
        "Gas on Arc is paid in USDC — nothing else to fund."
    )


def report_status(challenge: dict) -> str:
    """Human summary of who reported what + game-aware next step."""
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
    game_id = str(challenge.get("game") or challenge.get("game_type") or "")

    def _mark(ok: bool) -> str:
        return "✅" if ok else "⏳"

    creator_rep = _mark(c_score is not None or c_line is not None)
    opp_rep = _mark(o_score is not None or o_line is not None)
    creator_ph = _mark(c_shot)
    opp_ph = _mark(o_shot)

    stake = challenge.get("amount_usdc") or challenge.get("stake_amount") or "?"
    chain = challenge.get("settlement_chain") or "arc"
    chain_label = "Arc" if str(chain).lower() in ("arc", "arc-testnet") else str(chain)

    game_label = game_id or "—"
    try:
        from gaming.src.backend.services.game_catalog import display_name, is_binary_outcome

        if game_id:
            game_label = display_name(game_id)
            binary = is_binary_outcome(game_id)
        else:
            binary = False
    except Exception:
        binary = False

    lines = [
        f"⚔️ <b>Your match</b>",
        f"Code: <code>{match_code}</code>",
        f"Game: <b>{game_label}</b>",
        f"Status: <b>{status}</b> · Stake ${stake} · {chain_label}",
        f"Sides: creator=<b>{cs}</b> · opponent=<b>{os_}</b>",
    ]
    # Clubs only matter for scoreline / football-style
    if not binary and (ht not in ("?", "") or at not in ("?", "")):
        lines.append(f"Clubs: <b>{ht}</b> (H) vs <b>{at}</b> (A)")
    lines += [
        "",
        f"Creator report {creator_rep}  photo {creator_ph}",
        f"Opponent report {opp_rep}  photo {opp_ph}",
        f"AI: <b>{ai}</b>" + (f" ({float(conf):.0%})" if conf is not None else ""),
        "",
        "<b>What to do next</b>",
    ]

    if status in ("open",):
        lines.append("Waiting for the other player to accept.")
    elif status in ("accepted", "creator_locked"):
        lines.append("Tap <b>Lock my stake</b> (challenger locks first, then you).")
    elif status in ("locked", "playing"):
        if not binary and (cs == "?" or os_ == "?"):
            lines.append("Tap <b>I am HOME</b> or <b>I am AWAY</b> before you play.")
        try:
            from gaming.src.backend.services.game_catalog import how_to_report_short

            lines.append("")
            lines.append(how_to_report_short(game_id))
        except Exception:
            lines.append(
                "Play, then <b>Submit result</b> with a photo "
                "(caption <code>W</code>/<code>L</code> or <code>5-3</code> by game)."
            )
        if (c_score is not None or c_line is not None) and not (
            o_score is not None or o_line is not None
        ):
            lines.append("")
            lines.append("⏳ Your report is in — waiting on opponent.")
        if (o_score is not None or o_line is not None) and not (
            c_score is not None or c_line is not None
        ):
            lines.append("")
            lines.append("⏳ Opponent reported — your turn to submit.")
    elif status == "submitted":
        lines.append("Both reported — payout runs if results agree.")
    elif status == "disputed":
        lines.append("Disputed — support will review.")
        lines.append(f"If asked: <code>/support_id {match_code}</code>")
    elif status == "resolved":
        lines.append("Done. Check Wallet. Rematch?")
    elif status in ("cancelled", "expired", "declined"):
        lines.append("Match closed.")

    return "\n".join(lines)


def next_steps_after_lock(challenge_id: str, game_id: str = "") -> str:
    """After both locks — kind, game-aware playbook."""
    head = "🔒 <b>Both stakes locked — time to play</b>\n\n"
    try:
        from gaming.src.backend.services.game_catalog import (
            how_to_report_short,
            is_binary_outcome,
        )

        if game_id:
            side_line = (
                ""
                if is_binary_outcome(game_id)
                else "1. Tap <b>I am HOME</b> or <b>I am AWAY</b> (if you haven't)\n"
            )
            n = 2 if side_line else 1
            play = f"{n}. Play the match\n"
            rep = f"{n + 1}. Then follow this for your game:\n\n"
            return head + side_line + play + rep + how_to_report_short(game_id)
    except Exception:
        pass
    return (
        head
        + "1. Tap <b>My match</b>\n"
        + "2. Choose HOME or AWAY if needed\n"
        + "3. Play\n"
        + "4. <b>Submit result</b> — the bot will tell you the caption for this game"
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
        f"If support asks: <code>/support_id {match_code}</code>"
    )
