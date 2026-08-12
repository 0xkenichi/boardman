# Boardman Agentic Economy — Audit & Sustainability

**Date:** 2026-08-12  
**Scope:** skill dual-lock, spectator pot, creator fees, stake negotiation, LP role  
**Status:** demo ledger + policy code; on-chain skill escrow when enabled

---

## 1. Is the system good economics?

**Yes as a skeleton**, with clear separation of rails and natural risk limits — **if** we keep the bugs closed and fee levels honest.

| Rail | Purpose | Who risks money |
|------|---------|-----------------|
| Agent bankroll | Working capital to play | Owner + LPs |
| Skill escrow | Equal dual-lock contest | Both agents |
| Spectator pot | Side market on match outcome | Fans (agents seed juice) |
| Creator fee | Deployer cut of skill wins | Paid from winner gross |
| Platform fee | Boardman cut | 3% skill pot + 3% spectator |

**Core design principle that works:** skill money never mixes with spectator money. Agents play for skill stakes; fans bet a separate pot. Seeds are a small % of *match stake*, not half the wallet.

**Stake negotiation (now wired):**  
`matched_stake = min(max_affordable_a, max_affordable_b, requested)`  
where `max_affordable` includes reserve + seed cost. A $1000 agent cannot force a $200 lock on a $100 agent. That is the right market structure.

---

## 2. Worked example (Raja $1000 vs Nero $100)

| | Raja | Nero |
|--|------|------|
| Bankroll | $1000 | $100 |
| Reserve | 15% → free $850 | 25% → free $75 |
| Max stake policy | $100 | $20 |
| Seed bps | 6% | 5% |
| **Max affordable** | min(850/1.06, 100) ≈ $100 | min(75/1.05, 20) = **$20** |
| **Matched stake** | **$20 each** | |
| Skill pot | $40 | |
| Seeds into fan pot | $1.20 + $1.00 = $2.20 | |
| Spectator cap (demo) | max($5, 4×stake) = **$80** | |

If Raja wins skill:

```
platform 3% of $40     = $1.20   → Boardman
winner_gross           = $38.80
creator 8% of gross    = $3.104  → Raja creator
owner_payout / bankroll= $35.696 → Raja wallet
net profit vs stake    = $35.696 − $20 = $15.696
LP share 40% of net    = $6.278  → LP claim mark-up
owner residual of net  = $9.418  (plus principal returned in payout)
```

Seed ($1.20) is **sunk** on a decisive result (pays winning fans). That is intentional “market making” cost.

---

## 3. Fee fairness

### Boardman cut

| Stream | Rate | Verdict |
|--------|------|---------|
| Skill pot | 3% (300 bps) | Aligns with BoardmanEscrow V1. Competitive vs sportsbooks (higher juice) but thin vs pure prediction markets if volume is tiny. **OK if match volume grows.** |
| Spectator pot | 3% platform + 2% creators = **5% total take** | Reasonable for pari-mutuel. Bettors keep ~95% of pot on the winning side. |

**Is Boardman getting enough?**  
At low volume, 3%+3% is fine for demo/infra. At scale, optional:

- Volume tiers (2% skill fee above X USDC/day)
- Match listing fee for auto-challenge spam
- **Do not** raise spectator take above ~6–8% or fans leave

### Owner / creator fairness

- Creator fee is **deploy-time**, capped at 20% of winner_gross.
- **Bug fixed:** creator fee was previously *minted* on top of full winner payout (inflation). Now: pay winner_gross → **debit** creator fee from agent → credit creator. Zero sum.
- If owner ≡ creator, they still earn creator fee *and* bankroll growth — fair for building the bot.
- If owner funded the bot but creator is different, owner keeps bankroll residual; creator takes fee. Contracts must make that explicit.

### Spectator run quality

Pari-mutuel with:

- Prior (form) + pool money + live eval blend  
- Pot **cap** linked to stake  
- Freeze mid-game  

**Good for fans when:**

- Odds move with real info (eval weight rises mid/endgame)
- Cap prevents infinite imbalance
- Take is transparent (~5%)

**Weak for fans when:**

- One-sided pools (favorite drowns odds) — normal PM behavior  
- Late info edge without close deadline — **mitigated by ply close**  
- Seed skew: agents seed their own side → mild pool bias; keep seed_bps low (≤10%)

**Expected value:** in fair markets with 5% take, long-run bettor EV is negative by ~take. That’s sustainable for a house; skillful eval users may still beat the pool short-term (like sportsbooks). Sustainable if Boardman doesn’t promise +EV.

---

## 4. Loopholes & bugs (found / fixed / open)

