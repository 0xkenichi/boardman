# iMessage games · Mobile · Multi-channel Rematch

**Status:** product + integration plan (ship in phases)  
**Date:** 2026-07-30  
**Depends on:** `PRODUCT_STRATEGY_1V1_PUBLIC_FIAT.md`, `REMATCH_STACK.md`, `OUTCOME_VERIFICATION.md`  
**Hard rule:** still **1v1 + finite winner + one settle** — channel is just the UX shell.

---

## 1. What you want (cleaned)

| Idea | Meaning |
|------|---------|
| **iMessage games as stock** | People already play GamePigeon / iMessage games. Rematch only needs the **final result image** + stake rails. |
| **Catalog** | Each game has a known “what does a win screen look like?” so AI/settlement is reliable. |
| **Mobile next** | Same pattern: private 1v1 / deathmatch with a final screen. |
| **Beyond Telegram** | Rematch Stack API so any client can open/accept/lock/prove/settle. |
| **Phone number as friend** | SMS / WhatsApp / iMessage-style channel: text a number (or short code), bot is the counterparty — same as Telegram bot, different transport. |

You do **not** need Apple to host bets.  
You need: **challenge → lock → play in iMessage → screenshot final → settle**.

---

## 2. Architecture (one money path, many shells)

```
┌─────────────────────────────────────────────────────────────────┐
│  CLIENTS (shells)                                                 │
│  Telegram bot (live) · Web · Discord · WhatsApp · SMS · API       │
│  “iMessage game” is not a client — it’s a GAME MODE + proof pack  │
└───────────────────────────────┬─────────────────────────────────┘
                                │  Stack API / SDK
┌───────────────────────────────▼─────────────────────────────────┐
│  REMATCH STACK                                                    │
│  Identity · Wallets · Escrow · Match lifecycle · Proof · PLAY     │
└───────────────────────────────┬─────────────────────────────────┘
                                │
┌───────────────────────────────▼─────────────────────────────────┐
│  RAILS: Circle USDC · ClawEscrow · Supabase                        │
└─────────────────────────────────────────────────────────────────┘
```

**iMessage games sit in the Game registry**, not as a separate money system.

```
Challenge (game_id = imessage.sea_battle)
  → both lock
  → play in iMessage (off-platform)
  → each (or winner) uploads final screenshot to Rematch
  → catalog-aware AI verifier
  → settle
```

---

## 3. Game catalog (the missing piece)

Every stakeable game is a **catalog entry**. Without this, every screenshot is ad-hoc.

### 3.1 Schema (per game)

| Field | Purpose |
|-------|---------|
| `game_id` | Stable id, e.g. `imessage.8_ball` |
| `display_name` | “8 Ball (GamePigeon)” |
| `category` | `imessage` \| `mobile` \| `console` |
| `platforms` | e.g. `["ios_imessage"]` |
| `outcome_type` | `binary_winner` \| `scoreline` \| `set_score` |
| `result_screen` | Human notes: what the final image shows |
| `ai_hints` | Prompt fragments: “Winner banner”, “You Win”, score layout |
| `proof` | `screenshot_required`, optional `dual_report` |
| `duration_hint_min` | Timeout defaults |
| `stake_min` / `stake_max` | Product limits |
| `enabled` | Ship gate |

### 3.2 Seed catalog — iMessage / GamePigeon (finite winners only)

| game_id | Name | Outcome | What the final image usually shows |
|---------|------|---------|-------------------------------------|
| `imessage.8_ball` | 8 Ball | binary | “You Win” / “You Lose” or balls cleared |
| `imessage.basketball` | Basketball | scoreline or binary | Final score / winner screen |
| `imessage.archers` | Archers | scoreline | Points total both sides |
| `imessage.darts` | Darts | scoreline | Final tally |
| `imessage.sea_battle` | Sea Battle | binary | Fleet sunk / You Win |
| `imessage.cup_pong` | Cup Pong | binary / cups left | Winner |
| `imessage.word_hunt` | Word Hunt | scoreline | Points both players |
| `imessage.anagrams` | Anagrams | scoreline | Final points |
| `imessage.four_in_a_row` | 4 in a Row | binary | Connect-4 win |
| `imessage.checkers` | Checkers | binary | Winner |
| `imessage.chess` | Chess | binary / draw policy | Checkmate / resign |
| `imessage.gomoku` | Gomoku | binary | Five in a row |
| `imessage.crazy_8` | Crazy 8 | binary | Winner |
| `imessage.knockout` | Knockout | binary | Last standing (if clear) |
| `imessage.mini_golf` | Mini Golf | scoreline | Strokes (lower wins) |
| `imessage.one_on_one` | 1 on 1 (basketball) | scoreline | Final score |

**Exclude / defer:** games without a clear final screen, pure RNG with no shared result UI, multiplayer free-for-alls.

### 3.3 File layout (repo)

```
config/games/
  imessage.yaml    # seed catalog
  console.yaml     # EA FC, 2K, … (existing)
  mobile.yaml      # Free Fire 1v1, COD DM, later
```

Code loads catalog → challenge wizard shows **iMessage** games first for this product slice → verifier gets `ai_hints` for that `game_id`.

---

## 4. Player flow (iMessage stakes)

### A. Telegram-assisted (ship first — zero Apple partnership)

1. Both players already have Rematch (Telegram) wallets funded.  
2. **A** opens bot → **Challenge** → game = **iMessage → 8 Ball** → stake → **B**.  
3. **B** accepts → both **Lock**.  
4. They open **iMessage**, play that game (exchange handles in chat if needed).  
5. When finished, **each** (or winner first) sends the **final GamePigeon screen** to the bot:  
   - photo + caption `W` / `L` or `12-8` depending on game  
