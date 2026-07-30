# Rematch Product Strategy — 1v1 · Public · Mobile · Fiat · Deploy

**Status:** canonical decision log (do not re-litigate casually)  
**Date:** 2026-07-30 · **last ops update:** same day  
**Product:** Rematch (sideQuest) — Telegram 1v1 staked skill matches  
**Related:** `REMATCH_PRODUCT_BRIEF.md`, `GROWTH_TOURNAMENTS_AFFILIATES.md`, `SIMPLE_UX.md`, `GRANTS_AND_CHAIN_STRATEGY.md`, `AGENTIC_ECONOMY.md`, `docs/AKASH_DEPLOY.md`, `deploy/akash/`

### Ops snapshot (Akash)

| Item | State |
|------|--------|
| Always-on target | Akash **CPU** (no GPU) |
| Image | `ghcr.io/playingsidequest-dotplay/rematch:latest` (CI green) |
| Next human step | Public GHCR package → upload `deploy/akash/deploy.generated.yml` on Console |
| Full runbook | `docs/AKASH_DEPLOY.md` |

This document captures the full product strategy from product brainstorms so we **know it and never forget**.

---

## 0. One-line product

**Lock stake → play a finite-outcome 1v1 → prove the final result → settle in USDC (users see dollars / Naira, not chains).**

---

## 1. Hard rules (non-negotiable)

| Rule | Meaning |
|------|---------|
| **Everything is 1v1** | Money always settles as one side vs one side. |
| **Finite outcome only** | There must be a clear winner (or explicit draw rules). No ambiguous multi-survivor outcomes. |
| **One canonical settle** | One match → one outcome → pay once. |
| **Bot is escrow counterparty** | Players lock with the bot; they do not need to DM each other for money. |
| **Abstract money rails** | Users fund, bet, withdraw. They do not need to know Arc / Avalanche / gas. |
| **Team = one economic actor** | A group chat or “team rep” still maps to **one wallet / one stake / one result**. |

### What is in scope

- Chess, Ludo, Monopoly, EA FC, NBA 2K, Free Fire **1v1 / private room**, COD **deathmatch / 1v1**, iMessage / GamePigeon finals, fighting-game BO sets.
- Private challenges, public challenges, later tournaments (bracket of 1v1s).

### What is out of scope (or deferred)

- Battle royale placement (Warzone free-for-all, etc.) until we define a finite settle rule.
- Multi-wallet team pots as the primary path.
- Teaching users how to buy gas tokens.

---

## 2. Challenge modes

### 2.1 Private 1v1 (live)

Friends / known rivals challenge in Telegram DM.

```
Challenge → Accept → Both lock → HOME/AWAY (if needed) → Play → Final proof → Settle
```

### 2.2 Public challenge (next product priority)

Anyone can issue a challenge. Bot posts it to a **public Telegram channel**. Anyone can pick it up.

```
Issue public challenge
  → Bot posts in public channel
  → Opponent claims / picks up
  → Each person locks stake with the bot (own chat)
  → Play (exchange game IDs only if the title needs it)
  → Submit final proof
  → Settle
```

**Why this matters:** no DMs between rivals for money; channel is discovery; bot owns escrow.

### 2.3 Tournaments (later)

- Brackets (4 / 8 / 16 presets).
- Each bracket node = existing 1v1 dual-lock match.
- Bot updates bracket and can share a simple image/summary.
- Entry fee → pot; still no new chain primitive for v1.

### 2.4 Group chat reality (Nigeria / game centers)

- Friends hang in group chats; someone may fund the “rep.”
- Product still treats **one person** as the staker.
- Group is social coordination, not a multi-sig money model for v1.

---

## 3. Game surfaces & proof

### 3.1 Universal proof pattern (v1)

**The final image is enough for many games.**

1. Play happens outside the bot (console, mobile, iMessage, PC).
2. Winner/loser captures the **final result screen**.
3. Send screenshot (and score caption when needed) to the bot.
4. AI vision + dual-report + dispute path settle the match.

Same settlement rails whether the game is EA FC or Free Fire 1v1.

### 3.2 Console (already strongest)

- EA FC first; same pattern for 2K / Madden / eFootball.
- FT screenshot + optional platform activity later.

