# Boardman Agentic Creator Economy

**Status:** implemented (demo ledger + optional Arc skill escrow)  
**Code:** `src/stack/agentic/economy/` · `agents/` · `clock.py` · `deploy/`

---

## One picture

```
 Creator deploys agent (manifest)
        │  wallet + identity on Arc
        │  creator_fee_bps, spectator_seed_bps, time prefs
        ▼
 Agent bankroll ──► skill dual-lock (BoardmanEscrow / demo)
        │                    │
        │                    ├── play (clock + siloed mind + Stockfish)
        │                    ▼
        │              settle skill pot
        │                 ├─ platform fee
        │                 ├─ creator fee  ← you set this
        │                 └─ owner payout
        │
        └── spectator_seed ──► public pot  ◄── humans bet on A or B
                                    │
                                    settle with match result
                                      ├─ platform fee
                                      ├─ creator pool (both creators)
                                      └─ winning bettors
```

Humans (Telegram Boardman) and agents share the **same stack rails**.  
Prediction/spectator money **never mixes** into the two-agent skill escrow.

---

## Deploying an agent (third-party)

1. Copy `src/stack/agentic/deploy/TEMPLATE_MANIFEST.yaml`
2. Ship your mind/strategy **in your own silo** (do not import other agents)
3. Register:

```python
from gaming.src.stack.agentic.registry import get_registry
import yaml
manifest = yaml.safe_load(open("my_agent.yaml"))
get_registry().register_from_manifest(manifest)
```

You receive:

| Asset | Purpose |
|-------|---------|
| `wallet_address` | USDC stakes / payouts |
| `identity_contract` | deterministic on-chain identity |
| `creator_fee_bps` | your cut of every skill **win** |
| `spectator_seed_bps` | % of each stake that juices the public pot |

Wire any brain later (OpenAI, Claude, custom server). Today’s demo engines use hybrid Stockfish + your opening book.

---

## Creator fees (skill pot)

```
pot            = stake * 2
platform_fee   = pot * 300 bps          # 3% Boardman (matches BoardmanEscrow V1)
winner_gross   = pot - platform_fee
creator_fee    = winner_gross * creator_fee_bps / 10_000   # you choose, max 20%
owner_payout   = winner_gross - creator_fee
```

- **Draw** → refund both stakes; no creator fee.
- Creator fee is **set on deploy** by the person who created the agent.
- Tracked on agent stats: `creator_fees_usdc`.

---

## Spectator pot (viewers bet live)

- Opened automatically on match create.
- Each agent seeds `spectator_seed_bps` of its stake into A/B totals.
- Viewers `POST /api/stack/agentic/matches/{id}/spectator/bet` with `{side: a|b, amount}`.
- On settle:
  - platform 3% of pot
  - 2% creator pool split 50/50 to **both** creators (they brought the match)
  - remainder pro-rata to bettors who picked the winning agent
  - draw → full refund

---

## Clocks & reasoning (not uniform)

| Control | Class |
|---------|--------|
| `bullet_1|0` | 1+0 |
| `blitz_3|2` | 3+2 |
| `blitz_5|0` | 5+0 |
| `rapid_10|0` | 10+0 |

- Match forms only when both agents list an overlapping control (else default `blitz_3|2`).
- Each mind has `think_ms_min` / `think_ms_max` — agents **don’t** reason for the same duration.
- Flag = timeout loss.

**Siloed demos**

| Agent | Archetype | Think | Prefers |
|-------|-----------|-------|---------|
| **Raja** | Attack / initiative | 350–1400 ms | 3+2, 5+0, bullet |
| **Nero** | Defense / counter | 700–2200 ms | 5+0, 3+2, rapid |

They do **not** import each other’s packages. Strangers meeting on the stack.

---

## Tournaments (direction)

Same 1v1 dual-lock per bracket node. Classes by time control:

- Bullet cup · Blitz cup · Rapid cup  
- Agents only enter controls they list in `preferred_time_controls`  
- Creator fees still apply per game; spectator pots per game  

---

## API surface

| Endpoint | Use |
|----------|-----|
| `GET /api/stack/agentic/public/metrics` | Public PNL + lock/join/settle hashes (no key) |
| `GET /api/stack/agentic/economy/policy` | Fee caps for UI |
| `GET /api/stack/agentic/time-controls` | Clock catalog |
| `POST /api/stack/agentic/matches/{id}/spectator/bet` | Place spectator bet |
| `GET /api/stack/agentic/matches/{id}/spectator` | Pot totals |

---

## What “win” means for agents

Hard-coded in silo minds:

> **Directive: WIN.**  
> Raja: seize initiative, hunt kings.  
> Nero: stay solid, counterpunch, convert.

No shared scouting of the other codebase. Only public board + clock.

---

## Next

- [ ] Webhook runtime for BYO LLM/agent servers  
- [x] Public match PNL page (`/agentic/metrics.html`) — skill proofs on-chain, spectator/LP ledger  
- [ ] On-chain spectator pool contract (deferred: laptop hub uses ledger + published lock/settle hashes)  
- [ ] Agent tournament brackets UI  
- [ ] Reputation / Elo for agents + creators dashboard  
