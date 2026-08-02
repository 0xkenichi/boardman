# Rematch Stack (builders)

Platform layer under Rematch. Use this — not Telegram handlers — when building new experiences.

## Install / run

From rematch repo root (standalone layout):

```bash
export PYTHONPATH=$PWD
# ensure gaming/ → src shim if needed (see deploy/start_free_local.sh)
./.venv/bin/python -m uvicorn gaming.src.backend.main:app --port 8000
```

## HTTP (v0 — discovery)

| Endpoint | Description |
|----------|-------------|
| `GET /api/stack/v0/health` | Stack + Supabase/Circle config checks |
| `GET /api/stack/v0/catalog` | Modules, games, network, match model |
| `GET /api/stack/v0/chains` | Settlement chains |
| `GET /api/stack/v0/public/board` | Leaderboard + open challenges |

## HTTP (v1 — match lifecycle)

Set `STACK_API_KEY` on the server. Pass `X-Stack-Key: …` (or `Authorization: Bearer …`).

| Endpoint | Description |
|----------|-------------|
| `GET /api/stack/v1/games` | Catalog (iMessage + console) |
| `POST /api/stack/v1/matches` | Create challenge |
| `GET /api/stack/v1/matches/{id\|code}` | Status |
| `POST /api/stack/v1/matches/{id}/accept` | Accept |
| `POST /api/stack/v1/matches/{id}/lock` | On-chain lock stake |
| `POST /api/stack/v1/matches/{id}/report` | Text score / W\|L |
| `POST /api/stack/v1/matches/{id}/proof` | Screenshot multipart |
| `POST /api/stack/v1/matches/{id}/settle` | Force settle attempt |

```bash
curl -s localhost:8000/api/stack/v0/catalog | jq
curl -s -H "X-Stack-Key: $STACK_API_KEY" localhost:8000/api/stack/v1/games | jq
```

## Python façade

```python
from gaming.src.stack import get_stack

stack = get_stack()
print(stack.capabilities().to_dict())
print(stack.list_chains())
print(stack.public_board(leaderboard_limit=10))
```

## Interfaces

See `protocols.py`:

- `WalletProvider` — ensure wallet, USDC balance  
- `EscrowEngine` — lock / cancel  
- `MatchEngine` — public board (expanding)  
- `OutcomeVerifier` — pluggable proof  
- `ReputationEngine` — leaderboard  

## Design doc

`docs/REMATCH_STACK.md`

## Roadmap

- **v0** — discovery API + façade (you are here)  
- **v1** — API-key match lifecycle + webhooks  
- **v2** — multi-app partners + pluggable verifiers  
