# Rematch — From V1 to V2

**Brand:** Rematch by sideQuest  
**Date:** 2026-07-30  
**Audience:** community, builders, partners, content  
**Related:** `PRODUCT_STRATEGY_1V1_PUBLIC_FIAT.md`, `IMESSAGE_AND_CHANNELS.md`, `MOBILE_GAMES.md`, `WEBAPP_UX_AND_SECURITY.md`, `PAYMENT_RAILS.md`

---

## One-line story

**V1** was a Telegram bot for 1v1 console skill matches with USDC escrow.  
**V2** is the same unbreakable settle rule — **1v1 · finite winner · lock · proof · pay** — expanded into a **multi-game catalog**, **multi-surface product** (Telegram + Stack API + web), **smarter money UX**, and a path to **fiat top-up** so non-crypto players can just send money and play.

---

# Part A — What is Rematch V1?

*Use this for posts: “What we launched / what works today.”*

## V1 in one paragraph

Rematch is a **Telegram app for staked 1v1 skill matches**. Two players challenge each other, both **lock USDC** in dual-lock escrow, play (starting with **EA FC** on console), submit a **final score screenshot**, and AI + rules settle the pot. Wallets are **Circle custodial** — no seed phrases. Settlement rails started on **Arc testnet** (USDC-native gas story). Fair play is reinforced with **PLAY score**, caps, pause, and geo-safety.

## V1 core loop

```
Open bot → fund wallet → challenge friend → accept → both lock
→ play → submit FT photo → winner paid → rematch
```

## V1 feature set (baseline product)

| Area | V1 |
|------|-----|
| **Surface** | Telegram bot (button-first) |
| **Match model** | Private 1v1 dual-lock USDC |
| **Games** | Console-first (EA FC, NBA 2K, Other) |
| **Proof** | Final screenshot + scoreline + AI vision |
| **Money** | Circle developer wallets · ClawEscrow · testnet USDC |
| **Default chain** | Arc testnet (multi-chain config existed; product pushed Arc) |
| **Reputation** | PLAY points, streaks, tiers, public board |
| **Safety** | Stake/withdraw caps, pause, geo-fence, dispute path |
| **Web** | Thin pages: how-to, leaderboard, get-USDC helper |
| **Hosting** | Local / opportunistic 24-7 (not yet the full Akash path) |

## V1 what we promised players

- Challenge a friend on Telegram  
- Lock stake fairly (both sides committed)  
- Prove the result with a photo  
- Get paid without trusting the other person’s honesty alone  
- Earn PLAY for competing  

## V1 limitations (honest)

- Mostly **console / FC** mental model  
- **Telegram-only** for real play  
- **Crypto-shaped funding** (faucet / send USDC to an address)  
- Balance bugs and wallet rotation could confuse users  
- No first-class **iMessage / Free Fire / COD** catalog  
- No public **builder API** for other apps  
- **Fiat on-ramp** not productized  

**V1 was the proof:** skill matches + escrow + AI proof can work as a product.

---

# Part B — What changed (recent upgrades → V2 foundation)

*Roughly the last sprint of work: strategy, ops, money UX, multi-game, Stack, web/payment direction.*

## Theme 1 — Product clarity (never forget)

| Upgrade | Why it matters |
|---------|----------------|
| Canonical strategy doc | 1v1 only, finite outcomes, abstract money, public vs private, tournaments later |
| Decision log | Stop re-litigating Arc vs Avalanche, BR vs 1v1, team-as-wallet |

**Docs:** `docs/PRODUCT_STRATEGY_1V1_PUBLIC_FIAT.md`

## Theme 2 — Always-on ops (Akash)

| Upgrade | Why it matters |
|---------|----------------|
| `Dockerfile.akash` + SDL + start scripts | Bot + API off the laptop |
| CrashLoop fixes | No bash on slim images; `backend` package symlink; Python supervisor |
| Pinned images + GHCR CI | Reproducible deploys |
| Full runbooks | `docs/AKASH_DEPLOY.md` |

**Result:** Rematch can run **24/7** on cheap CPU (no GPU).

## Theme 3 — Money UX & wallet truth

| Upgrade | Why it matters |
|---------|----------------|
| **Balance $** language | Non-crypto users don’t need chain names |
| **Get money** (not only “Get USDC”) | Abstraction |
| **Play wallet vs linked/old address** | Fixed silent $0 while funds sat on another address |
| Never auto-orphan funded wallets | Stop creating a second empty Circle address |
| Scan known addresses | Show “funds on another address — move to play wallet” |
| Strict balance for deposit watch | RPC errors ≠ fake $0 / fake deposits |
| Arc native + ERC-20 USDC read | Correct Arc gas-token model |

**Result:** Wallet screen tells the truth. Stakes still use **play wallet** on-chain.

## Theme 4 — Personality

| Upgrade | Why it matters |
|---------|----------------|
| **Win/loss zingers** | Creative, non-repetitive banter on settle |
| Score-aware lines | Blowouts vs close games feel different |

**Code:** `src/bot/utils/zingers.py`

## Theme 5 — Simpler Telegram UX

| Upgrade | Why it matters |
|---------|----------------|
| Cleaner main menu | My match · Challenge · Wallet · Get money · Rematch · Profile · More |
| Less chain education in UI | Arc-first without forcing multi-chain UI |

## Theme 6 — Multi-game catalog (V2 heart)

| Surface | What’s new |
|---------|------------|
| **iMessage / GamePigeon** | Full catalog + wizard category + AI hints for final screens |
| **Mobile** | **FC Mobile** flagship + Free Fire, COD Mobile, Valorant, PUBG/BGMI, eFootball, Clash Royale, MLBB, Wild Rift, Chess, Ludo, … |
| **Console** | Still EA FC / 2K / Other |
| **Loader** | `game_catalog.py` + `config/games/*.yaml` |