6. AI + dual report + dispute window → **settle**.

**Why this works:** iMessage is only the **play venue**. Settlement stays on Rematch rails. No Apple API required.

### B. “Phone number friend” (phase 2)

Same match state machine; transport = **SMS or WhatsApp Business**:

```
User texts: CHALLENGE @tag 5 8ball
Bot replies: Accept? Lock? Send photo of final screen
```

Or: “Add this number as a contact → chat like a friend.”

| Channel | Feasibility | Notes |
|---------|-------------|--------|
| **Telegram** | Live | Best UX, buttons, photos |
| **WhatsApp Business API** | High | Official, media, templates; needs Meta business |
| **SMS short code / long code** | Medium | Photos via MMS messy; good for alerts + links |
| **iMessage Business / Apple** | Hard | No open bot API like Telegram; usually link-out or Apple Business Chat (enterprise) |
| **Pure iMessage app** | Hard | Needs iOS app + Messages extension; not SMS |

**Honest answer:** a **phone number people text** is absolutely possible via **WhatsApp or SMS**, not via becoming a free-form iMessage bot without Apple Business / an iOS app.  
Best combo for Nigeria + global:

1. Telegram (now)  
2. WhatsApp number (next)  
3. Web link `playingsidequest.fun/m/CODE` for anyone  
4. iMessage = **where they play**, not necessarily where they stake  

### C. API for everyone (Stack)

Any third party or your own shell:

```http
POST /api/stack/v1/matches
  { "game_id": "imessage.8_ball", "stake_usdc": 2, "challenger": "...", "opponent": "..." }

POST /api/stack/v1/matches/{id}/lock
POST /api/stack/v1/matches/{id}/proof   # multipart screenshot
POST /api/stack/v1/matches/{id}/settle  # or auto
```

Webhooks: `match.locked`, `match.settled`, `match.disputed`.

That is how Rematch becomes **infrastructure**, not “only a Telegram bot.”

---

## 5. Settlement / proof for iMessage screenshots

Reuse existing vision path (`score_verifier`) with **per-game packs**:

| Step | Behavior |
|------|----------|
| 1 | User picks `game_id` at challenge time (catalog) |
| 2 | Submit photo bound to that match |
| 3 | AI prompt includes catalog `ai_hints` + outcome_type |
| 4 | Binary games: extract winner side / You Win-Lose |
| 5 | Scoreline games: extract H-A or points |
| 6 | Dual report agreement **or** high-confidence AI |
| 7 | Dispute window + admin (same as FC) |

**Minimum viable proof for v1:**

- One clear final screen photo  
- Caption: `W` / `L` or `score`  
- Prefer both players submit  
- Zinger + payout on settle (already wired)

---

## 6. Phased ship plan

### Phase 0 — shipped in code

- [x] Dual-lock escrow + AI screenshot (console)  
- [x] `config/games/imessage.yaml` catalog (seed)  
- [x] `game_catalog.py` loader  
- [x] Challenge wizard: **Where do you play?** → iMessage / Console → game list  
- [x] Verifier: catalog AI hints for `imessage.*`  
- [x] Copy after lock: play in iMessage → final screenshot  
- [x] Wallet address bugfixes (play vs linked)  
- [x] Stack API **v1** match lifecycle (`STACK_API_KEY`)  

### Phase 1 — iMessage product polish

- Timeouts per game  
- Public challenge for “open iMessage 8-ball $2”  
- Leaderboard filter by `imessage.*`  
- Better binary W/L dual-report mapping  

### Phase 2 — Stack API polish

- Webhooks `match.locked` / `match.settled`  
- Partner API keys (multi-tenant)  
- OpenAPI examples for builders  

### Phase 3 — WhatsApp / SMS “phone friend”

- Same match IDs  
- Photo over WhatsApp  
- Deep link for funding wallet  

### Phase 4 — Mobile catalog

- Free Fire private 1v1, COD deathmatch, etc.  
- Same catalog schema, different `ai_hints`  

### Phase 5 — Optional iOS

- Share Extension: “Send result to Rematch”  
- Or Messages app that only **opens** Rematch deep link with match code  

---

## 7. What is *not* required

| Myth | Reality |
|------|---------|
| Apple must approve gambling in iMessage | Stake happens in Rematch; iMessage is only the game |
| Need Free Fire API for v1 | Final screenshot + catalog is enough |
| Must rebuild escrow per channel | One Stack, many shells |
| Phone number = iMessage bot | Phone = WhatsApp/SMS; iMessage play stays on-device |

---

## 8. Risks (be professional about them)

| Risk | Mitigation |
|------|------------|
| Fake screenshots | Dual report, AI confidence, dispute, reputation |
| Wrong game / wrong screen | Catalog binding + reject low confidence |
| Wallet address rotation | Fixed: never orphan funded play address; show linked funds |
| Regulatory | Skill contest framing, geo-fence, testnet until rails ready |
| Channel spam | Rate limits, stake caps, pause switch |

---

## 9. Decision log

| Decision | Choice |
|----------|--------|
| iMessage role | **Play venue + screenshot proof**, not money rail |
| Catalog | Required before mass iMessage launch |
| First shell beyond Telegram | **Stack API + WhatsApp**, not Apple iMessage bot |
| Phone friend | WhatsApp Business / SMS long-code |
| Same escrow | Yes — always 1v1 finite settle |

---

## 10. One-liner

**Rematch is the stake + proof + settle layer. iMessage (and mobile) are just games with a final image. Telegram is the first phone; Stack API and WhatsApp make it a number people can always call.**
