# Rematch Tournament Mode — product design (v0 decisions)

**Status:** product decision doc + **v0 engine live** (dry-run seats; money gated)  
**Date:** 2026-08-04 · ops update 2026-08-09  
**Product:** Boardman (sideQuest)  
**Related:** `GROWTH_TOURNAMENTS_AFFILIATES.md`, `ONILE_GAME_CENTERS.md`, `PHYSICAL_GAMES.md`, live 1v1 escrow  

### Implementation snapshot

| Piece | State |
|-------|--------|
| Bracket T4/T8/T16 + 3rd place | `src/backend/services/tournament.py` |
| Bot commands + **Cups** menu | `src/bot/handlers/tournament.py` |
| SQL | `sql/055_tournaments.sql` (optional; JSON store works) |
| **Money on join** | `TOURNAMENTS_MONEY_LIVE=1` → entry lock via `tournament_money.py` |
| **Auto-advance** | Settled cup 1v1 → `report_match_winner` → next challenge spawned |
| Bracket 1v1s | `$0` challenges (`[CUP:code:match]`) — pot already funded |
| Onile tag | `/tcreate … --center=IKEJA01` · deep link `?start=cup_CODE` |
| Onile kit | `scripts/generate_onile_kit.py` → `data/onile_kit/` |

### Money env

```bash
TOURNAMENTS_MONEY_LIVE=1
TOURNAMENT_MONEY_MODE=transfer   # or commit (balance check only)
TOURNAMENT_POT_ADDRESS=0x...     # default: BOARDMAN_OPS_USDC_ADDRESS
TOURNAMENT_POT_WALLET_ID=...     # Circle wallet id for refunds + prize pays
```

### Flow (live)

```
/tcreate 8 5 physical.chess Night Cup --center=IKEJA01
players /tjoin or ?start=cup_CODE  → entry USDC → pot
/tstart CODE → R1 $0 challenges created + DMs
players Report → settle → auto advance + next challenges
final → pay 1st/2nd/3rd from pot wallet
```

**Purpose:** Answer, in one place: *who can host, who pays, how brackets run, how the bot/app feels, and what we ship first* — so we stop re-litigating economics mid-build.

---

## 0. One-line product

**A tournament is a fixed bracket of Rematch 1v1 matches, funded by a clear pot, with a published payout card, settled only after finite outcomes.**

Not a free-for-all lobby. Not a casino wheel. Same skill proof as today — **orchestrated**.

---

## 1. Hard rules (same spine as 1v1)

| Rule | Meaning |
|------|---------|
| **Everything is 1v1** | Every bracket node is one match, one winner advances. |
| **Finite outcome** | Scoreline or W/L per game catalog — no BR placement. |
| **Money only under published rules** | Entry, pot, fee %, places — locked before first match. |
| **One wallet per seat** | No multi-account “teams” as one seat. |
| **No unilateral exit after lock** | Once entry is locked into the pot, cancel only under explicit rules (mutual host cancel before start, or admin). |
| **Proof path reused** | Dual report / interview / dispute — same as 1v1. |

**Implication:** Tournament code is mostly **state machine + pot accounting**, not a new chain game type.

---

## 2. The three pot models (only these)

Users were mixing “everyone chips in” with “host puts $100 winner prize.” Those are **different products**. We name them:

### Model A — **Entry pool** (default, scale volume)

| | |
|--|--|
| **Who funds** | Every entrant pays **entry fee E** |
| **Pot** | `N × E` |
| **Payout** | 1st / 2nd / (optional 3rd–4th) from pot after fees |
| **Host money** | Host may take a **host share of fees** (if allowed), not “steal entries” |
| **Incentive to host** | Status, PLAY, optional host cut, community / center revenue, free entry seat |
| **Best for** | Friend groups, gaming centers, daily cups, public skill opens |

**Example:** 16 players × $5 = **$80 pot** → platform 10% = $8 → distributable $72 → 1st 65% / 2nd 20% / 3–4 15% split.

### Model B — **Host-seeded prize** (sponsor / flex / marketing)

| | |
|--|--|
| **Who funds prize** | Host locks **prize P** (e.g. $100 “winner takes this”) |
| **Who funds side pot (optional)** | Entrants pay **entry E** (can be $0 for pure sponsored) |
| **What winner gets** | At minimum **P** (host seed), plus share of entry pot if any |
| **What host can earn** | **Entry pot after platform fee** (minus optional refund of seed rules) — **only if published** |
| **Incentive to host** | If they charge entry, entries can profit *if* they don’t win their own seed back as player; or brand/studio marketing; or center prestige |
| **Best for** | Rematch official cups, game studios, streamers, “I put $50 — beat me” |

