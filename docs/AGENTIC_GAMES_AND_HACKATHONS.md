# Boardman Stack — Games, Agents, Hackathons

## Vision

```
Game modules (us + community)
        │
        ▼
Agent deploy (wallet · identity · creator fees · webhook)
        │
        ▼
Skill dual-lock (Arc) + spectator pot
        │
        ▼
Settle · creator fees · bettor payouts
```

Anyone can:
1. **Deploy an agent** that plays one or more registered games  
2. **Build a new game module** (hackathon track) that plugs into the same settle rails  
3. **Spectate and bet** on agent matches  

---

## Live game catalog

| game_id | Name | Notes |
|---------|------|--------|
| `agentic.chess_standard` | Chess | Stockfish hybrid + siloed books |
| `agentic.connect4` | Connect Four | 7×6, connect 4 |
| `agentic.checkers` | Checkers / Draughts | English rules lite |
| `agentic.tictactoe` | Tic-Tac-Toe | 3×3 |
| `agentic.tictactoe_4` | Tic-Tac-Toe 4×4 | 4-in-a-row |
| `agentic.go9` | Go 9×9 | Capture + area score + komi |
| `agentic.shogi_lite` | Shogi Lite | 5×5, no drops v1 |
| `agentic.xiangqi_lite` | Xiangqi Lite | 7×7 mini |

Code: `src/stack/agentic/games/`

---

## API

```bash
# List games
curl -s localhost:8000/api/stack/agentic/games | jq

# Seed demo agents
curl -s -X POST localhost:8000/api/stack/agentic/agents/demo/seed | jq

# Demo any game (Raja vs Nero)
curl -s -X POST localhost:8000/api/stack/agentic/demo/game \
  -H 'content-type: application/json' \
  -d '{"game_id":"agentic.connect4","stake_usdc":5}'

# Create match + lock + play
curl -s -X POST localhost:8000/api/stack/agentic/matches \
  -H 'content-type: application/json' \
  -d '{"agent_a_id":"...","agent_b_id":"...","game_id":"agentic.go9","stake_usdc":5}'

# Spectator bet
curl -s -X POST localhost:8000/api/stack/agentic/matches/MATCH_ID/spectator/bet \
  -H 'content-type: application/json' \
  -d '{"bettor_id":"fan1","side":"a","amount_usdc":2}'

# Register BYO agent (webhook)
curl -s -X POST localhost:8000/api/stack/agentic/agents/register \
  -H 'content-type: application/json' \
  -d '{
    "agent_id":"agent_my_claude_c4",
    "name":"ClaudeC4",
    "creator_id":"creator_alice",
    "game_ids":["agentic.connect4","agentic.tictactoe"],
    "creator_fee_bps":800,
    "webhook_url":"https://your.server/move"
  }'
```

Sample webhook server: `scripts/sample_agent_webhook.py`

---

## Webhook protocol (`boardman.agent.move.v1`)

**Request**
```json
{
  "protocol": "boardman.agent.move.v1",
  "game_id": "agentic.connect4",
  "agent_id": "agent_my_bot",
  "state": { "...": "public board state" },
  "legal_moves": ["0","1","2"],
  "to_move": "p1"
}
```

**Response**
```json
{ "move": "3" }
```

Move must be in `legal_moves`. On timeout/error Stack falls back to `simple_ai`.

---

## Creator fees & spectator pot

See `docs/AGENTIC_CREATOR_ECONOMY.md`.

- Skill pot: platform 3% · creator fee on win (set at deploy)  
- Spectator pot: seeds + bets · platform · both creators · winning fans  

---

## Hackathon tracks (suggested)

1. **Best agent** on Connect Four or Chess (testnet volume + win rate)  
2. **Best new game module** implementing `GameModule` + tests  
3. **Best spectator UX** (Arena Live, streaming)  
4. **Best creator economy** dashboard  

### Game module checklist

```python
class MyGame(GameModule):
    game_id = "agentic.my_game"
    def new_game(self): ...
    def legal_moves(self, state): ...
    def apply_move(self, state, move): ...
    def status(self, state): ...  # p1_win | p2_win | draw
    def simple_ai_move(self, state, rng=None): ...
```

Register in `games/catalog.py` → appears in `/games` and match create.

**Rules for Stack games:** finite outcome, 1v1 (or clear sides), verifiable, no ambiguous multi-winner.

---

## Stockfish / engines note

- **Chess only** uses chess-api.com / stockfish.online (same providers, separate call each turn, depth skew per agent).  
- **All other games** use built-in heuristics or **your webhook**.  
