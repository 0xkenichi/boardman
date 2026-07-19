# ClawStation simple UX (button-first)

Designed so non-web3 / low-literacy users never type long IDs.

## Main menu buttons

| Button | Action |
|--------|--------|
| **My match** | Open active match + actions |
| **New challenge** | Wizard: @tag → $ stake → game → network → Send |
| **Wallet** | USDC + $PLAY + tier |
| **Profile** | Tag, streak, W/L |
| **How to play** | Full guide |
| **$PLAY playbook** | Points & tiers |

## Match action buttons

| Status | Buttons |
|--------|---------|
| Accepted / waiting lock | **Lock my stake** |
| Locked / playing | **I am HOME** / **I am AWAY**, **Submit result** |
| Submitted | **Check settlement**, **Match status** |

## Submit result (no ID)

1. Tap **Submit result**
2. Send FT **photo**
3. Caption only: `5-3` (home–away)

Also works: `H-A 5-3`

## Docs index

| Doc | Content |
|-----|---------|
| `SIMPLE_UX.md` | This file |
| `PLAYBOOK.md` | $PLAY, streaks, tiers, no-show penalty |
| `REPORTING_EDGE_CASES.md` | One-sided, conflict, no-show settle |
| `OUTCOME_VERIFICATION.md` | AI + sides + proof |
| `/howto` in bot | Same as How to play button |

## Advanced (still work)

`/challenge`, `/lock_stake`, `/set_side`, `/submit_score ID 5-3` for power users.