### 3.3 iMessage / casual games (“iMessage stock”)

- People already play on iMessage.
- Capture **final image** → send to bot.
- Optional note of iMessage handle for disputes; settlement identity remains Telegram user + wallet.

### 3.4 Mobile (Free Fire, COD, etc.)

| Prefer | Avoid (for now) |
|--------|------------------|
| Private room / 1v1 face-off | Open battle royale with many survivors |
| Deathmatch with clear win | Placement-only lobbies without agreed rule |
| Hide/swap usernames if game supports clean 1v1 | Modes with no final win screen |

Flow:

1. Accept challenge (and lock).
2. **Time window** to create room / exchange IDs.
3. Play.
4. Final screen → bot.

**Do not block on per-game free APIs.** APIs are anti-cheat later; screenshot + timers + disputes ship first.

### 3.5 Finite-outcome checklist (add a game only if yes)

- [ ] Clear winner (or draw policy)
- [ ] Final screen or verifiable result
- [ ] Reasonable match duration for timeouts
- [ ] Can be private / 1v1 (or deathmatch with agreed rules)

---

## 4. Timers (defaults — tune per game later)

| Phase | Suggested default | Purpose |
|-------|-------------------|---------|
| Public challenge open | ~24h | Dead posts expire |
| Accepted → both locked | ~5–15 min | Match “setup before kickoff” |
| Locked → must start | ~15–30 min | Stop stalling after IDs/rooms |
| Play → submit proof | ~60–120 min | Local shorter; online longer |
| No-show / one-sided report | Existing PLAY + settle rules | Anti-ghost |

If they create a challenge and accept but never start within the window → expire / void / no-show path (product rule, not ad hoc chat drama).

---

## 5. Money & chain strategy

### 5.1 User-facing UX (north star)

| User sees | User does not see |
|-----------|-------------------|
| Balance $2 / ₦x | “Which chain am I on?” |
| Fund · Bet · Win · Withdraw | Seed phrases, gas tokens, RPC |
| Stake $1 | Arc vs Avalanche education |

Under the hood: **USDC + Circle wallets + ClawEscrow**.

**Spendable vs ledger (important bug class):**

| Field | Meaning |
|-------|---------|
| **Balance** (bot) | On-chain USDC at fund address — **can stake** |
| `profiles.wallet_balance_usdc` | Legacy internal credit — **cannot** lock escrow until funded on-chain |

Example: `@stillkenichi` had **$57 ledger** + **$0 Arc on-chain** → Wallet showed $0 for staking. UX now shows spendable clearly and notes credit-on-file.

### 5.2 Why Arc is the best first real-money rail

| | Arc | Avalanche / Base |
|--|-----|------------------|
| Gas | USDC-native story | AVAX/ETH **or** platform gas tank |
| Capital to abstract | Lower | Need float for gas tank |
| Grant narrative | Circle wallets + USDC + Arc | Retro volume later |
| Ship real money sooner | Preferred | Possible, more ops |

**Decision:** Arc-primary for settlement UX. Multi-chain remains in config for grants/tests, not for user education.

### 5.3 Gas tank (only if we leave Arc-only UX)

If users settle on Avalanche/Base with abstracted UX:

- Platform (or shared) **gas tank** pays tx gas.
- User only tops up USDC.
- Cost either absorbed or small cut from deposit.

**Do not ship full gas abstraction without capital.** Testnet and Arc path first.

### 5.4 Fiat (Naira) path — required for mass non-crypto users

**Goal:** Naira in → credit wallet → bet in USDC ledger → withdraw Naira out.

**MVP deposit design (preferred):**

1. One **business** bank/Kobo account (not long-term personal).
2. User gets payment reference / exact amount.
3. Backend maps payment → credits Rematch balance.
4. Withdraw reverses the path after checks.

Virtual accounts per user are nicer later (cleaner recon). Single designated account + strict mapping is OK for early MVP.

**Legal / ops:**

- Prefer **business account + CAC** before real deposits at scale.
- Personal account is a temporary risk, not the strategy.
- Raise / grants can fund registration and compliance work.

### 5.5 What blocks “real money” today

