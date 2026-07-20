# Rematch — Paste-ready grant applications

**Project:** **Rematch** (sideQuest competitive gaming settlement; internal codename ClawStation)  
**Prepared:** 2026-07-20  
**Product status:** Live Telegram bot · Circle developer-controlled wallets · ClawEscrow dual-lock USDC · AI screenshot settlement · multi-chain testnets  
**Brand:** see `BRAND_REMATCH.md`

**Portals**

| Grant | Apply |
|-------|--------|
| Circle Developer Grants | https://circle.questbook.app/ |
| Team1 Mini Grants (Avalanche) | https://go.team1.network/mini-grants |

**Replace before submit**

- `[FOUNDER_NAME]` · `[EMAIL]` · `[TELEGRAM]` · `[TWITTER/X]`  
- `[COMPANY_LEGAL_NAME]` / “Individual / pre-incorporation”  
- `[GITHUB_OR_DEMO_URL]` · `[WEBSITE]` (e.g. playingsidequest.fun)  
- `[WALLET_FOR_PAYOUT]` if asked  
- Metrics: swap bracket numbers for latest real counts  

---

# A. Circle Developer Grants (Questbook)

**Tone:** Arc-core · Circle Wallets · USDC settlement · real users · agent-assisted fairness  

## Elevator / one-liner

**Rematch** is a Telegram-native skill settlement app by sideQuest: two console players lock **USDC** in non-custodial escrow via **Circle developer-controlled wallets**, play EA FC (and expanding sports titles), then settle with **AI vision** on full-time screenshots—defaulting to **Arc** because gas is USDC-native (no test ETH friction for emerging-market players).

## Problem

Friends and game-center regulars already put money on console skill (especially in Nigeria and similar markets), but settlement is informal, trust-based, and offline. Crypto apps either require complex wallets/gas or take full custody. There is no production path that combines **Circle USDC rails**, **deterministic escrow**, and **fair outcome proof** for console 1v1s — without sounding like a casino.

## Solution / product

1. Player opens Telegram bot → Circle wallet provisioned per chain (Arc / Base / Avalanche).  
2. Challenge with short public match code (UUID stays internal).  
3. Both players **approve + lock** USDC into **ClawEscrow** (createMatch / joinMatch).  
4. Play offline on PS/Xbox/PC.  
5. Submit FT screenshot → **AI extracts scoreline** → on agreement / high-confidence AI, **resolver pays winner** (minus platform fee).  
6. Disputes + Support ID path for staff confirmation.

**Circle stack in architecture**

| Circle product | How we use it |
|----------------|---------------|
| Developer-controlled wallets (W3S) | Per-user EOAs; per-chain wallet IDs (no Base wallet used on Arc) |
| USDC | Stake asset on Arc / Base / Avalanche testnets |
| Arc | Preferred settlement chain (USDC gas UX) |
| contractExecution | approve, createMatch, joinMatch from user wallets |
| (Roadmap) CCTP | Fund on Base → settle on Arc without user-managed bridges |

## Why Arc is core (not optional)

- **USDC-native gas** removes the #1 drop-off for non-crypto gamers (no separate gas token hunt).  
- Skill stakes are **economic contracts**—Arc’s positioning as stablecoin settlement OS matches our product.  
- We already ship Arc testnet: escrow `0xFC44a06295d4fC58420027932A6FcB3C13D83859`, dual-lock + resolve proven in production testing.  
- **Mainnet plan:** deploy ClawEscrow + configs day-1 of Arc mainnet beta; keep Arc as default chain in bot UX.

## Traction (edit with live numbers)

- Multi-chain testnet escrow live: **Arc Testnet**, Base Sepolia, Avalanche Fuji.  
- End-to-end path proven: fund → challenge → dual lock → AI score read → on-chain resolve → winner USDC.  
- Telegram bot live (display name migrating to **Rematch**; sideQuest Official).  
- PLAY points ledger (participation vouchers, **not** 1:1 token).  
- Product docs: multi-chain wallets, fee-only partner model, tokenomics draft for testnet $PLAY airdrop weights.

## Team

- Founder: `[FOUNDER_NAME]` — building sideQuest / **Rematch**; shipping Telegram + Circle + multi-chain escrow.  
- Contact: `[EMAIL]` · Telegram `[TELEGRAM]`  

## Grant ask & milestones (suggested)

