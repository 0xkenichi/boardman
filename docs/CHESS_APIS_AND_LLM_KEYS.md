# Chess engines, APIs, and per-agent LLM keys

## Why Gemini “wasn’t being used”

The arena only calls Gemini/ASI when **server-side env keys** are set on the
Next.js host (Vercel / local `.env.local`). If keys are missing, every move
falls back to Stockfish WASM / chess-api.com — which looks “dumb” or
engine-flat, and the log never shows `Gemini` / `ASI:One`.

**Check:** open arena → log line `LLM key probe · nero: gemini=…`  
or `GET /api/agentic/asi-move` → `per_agent[].gemini_configured`.

| Symptom | Cause | Fix |
|---------|--------|-----|
| No “API call →” lines | Old arena only probed Nero weakly | Redeploy arena (both agents call LLM) |
| `gemini=off` in probe | No env key on Vercel | Set `GEMINI_API_KEY_NERO` / `_RAJA` |
| `HTTP 400/403` from Gemini | Bad key / quota | New key from AI Studio |
| Always `stockfish_gm_wasm` | LLM returned illegal move or failed | Check server logs `[asi-move]` |

---

## Per-agent keys (do not share one brain)

| Agent | Gemini env | ASI env |
|-------|------------|---------|
| Nero | `GEMINI_API_KEY_NERO` | `ASI_ONE_API_KEY_NERO` |
| Raja | `GEMINI_API_KEY_RAJA` | `ASI_ONE_API_KEY_RAJA` |
| Custom slug | `GEMINI_API_KEY_<SLUG>` | `ASI_ONE_API_KEY_<SLUG>` |

Shared fallbacks (`GEMINI_API_KEY`, `ASI_ONE_API_KEY`) only apply to agents listed
in `BOARDMAN_LLM_AGENTS=nero,raja`.

**Reasoner order:** `BOARDMAN_LLM_REASONERS=asi,gemini` then Stockfish.

---

## Chess engine APIs (research)

| Provider | Auth | Use on Boardman | Notes |
|----------|------|-----------------|-------|
| **Local Stockfish WASM** | none | Arena primary fallback | Free, offline-capable, GM-depth with movetime |
| **[chess-api.com](https://chess-api.com/)** | none (free tier) | Python hybrid + arena remote | Stockfish 18; free depth ≤18, think ≤100ms |
| **[stockfish.online](https://stockfish.online/)** | none | Secondary remote | Depth cap ~15 |
| **Lichess Bot API** | OAuth bot account | Not wired (platform play) | Full games vs humans/bots; not a pure eval API |
| **Chess.com PubAPI** | none | Read-only games/stats | **No** move submission for live play |
| **Lichess cloud eval** | none | Optional future | Opening-book-ish evals; not full multipv engine |
| **Self-hosted Stockfish UCI** | process | Best for production agents | No rate limits; needs CPU |

Boardman **does not** need Chess.com interactive API for agent arena.
Skill is local/remote Stockfish + optional LLM strategy; money is Arc USDC.

---

## Rule book

All agents must obey **FIDE Laws** — see [`CHESS_RULE_BOOK.md`](./CHESS_RULE_BOOK.md).

- Injected into every LLM system prompt  
- Hard gate: only `legal_moves` accepted  
- Checkmate / stalemate / castling / en passant / promotion covered  

---

## Wallet identity

Each agent has a real EOA `wallet_address` (deterministic seed → secp256k1).

| Mode | Balance source | Escrow |
|------|----------------|--------|
| Demo | `data/agentic/ledger.json` keyed by wallet | book-entry dual-lock |
| On-chain | Arc USDC `balanceOf(wallet)` | BoardmanEscrow |

Enable real wallets:

```bash
export BOARDMAN_AGENTIC_ONCHAIN=1
export BOARDMAN_RESOLVER_KEY=0x...
export BOARDMAN_FUNDER_KEY=0x...
python3 scripts/fund_agent_wallets.py --amount 20
```

Agents **play as** their wallet: stakes, seeds, and settlement use `wallet_address`,
never a floating nickname balance.
