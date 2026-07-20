# Rematch / sideQuest Tokenomics — $PLAY

**Status:** draft design for testnet → mainnet path  
**Last updated:** 2026-07-20  
**Product brand:** **Rematch** (settlement app) · parent **sideQuest** · see `BRAND_REMATCH.md`  
**Related:** `PLAYBOOK.md` (live points rules), `GROWTH_TOURNAMENTS_AFFILIATES.md`, `PHASES_1_2_3_SAFE_DESIGN.md`

---

## 0. One-line model

| Name | What it is | Transferable? | = Token? |
|------|------------|---------------|----------|
| **PLAY points** | Off-chain **vouchers / score** earned by playing | No (account-bound) | **No** |
| **$PLAY** | On-chain **token** (testnet first) | Yes (wallet) | **Yes** |

**Critical rule: PLAY points are NOT 1:1 with $PLAY.**

Points are a **voucher / eligibility weight** for seasons, perks, and **airdrop allocation**.  
The **exchange rate** (if any) is set by **season rules / governance / published formula** — never assumed fixed forever.

```
Play matches → earn PLAY points (ledger)
                    ↓
         seasons · tiers · quests · referrals
                    ↓
         airdrop snapshot(s) → claim $PLAY (testnet → mainnet)
```

---

## 1. Naming (product copy)

| Context | Say | Avoid |
|---------|-----|--------|
| Bot today | “**$PLAY points**” or “PLAY score” | “You earned $PLAY tokens” |
| After claim | “**$PLAY** on Arc/Base testnet” | Equating balance to points |
| Docs | **PLAY points** vs **$PLAY token** | Using one word for both |

In UI after token launches:

- Wallet line A: `PLAY points: 12,400 · Gold`  
- Wallet line B: `$PLAY token: 85.2 (testnet)`  

---

## 2. PLAY points (live system — vouchers)

Already implemented in `play_points.py` / `PLAYBOOK.md`.

### 2.1 What they measure

Participation quality: show up, finish matches, win, don’t ghost.

| Action | Base points (default) |
|--------|------------------------|
| Win | +100 × streak mult + stake bonus |
| Loss | +40 + stake bonus |
| Draw | +50 each |
| No-show | **−50** (penalty) |

Tiers from **lifetime** points: Bronze → Silver → Gold → Platinum → Diamond.

### 2.2 What they are **not**

- Not USDC  
- Not a stablecoin  
- Not redeemable 1:1 for $PLAY  
- Not a promise of market value  

### 2.3 Voucher uses (now + near)

| Use | Status |
|-----|--------|
| Tier badge | Live |
| Leaderboards / seasons | Design |
| Airdrop weight | Design (this doc) |
| Fee discounts / cosmetics | Later |
| Unlock public board limits | Later |

---

## 3. $PLAY token (on-chain)

### 3.1 Purpose

1. **Reward early skill economy** (testnet → mainnet airdrop)  
2. **Align partners** (centers / creators may earn $PLAY or points→airdrop weight)  
3. **Future utility** (fee discounts, boosts, governance — phased, not day-one)  
4. **Not** the stake currency — **USDC stays the match stake**

### 3.2 Network path

| Phase | Network | Goal |
|-------|---------|------|
| **T0 — now** | Points only (DB) | Earn, tier, ledger |
| **T1 — testnet** | Arc Testnet and/or Base Sepolia | Deploy `$PLAY`, claim from airdrop contracts, faucet UX |
| **T2 — mainnet** | Arc and/or Base (TBD) | Real $PLAY; migrate eligibility from testnet seasons |

**Testnet first is mandatory:** no mainnet $PLAY until claim flow, anti-sybil, and support path are proven on testnet.

### 3.3 Suggested token parameters (draft — changeable)

| Parameter | Draft | Notes |
|-----------|-------|--------|
| Symbol | `$PLAY` | Matches brand |
| Standard | ERC-20 | Circle / escrow ecosystem friendly |
| Decimals | 18 | Standard |
| Initial chain | **Arc Testnet** preferred (USDC gas UX) | Mirror on Base Sepolia optional |
| Max supply | **TBD** (see §4) | Cap recommended for clarity |
| Mint authority | Multisig / timelock after T1 | Testnet can use admin key |

*These numbers are design placeholders until legal + treasury finalize.*

---

## 4. Supply buckets (illustrative framework)

Treat as a **template**, not final percentages until locked in a public “Genesis” post.

