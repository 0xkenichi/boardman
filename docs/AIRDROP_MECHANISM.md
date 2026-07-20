# Rematch — Airdrop mechanism (full spec)

**Product:** Rematch by sideQuest  
**Status:** design + testnet implementation path  
**Related:** `TOKENOMICS_PLAY.md`, `PLAYBOOK.md`, `BRAND_REMATCH.md`, `play_points.py`

---

## 0. Disclaimer (required everywhere)

> **PLAY points are not money, not equity, and not a promise of tokens.**  
> **$PLAY (if ever claimed) is not guaranteed.** Seasons, weights, and pools may change or be cancelled.  
> **Testnet USDC / test $PLAY have no cash value** and may be reset.  
> **Funding risk:** Rematch depends on ecosystem grants, partners, and future fundraising.  
> **If we do not secure funding or choose not to launch a token,** PLAY points remain a free participation score only — **no obligation to airdrop, list, or redeem.**  
> Nothing here is an offer of securities or investment advice. Skill matches only; not a casino.

Show a short form of this on: `/playbook`, public `/rematch` page, airdrop claim UI, and grant decks (honest).

---

## 1. Two different things

| | **PLAY points** | **$PLAY token** |
|--|-----------------|-----------------|
| What | Off-chain **voucher / score** | On-chain ERC-20 (testnet first) |
| Earn | Settled Rematch matches | Optional **claim** from season pool |
| 1:1? | — | **No** |
| If no funding | Still work as score | **May never launch** |

```
Settle match → PLAY points (now)
                    ↓
         season weight formula
                    ↓
    IF season funded & live → claim $PLAY (not 1:1)
    IF not funded → points stay points only
```

---

## 2. How you earn PLAY points (live)

Base awards (defaults; env-overridable):

| Result | Base |
|--------|------|
| Win | 100 |
| Loss (honest) | 40 |
| Draw | 50 |
| No-show | **−50** |

Then multipliers **stack**:

### 2.1 Settlement chain (testnet volume push)

| Chain | Mult | Why |
|-------|------|-----|
| **Arc** | **1.50×** | Highest — grants + mainnet design-partner story |
| **Avalanche** | **1.25×** | Onchain volume / Retro readiness |
| **Base** | **1.00×** | Baseline consumer rail |

### 2.2 Hot streak (wins only)

```
streak_mult = 1 + 0.15 × (streak − 1)   # cap streak 10 → ~2.5×
```

### 2.3 Rival novelty (new users > endless rematch)

| Situation | Mult (default) |
|-----------|----------------|
| **First settled match** vs this opponent | **1.45×** |
| Opponent’s **first ever** Rematch settle | × **1.25** more (stacks on new rival) |
| 2nd–3rd match together | Decays toward 1.0 |
| Regular rematch (same friend often) | **0.90×** floor (still paid — not punished hard) |

**Intent:** Bring **new Telegram users** onto testnet. Rematching friends is fine and still earns; recruiting pays more.

### 2.4 Multi-chain badge (season weight, not instant points)

Players who settle **≥1 match on Arc AND Avalanche AND Base** in a season get an extra **season weight** bonus (see §4), not necessarily more instant points every match.

### 2.5 Cap

Combined mult capped (default **4.0×**) so farming cannot explode.

---

## 3. Instant points formula

```
base = WIN | LOSS | DRAW  (+ stake bonus)
points = round(base × chain_m × rival_m × streak_m)   # streak only on wins
```

Logged in `gaming.play_ledger` with metadata: `chain_mult`, `rival_mult`, `streak_mult`, `prior_together`.

---

## 4. Airdrop seasons (when / if funded)

### 4.1 Epoch

| Field | Example |
|-------|---------|
| Name | Testnet Season 0 |
| Window | Start–end UTC |
| Chain focus | Arc-weighted |
| Pool | X test $PLAY **only if treasury/grants fund it** |
| Eligibility | ≥ N settled matches in window |

### 4.2 Weight (not 1:1 points)

```
weight_i =
    α × points_earned_in_epoch
  + β × settled_matches_in_epoch
  + γ × usdc_volume_settled_in_epoch
  + δ × new_rivals_count          # distinct opponents first-time
  + ε × multi_chain_bonus         # 1 if settled on all 3 chains
  − sybil_penalty

allocation_i = pool × weight_i / Σ weight
```

Caps: max % of pool per wallet; min matches; ban wash pairs.

**α, β, γ, δ, ε** published at season start. Defaults draft:

| Coeff | Value | Notes |
|-------|-------|--------|
| α | 1.0 | Points matter |
| β | 50 | Completing matches matters |
| γ | 0.1 | Volume (USDC) |
| δ | 80 | New rivals |
| ε | 200 | All three chains |

### 4.3 Claim

1. Snapshot at epoch end  
2. Merkle root or allowlist published  
3. User claims to **settlement-chain wallet** (prefer Arc testnet)  
4. PLAY points **remain** (unless season says burn weight only)

### 4.4 If pool is $0 / no funding

- Publish: “Season unfunded — no token claim”  
- Points and tiers still update  
- **No liability** to users for tokens  

---

## 5. Anti-sybil

| Signal | Action |
|--------|--------|
| Dual lock + resolve | Full weight |
| AI conf ≥ threshold | Bonus in season |
| Same two wallets looping | Cap prior_together / ban |
| Self-referral | Ban |
| Cancel / no lock | Zero weight |
| New account only vs alts | Manual review |

---

## 6. Testnet campaign (ops)

**Goal:** max **settled** matches + USDC volume, **Arc first**.

| Week theme | Message in bot |
|------------|----------------|
| Arc week | “Arc = 1.5× PLAY — help us prove Arc volume” |
| Avalanche week | “1.25× on Avalanche — C-Chain story” |
| Base weekend | “Onboard friends on Base baseline” |
| Multi-chain | “Hit all three for season badge” |

Public stats page (manual or auto): wallets, settles, volume **by chain**.

---

## 7. Simple bot rules (player-facing)

1. Use **buttons** — My match, New challenge, Wallet, Network.  
2. Default **Arc** for best PLAY + product mission.  
3. Bring **new** friends for higher mults.  
4. Rematch same rival = still earn, slightly lower mult.  
5. Ghosting = penalty.  
6. Points ≠ cash. Token only if we run a funded season.

---

## 8. Funding dependency (plain language)

| Outcome | What users get |
|---------|----------------|
| Grants / runway secured | Testnet seasons → possible $PLAY claims; mainnet path |
| Grants delayed | Keep shipping; points accumulate; claim TBD |
| No token ever | PLAY stays a score + tier system only |

We will **not** invent token value to fill a funding gap.

---

## 9. Env knobs

```
PLAY_POINTS_WIN=100
PLAY_POINTS_LOSS=40
PLAY_POINTS_DRAW=50
PLAY_POINTS_NO_SHOW_PENALTY=-50
PLAY_STREAK_STEP=0.15
PLAY_STREAK_CAP=10
PLAY_CHAIN_MULT_ARC=1.50
PLAY_CHAIN_MULT_AVALANCHE=1.25
PLAY_CHAIN_MULT_BASE=1.00
PLAY_NEW_RIVAL_MULT=1.45
PLAY_FIRST_EVER_OPPONENT_MULT=1.25
PLAY_REMATCH_DECAY_AFTER=3
PLAY_REMATCH_FLOOR_MULT=0.90
PLAY_MULT_CAP=4.0
```

---

*Last updated: 2026-07-20 · Brand: Rematch by sideQuest*