**Critical honesty:** If host locks $100 for the winner and also collects $5 × 16 = $80 entries, then:

- Winner gets **$100 seed** (or seed + part of entries — **pick one card and publish**).  
- Host’s **incentive** is either: (1) **entry rake after fee**, or (2) **playing to win their seed back + more**, or (3) **marketing**, not free money with zero risk.

**Recommended v0 for host-seeded:**

```
Winner prize  = host seed P (locked at create)
Entry fees    = optional; after platform fee, go to: host (host profit) OR top-up prize
Host may play = YES (defending their pride / seed)
If host wins  = they reclaim P + any top-up rules as published
```

Default recommendation: **entries top up the prize pool** (better for entrants, worse host profit) **OR** entries go to host after fee (better for centers). **v0 ships only one:**  

**Decision for v0: Model A only.**  
Model B as **v0.5** when we need official/sponsored cups (Rematch-hosted first).

### Model C — **Hybrid** (later)

Host seeds a **guarantee** floor; entries grow the pot above floor. Complex accounting → **not v0**.

---

## 3. Who can create tournaments? (access control)

### Problem you named correctly

If **anyone** can spam public 32-slot $1 cups, you get:

- Dead half-full brackets  
- Support load  
- Trust damage  

So **create** must be gated. **Join** should stay easy.

### Options evaluated

| Option | Pros | Cons | Verdict |
|--------|------|------|---------|
| **Free for all create** | Growth | Spam, garbage pots | ❌ No |
| **PLAY points threshold** | Aligns with skill economy you already have | Farmers create junk; threshold gaming | ✅ Soft gate only |
| **Paid subscription “Host”** | Revenue, serious hosts, centers | Friction; Nigeria/global UX of cards/subs | ✅ **Primary for public host** |
| **Invite / allowlist** | Quality | Ops bottleneck | ✅ Rematch staff + partners |
| **Deposit “bond” $1–$10** | Skin in game | Feels like fee without product | Soft add-on only |

### Recommended access ladder

| Role | Who | Can create | Can join |
|------|-----|------------|----------|
| **Player** | Anyone with wallet + KYC/geo rules as today | No public tournaments | Yes (if seats open) |
| **Host (subscriber)** | Active Host plan (or trial) | Public + private cups (caps) | Yes |
| **Pro host / Center** | Higher plan or agreement | Larger N, higher stakes, multi-cup, QR | Yes |
| **Rematch official** | You / ops | Unlimited official cups, Model B seeds | Yes |
| **Partner (studio/brand)** | Contract | Seeded Model B, branded | Yes |

**v0 simpler:**

1. **Rematch-hosted only** (you create) — ship bracket engine without host marketplace.  
2. **Then** open Host subscription for public create.  
3. Private “friend cup” (invite-only, N≤8) can be **unlocked earlier with PLAY ≥ X or $0 host** because spam risk is low.

### Subscription narrative (sales)

**Don’t sell “pay us to gamble.”** Sell:

> **Host pass = tools for people who already gather players**  
> Gaming centers · Discord admins · campus crews · streamers  

| Plan (example) | Price (TBD local) | Rights |
|----------------|-------------------|--------|
| **Player** | Free | Join any open cup |
| **Host** | Monthly (or annual) | Create up to N cups/month, N≤16, entry ≤ $25 |
| **Center** | Higher | N≤32, entry ≤ $50, multi-room, lower platform fee |

**Fee sweetener (your instinct — keep it):**

| Host type | Platform take of pot |
|-----------|----------------------|
| Free / non-sub (if ever allowed private only) | **12–15%** |
| Host subscriber | **8–10%** |
| Center / agreement | **6–8%** |
| Official Rematch / sponsored | **5–7%** or fixed deal |

Subscription = **lower take + create rights**, not a second opaque tax.

**Host may also get** a small **host credit** (e.g. 2% of pot) from the fee slice — so centers profit without inventing shady economics.

---

## 4. Tournament lifecycle (efficient operations)

