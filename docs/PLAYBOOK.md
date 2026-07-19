# ClawStation $PLAY Playbook

**$PLAY** is ClawStation’s participation score.  
It is **not USDC**. It tracks how much you play, win, and show up.

### Tier (from $PLAY)

| Tier | $PLAY needed | Meaning |
|------|----------------|---------|
| **Bronze** | 0+ | Just starting |
| **Silver** | 500+ | Regular |
| **Gold** | 2,000+ | Active competitor |
| **Platinum** | 5,000+ | High volume |
| **Diamond** | 10,000+ | Top grind |

Tier is **only** a rank badge from $PLAY — not a separate “reputation” number.  
Later it may unlock fee discounts, cosmetics, or leaderboard perks.

---

## How to earn $PLAY

| Action | Base $PLAY | Notes |
|--------|------------|--------|
| **Win** a resolved match | **+100** | Multiplied by hot streak |
| **Lose** a resolved match | **+40** | You still earn for showing up |
| **Draw** | **+50** each | Both players |
| **No-show** (ghosted / never reported) | **−50** | Hard penalty — **zero rewards** for silence / dodging |
| **Stake size bonus** | up to **+50** | ~5 $PLAY per 1 USDC stake (capped); not on no-show |

### Hot streak multiplier (wins only)

```
multiplier = 1 + 0.15 × (current_win_streak − 1)
capped at streak 10  →  max ~2.5×
```

| Streak | Mult | Win points (base 100) |
|--------|------|------------------------|
| 1 | 1.00× | 100 |
| 2 | 1.15× | 115 |
| 3 | 1.30× | 130 |
| 5 | 1.60× | 160 |
| 10 | 2.50× | 250 |

A **loss or no-show resets** your streak to 0.

---

## Rules that protect the game

1. **One match at a time** — you cannot create or accept a new challenge until your current one is `resolved`, `cancelled`, `expired`, or `declined`.
2. **Report with proof** — FT photo + scoreline protects you if the other player ghosts (no-show payout).
3. **Both players earn $PLAY** — winning pays more; losing still pays so every match matters.
4. **Ledger** — every award is stored in `gaming.play_ledger` for transparency.

---

## Bot (prefer buttons)

| Button / command | Purpose |
|------------------|---------|
| **$PLAY playbook** or `/playbook` | This guide |
| **Profile** or `/profile` | Tag, tier, **$PLAY**, streak, W/L |
| **Wallet** or `/balance` | USDC + $PLAY + tier |
| **My match** | Status + Lock / Side / Submit |
| **How to play** or `/howto` | Full match flow |

See also `SIMPLE_UX.md` for the button-only flow.

---

## Future value (honest note)

$PLAY might later map to:

- Seasonal leaderboards & badges  
- Reduced fees or access tiers  
- Cosmetics / sideQuest perks  
- Governance or airdrop weighting  

No promise of token listing. The point **now** is: **play more, show up, build streak.**

---

## Env knobs (ops)

```
PLAY_POINTS_WIN=100
PLAY_POINTS_LOSS=40
PLAY_POINTS_DRAW=50
PLAY_POINTS_NO_SHOW_PENALTY=-50
PLAY_STREAK_STEP=0.15
PLAY_STREAK_CAP=10
PLAY_STAKE_BONUS_PER_USDC=5
PLAY_STAKE_BONUS_CAP=50
```
