# Arc money vs ASI:One reasoning (Nero)

## Plain English

| Layer | Job | Needs money? |
|-------|-----|----------------|
| **Boardman Stack** | Register agents, legal moves, matchmaking, pots, LPs | No (demo ledger) |
| **Arc** | Dual-lock **USDC** when you settle on-chain | Yes — **testnet** USDC (+ gas if not USDC-gas) |
| **ASI:One (asi1.ai)** | **Think** — pick Nero’s move with an LLM | No Arc money; free/dev **API key** only |

You can create and run agents **with Boardman alone** (Stockfish brains + demo ledger) without Arc or ASI.

You use **Arc alone** when you want agents (or humans) to **lock real testnet USDC** in BoardmanEscrow.

You use **ASI as the reasoning layer** when you want Nero’s moves chosen by ASI:One instead of Stockfish. ASI does **not** spend USDC; Boardman still settles.

```
                    ┌─────────────┐
   create agent ──► │ Boardman    │◄── bankroll policy, fees, pots
                    │  Stack      │
                    └──────┬──────┘
           play moves      │
           ┌───────────────┼───────────────┐
           ▼               ▼               ▼
      ┌─────────┐    ┌──────────┐    ┌────────────┐
      │ Raja    │    │ Nero     │    │ Arc escrow │
      │Stockfish│    │ ASI:One  │    │ (optional) │
      │ (free)  │    │ (API key)│    │ testnet $  │
      └─────────┘    └──────────┘    └────────────┘
```

## Free setup (what you need)

### Always free / no wallet
1. Run arena + demo ledger (already live).
2. Raja: local Stockfish WASM (free).
3. Nero: Stockfish fallback until ASI key is set.

### Nero + ASI reasoning (free API key, no Arc)
1. Create/get API key at [ASI:One docs](https://docs.asi1.ai) / [asi1.ai](https://asi1.ai).
2. Set on **Vercel** (frontend) and/or backend:
   ```
   ASI_ONE_API_KEY=sk-...
   ASI_ONE_MODEL=asi1-mini
   BOARDMAN_ASI_AGENTS=nero
   ```
3. Redeploy. Arena calls `POST /api/agentic/asi-move` for Nero only.
4. Python matches: `HybridEngine` calls ASI when agent id contains `nero`.

### Real Arc testnet money (optional — only for on-chain dual-lock)
You need these **only** if `BOARDMAN_AGENTIC_ONCHAIN=1` (or human bot main path on Arc):

| What | Why |
|------|-----|
| Arc testnet RPC | Talk to chain |
| BoardmanEscrow address | Dual-lock contract |
| Agent/player wallets with **testnet USDC** | Stake |
| Optional: small native gas if chain requires it | Some Arc setups use USDC gas — check current Arc docs |
| Resolver key (ops) | Settle match |

**ASI key is never an Arc wallet.** No ETH from ASI is required for Nero to think.

Faucets (check current links):
- Circle USDC faucet: https://faucet.circle.com/
- Arc testnet docs / faucet from Circle Arc developer portal

## Who thinks what (this product)

| Agent | Brain |
|-------|--------|
| **Raja** | Stockfish only (5–10s local) |
| **Nero** | **ASI:One first** → if key missing/fail → Stockfish |

## Code map

| Piece | Path |
|-------|------|
| ASI reasoner (Python) | `src/stack/agentic/runtime/asi_reasoner.py` |
| Hybrid engine hook | `src/stack/agentic/chess/hybrid_engine.py` |
| Arena Nero path | `frontend/public/agentic/arena.html` → `/api/agentic/asi-move` |
| Server proxy | `frontend/app/api/agentic/asi-move/route.ts` |
| Nero manifest | `src/stack/agentic/agents/nero/manifest.py` |

## Test

```bash
# Server has key
curl -s https://boardman.playingsidequest.fun/api/agentic/asi-move

curl -s -X POST https://boardman.playingsidequest.fun/api/agentic/asi-move \
  -H 'content-type: application/json' \
  -d '{"fen":"rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1","agent":"nero"}'
```

If `fallback: true`, key is missing or ASI rejected — Nero still plays via Stockfish.

---

## Free Gemini (also for Nero)

Nero’s LLM chain (default order):

1. **ASI:One** — `ASI_ONE_API_KEY`
2. **Gemini** — `GEMINI_API_KEY` (or `GOOGLE_API_KEY`) from [Google AI Studio](https://aistudio.google.com/apikey)
3. **Stockfish** — always free fallback

Env:

```bash
GEMINI_API_KEY=...
GEMINI_MODEL=gemini-2.0-flash
BOARDMAN_NERO_REASONERS=asi,gemini   # or gemini,asi to prefer Gemini
BOARDMAN_ASI_AGENTS=nero
```

Set on **Vercel Production** (and redeploy). Raja never uses Gemini/ASI.

Python: `src/stack/agentic/runtime/gemini_reasoner.py`  
Proxy: `frontend/app/api/agentic/asi-move` tries both providers.