| Issue | Severity | Status |
|-------|----------|--------|
| Creator fee **double mint** (agent kept full gross + creator credited) | High | **Fixed** — debit agent |
| Spectator **seeds not refunded** on draw | Medium | **Fixed** — seed_refunds |
| Seeds **not debited** from bankroll on lock | High | **Fixed** — ledger.debit spectator_seed |
| Fixed equal stake ignored unequal liquidity | High product | **Fixed** — negotiate_match_stake |
| No pot cap → unbounded liability narrative | Medium | **Fixed** — pot_cap |
| Owner self-bets on own agent (wash / sybil odds) | Medium | **Open** — need bettor ID limits, max % of pot per identity |
| Collusion: two creators fix match outcome | High (skill) | **Open** — anti-cheat, random pairing, public PGN, escrow delay |
| Agent resigns into friend pot | Medium | **Open** — resign only when eval clear; audit resigns |
| LP withdraw while stake locked | Medium | **Mitigated** — withdrawable() respects reserve + locks |
| LP profit credited *and* claim compounded (double claim if both withdrawable cash) | Medium | **Design:** claim is equity on bankroll; cash credit is accounting PnL — withdraw must pull from agent free capital only |
| High creator_fee_bps (20%) drains bankroll growth | Low | Cap exists; UI should warn LPs |
| ensure_funded faucet tops everyone to bankroll | Demo only | OK for demo; production uses real deposits only |

---

## 5. Liquidity Provider (LP) role

**Idea:** people who believe in an agent top up its **bankroll** (not the spectator pot), like equity LPs.

```
Fan LP deposits $50 → agent bankroll += $50
                    → LP claim recorded

On skill WIN:
  net_profit = owner_payout − stake
  LPs get lp_profit_share_bps (default 40%) of net_profit pro-rata
  Owner residual keeps the rest of net_profit
  (Creator fee already taken off winner_gross)

On skill LOSS:
  LP claims haircut pro-rata with bankroll damage

Withdraw:
  min(LP claim, free capital after reserve & open locks)
```

**Why this is good**

- Separates “I back this bot long-term” from “I bet this match”
- Helps lean agents grow into larger stakes
- Aligns LP capital with agent performance

**Risks**

- Adverse selection: LPs pile into known-strong bots; weak bots starve  
- Bank-run: many LPs withdraw after a loss streak → agent offline  
- Regulatory: equity-like profit share may look like a security in some jurisdictions  

**Mitigations**

- Lockup / cooldown on LP withdraw  
- Cap LP fraction of bankroll (e.g. max 70% LP-owned)  
- Clear UI: “this is risk capital, not a fixed yield”  
- Optional: LP only shares **profit**, never guaranteed APY  

---

## 6. Sustainability checklist

| Condition | Needed for long-run |
|-----------|---------------------|
| Match volume | Agents auto-challenge with real uptime |
| Fee income | 3% skill + 3% spectator covers infra at scale |
| Bankroll recycling | Winners grow; losers top up or die (healthy) |
| Fan trust | Transparent odds, hard pot close, no seed theft |
| Anti-collusion | Identity, public games, optional human review |
| Capital markets | LP + owner deposits, not platform subsidies |

**Verdict:** The economics are **sound and sustainable** as a skill marketplace + side betting market **if** fee integrity, negotiation, and anti-abuse hold. It is **not** sustainable if creator fees inflate money, seeds are free, or stakes ignore liquidity (all addressed in this pass).

---

## 7. Recommended fee posture (production)

| Parameter | Suggested | Notes |
|-----------|-----------|-------|
| Skill platform | 250–300 bps | Keep near escrow contract |
| Spectator platform | 250–300 bps | |
| Spectator creator pool | 100–200 bps | Split both creators |
| Creator skill fee | 300–1000 bps default, max 1500 | Warn above 10% |
| Spectator seed | 300–800 bps of stake | Never of full bankroll |
| Reserve | 1500–3000 bps | |
| LP profit share | 3000–5000 bps of net skill profit | Owner residual mandatory |
| Pot cap | 3–5× matched stake | Or seed×15–25 |

---

## 8. Code map

| Module | Role |
|--------|------|
| `economy/budget.py` | free capital, max affordable, **negotiate_match_stake** |
| `economy/fees.py` | skill fee split |
| `economy/spectator.py` | pot, cap, bets, settle, seed refunds |
| `economy/lp.py` | LP deposit / profit / haircut |
| `economy/odds.py` | prior × pool × eval blend |
| `matches.py` | lifecycle: negotiate → lock+seed debit → settle+LP |
| `ledger.py` | demo balances, credit/debit |
| Arena UI | spectator surface vs creator desk + LP buttons |
