"""Creative, non-repetitive win/loss banter for Rematch settle messages.

No LLM required — large template pool + anti-repeat + score-aware lines.
"""
from __future__ import annotations

import random
import re
from collections import deque
from typing import Deque, Optional, Sequence

# Avoid repeating the same line across recent settles in this process.
_RECENT: Deque[str] = deque(maxlen=48)
_RNG = random.SystemRandom()


def _pick(pool: Sequence[str], *, salt: str = "") -> str:
    """Pick a line not in recent history when possible."""
    if not pool:
        return ""
    candidates = [p for p in pool if p not in _RECENT]
    if not candidates:
        candidates = list(pool)
    # light salt bias so same match_id tends not to collide both sides with identical vibe
    if salt and len(candidates) > 1:
        idx = (sum(ord(c) for c in salt) + _RNG.randint(0, 7)) % len(candidates)
        choice = candidates[idx]
    else:
        choice = _RNG.choice(candidates)
    _RECENT.append(choice)
    return choice


def _margin(home: Optional[int], away: Optional[int]) -> Optional[int]:
    if home is None or away is None:
        return None
    return abs(int(home) - int(away))


def _score_str(home: Optional[int], away: Optional[int]) -> str:
    if home is None or away is None:
        return ""
    return f"{int(home)}-{int(away)}"


def _parse_scoreline(scoreline: Optional[str]) -> tuple[Optional[int], Optional[int]]:
    if not scoreline:
        return None, None
    m = re.search(r"(\d+)\s*[-:]\s*(\d+)", str(scoreline))
    if not m:
        return None, None
    return int(m.group(1)), int(m.group(2))


# ── Winner lines ────────────────────────────────────────────────────────────

_WIN_GENERIC = [
    "Nice game — you really showed them who the boss is.",
    "Clean. Clinical. Cash. That's how you do it.",
    "You cooked. The pot agrees.",
    "Main character energy. Wallet's smiling.",
    "That wasn't a match, that was a statement.",
    "You didn't just win — you made it look easy.",
    "Boss mode activated. Rematch if they dare.",
    "Ice in the veins. Money in the wallet.",
    "That's how legends move. Take the bag.",
    "You turned up. They turned off.",
    "Respect. That was pure skill, not luck.",
    "Highlight reel material. Get paid.",
    "You walked in quiet, left loud.",
    "Unbothered. Undefeated (this one). Unstoppable.",
    "They brought ambition. You brought the L.",
    "W registered. Ego optional — flex allowed.",
    "You made the controller look expensive.",
    "That's a W with seasoning.",
    "They blinked. You banked.",
    "Skill issue… for them. For you? Payday.",
]

_WIN_BLOWOUT = [  # margin >= 3
    "Can't believe the scoreline — that was a demolition.",
    "You didn't beat them, you archived them.",
    "That score should come with a warning label.",
    "Absolute masterclass. They need a recovery arc.",
    "You pressed delete on their pride.",
    "That wasn't close. That was a public service announcement.",
    "They'll feel that one in the group chat.",
    "Blowout energy. Keep the receipts.",
    "You cooked so hard the smoke alarm went off.",
    "Mercy was optional. You chose violence (in-game).",
]

_WIN_CLOSE = [  # margin == 1
    "Heart-stopper. One goal, one bag, all nerves.",
    "That was chess with sweat. You edged it.",
    "Too close for comfort — perfect for legends.",
    "Clutch gene activated. Barely… but cleanly.",
    "One slip either way. You didn't slip.",
    "Photo finish. Wallet still knows who won.",
    "Nails bitten, stake secured. Beautiful.",
    "That margin is thinner than their excuses.",
]

_WIN_DRAW_AVOIDED = []  # unused; draws have own pool


# ── Loser lines ─────────────────────────────────────────────────────────────

_LOSS_GENERIC = [
    "Can't believe you took that L — where did the ego go?",
    "Tough one. Next time you better win… or at least look cooler losing.",
    "They got you. Chin up, wallet down, rematch ready.",
    "Ouch. That one stings. Channel it into the rematch.",
    "Not your night. Make the next one personal.",
    "You got cooked. Kitchen's still open for round two.",
    "Lesson paid for in USDC. Study the tape.",
    "They took the bag. Steal the next one.",
    "Respect the W they earned — then erase it.",
    "Loss logged. Pride optional. Rematch mandatory.",
    "You blinked. They banked. Fix the blink.",
    "Even bosses drop games. Don't drop the rematch.",
    "That wasn't the plan. Rewrite the plan.",
    "GG… but not really. Go get your money back.",
    "They had your number. Change the number.",
    "Skill issue (temporary). Rematch issue (permanent).",
    "Walk it off. Then run it back.",
    "The controller didn't fail you. The decisions did.",
    "Pain is temporary. That scoreline is a screenshot forever.",
    "You donated. Next time charge rent.",
]

