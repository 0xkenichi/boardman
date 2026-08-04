# Proof by game (what the bot expects)

Rematch does **not** assume every game is football. Each catalog entry declares:

| Field | Purpose |
|--------|---------|
| `outcome_type` | `scoreline` (home-away goals/points) or `binary_winner` (win/lose) |
| `result_screen` | Human + AI description of a valid final screen |
| `ai_hints` | Bullet hints for vision (layout, banners, what to ignore) |

Files: `config/games/*.yaml` · loaded by `game_catalog.py`.

## Player captions (always work without AI)

| Type | Caption examples |
|------|------------------|
| Scoreline (FC Mobile, EA FC, NBA…) | `5-3`, `2-1` (home-away) |
| Binary (8 Ball Pool, Free Fire 1v1, GamePigeon…) | `W` / `L` / `I won` / `I lost` |

**My match → Submit result** shows the right instructions for that match’s game.

## AI vision (optional, smarter)

If a vision API key is set (`OPENAI_API_KEY`, `OPENROUTER_API_KEY`, `NIM_API_KEY`, etc.), the bot:

1. Loads catalog context for the challenge’s `game_id`
2. Asks vision to extract scoreline **or** winner (binary → 1-0 / 0-1)
3. Falls back to the player caption if AI is low confidence

Without any vision key, **caption is required** (or AI is skipped).

### Example: Miniclip 8 Ball Pool

Valid proof looks like:

- Gold **Winner** over one avatar  
- Two portraits + usernames (VS)  
- Coin / piggy prize in the middle  
- Pool table background  

Not valid: mid-game table only, lobby, free-play without a winner banner.

## Adding a new game

1. Add entry under `config/games/mobile.yaml` (or imessage/console)
2. Set `outcome_type`, `result_screen`, `ai_hints` from a real screenshot
3. Restart the bot so the catalog cache reloads

Prefer **real screenshots** when writing `ai_hints` — one solid example beats generic text.