**Ask:** USDC grant for (1) Arc mainnet readiness, (2) user acquisition / game-center pilot, (3) engineering (CCTP + reliability), (4) security review.

| Milestone | Deliverable | Success metric |
|-----------|-------------|----------------|
| **M1** | Arc-primary UX + public metrics dashboard | Arc default in bot; weekly published wallet/match/USDC stats |
| **M2** | Scale Arc testnet usage | e.g. 200+ settled Arc matches / 100+ unique wallets (set honest targets) |
| **M3** | Trust features | Cancel rules (pre-lock free / post-lock mutual); public board + 24h lock |
| **M4** | Nigeria game-center QR pilot | ≥3 centers; partner cut **from platform fee only** |
| **M5** | Arc mainnet beta | ClawEscrow + wallets live day-1; migration guide |
| **M6** (stretch) | CCTP deposit path | Base USDC → Arc play without user bridge UX |

## Ecosystem impact

- Expands **USDC utility** into console gaming skill settlement (high-frequency small stakes).  
- Demonstrates **Circle wallets** for non-DeFi users (Telegram-first).  
- Showcases **Arc** as the best UX chain for stablecoin gas.  
- Partner model (centers/creators) grows USDC volume without taxing players twice (fee-share only).  
- AI mediation reduces disputes → higher completion rate → more settlement txs on Arc.

## Use case tags (if multi-select)

- Peer-to-peer payments / settlement  
- Agentic economic activity (vision agent + settlement automation)  
- Consumer onchain finance  

## Risks / compliance (honest)

- Skill contests vs local gambling rules: product framed as **skill + proof of play**, with dispute path; legal review ongoing.  
- Testnet volume ≠ mainnet: grant funds bridge that gap with metrics + mainnet deploy.  
- No promise of token listing; PLAY points are vouchers for airdrop **weight**, not 1:1 $PLAY.

## Short answers bank

**How do you use Circle today?**  
Developer-controlled wallets per user/chain; USDC approve + ClawEscrow lock/join/resolve via contractExecution; Arc preferred.

**What makes you different?**  
Console skill 1v1 + dual USDC lock + AI FT screenshot settlement in Telegram—not a casino, not a DEX, not custodial balances.

**What do you need from Circle?**  
Milestone funding, Arc design-partner access, co-marketing, technical guidance on wallets/CCTP, path to mainnet cohort.

---

# B. Team1 Mini Grants (Avalanche) — up to $10,000

**Tone:** builders shipping now · Avalanche activity · gaming · community  

## Project name

Rematch

## One-sentence description

Telegram bot where console gamers lock USDC in escrow for 1v1 skill matches, settle with AI screenshot proof—live on Avalanche Fuji (and Arc/Base), expanding to C-Chain mainnet volume. Product: **Rematch** (sideQuest).

## Longer description (paste)

**Rematch** is the competitive settlement layer for sideQuest. Players create challenges in Telegram, fund **Circle wallets** with USDC, dual-lock stakes into **ClawEscrow**, play EA FC (Tier-A sports titles next), and resolve via **AI vision** on full-time screenshots.  

We already support **Avalanche Fuji** (`ClawEscrow` deployed, gas-tank pattern for AVAX). Same app also runs Arc Testnet (USDC gas) and Base Sepolia. Architecture rule: **everything reuses the 1v1 match**—tournaments, public boards, and game centers are orchestration, not a second money rail.

**Why Avalanche:** high-throughput C-Chain for public matches and future tournaments; gaming ecosystem (Team1 / Helika / Retro9000); clear gas metering for retro programs once we’re on mainnet.

**Go-to-market:** Nigeria game centers (QR onboarding; partner share **from platform fees only**), friend 1v1 bragging rights, later public “fastest fingers” board. PLAY points reward participation (vouchers); seasonal **$PLAY** airdrop weights **settled** matches—with chain multipliers to drive Avalanche volume.

## Problem

Informal cash stakes on console games fail at trust and scale. Web3 tools fail at UX (gas tokens, seed phrases). Avalanche needs real consumer apps that burn gas with **repeat** users—not one-off deploys.

## Solution

Non-custodial USDC escrow + Telegram UX + AI fairness + multi-chain, with Avalanche as a first-class settlement rail for high-activity modes (public matches, tournaments).

## Current status