_LOSS_BLOWOUT = [
    "Can't believe you got beaten that bad — that's a lot. Ego check, please.",
    "That scoreline is disrespectful. Make them pay interest next time.",
    "They didn't just win — they held a seminar. Attend the rematch.",
    "Yikes. That was a full send… into the wall.",
    "Where's the ego after that score? In witness protection?",
    "You got turbo-smoked. Rematch is the only redemption arc.",
    "That wasn't a loss, that was a documentary.",
    "They cooked you medium-well. Next time bring oven mitts.",
    "Scoreline said schooling. Pride said leave the chat",
    "Big L energy. Bigger rematch energy required.",
]

_LOSS_CLOSE = [
    "So close it hurts. One moment decided the bag.",
    "Heartbreak special. You were one play away.",
    "Almost. Almost doesn't pay — rematch does.",
    "Thin margin, thick pain. Run it back.",
    "You had it… until you didn't. Classic.",
    "One goal from glory. Don't let that be the story.",
    "Agony. Beautiful, expensive agony.",
    "Closest L of the week. Make the next W closer to free money.",
]

_DRAW = [
    "Draw. Nobody flexed, nobody cried — stakes back, pride intact.",
    "Stalemate. The universe said 'touch grass, then rematch.'",
    "Even Steven. The pot shrugged and went home.",
    "Draw. Rematch is where the plot thickens.",
    "Split decision. Split nothing — refunds only. Run it back for blood.",
    "1-1 energy even if it wasn't. Rematch will settle the argument.",
]


def zinger_for_result(
    *,
    won: Optional[bool],
    home: Optional[int] = None,
    away: Optional[int] = None,
    scoreline: Optional[str] = None,
    match_code: str = "",
    rival_tag: str = "",
) -> str:
    """Return one HTML-safe zinger line (no HTML tags needed).

    won=True winner, False loser, None draw.
    """
    if home is None and away is None and scoreline:
        home, away = _parse_scoreline(scoreline)

    margin = _margin(home, away)
    score = _score_str(home, away)
    salt = f"{match_code}:{won}:{score}:{rival_tag}"

    if won is None:
        line = _pick(_DRAW, salt=salt)
        if score:
            line = f"{line} Final: {score}."
        return line

    if won:
        if margin is not None and margin >= 3:
            pool = _WIN_BLOWOUT + _WIN_GENERIC
        elif margin == 1:
            pool = _WIN_CLOSE + _WIN_GENERIC
        else:
            pool = _WIN_GENERIC
        line = _pick(pool, salt=salt)
        if score:
            extras = [
                f" Final {score} — frame it.",
                f" Scoreboard said {score}.",
                f" {score} and the money moved.",
                f" They'll remember {score}.",
            ]
            if margin is not None and margin >= 3:
                extras.append(f" A {score} thrashing. Unserious from them.")
            if _RNG.random() < 0.75:
                line = line.rstrip(".") + "." + _pick(extras, salt=salt + "x")
        if rival_tag and _RNG.random() < 0.35:
            line += f" Tell @{rival_tag} you said hey… from the winner's circle."
        return line

    # lost
    if margin is not None and margin >= 3:
        pool = _LOSS_BLOWOUT + _LOSS_GENERIC
    elif margin == 1:
        pool = _LOSS_CLOSE + _LOSS_GENERIC
    else:
        pool = _LOSS_GENERIC
    line = _pick(pool, salt=salt)
    if score:
        extras = [
            f" Can't believe it ended {score}.",
            f" {score} is a lot to sit with.",
            f" Scoreline {score} — ego in shambles.",
            f" They hit you with a {score}.",
        ]
        if margin is not None and margin >= 3:
            extras.append(f" {score}?! Where's the ego?")
        if _RNG.random() < 0.8:
            line = line.rstrip(".") + "." + _pick(extras, salt=salt + "y")
    if rival_tag and _RNG.random() < 0.3:
        line += f" @{rival_tag} is eating good tonight — flip that next game."
    return line


def format_result_banner(
    *,
    won: Optional[bool],
    match_code: str,
    pot_usdc: Optional[float] = None,
    scoreline: Optional[str] = None,
    home: Optional[int] = None,
    away: Optional[int] = None,
    rival_tag: str = "",
) -> str:
    """Full HTML block: headline + zinger (for settle DMs)."""
    z = zinger_for_result(
        won=won,
        home=home,
        away=away,
        scoreline=scoreline,
        match_code=match_code,
        rival_tag=rival_tag,
    )
    # Escape not needed if we never inject user HTML; tags are ours
    if won is True:
        money = f"\nPayout: <b>${pot_usdc:,.2f}</b>" if pot_usdc is not None else ""
        return (
            f"🏆 <b>You won</b> · match <code>{match_code}</code>{money}\n\n"
            f"<i>{z}</i>"
        )
    if won is False:
        money = (
            f"\nWinner took <b>${pot_usdc:,.2f}</b> (after fee)"
            if pot_usdc is not None
            else ""
        )
        return (
            f"😤 <b>You lost</b> · match <code>{match_code}</code>{money}\n\n"
            f"<i>{z}</i>"
        )
    return (
        f"🤝 <b>Draw</b> · match <code>{match_code}</code>\n"
        f"Stakes refunded.\n\n"
        f"<i>{z}</i>"
    )
