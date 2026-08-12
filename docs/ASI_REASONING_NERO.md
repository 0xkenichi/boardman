# LLM strategy layer (Gemini / ASI) — not a one-size bot

## Plain English

| Layer | Job | Needs money? |
|-------|-----|----------------|
| **Boardman Stack** | Register agents, legal moves, matchmaking, pots, LPs | No (demo ledger) |
| **Arc** | Dual-lock **USDC** when you settle on-chain | Yes — **testnet** USDC (+ gas if not USDC-gas) |
| **Your strategy** | The mind *you* design (directive, openings, knobs) | No |
| **ASI:One / Gemini** | **Amplify** that strategy when choosing a move | Free **API keys** only — no Arc gas |

**Every builder will build their agents differently.**  
Gemini and ASI are a **plus** on *your* strategy — they do not replace it with a shared “Nero chess bot.”  
Nero is just the **reference silo** that demonstrates the pattern.

You can create and run agents **with Boardman alone** (Stockfish + demo ledger) without Arc or LLM keys.

```
   builder mind ──► strategy_id + strategy_notes + knobs
                           │
                           ▼
                    ┌──────────────┐
                    │ ASI / Gemini │  free keys (optional plus)
                    └──────┬───────┘
                           │ legal move only
                           ▼
                    ┌──────────────┐     optional
                    │ Stockfish    │ ◄── fallback
                    └──────┬───────┘
                           ▼
                    Boardman Stack ──► Arc escrow (money only)
```

## What you ship vs what keys do

| You ship (unique) | Keys amplify |
|-------------------|--------------|
| `strategy_id` | Prompt identity tag |
| `mind.directive` / `strategy_notes` / `principles` / `avoid` | System prompt |
| Style knobs (`aggression`, `counterpunch`, …) | Soft guidance |
| Openings / books | Preferred ideas |
| Webhook or hybrid runtime | When LLM is called |

Stack still enforces: **response must be one of `legal_moves`.**

## Free setup

### Always free / no wallet
1. Run arena + demo ledger.
2. Engines: local Stockfish WASM (free).
3. Without LLM keys → pure Stockfish (openings/mind still apply on Python hybrid).

### Strategy + ASI (free API key, no Arc)
1. Key from [ASI:One](https://asi1.ai) / [docs](https://docs.asi1.ai).
2. Env:
   ```
   ASI_ONE_API_KEY=sk-...
   ASI_ONE_MODEL=asi1-mini
   BOARDMAN_ASI_AGENTS=nero   # or your agent slug substring, or * for all
   ```

### Strategy + free Gemini (also no Arc)
1. Key from [Google AI Studio](https://aistudio.google.com/apikey).
2. **Per-agent keys** (recommended — Nero and Raja each get their own brain key):
   ```
   GEMINI_API_KEY_NERO=...
   GEMINI_API_KEY_RAJA=...
   ASI_ONE_API_KEY_NERO=...   # optional
   ASI_ONE_API_KEY_RAJA=...
   GEMINI_MODEL=gemini-2.0-flash
   BOARDMAN_LLM_AGENTS=nero,raja
   BOARDMAN_LLM_REASONERS=asi,gemini   # or gemini,asi
   ```
3. Shared fallback only (legacy):
   ```
   GEMINI_API_KEY=...
   BOARDMAN_LLM_AGENTS=nero,raja
   ```

Set keys on **Vercel Production** (frontend proxy) and/or agent host; **redeploy**.  
Without keys, arena falls back to Stockfish and logs `LLM key probe · gemini=off`.

### Chess rule book (mandatory)
All LLM prompts include the FIDE-based Boardman rule book. Illegal moves are
rejected. See [`CHESS_RULE_BOOK.md`](./CHESS_RULE_BOOK.md).

### Arc testnet money (optional)
Only for on-chain dual-lock — never required for thinking. See developer docs [05 — Contracts](./developers/05-contracts.md).

## Demo agents (reference only)

| Agent | Strategy (example) | Brain in live arena |
|-------|--------------------|---------------------|
| **Nero** | `nero_defense_v2` — solid, counterpunch | LLM chain (ASI → Gemini) using **Nero’s** strategy JSON → SF |
| **Raja** | `raja_mate_hunter_v3` — attack / mate hunt | Stockfish (can enable LLM by listing Raja in `BOARDMAN_ASI_AGENTS` + sending strategy) |

Builders should **not** copy Nero’s mind for a different product — write your own `strategy_notes`.

## Call the proxy with *your* strategy

```bash
curl -s -X POST https://boardman.playingsidequest.fun/api/agentic/asi-move \
  -H 'content-type: application/json' \
  -d '{
    "fen": "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
    "agent": "my_bot",
    "legal_moves": ["e2e4","d2d4","g1f3","c2c4"],
    "legal_san": ["e4","d4","Nf3","c4"],
    "strategy": {
      "agent_name": "MyBot",
      "strategy_id": "acme_squeeze_v1",
      "directive": "WIN. Squeeze space, avoid early sacs.",
      "archetype": "balanced",
      "strategy_notes": "Prefer closed structures; trade into better endings.",
      "openings": ["queens_gambit", "english"],
      "aggression": 0.9,
      "sacrifice_bias": 0.4
    }
  }'
```

If `fallback: true`, keys missing or model failed — fall back to Stockfish; **your strategy still lives in openings/webhook**.

## Code map

| Piece | Path |
|-------|------|
| Strategy prompt builder | `src/stack/agentic/runtime/strategy_prompt.py` |
| ASI reasoner | `src/stack/agentic/runtime/asi_reasoner.py` |
| Gemini reasoner | `src/stack/agentic/runtime/gemini_reasoner.py` |
| Hybrid engine hook | `src/stack/agentic/chess/hybrid_engine.py` |
| Arena (sends Nero strategy) | `frontend/public/agentic/arena.html` |
| Server proxy | `frontend/app/api/agentic/asi-move/route.ts` |
| Manifest template | `src/stack/agentic/deploy/TEMPLATE_MANIFEST.yaml` |
| Nero / Raja silos | `src/stack/agentic/agents/{nero,raja}/` |

## Mental model (print this)

```
Your strategy  →  free LLM keys amplify it  →  legal move
                     (optional plus)
Stockfish always available as free fallback
Arc only if you want real USDC dual-lock
```
