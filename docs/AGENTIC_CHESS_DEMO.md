# Boardman Agentic Chess Demo

**Status:** Phase 1 reference implementation (demo ledger + live engines)  
**Stack path:** `src/stack/agentic/`  
**HTTP:** `/api/stack/agentic/*`

## What this is

Two AI chess agents on **Boardman Stack** (formerly Rematch Stack):

| Agent | Name | White mind | Black mind |
|-------|------|------------|------------|
| `agent_raja_kia_alekhine` | **Raja** | King's Indian Attack | Alekhine's Defence |
| `agent_nero_sicilian_french` | **Nero** | Sharp e4 systems | Sicilian + French |

Each agent has:

- **Identity contract** — deterministic CREATE2-style address (`identity_contract`)
- **Wallet** — deterministic EOA for USDC locks (`wallet_address`)
- **Mind** — style weights + opening books (not the same engine personality)
- **Stats** — W/L/D after settled matches

Match flow (same as human skill matches):

```
register agents → open match → dual-lock USDC → play until terminal → settle
```

**Settlement modes**

| Mode | When | What |
|------|------|------|
| **On-chain** | `BOARDMAN_AGENTIC_ONCHAIN=1` + funded agent wallets + resolver key | Real `approve` / `createMatch` / `joinMatch` / `resolveMatch` on **BoardmanEscrow** (Arc testnet) |
| **Demo ledger** | default / on-chain failure fallback | Book-entry USDC in `data/agentic/ledger.json` — same state machine |

Escrow (Arc): `0x3cD57447490c81598Bd8CaCBe3843b24E5735A77`

## Engines (record quality)

After opening books, each agent queries **Stockfish** remotely:

| Priority | Provider | Docs |
|----------|----------|------|
| 1 | [chess-api.com](https://chess-api.com/) `POST /v1` | Stockfish 18 NNUE |
| 2 | [stockfish.online](https://stockfish.online/) `GET /api/s/v2.php` | Stockfish 17.1 |
| 3 | Local styled alpha-beta | Offline fallback |

Env knobs:

```bash
export BOARDMAN_USE_STOCKFISH=1          # default on
export BOARDMAN_SF_DEPTH=12              # chess-api max free-ish ~12–18
export BOARDMAN_SF_THINK_MS=80
export BOARDMAN_SF_PROVIDER=chess-api    # or stockfish-online
export BOARDMAN_USE_STOCKFISH=0          # force local only
```

## Record a demo (recommended)

**Terminal (OBS / QuickTime):**

```bash
export PYTHONPATH=$PWD
mkdir -p gaming && ln -sfn ../src gaming/src && touch gaming/__init__.py
python3 -m pip install 'chess>=1.10.0' eth-account

# Slow, camera-ready pace (~1.25s/move)
python3 scripts/record_chess_demo.py
python3 scripts/record_chess_demo.py --delay 1.5 --white raja --seed 20260812

# Faster take
python3 scripts/record_chess_demo.py --fast
```

**Browser board (best for screen recording):**

1. Serve frontend static files, or open the file after deploy:
   - Local: `cd frontend && npx serve public -p 3456` then open  
     http://localhost:3456/agentic/arena.html  
   - Production: `https://boardman.playingsidequest.fun/agentic/arena.html`
2. Click **Record demo** — escrow lock → book openings → Stockfish middlegame → settle.

## Quick demo (CLI)

From repo root:

```bash
export PYTHONPATH=$PWD
# if needed:
mkdir -p gaming && ln -sfn ../src gaming/src && touch gaming/__init__.py

python3 -m pip install 'chess>=1.10.0' eth-account
python3 scripts/demo_chess_agents.py
python3 scripts/demo_chess_agents.py --white nero --stake 10 --delay 0.05 --seed 42
python3 scripts/demo_chess_agents.py --quiet --json-out /tmp/match.json
```

## HTTP API

Start backend (`uvicorn gaming.src.backend.main:app --port 8000`), then:

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/stack/agentic/health` | Layer health |
| POST | `/api/stack/agentic/agents/demo/seed` | Register Raja + Nero |
| GET | `/api/stack/agentic/agents` | List agents + wallets/contracts |
| POST | `/api/stack/agentic/demo/chess` | Full demo: lock → play → settle |
| POST | `/api/stack/agentic/demo/chess` `{"stream":true}` | NDJSON move stream |
| POST | `/api/stack/agentic/matches` | Create match |
| POST | `/api/stack/agentic/matches/{id}/lock` | Dual lock |
| POST | `/api/stack/agentic/matches/{id}/play` | Run chess + settle |
| GET | `/api/stack/agentic/ledger` | Balances / recent txs |

Example:

```bash
curl -s -X POST localhost:8000/api/stack/agentic/demo/chess \
  -H 'content-type: application/json' \
  -d '{"stake_usdc":5,"white":"raja","move_delay_sec":0}'
```

## Minds (strategies)

**Raja** — hypermodern  
- Books: `kia_white`, `alekhine_black`  
- Higher fianchetto + king-attack weights; delayed center  

**Nero** — counterpuncher  
- Books: `nero_white`, `sicilian_black`, `french_black`  
- Higher counterpunch + central breaks; Sicilian preferred, French alternate  

Middlegame uses **remote Stockfish** (chess-api.com / stockfish.online); local alpha-beta is fallback only.

## On-chain setup (record with real Arc txs)

```bash
export PYTHONPATH=$PWD
export BOARDMAN_AGENTIC_ONCHAIN=1
export BOARDMAN_RESOLVER_KEY=0x...    # BoardmanEscrow resolver
export BOARDMAN_FUNDER_KEY=0x...      # Arc testnet USDC (optional if = resolver)

python3 scripts/fund_agent_wallets.py --amount 20
python3 scripts/record_chess_demo.py --onchain --delay 1.4
```

**Teleprompter:** `docs/AGENTIC_TELEPROMPTER.md`

## Data files

```
data/agentic/
  agents.json
  games.json
  matches.json
  ledger.json
  secrets_<agent_id>.json   # demo private keys (local only)
```

## Roadmap hook

See `docs/AGENTIC_ECONOMY.md` Phase 1–3. This demo covers:

- [x] Agent registry + wallet binding  
- [x] Game registry (`agentic.chess_standard`)  
- [x] Engine/oracle verifier (board terminal state)  
- [x] Dual-lock skill escrow (demo ledger **and** Arc BoardmanEscrow)  
- [x] Stockfish remote engines for recordable play  
- [ ] Spectator pools  
- [ ] Circle W3S wallets per agent (optional vs EOA keys)

## Safety

- Demo private keys are **test-only** deterministic seeds — never fund with real mainnet assets.  
- Same-owner matches are allowed in demo (both owned by `boardman_demo`). Production should enforce anti-sybil rules from the agentic design doc.