**Rule unchanged:** finite winner only — **no open battle royale** as default.

## Theme 7 — Rematch Stack (platform API)

| Layer | What |
|-------|------|
| **v0** | Discovery: health, catalog, chains, public board |
| **v1** | Match lifecycle: games, create, accept, lock, report, proof, settle |
| Auth | `STACK_API_KEY` server-side |
| Purpose | Telegram is not the only client |

**Name:** Product = **Rematch**. Platform API = **Rematch Stack**.

## Theme 8 — Web & MiniPay direction

| Piece | Status |
|-------|--------|
| Existing web | `/rematch`, leaderboard, get-usdc |
| Plan | Full app at `playingsidequest.fun/rematch/app` |
| Parity | Same features as Telegram via Stack |
| Security model | Telegram login verified server-side; no Stack key in browser; custodial wallets |
| MiniPay | Later shell for Africa — same webapp |

**Docs:** `WEBAPP_UX_AND_SECURITY.md`, `WEBAPP_AND_MINIPAY.md`

## Theme 9 — Identity & professionalism

| Upgrade | Why |
|---------|-----|
| Git history attributed to **0xkenichi** | Correct ownership |
| Hard fixes over hand-wavy balance excuses | Deposit $189 vs Wallet $0 root-caused and fixed |

---

# Part C — Rematch V2 (what we’re offering now / shipping into)

*V2 = V1 settle core + multi-game + multi-surface + serious money abstraction + fiat prep.*

## V2 one-liner

**Stake any finite 1v1 — console, iMessage, or mobile — settle with a final screenshot, on rails built for Telegram today and every client tomorrow.**

## V2 pillars

### 1. Universal 1v1 settlement

Still the only money path:

```
open → accept → dual lock → play anywhere → final image proof → settle
```

### 2. Game surfaces (catalog)

| Category | Examples |
|----------|----------|
| **Console** | EA FC, NBA 2K |
| **iMessage** | 8 Ball, Sea Battle, Chess, Word Hunt, … |
| **Mobile** | FC Mobile, Free Fire 1v1/CS, COD DM/TDM/1v1, Valorant custom, PUBG TDM, Clash Royale, … |

### 3. Multi-surface product

| Surface | Role |
|---------|------|
| Telegram | Primary live UX |
| Stack API | Builders, webapp, MiniPay, WhatsApp later |
| Web (`/rematch/...`) | Public board today · full app next |
| Fiat payment rail | Prep for mainnet non-crypto top-up (see Payment Rails) |

### 4. Money, humanized

- **Balance $** (stakeable play wallet)  
- **Get money**  
- Clear warnings if funds sit on a linked/old address  
- Path to: **send fiat → we convert → USD balance in play wallet**  

### 5. Trust & ops

- Escrow dual-lock  
- AI + dual report + dispute  
- Caps, pause, geo  
- 24/7 deploy path (Akash)  
- Zingers — product has a voice  

## V2 vs V1 snapshot

| | V1 | V2 |
|--|----|----|
| Games | Console FC-centric | Catalog: console + **iMessage** + **mobile** |
| Proof | FC-style FT | Same engine + **per-game AI packs** |
| Clients | Telegram | Telegram + **Stack API** + **web roadmap** |
| Wallet UX | Chain-y / easy to misread | Abstracted $ + address honesty |
| Personality | Functional | **Zingers** on settle |
| Hosting | Laptop-fragile | **Akash-ready** always-on |
| Fiat | Not productized | **Payment rail design** (mainnet prep) |
| Builders | No public match API | **Stack v1** match lifecycle |

---

# Part D — Content kit (copy-paste)

### Tweet / short post — V1

> Rematch V1: 1v1 skill matches on Telegram.  
> Challenge → both lock USDC → play → final screenshot → settle.  
> Circle wallets, no seed phrases. PLAY score for competing.  
> Built by sideQuest.  
> Bot: t.me/ClawStationOfficialBot · playingsidequest.fun/rematch

### Tweet / short post — V2 direction

> Rematch V2: same fair settle — more ways to play.  
> iMessage games · FC Mobile · Free Fire 1v1 · COD · Valorant customs · PUBG TDM  
> Plus Rematch Stack API so web/MiniPay/WhatsApp can use the same rails.  
> Still 1v1. Still a final image. Still dual-lock.  
> playingsidequest.fun/rematch

### Thread outline

1. Problem: friends bet, no trust, no clean settle  
2. V1 solution: Telegram + escrow + AI screenshot  
3. What we shipped in V1 (loop + safety)  
4. What’s new for V2: multi-game catalog  
5. Stack API / web — Rematch not bot-only  
6. Money abstraction + fiat rail coming  
7. CTA: open bot, fund, challenge  

---

# Part E — What’s next (active V2 workstreams)

| Priority | Workstream | Outcome |
|----------|------------|---------|
| P0 | Fiat **payment rail** (see `PAYMENT_RAILS.md`) | Non-crypto top-up → USDC play balance |
| P0 | Webapp MVP at `/rematch/app` | Full parity shell, simple UX |
| P1 | Telegram WebApp button | Bot opens web for uploads |
| P1 | Catalog polish | Timeouts, room codes, public iMessage/mobile lobbies |
| P2 | MiniPay shell | Africa distribution |
| P2 | Mainnet Arc when rails + legal ready | Real money with caps |

---

## Bottom line

**V1 proved the settle loop.**  
**V2 makes Rematch the place you stake any real 1v1 — iMessage, mobile, console — with product UX for humans and an API for every surface.**  
**Payment rails** are how we stop forcing every player through crypto plumbing while we keep testnet today and prepare for mainnet tomorrow.