```
DRAFT  → host picks preset, game, entry, visibility, start rule
  ↓
OPEN   → seats fill; each entrant locks entry (or host locks seed)
  ↓
LOCKED → roster full (or host force-start if min seats met — optional later)
  ↓
SEEDING → random or seeded by PLAY; bracket frozen
  ↓
LIVE   → round by round 1v1 matches (same proof path)
  ↓
FINAL  → payouts 1st/2nd/(3rd)
  ↓
CLOSED → archive, PLAY awards, leaderboard
```

### When does it “start”?

**v0 rule (simple):**

- Preset size **must be full** (8 or 16) before LIVE.  
- Soft timeout: if not full in **T hours**, auto-cancel + **full refund** of entries (and host seed).  

No half brackets. No byes in v0 (or only for power-of-two fill).

### Bracket presets (v0)

| Code | Players | Rounds (single elim) | 3rd place match |
|------|---------|----------------------|-----------------|
| **T4** | 4 | 2 | Optional |
| **T8** | 8 | 3 | Yes recommended |
| **T16** | 16 | 4 | Yes optional |
| **T32** | 32 | 5 | Later (ops heavy) |

**v0 ship: T4 + T8 only.** T16 after one week of boring ops. T32 when Mini App exists.

### How matches run (efficient)

| Approach | Description | v0? |
|----------|-------------|-----|
| **A. Pot settles at end** | Entries in tournament vault; bracket matches are **$0 stake** 1v1 for progression only; pot pays final places | ✅ **Recommended** |
| **B. Each match is a cash 1v1** | Confusing (entry already paid); double money risk | ❌ |
| **C. Progressive cash** | Loser of match loses something extra | Later / optional modes |

**Approach A** is the clean mental model:

> “I paid $10 to enter. I play free 1v1s until I’m out. Winner(s) of the cup get the pot.”

### No-show / stall (must define)

Same family as 1v1:

- Match window (e.g. 2–6 hours per round, host-configurable preset).  
- If one side reports and other silent → no-show rules → advance reporter if proof of opponent absence / dual report timeout.  
- If both silent → both out or rematch admin — **publish one rule**.

**v0:** reuse `nudge_and_timeout_reports` patterns with **tournament_round_deadline**.

### Host participates?

**Yes by default** (defending pride / seed / skill).  
Optional toggle: “Host sits out (organizer only)” for pure center hosts.

If host plays, they are seat #1 or random seed like everyone else — **no free win**.

---

## 5. Economics — worked examples

### 5.1 Model A — pure entry (what most people mean)

**8 players × $10 entry = $80 pot**

| Slice | % of pot | $ |
|-------|----------|---|
| Platform | 10% | $8.00 |
| Host credit (optional, from platform or pot) | 2% | $1.60 (if from pot, reduce prize) |
| Distributable | 88–90% | ~$70–72 |

**Payout card “Standard” (published at create):**

| Place | % of distributable |
|-------|---------------------|
| 1st | 65% |
| 2nd | 20% |
| 3rd | 15% (3rd-place match) |

**Host incentive without seed:**

- Host credit $  
- Free entry (seat free) *or* paid entry like everyone  
- PLAY host points  
- Center foot traffic / reputation  
- Subscription ROI (tools + lower fee)

### 5.2 Model B — host seeds $100, entrants $5 × 16

**Bad opaque version (avoid):**  
Winner gets $100; host keeps all $80 entries → looks like a house edge casino if host never at risk.

**Good transparent version:**

| Line | $ |
|------|---|
| Host seed (locked) | $100 → **winner prize floor** |
| Entries 16 × $5 | $80 |
| Platform 10% of entries | $8 |
| Remainder of entries | $72 → **top up prize** OR **host profit** |

**Pick one and label the cup:**

1. **“Guaranteed $100 + entry top-up”** → prize = 100 + 72 = $172 to places (best for players).  
2. **“$100 prize, host keeps entries after fee”** → prize = $100 fixed; host +$72 (best for centers; disclose hard).

**Rematch official cups:** prefer (1).  
**Gaming centers:** may prefer (2) with disclosure + Center plan.

### 5.3 Why host would seed money at all

| Motive | Works? |
|--------|--------|
| Win it back by playing | Yes — skill |
| Entry rake (Model B type 2) | Yes — business |
| Brand / streamer clout | Yes — marketing budget |
| Pure charity pot | Rare — official only |

If none of those → **don’t force seed**; use Model A.

---

## 6. Product + sales recommendation (best move)

