# Physical / tabletop games (IRL)

**Lock stake → play at the table → photo + both agree → settle USDC.**

Same money rails as digital matches. The bot never runs Monopoly, Chess, or Ludo — it only holds stakes and pays the winner.

## Catalog

| `game_id` | Title | Notes |
|-----------|--------|--------|
| `physical.chess` | Chess | Checkmate / resign / agreed |
| `physical.ludo` | Ludo | **1v1 only** (two colours) |
| `physical.monopoly` | Monopoly | Agree end rule **before** lock |
| `physical.checkers` | Checkers / Draughts | No pieces / no moves / resign |
| `physical.other` | Other board / table | Any finite 1v1 |

Config: `config/games/physical.yaml`  
Loader: `src/backend/services/game_catalog.py` (`is_physical`, `requires_screen_name`)

## Player flow

```
New challenge → Physical / Table → pick game → stake → opponent accepts
  → both Lock
  → play IRL
  → each: Report result → board photo → I won / I lost
  → agree → payout · disagree → dispute
```

### Proof (v1)

| Signal | Required? |
|--------|-----------|
| Board / score-pad photo | Yes (dispute evidence) |
| Both report W/L | Yes (auto-pay when they agree) |
| On-screen gamertag | **No** (you're at the same table) |
| HOME / AWAY | No for physical |

### Monopoly rule

Money is still **1v1** (two stakers). Before lock, agree how the game ends, e.g.:

- First player bankrupt loses  
- Highest cash + property after N turns  

3–4 people at the table can play socially; only **two** wallets lock stake (or two team reps).

## Bot UX

- Category button: **🎲 Physical / Table** (first in category list)
- Confirm copy: IRL mode + Monopoly end-rule reminder
- Report copy: board photo + I won / I lost (no in-game name step)

## Product rules (unchanged)

- Finite outcome only  
- One match → one settle  
- Bot is escrow counterparty  

See also: `docs/PRODUCT_STRATEGY_1V1_PUBLIC_FIAT.md` · `docs/PROOF_BY_GAME.md` · growth “gaming centers” in `docs/GROWTH_TOURNAMENTS_AFFILIATES.md`
