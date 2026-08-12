# Agentic Economy on Rematch Stack

**Status:** vision + architecture (not shipped)  
**Rails (now):** Arc Testnet · Circle W3S · ClawEscrow · USDC  
**Next chain:** Avalanche Fuji (not enabled)  
**Related:** `REMATCH_STACK.md`, `TOKENOMICS_PLAY.md`, `OUTCOME_VERIFICATION.md`, `CONTRACTS.md`

---

## 1. The idea (cleaned up)

You described a template that starts with **chess** and generalizes:

1. A **digital game** with a **finite outcome space**  
   - Chess: white wins / black wins / draw  
   - Virtual football / FM / many esports sims: home win / away win / draw (or scoreline)
2. People **create AI agents (bots)** trained to play that game  
3. Two agents (or agent vs agent pools) **drop into matches** on shared rails  
4. **Spectators** can **predict / stake / trade** on who wins  
5. **Fees** flow to:
   - the platform (Stack / Rematch)
   - the **game creator** (rules module)
   - the **agent creator** (when their agent plays / wins)
6. That loop is a **production economy for virtual agents** — agents are economic actors with wallets, stakes, and reputation, not just chatbots

That is not “Rematch becomes chess.”  
That is: **Rematch Stack becomes the settlement + match + fee infrastructure for any finite-outcome digital contest**, human or agent.

| Today (Rematch app) | Agentic layer (Stack) |
|---------------------|------------------------|
| Human vs human on console | Agent vs agent (or human vs agent) |
| FT photo / AI vision proof | Game oracle / engine / signed result |
| Telegram UX | Any client (API, Discord, web arena) |
| Dual-lock stake between two players | Same dual-lock **or** multi-party spectator pot |

**Hard rule still holds for the skill match:**  
one contest → one canonical outcome → settle once.  
Prediction markets are a **layer on top**, not a second conflicting money path.

---

## 2. Why Circle + Arc fit this story

| Piece | Why it matters for agents |
|-------|---------------------------|
| **Circle developer-controlled wallets** | Every agent (or agent-owner) can have a **USDC wallet** without seed phrases in the bot. Agents can lock, receive, and pay fees programmatically. |
| **USDC** | Stable unit of account for stakes, creator fees, prediction pools — agents don’t need volatile gas tokens if possible. |
| **Arc (testnet first)** | Settlement chain with **USDC-native gas** story → better UX for high-frequency agent matches than “find testnet ETH.” |
| **ClawEscrow** | Proven dual-lock pattern: both sides commit → play → resolve. Agents use the same primitive humans use. |

**Agentic economy one-liner for grants / Circle:**  
*Stablecoin rails where autonomous agents compete in finite-outcome games, settle stakes trustlessly, and share fees with creators — starting on Arc testnet.*

---

## 3. What you’re *not* missing — and what you almost left out

### You already have the right pillars
- Finite outcome games  
- Agent creators + agent vs agent competition  
- Spectator capital (predict / stake on outcomes)  
- Fee economy (platform + creators + agent owners)

### Integral pieces to add explicitly

| Gap | Why it matters |
|-----|----------------|
| **Canonical outcome oracle** | Chess can be *deterministic* (PGN + engine). Human EA FC still needs vision. Stack must support **pluggable verifiers**. |
| **Match vs market** | **Match escrow** (two sides lock skill stake) ≠ **prediction pool** (many people bet on the result). Different contracts / ledgers; same match_id. |
| **Agent identity** | Who owns the agent? Version? Can the same owner run both sides? (sybil / sandbagging) |
| **Fairness & collusion** | Owner A’s agent vs Owner A’s agent = wash trading. Need ownership rules, cooldowns, maybe commit-reveal. |
| **Liquidity** | “Trade on outcome” needs either simple winner-take-all pools or a real market maker — start simple. |
| **Agent runtime** | Stack settles money; **who runs the chess engine?** Builder sandbox, shared arena, or bring-your-own server with signed results. |
| **Dispute path** | Agents can bug. Humans can cheat. Always need timeout + admin/resolve + pause switch (`safety.py`). |
| **Regulatory framing** | Skill contest + optional prediction. Keep **testnet / play money** messaging until counsel clears mainnet spectator markets. |

None of that kills the vision — it just means **Stack docs must separate layers** so builders don’t mush “agent plays chess” with “fans bet on chess” into one broken contract.

---

## 4. Layered architecture (how we set it up)

```
┌─────────────────────────────────────────────────────────────────┐
│  EXPERIENCES                                                      │
│  Rematch (humans) · Agent Arena · Spectator app · partner UIs   │
└───────────────────────────────┬─────────────────────────────────┘
                                │ Stack API / SDK
┌───────────────────────────────▼─────────────────────────────────┐
│  REMATCH STACK                                                    │
│  A. Game registry     — rules, outcome schema, verifier type    │
│  B. Agent registry    — agent_id, owner, version, wallet        │
│  C. Match engine      — open → accept → lock → play → settle    │
│  D. Outcome verifier  — engine / API / vision / manual          │
│  E. Escrow            — ClawEscrow dual-lock (players/agents)   │
│  F. Spectator markets — optional pools keyed by match_id        │
│  G. Fee router        — platform / game creator / agent creator │
│  H. Reputation        — PLAY-like skill score for agents+humans │
│  I. Safety            — pause, caps, anti-sybil hooks           │
└───────────────────────────────┬─────────────────────────────────┘
                                │
┌───────────────────────────────▼─────────────────────────────────┐
│  RAILS                                                            │
│  Circle W3S · Arc Testnet USDC · ClawEscrow.sol · Supabase      │
└─────────────────────────────────────────────────────────────────┘
```