### Narrative (marketing)

> **1v1 is how you get paid for being better tonight.  
> Tournaments are how a room full of players builds a prize for the best in the room.  
> Hosts are the people who already gather the room — Rematch is the escrow and the bracket.**

Do **not** lead with subscription. Lead with:

1. Free **join** any official cup  
2. Free **private T4/T8 friend cups** (invite) once trust is high  
3. **Host pass** when someone says “I run a center / Discord and want weekly cups”

### Sequencing (sales + product)

| Phase | What ships | Who hosts | Why |
|-------|------------|-----------|-----|
| **T0** | Bracket engine + Model A + T4/T8 + Rematch-created only | You / ops | Learn ops without host spam |
| **T1** | Public join from board / group; PLAY rewards | Players | Habit + clips |
| **T2** | **Host subscription** + private/public create caps | Centers, streamers | Monetization + supply of cups |
| **T3** | Model B official + partner seeds | Brands / games | Big pots without player bankroll |
| **T4** | Mini App bracket UI; QR for centers; WhatsApp later | Everyone | Scale UX |

**Best first move:**  
**Rematch-run weekly Model A cups** (8-ball or FC Mobile) at **$5–$10 entry**, while 1v1 stays free-form.  
Subscription is **phase 2**, not a gate on *playing* tournaments.

### Fee philosophy

- 1v1 stays ~**7%** (already in product mindshare).  
- Tournaments can be **8–10%** of pot (more ops).  
- Subscribers get **fee discount + create rights**.  

---

## 7. Bot & Mini App UX (how it feels)

### 7.1 Player join (Telegram-first v0)

```
Public board / group post / deep link
  → "Join cup: FC Mobile · 8 seats · $10 · starts when full"
  → Lock entry (same wallet UX as lock stake)
  → Wait for full roster
  → Bot DMs: "Round 1: you vs @rival · report when done"
  → Win → wait next round
  → Lose → "Eliminated · final standings when cup ends"
  → Winner(s) auto-paid from pot
```

### 7.2 Host create (T2+)

**Mini App preferred** for bracket visualization; bot can do linear wizard:

1. Game (catalog)  
2. Preset T4 / T8  
3. Entry amount  
4. Visibility: private invite / public board  
5. Start rule: full only  
6. Payout card preset  
7. Confirm → share link  

**Subscription check** on create, not on join.

### 7.3 Surfaces

| Surface | Job |
|---------|-----|
| **Bot DM** | Wallet, join, lock entry, report match, receive pings |
| **Group** | Roster noise, hype, “who’s next” |
| **Mini App / web** | Bracket tree, standings, create form, QR |
| **Later native app** | Same account, same pots |

### 7.4 Gaming centers

Center host (subscription):

- Creates **local cup** (public or invite QR)  
- Players walk in, scan, lock entry on phone  
- Play on center consoles / phones  
- Rematch settles pot — center doesn’t hold cash in a notebook  

That’s the B2B story: **subscription = business tool**, not player tax.

---

## 8. What “tournament mode” is *not*

| Not this | Why |
|----------|-----|
| A separate app with different wallets | Account fragmentation |
| Unlimited custom 37-player brackets | Support hell |
| Host can change payout after fill | Fraud |
| Join without locked entry | No-shows kill brackets |
| Subscription required to **play** | Kills growth |
| Model B without huge disclosure | Looks like house edge |

---

## 9. Decision table (freeze these for v0)

| Topic | **v0 decision** |
|-------|------------------|
| Pot model | **Model A — entry pool only** |
| Sizes | **T4 and T8** |
| Who creates | **Rematch ops only** (no open host create yet) |
| Who joins | **Anyone** who can pass money rails |
| Start rule | **Full roster required**; timeout → refund |
| Match stakes | **$0 progression matches**; pot pays end |
| Payout card | **65 / 20 / 15** (1st/2nd/3rd) of post-fee pot |
| Platform fee | **10% of pot** (tournament ops premium vs 1v1) |
| Host cut | **$0 in v0** (Rematch is host) |
| Host plays | **Yes** allowed in official cups |
| Subscription | **Not required for v0**; design Host plan for T2 |
| Proof | **Same as 1v1** dual report / dispute |
| Games | **One Tier A game per cup** (start: 8 Ball Pool *or* FC Mobile — pick one) |
| Chain | **Default Arc** (same as product) |

### T2 decisions (when Host pass ships)

