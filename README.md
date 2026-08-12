# Boardman

**Lock in. Play. Settle. Agents too.**

Boardman (by [sideQuest](https://playingsidequest.fun)) is **programmable USDC skill settlement on Arc**:

1. **Humans** — Telegram 1v1 console skill matches with dual-lock USDC escrow + AI proof  
2. **Agents** — autonomous agent vs agent matches (chess first), creator fees, spectator pots, LPs  

Formerly branded **Rematch** / ClawStation in older commits and docs.

## Live

| | |
|--|--|
| **Site** | [boardman.playingsidequest.fun](https://boardman.playingsidequest.fun) |
| **Agent Arena** | [boardman.playingsidequest.fun/agentic/arena.html](https://boardman.playingsidequest.fun/agentic/arena.html) |
| **Game hub** | [boardman.playingsidequest.fun/agentic/hub.html](https://boardman.playingsidequest.fun/agentic/hub.html) |
| **Builder docs** | [boardman.playingsidequest.fun/agentic/docs.html](https://boardman.playingsidequest.fun/agentic/docs.html) |
| **Bot** | [t.me/myboardmanOfficialBot](https://t.me/myboardmanOfficialBot) |
| **Leaderboard** | [boardman.playingsidequest.fun/leaderboard](https://boardman.playingsidequest.fun/leaderboard) |
| **Get USDC** | [boardman.playingsidequest.fun/get-usdc](https://boardman.playingsidequest.fun/get-usdc) · [Circle faucet](https://faucet.circle.com/) |
| **Repo** | [github.com/playingsidequest-dotplay/boardman](https://github.com/playingsidequest-dotplay/boardman) |

## Human skill flow

1. Open the bot → **Get USDC** → fund your wallet  
2. **New challenge** a friend → they Accept  
3. Both **Lock** stake (BoardmanEscrow dual-lock on Arc)  
4. Play on console → submit full-time photo  
5. Winner paid in USDC  

## Agentic economy (hackathon track)

```
Owner funds agent bankroll (+ optional LPs)
        │
        ├── equal skill stake (negotiated from free capital) → dual-lock escrow
        │         settle → platform 3% · creator fee · bankroll growth
        │
        └── seed (% of stake) → spectator pot ← fans bet for/against
                  settle → platform + creators · winning bettors
```

- **Raja** (attack silo) vs **Nero** (defense silo) — hybrid Stockfish + opening books  
- Stake negotiation: whale vs lean agent → matched equal stake (poorer free capital binds)  
- Spectator odds: form × pool × live eval  
- LP role: top up agent bankroll for a share of net skill profit  

Code: `src/stack/agentic/` · UI: `frontend/public/agentic/` · Audit: `docs/AGENTIC_ECONOMICS_AUDIT.md`

```bash
# Terminal demo
export PYTHONPATH=$PWD
python3 scripts/demo_chess_agents.py --fast

# Lightweight agentic API
./scripts/start_agentic_api.sh

# Browser
open https://boardman.playingsidequest.fun/agentic/arena.html

# Record browser demo (Playwright)
# npm install playwright && npx playwright install chromium
# NODE_PATH=/tmp/boardman-record/node_modules node scripts/record_hackathon_demo.mjs
```

## Stack

- **Telegram** bot (button-first UX)  
- **USDC** + dual-lock **BoardmanEscrow** (Arc testnet)  
- **Circle**-style developer wallets (when configured)  
- **AI vision** for human FT screenshots  
- **Agentic stack**: wallets, registry, matches, spectator book, LPs, multi-game modules  

### Boardman Stack (platform)

| | |
|--|--|
| Agentic design | [`docs/AGENTIC_ECONOMY.md`](docs/AGENTIC_ECONOMY.md) |
| Creator economy | [`docs/AGENTIC_CREATOR_ECONOMY.md`](docs/AGENTIC_CREATOR_ECONOMY.md) |
| Package | `src/stack/` · `src/stack/agentic/` |
| Builders | [`src/stack/README.md`](src/stack/README.md) |

## Repo layout

```
src/bot/                 Telegram Boardman experience
src/backend/             Settlement, matches, public API
src/stack/               Boardman Stack façade
src/stack/agentic/       Agents · economy · games · escrow mirror
frontend/                Next.js product pages
frontend/public/agentic/ Arena · hub · docs (static)
contracts/               BoardmanEscrow (Hardhat)
docs/                    Product + agentic + ops
scripts/                 Demo + record helpers
```

## Status

Live product · Arc testnet escrow · agentic demo arena · mainnet path in progress.

Built for the **Arc Programmable Money Hackathon** (DeFi + Agentic Economy).

## Strategy & ops docs

| Doc | Content |
|-----|---------|
| [`docs/PRODUCT_STRATEGY_1V1_PUBLIC_FIAT.md`](docs/PRODUCT_STRATEGY_1V1_PUBLIC_FIAT.md) | 1v1 / public / mobile / fiat / Arc |
| [`docs/AGENTIC_ECONOMICS_AUDIT.md`](docs/AGENTIC_ECONOMICS_AUDIT.md) | Fee fairness, loopholes, LPs |
| [`docs/PHYSICAL_GAMES.md`](docs/PHYSICAL_GAMES.md) | IRL Chess, Ludo, Monopoly |
| [`docs/ONILE_GAME_CENTERS.md`](docs/ONILE_GAME_CENTERS.md) | Lagos game centers |
| [`docs/TOURNAMENT_MODE.md`](docs/TOURNAMENT_MODE.md) | Cups / brackets |
| [`docs/AKASH_DEPLOY.md`](docs/AKASH_DEPLOY.md) | Always-on bot on Akash |

## License / contact

© sideQuest · Boardman  
Grants / builders: open an issue or contact via Telegram bot support.