### 4.1 Game registry (chess as template)

```text
game_id: chess_standard
outcome_space: [white_win, black_win, draw]
verifier: chess_engine_v1          # not screenshot
match_format: agent_vs_agent | human_vs_agent | human_vs_human
time_control: optional
creator_id: who published the game module
creator_fee_bps: from platform fee or volume (policy)
```

Any virtual game with a clear terminal state can register the same way:  
`fm_matchday`, `virtual_fc_sim`, `poker_hu` (careful: skill vs chance), etc.

### 4.2 Agent registry

```text
agent_id
owner_profile_id          # human or org wallet/owner
game_ids[]                # which games it can play
wallet_id / address       # Circle wallet (or owner pays on behalf)
version / model_uri       # reproducibility
stats                     # W/L/D, Elo-like, PLAY-agent score
```

**Bot on a boat** in your wording ≈ **agent with a wallet + policy + version**, registered on Stack, playable by the match engine.

### 4.3 Match (skill stake) — reuse today’s path

Same state machine as Rematch humans:

```text
open → accepted → dual_lock → playing → outcome → settled | disputed
```

- Side A / Side B can be **human profile** or **agent_id**  
- Stake: USDC dual-lock via ClawEscrow on **Arc**  
- Outcome: verifier returns one of `outcome_space`  
- Settlement: winner wallet gets pot − fees  

This is why Stack is the right foundation: **you already built dual-lock USDC matches.**

### 4.4 Spectator / prediction layer (new)

Keyed by `match_id` after both agents locked (or after match is scheduled):

| Simple v1 | Later |
|-----------|--------|
| Fixed-odds or pari-mutuel pool: “Agent A wins” / “Agent B wins” / “Draw” | Continuous trading, order books |
| Users lock USDC into outcome buckets | Secondary markets |
| After match settles, buckets pay winners | Oracles for live odds |

**Important:** spectator funds should **not** mix into the two agents’ skill escrow in v1.  
Two pots, one outcome:

```text
match_id
  ├─ skill_escrow     (agent A stake + agent B stake) → winner agent owners
  └─ spectator_pool   (predictors) → winning side of market
         fees skimmed from both under policy
```

### 4.5 Fee router (creator economy)

Illustrative only (config, not hardcoded forever):

```text
gross_skill_pot = stake_a + stake_b
platform_fee    = fee_bps * gross          # e.g. 7% today
remainder       → winner (skill)

from platform_fee (or from spectator volume):
  game_creator_cut   (published the chess module)
  agent_creator_cut  (optional: % of fee when their agent participates / wins)
  stack_treasury     (remainder)
```

**Policy principles (align with PHASES fee design):**
- Never stack a surprise second tax that changes the **advertised** winner payout without disclosure  
- Partner/creator cuts ideally come **from platform fee** so winner math stays clean  
- Agent creator rewards can also be **off-escrow** (streaming from treasury, seasons) if on-chain split is hard at first  

That creates the **production economy**:  
train better agents → win more → earn more creator share + reputation → attract spectator volume → more fees.

---

## 5. Chess example end-to-end (template)

1. Builder registers `game:chess_standard` + `verifier:chess_engine_v1`  
2. Alice registers `agent:alice_stockfish_style_v3` with Circle wallet  
3. Bob registers `agent:bob_rl_v1`  
4. Arena opens match: Alice’s agent vs Bob’s agent, **$5 USDC** each on Arc  
5. Both dual-lock via Stack → status `locked`  
6. Optional: spectators put $1 into “Alice wins” / “Bob wins” / “Draw” pool  
7. Match runner executes game; engine emits signed result `{winner: white, pgn: ...}`  
8. Stack verifier accepts result → skill escrow settles to winner’s owner wallet  
9. Spectator pool settles; fees to platform + chess module creator + (optional) agent creators  
10. Agent Elo / PLAY-agent score updates  

Swap chess for **virtual football sim**: same skeleton, different verifier and outcome schema.

---

## 6. What Rematch Stack must document (for builders)

This is the documentation set Stack should own:

| Doc | Audience | Content |
|-----|----------|---------|
| **REMATCH_STACK.md** | everyone | Platform map, modules, Arc-only posture |
| **AGENTIC_ECONOMY.md** (this) | vision / grants / partners | Agent + spectator + fee thesis |
| **Game module spec** (todo) | game creators | Outcome schema, verifier interface, fee bps |
| **Agent module spec** (todo) | agent creators | Register agent, wallet, versioning, anti-sybil |
| **Match lifecycle API** (v1) | all builders | create / lock / settle / webhooks |
| **Spectator market spec** (todo) | prediction UIs | Pool rules, settle hook on match_id |
| **Oracle / verifier interface** | infra builders | `verify(match) → outcome` contract |
| **Fee policy** | finance / legal | Who gets what, testnet vs mainnet |
| **Safety & abuse** | ops | pause, caps, same-owner matches, rate limits |

**Builder promise (one sentence):**  
*If your game has a finite outcome and your agents can produce a verifiable result, Rematch Stack will wallet, lock, settle, and fee-split on Arc USDC — you build the game and the UX.*

---

## 7. Phased build (realistic)

### Phase 0 — now (foundation)
- Rematch human 1v1 on **Arc testnet** (live product)  
- Stack v0 discovery API  
- This vision doc  

### Phase 1 — Agent matches (no spectators yet)
- `agent` entity in DB + Circle wallet per agent (or owner-funded)  
- Game registry: start with **one** deterministic game (chess or simple sim)  
- Verifier: engine/API signed result (not FT photo)  
- Same dual-lock escrow as humans  
- Public “arena” list of open agent matches  

### Phase 2 — Creator fees
- Config fee router: platform / game creator / agent creator  
- Attribution on match: `game_id`, `agent_a`, `agent_b`  
- Dashboard: earnings per agent  

### Phase 3 — Spectator pools (simple)
- Pari-mutuel or fixed buckets per match_id  
- Settle only after skill match terminal state  
- Hard caps, testnet only messaging  

### Phase 4 — Generalize games
- Football manager / virtual sports modules  
- Human vs agent hybrid  
- Avalanche enablement when Arc path is solid  

### Phase 5 — Mainnet / richer markets
- Only after volume, abuse model, and legal review  
- Optional richer prediction designs  

---

## 8. Corrections / sharpening of the thesis

| Your words | Sharper Stack language |
|------------|----------------------|
| “Boat / bleaches” | **Bot / agent** with wallet + policy |
| “Drop into agentic economy” | **Register agent → join match market → settle on Stack** |
| “Trade on outcome” | Start as **predict/stake pools**, not full order-book trading |
| “Every game that wins generates fees” | Fees from **stakes and/or spectator volume**, split by policy — not magic inflation |
| “Any digital game” | Any game with **finite terminal outcomes + a verifier** you trust |
| Chess as foundation | Chess is the **reference module**; the foundation is **finite-outcome match settlement** |

**What’s not required for v1:** full DeFi prediction markets, multi-chain, mainnet, or replacing Rematch human product.

**What is required for the story to be real:**  
verifiable outcomes, agent identity, unmixed pots (skill vs spectator), and fee policy that doesn’t break escrow math.

---

## 9. How this sits next to human Rematch

```text
                    Rematch Stack
                   /             \
        Human Rematch              Agent Arena
     (console, FT proof)        (engine oracle)
              \                   /
               \                 /
                Arc USDC + Circle + ClawEscrow
```

Same Stack, different **experience** and **verifier**.  
That’s the product strategy: Rematch proves human demand; Stack + agentic economy expands to **autonomous competitive capital**.

---

## 10. Open decisions (to resolve before coding Phase 1)

1. **Who runs agent compute?** Platform arena vs bring-your-own with signed results  
2. **Same-owner matches** allowed or blocked?  
3. **Draws** in chess: split pot, rematch, or bank?  
4. **Agent creator fee** on skill pot only, spectator only, or both?  
5. **Spectator v1:** three-bucket pool vs “pick winner only”  
6. **Legal:** keep agent stakes as skill contests; spectator as play-money testnet until advised  

---

## 11. Immediate doc/code checklist for Stack

- [x] `REMATCH_STACK.md` — platform map  
- [x] `AGENTIC_ECONOMY.md` — this thesis  
- [x] Arc-only live chain posture  
- [x] Game registry schema + chess engine verifier (`src/stack/agentic/`)  
- [x] Agent registry schema + wallet + identity contract binding  
- [x] Agent match API: create → dual-lock → play → settle (`/api/stack/agentic/*`)  
- [x] Chess reference module: Raja (KIA/Alekhine) vs Nero (Sicilian/French) — see `docs/AGENTIC_CHESS_DEMO.md`  
- [x] Wire agent locks to **BoardmanEscrow on Arc** (`src/stack/agentic/onchain.py`; fallback demo ledger)  
- [x] Stockfish APIs + teleprompter (`docs/AGENTIC_TELEPROMPTER.md`)  
- [ ] Fee router config (no hardcode)  
- [ ] Spectator pool design doc (separate from ClawEscrow)  
- [ ] Circle W3S wallets per agent (optional)

---

*The foundation of the thought process is sound: finite-outcome digital contests + AI agents + stablecoin settlement + creator fees. Rematch Stack is the right place to host it; Circle and Arc are the right rails for the agent money loop. Start with agent vs agent skill escrow on Arc testnet; add spectator markets only after the match oracle is trustworthy.*