| Topic | Decision |
|-------|----------|
| Create gate | Active Host subscription **or** Center agreement **or** PLAY ≥ threshold *and* invite-only T4 |
| Public create | Host sub required |
| Host credit | **2% of pot** to host wallet (from pot, shown on card) *or* from platform share — prefer **from platform share** so prize card stays clean |
| Fee | 10% non-sub private experiments / **8% Host sub** / **6% Center** |
| Model B | Official + partners only until templates proven |

---

## 10. Open questions (intentionally later)

1. Exact Host plan price in USD / NGN / local rails.  
2. Whether 3rd-place match is mandatory for T8.  
3. Seeding: pure random vs PLAY-weighted.  
4. Multi-game “open format” cups (no — one game per cup).  
5. Fiat on-ramp inside join flow (Minipay etc.) — orthogonal.  
6. Legal packaging of “skill contest” vs jurisdiction (see `LEGAL.md`).

---

## 11. Implementation sketch (for engineering later)

```
tournament
  id, host_id, game_id, preset (4|8|16), entry_usdc,
  status (draft|open|locked|live|final|cancelled),
  visibility, payout_card_json, fee_bps, chain

tournament_entry
  tournament_id, profile_id, lock_tx, status (pending|locked|refunded)

tournament_match
  tournament_id, round, slot_a, slot_b, challenge_id (nullable),
  winner_id, status

tournament_payout
  tournament_id, profile_id, place, amount_usdc, tx_hash
```

Bracket generation: standard single-elim array.  
Each LIVE match: create challenge with `amount_usdc=0`, `tournament_match_id=…`, or synthetic challenge type `tournament_progression`.  
End: compute places → single resolver multi-send or N payouts from vault.

---

## 12. Summary for you (stillkenichi)

**Best structure:**

1. **Players** freely **join** cups.  
2. **Pots** are usually **everyone’s entry** (Model A).  
3. **Hosts** (later) pay a **subscription / agreement** for the *right to create* and get **lower fees + tools** — not for the right to play.  
4. **Host-seeded $100 prizes** are a **separate labeled mode** for official/sponsor — don’t confuse with entry pools.  
5. **v0 = Rematch hosts T4/T8 Model A only**, reuse 1v1 proof, pot settles at end.  
6. **Centers** are the natural Host customers; **subscription is B2B narrative**, not a tax on kids grinding 8-ball.

## 13. Implemented (v0 code) — dry-run ready

| Piece | Location |
|-------|----------|
| Service + bracket + JSON/Supabase store | `src/backend/services/tournament.py` |
| SQL (optional) | `sql/055_tournaments.sql` |
| Bot commands | `src/bot/handlers/tournament.py` |
| Local store default | `data/tournaments.json` |
| Unit tests | `tests/test_tournament_bracket.py` |

### Env flags

| Env | Default | Meaning |
|-----|---------|---------|
| `TOURNAMENTS_ENABLED` | `1` | Feature on/off |
| `TOURNAMENTS_MONEY_LIVE` | `0` | **Keep 0** until entry vault + payouts wired |
| `TOURNAMENT_FORCE_JSON` | unset | Force file store even if SQL exists |
| `TOURNAMENT_STORE_PATH` | `data/tournaments.json` | Local path |

### Ops runbook (first cup — no money)

1. Restart bot with `TOURNAMENTS_MONEY_LIVE=0`.
2. As @stillkenichi / admin:
   ```
   /tcreate 8 10 mobile.8_ball_pool Friday Night Pool
   ```
3. Share code. Players:
   ```
   /tjoin CODE
   /tstatus CODE
   /tlist
   ```
4. When 8 seats full:
   ```
   /tstart CODE
   ```
5. After each match, ops records winner:
   ```
   /twinner CODE R1-M0 @winner_tag
   ```
6. When final (and 3rd if any) done → status `final`, payout **plan** printed (not paid while dry-run).
7. Cancel if needed: `/tcancel CODE reason`

### When money goes live (later)

1. Apply `sql/055_tournaments.sql` in Supabase.
2. Implement entry vault lock in `join_tournament` (today raises if `MONEY_LIVE=1`).
3. Implement multi-payout on `final` from pot.
4. Set `TOURNAMENTS_MONEY_LIVE=1` only after a testnet dry cup with real locks.

---

*End of decision doc. Amend by editing this file; don’t fork parallel tournament specs.*