| Bucket | Example share | Purpose |
|--------|---------------|---------|
| **Community airdrop / seasons** | 30–40% | Convert PLAY-point seasons → $PLAY claims |
| **Ecosystem / partners** | 10–15% | Centers, creators (fee-aligned, not double tax) |
| **Team + advisors** | 15–20% | Vesting 12–36 months |
| **Treasury / liquidity** | 15–20% | DEX / CEX later, ops |
| **Future play-to-earn seasons** | 10–15% | Ongoing emissions after T2 |
| **Reserve** | 5–10% | Buffer |

**Emission principle:**  
Most long-term $PLAY to users should come from **proven activity** (settled matches, not empty wallets).

---

## 5. Airdrop design

### 5.1 Core idea

PLAY points are **vouchers** that buy **weight** in one or more airdrop epochs.

```
weight_i = f(points_i, tiers, streaks, volume, referrals, anti_sybil)
allocation_i = (weight_i / Σ weight) × epoch_pool_$PLAY
```

**Not:** `allocation = points × 1.0 $PLAY`

### 5.2 Example non-1:1 formula (testnet epoch 0)

```
raw_weight = 
    lifetime_points
  + 2.0 × points_earned_in_epoch
  + 500 × diamond_tier_bonus          # 1 if diamond else 0, etc.
  + 0.1 × usdc_volume_settled_epoch   # skill volume, not deposits only
  − sybil_penalty

allocation = epoch_pool * raw_weight / sum(raw_weight)
```

Capped per wallet (e.g. max 1% of epoch pool) to stop whales farming.

### 5.3 Epochs

| Epoch | When | Pool | Eligibility |
|-------|------|------|-------------|
| **Testnet S0** | Arc testnet live | Test $PLAY only | Settled testnet matches + min N matches |
| **Testnet S1** | After public board / partners | Test $PLAY | + partner-attributed volume weight |
| **Mainnet Genesis** | After audit + legal | Real $PLAY | Snapshot of seasons; may require claim on testnet first |
| **Ongoing seasons** | Quarterly | Smaller pools | New points only in window |

### 5.4 Claim flow (testnet)

1. User earns PLAY points (already)  
2. Snapshot at epoch end (profile_id → weight)  
3. Merkle root (or simple allowlist for early testnet) published  
4. User connects Circle / wallet that owns gaming deposit address **on that chain**  
5. `claim()` mints/transfers test $PLAY  
6. Bot shows: “Claimed X $PLAY (testnet) — points unchanged”

**Points stay after claim** (unless a season explicitly burns voucher weight for that epoch only).

### 5.5 Anti-sybil (airdrop integrity)

| Signal | Treatment |
|--------|-----------|
| Settled matches with dual lock | Strong weight |
| Both screenshots / AI conf | Bonus |
| No-show / cancel farm | Low or zero weight |
| Same device / referral rings | Cap / exclude |
| Self-partner attribution | Ban |
| Wash trading same two wallets | Detect pairs, cap |

---

## 6. Relationship: points ↔ token (never 1:1)

| Scenario | What happens |
|----------|----------------|
| User has 10,000 points | High **tier** + high **airdrop weight** — not “10,000 $PLAY” |
| Epoch pool 1,000,000 $PLAY, user 1% of weight | Claim **10,000 $PLAY** that season (coincidence of numbers, not a rule) |
| Next season different pool / weights | Same points can yield different $PLAY |
| User sells $PLAY on a market (later) | Points balance **unchanged** |
| User is banned for fraud | Points and claims clawback / deny claim |

### Optional later: “redeem” voucher

Only if product wants sinks:

- Burn N points → lottery ticket for bonus $PLAY  
- Burn N points → fee discount NFT  

Still **not** a fixed 1:1 redeem.

---

## 7. Utility roadmap for $PLAY token

| Phase | Utility |
|-------|---------|
| Testnet | Claim, hold, show in bot, transfer between test wallets |
| Early mainnet | Fee discount tiers (e.g. hold X $PLAY → −50 bps fee from **platform share only**) |
| Growth | Boost listing on public board, tournament host bond |
| Later | Governance on presets / fee parameters (narrow scope) |

**USDC remains stake.** $PLAY never replaces escrow USDC in v1.

---

## 8. Partners & tokenomics (aligned with fee-only cut)

From growth docs:

- Centers / creators earn **cash share from platform fee (USDC)** — **not** from player principal.  
- Separately, they can earn **PLAY points weight** or **$PLAY partner pool** for onboarding quality volume.  