- [x] Live bot  
- [x] Circle wallets multi-chain  
- [x] ClawEscrow on **Avalanche Fuji**  
- [x] Dual lock + resolve path  
- [x] AI score extraction  
- [ ] C-Chain **mainnet** deploy (funded goal)  
- [ ] Sustained Avalanche match volume campaigns  

## What the mini grant funds (budget sketch — adjust totals ≤ $10k)

| Item | Approx USD | Notes |
|------|------------|--------|
| Avalanche mainnet deploy + config hardening | 2,000 | Escrow, RPCs, monitoring |
| AVAX gas tank for user top-ups (ops) | 1,500 | Platform tops up user gas pre-lock |
| Security review / test suite expansion | 2,000 | Escrow + cancel/refund paths |
| Avalanche user campaign (airdrop weight week) | 2,000 | Incentives for **settled** Fuji→mainnet matches |
| Content + Team1 community demos | 1,000 | Loom, docs, events |
| Contingency | 1,500 | RPC, infra, incident |
| **Total** | **≤ 10,000** | |

## Milestones (60–90 days)

1. **M1:** Public Avalanche status page (matches, unique wallets, USDC volume on Fuji).  
2. **M2:** “Play on Avalanche” season—airdrop weight multiplier for Avalanche settles.  
3. **M3:** C-Chain mainnet ClawEscrow + bot chain toggle production-ready.  
4. **M4:** ≥ N settled Avalanche matches (set honest N) + Team1 demo day / Discord showcase.  
5. **M5:** Retro9000-ready metrics (gas, unique contracts, verified users) for next round.

## Team1 / community impact

- Content: how-to for Avalanche USDC skill stakes  
- Open metrics for ecosystem dashboards  
- Game-center pilots that bring **non-crypto-native** users onto C-Chain  
- Collaboration with Team1 for events / demos  

## Links

- Website: `[WEBSITE]`  
- Bot: Telegram **Rematch** (sideQuest Official / migrate display name)  
- Docs: multi-chain, tokenomics, grants strategy (repo)  
- Escrow Fuji: `0xFC44a06295d4fC58420027932A6FcB3C13D83859` (confirm in explorer)  
- Contact: `[EMAIL]` · `[TELEGRAM]`

## Short answers bank

**Stage:** Live testnet product; pre/seed; shipping weekly.  

**Category:** Gaming / Consumer / Payments settlement  

**Chains:** Avalanche Fuji (live), Avalanche C-Chain mainnet (grant milestone), also Arc + Base testnets  

**Ask:** Up to $10,000 Mini Grant  

**Equity:** N/A for grant  

**How is this Avalanche-specific?**  
Native ClawEscrow on Fuji; AVAX gas tank; planned C-Chain mainnet volume for public matches/tournaments; airdrop weight boosts for Avalanche settles so users choose AVAX deliberately.

---

# C. Optional: Base nomination blurb (Google Form)

**Paste if nominating Rematch for Base Builder Grants**

> **Rematch** (sideQuest) is a shipped Telegram skill-settlement app: dual USDC lock via Circle wallets, AI screenshot match resolution, multi-chain (Base Sepolia + Arc + Avalanche). We’re bringing console 1v1 skill matches onchain for emerging markets and Coinbase-adjacent users. Base is our consumer on-ramp / public-match narrative; live product already settles testnet matches end-to-end. Links: `[WEBSITE]`, bot demo loom `[URL]`, GitHub `[URL]`. Contact `[TELEGRAM]`.

---

# D. Pre-submit checklist

- [ ] Loom 2–4 min: create challenge → both lock on **Arc** → AI score → payout  
- [ ] Second 60s clip: switch network → Avalanche Fuji lock  
- [ ] Honest metrics table (wallets, settles, volume by chain)  
- [ ] Founder legal name + payout wallet ready for KYC  
- [ ] Confirm escrow addresses on explorers  
- [ ] Circle: emphasize Arc-core + Wallets + USDC  
- [ ] Team1: emphasize Avalanche deploy + volume plan + budget ≤ $10k  
- [ ] No “guaranteed token ROI” language  
- [ ] Skill contest framing, not casino  

---

# E. Suggested submit order

1. **Today:** Circle Questbook (best fit).  
2. **Same day:** Team1 Mini Grant (only open AVAX cash form).  
3. **This week:** Base nomination + Talent profile for weekly rewards.  

---

*Customize bracket metrics and personal details before submit. Do not invent user counts.*
