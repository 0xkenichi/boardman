# Two venues, one brain

Lichess is the **gym**. Each agent plays whoever it wants, as many games as
it wants, to get stronger. That is the agent’s business.

Boardman is the **venue**. Same `pick_move`, but now with a Boardman identity,
USDC wallet, stake lock, spectator book, and settle. The Lichess API key is
how we know which gym account is that Boardman agent — it is linked to the
wallet, never stored in `agents.json`.

```
   Lichess gym (anyone, any clock)     Boardman venue (stakes + wallet)
   myrajafromboardman  ←token A→       agent_raja  0xDB13…  :18761
   keniichii           ←token B→       agent_nero  …         :18762
              │                                    │
        lichess-bot × 2                      House / API
              └──────── same pick_move ────────────┘
```

One Lichess account cannot play both sides. Two gym accounts = two tokens.

## Right now

| | Raja | Nero |
|---|---|---|
| Boardman identity + wallet | live | live |
| Webhook | `:18761` | `:18762` |
| House pairing | when API is up | when API is up |
| Lichess gym | [myrajafromboardman](https://lichess.org/@/myrajafromboardman) | [keniichii](https://lichess.org/@/keniichii) |

```bash
python3 builders/lichess_bots/run.py --agent raja
python3 builders/lichess_bots/run.py --agent nero   # after Nero token
# optional: they challenge each other on Lichess (public watch)
python3 builders/lichess_bots/challenge.py
# Boardman money path (independent of Lichess)
PYTHONPATH=. python3 scripts/run_house_session.py --games 1
```

## Do not

- Reuse Raja’s token on Nero.
- Expect a Lichess PGN to move USDC. That’s House only.
