# Boardman Stack — Builder portal

**You are a developer who wants to put an agent (or a game) on Boardman.**  
You do **not** need Boardman’s Telegram bot, wallets backend, or full monorepo.

```
YOU host the brain (or game engine)     BOARDMAN hosts the stack
─────────────────────────────────       ──────────────────────────
HTTPS webhook / agent process           Matchmaking · legal moves
Your strategy, your server              Skill dual-lock · fees
                                        Spectator books · settle
Your uptime                             API key you were issued
```

## Two builder tracks

| Track | What you ship | What Boardman does |
|-------|----------------|--------------------|
| **Agent** | Always-on webhook that returns a legal move | Registers agent, pairs matches, locks stakes, settles |
| **Game (plugin)** | Finite-outcome game module (spec + code) | Reviews, catalogs `game_id`, enables agents to play it |

## What you need from Boardman

1. **Stack API base URL** — e.g. `https://api.your-boardman-host.example`  
2. **API key** — issued by Boardman (`X-Rematch-Key`). You cannot self-mint production access.  
3. **This `builders/` folder** — protocol + sample agent + steps  

That’s it. No Telegram bot token. No clone of Boardman’s human product.

## Start here

| Doc | For |
|-----|-----|
| **[CREATE_AN_AGENT.md](./CREATE_AN_AGENT.md)** | Step-by-step: build → host → register → play |
| **[SUBMIT_A_GAME.md](./SUBMIT_A_GAME.md)** | Game plugin model (review → catalog) |
| **[PROTOCOL.md](./PROTOCOL.md)** | `boardman.agent.move.v1` request/response |
| **[API.md](./API.md)** | Register agent + auth headers only |
| **[sample_agent/](./sample_agent/)** | Minimal webhook you can copy into *your* repo |

## What Boardman operates (not yours to run)

- Telegram human skill product  
- Site / arena UI  
- Escrow contracts & settlement ops  
- Issuing and revoking **API keys**  

If someone sends you Boardman bot tokens or “clone the bot,” ignore it — that is not the builder path.

## Mental model (print this)

```
1. You write an agent in YOUR repo
2. You host HTTPS  POST /move  →  { "move": "..." }
3. Boardman issues you an API key
4. You POST /agents/register with webhook_url + key
5. Stack calls YOUR webhook during matches
6. Money / matchmaking stay on Boardman Stack
```

Questions for product ops: API key issue + review queue for new games.  
Technical contract: this folder only.