| Partner reward | Source |
|----------------|--------|
| USDC cut | Platform fee only |
| $PLAY (optional) | Partner bucket of supply / seasons |
| Points | Referral bonuses (voucher, not token) |

**Lifetime residual (creators):** USDC fee share **until further notice** (policy).  
$PLAY partner allocations can follow different vesting.

---

## 9. Testnet deployment checklist

### 9.1 Contracts (T1)

- [ ] ERC-20 `$PLAY` on **Arc Testnet**  
- [ ] (Optional) same bytecode on Base Sepolia  
- [ ] `PlayAirdrop` or MerkleDistributor — claim by epoch  
- [ ] Multisig owns mint for testnet (ok to be hot key while testing)  
- [ ] No mainnet deploy until T1 claim works for real users  

### 9.2 Off-chain

- [ ] Export `play_ledger` + settled challenges → weight CSV  
- [ ] Publish formula + epoch end time in bot `/playbook`  
- [ ] Bot: “Airdrop” button → claim instructions  
- [ ] Clear banner: **test tokens, no real value**  

### 9.3 Comms

- “PLAY points ≠ $PLAY token”  
- “Airdrop weights from activity, not 1:1”  
- “Testnet $PLAY can be reset / re-minted”  

---

## 10. Accounting diagram

```
┌─────────────────────────────────────────────────────────┐
│  MATCH (USDC)                                           │
│  lock → play → AI → settle                              │
│  winner gets pot − 7% fee                               │
│  fee → treasury; partner cut FROM FEE ONLY              │
└───────────────────────────┬─────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────┐
│  PLAY POINTS (DB voucher)                               │
│  win/loss/draw/no-show → play_ledger                    │
│  tier · streak · season weight                          │
│  NOT transferrable · NOT 1:1 token                      │
└───────────────────────────┬─────────────────────────────┘
                            │ snapshot / formula
                            ▼
┌─────────────────────────────────────────────────────────┐
│  $PLAY TOKEN (chain)                                    │
│  airdrop claim · optional utility · testnet first       │
│  transferrable ERC-20                                   │
└─────────────────────────────────────────────────────────┘
```

---

## 11. Example season (numbers for intuition only)

**Testnet Season 0**

- Epoch pool: **1,000,000 test $PLAY**  
- Active players with ≥3 settled matches: 500  
- Alice: 8,000 points this season, 12 settled matches, Gold  
- Bob: 800 points, 2 matches  

Alice weight ≫ Bob → Alice claims much more $PLAY **even if** Bob’s points were “1:1 fantasized.”  
If formula were wrongly 1:1 with total points across all users, supply would inflate unbound — **rejected**.

---

## 12. Risks & mitigations

| Risk | Mitigation |
|------|------------|
| Users think points = tokens | UI copy + this doc + claim screen |
| Sybil farms airdrop | Dual-lock + AI proof weight; caps |
| Partner double-dip | Fee-only USDC; separate $PLAY bucket |
| Testnet dump narrative | Explicit “no value”; reset rights |
| Legal (securities / gambling) | Skill-contest framing; LEGAL.md; no ROI promise |

---

## 13. Open parameters (to freeze before mainnet)

1. Max supply & final bucket %  
2. Exact weight formula v1  
3. Claim chain (Arc vs Base primary)  
4. Whether testnet claim is required for mainnet eligibility  
5. Team vesting schedule  
6. Whether fee discounts use **balance** or **staked** $PLAY  

---

## 14. Implementation phases (token-specific)

| Phase | Work | Break 1v1? |
|-------|------|------------|
| **P0** | Keep points as today; doc + bot copy “voucher ≠ token” | No |
| **P1** | Deploy testnet ERC-20 $PLAY | No |
| **P2** | Season snapshot job + Merkle + claim page/bot | No |
| **P3** | Show token balance in Wallet (testnet) | No |
| **P4** | Mainnet + utility (fee discount from fee share) | Careful |

---

## 15. Summary for the team

1. **PLAY points** = participation **vouchers** (live now).  
2. **$PLAY** = **token**, testnet first, then mainnet.  
3. **Not 1:1** — airdrop uses a **weight formula** over points + behavior.  
4. Match stakes stay **USDC**; fee cuts for centers stay **from fees only**.  
5. Creator residual USDC policy: **lifetime until further notice** (separate from token).  

---

*This document does not constitute an offer of securities or a guarantee of token value. Testnet assets may be reset.*