| Blocker | Not a blocker |
|---------|----------------|
| Fiat deposit + withdraw rails | “Need 10 more games” |
| Legal/entity for taking user funds | Perfect Free Fire API |
| Capital if abstracting multi-chain gas | Fancy tournament UI |
| 24/7 hosting (ops) | Rewriting escrow |

**Honest ship ladder:**

1. **Testnet (Arc)** — real users, fake/test USDC, prove loop  
2. **24/7 host** — bot not on laptop  
3. **Public challenges** — growth  
4. **Mainnet USDC on Arc** — crypto-native users  
5. **Naira rails** — mass market  

---

## 6. Hosting & cost reality

| Workload | Needs GPU? | Notes |
|----------|------------|--------|
| Telegram bot + API | **No** | ~0.5 CPU, 512Mi–1Gi RAM is fine |
| AI vision | Optional API | OpenRouter / remote model; not Akash GPU required for bot |
| Always-on | Yes | Akash CPU, Fly, Oracle free, Hetzner ~$5 |

**Target deploy for this strategy:** **Akash Network (CPU)** — cheap always-on for bot + API.

See: `docs/AKASH_DEPLOY.md` and `deploy/akash/`.

Rough cost class discussed: often **well under ~$10/month** for a thin bot (not GPU pricing).

---

## 7. Decision log (locked)

| Topic | Decision |
|-------|----------|
| Match shape | Always 1v1 finite outcome |
| Modes | Private (live) + Public (next) + Tournaments (later) |
| Proof v1 | Final image to bot |
| Mobile | Private room / deathmatch only; no BR ambiguity |
| iMessage | Same screenshot settlement pattern |
| Teams | One rep / one wallet |
| User money UX | Abstracted $ / ₦ |
| Chain preference | Arc first (USDC gas) |
| Fiat MVP | Business account + map payments → wallet |
| Real-money blocker | Deposits/withdraw + compliance, not game count |
| Near-term ship | 24/7 on Akash + testnet + public challenges |

---

## 8. Build priority queue

1. **Deploy bot+API 24/7 on Akash** — image ready; finish Console deploy (`docs/AKASH_DEPLOY.md`)
2. **Public challenge** channel post + claim + dual lock
3. **Timers** accept/lock/start/proof expiry
4. **Copy** wallet UI = balance in $, not chain names
5. **One extra game surface** if demand (mobile or iMessage) — still screenshot
6. **Fiat design + Kobo recon** only when ready for real ₦
7. **Tournaments / brackets** on top of 1v1 rails

---

## 9. Stack alignment (already true in codebase)

Rematch Stack hard rule stays:

```
open → accepted → lock → play → proof → settle
```

Public lobbies, tournaments, mobile, and iMessage are **apps/modes on the same rails**, not a second money path.

---

## 10. Anti-amnesia summary

> Rematch is **1v1 skill settlement**.  
> Discovery can be private DM or **public channel**.  
> Proof can be **any final image** (console, mobile, iMessage).  
> Users fund and cash out without learning crypto.  
> Arc + Circle + USDC under the hood.  
> Ship **always-on bot** now; fiat when legal + rails exist; tournaments as bracketed 1v1s later.

**If someone asks “what about COD teams / Free Fire / Naira / Avalanche gas?” — re-read this file.**

---

## 11. Voice & zingers (product personality)

After every settle, the bot sends a **creative, non-repetitive** one-liner:

- Winner: flex / respect / “who the boss is”
- Loser: roast-with-love / “where’s the ego” / rematch fuel  
- Blowouts and close games get score-aware lines  
- Draws get their own pool  

Implementation: `src/bot/utils/zingers.py` · wired in settlement DMs  
Never sound like a bank receipt first — money line + **zinger**, then balance + Rematch button.

---

## 12. Where this doc lives (do not lose it)

| Copy | Path |
|------|------|
| **Canonical** | `docs/PRODUCT_STRATEGY_1V1_PUBLIC_FIAT.md` |
| Deploy | `docs/AKASH_DEPLOY.md` |
| Linked from | `README.md` → Strategy & 24/7 deploy |

Absolute on this machine (worktree):

```text
/Users/kenichi/.grok/worktrees/rematch-rematch/scaling/docs/PRODUCT_STRATEGY_1V1_PUBLIC_FIAT.md
```
