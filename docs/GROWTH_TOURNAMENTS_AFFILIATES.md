# ClawStation — Growth Layers: Tournaments · Gaming Centers · Affiliates · Public Lobbies

**Status:** design + partial ship (centers QR · cups dry-run)  
**Date:** 2026-07-19 · ops update 2026-08-09  
**Builds on:** live 1v1 Arc escrow + short match codes + AI score proof  
**Ship notes:** `docs/ONILE_GAME_CENTERS.md` · `config/partners.yaml` · `?start=ctr_*` · Cups menu  
**Games (Tier A first):** EA FC → mobile → **physical IRL** → NBA 2K → …

---

## 0. North star

ClawStation is the **settlement + trust layer** for console skill bets.

| Layer | Who | Job |
|-------|-----|-----|
| **1v1 private** (live) | Friends | Stake, lock, play, AI proof, pay |
| **1v1 public** | Strangers | Fastest accept, 24h lock window |
| **Group tournaments** | Friend groups / hubs | Shared pot, bracket, top-3 pay |
| **Gaming centers** | Physical shops (NG) | QR onboard + % of volume |
| **Creators / streamers** | Twitch / TikTok / X | Referral link, % of referred volume |

Money only moves under clear rules: **open → matched → locked → outcome**.  
After both stakes lock, **no unilateral exit** (mutual cancel only).

---

## 1. Tier A games (product, not just a list)

### 1.1 Why Tier A first

Same verification pattern as today:

| Mode | Games | Proof |
|------|--------|--------|
| **Scoreline** | EA FC, NBA 2K, Madden, eFootball, UFL | FT screenshot + `H-A` |
| **BO sets** (later Tier A+) | Tekken, SF6, RL 1v1 | Set score / win screen |

### 1.2 Integration with tournaments

Every tournament match **reuses the existing 1v1 pipeline**:

```
Tournament bracket node
    → spawn Challenge (same ClawEscrow lock + AI settle)
    → winner advances
    → loser may go to 3rd-place path (8/16 presets)
```

No new chain primitive for v1 — only **orchestration** (bracket state machine + pot).

### 1.3 Per-game preset pack (when we ship)

For each Tier A title store:

- `game_id`, display name, platforms  
- default duration / no-show window  
- AI vision hints (home/away layout, “FT”, etc.)  
- allowed stake range  

---

## 2. Group tournaments (friend pods)

### 2.1 Core idea

A **tournament** is a shared USDC pool + a fixed-size bracket.

- N players (presets: **4 / 8 / 16**)  
- Each pays **entry fee** into the **whirlpool** (pot)  
- Single-elim bracket  
- **1st / 2nd / 3rd** (and optionally 4th) get payout shares  
- Played as a series of normal ClawStation matches  

### 2.2 Telegram surface

| Surface | Role |
|---------|------|
| **Bot DM** (now) | Wallet, 1v1, personal actions |
| **Group chat** (target) | Tournament room: roster, bracket, pings |
| **Mini App** (target) | Bracket UI, presets, join, standings, QR |

**Group “funnel” concept (optional social rule, not hard enforcement at first):**

1. Host creates tournament → bot posts invite + Mini App link in a **dedicated group**.  
2. Players join group + pay entry (or pay then get invite).  
3. When eliminated, bot **suggests leaving** the group (or auto-kicks if bot is admin — optional, phase 2).  
4. Group shrinks toward finalists → social pressure + cleaner chat.

Hard kick is **ops-heavy** (permissions, drama). Phase 1: soft (“You’re out — leave when ready”). Phase 2: bot as group admin can remove.

### 2.3 Presets only (v1) — custom later

| Preset | Players | Rounds | 3rd place? |
|--------|---------|--------|------------|
| **Quad** | 4 | SF + F + 3rd | Yes (SF losers) |
| **Octo** | 8 | QF → SF → F + 3rd | Yes |
| **Hex** | 16 | R16 → QF → SF → F + 3rd | Yes |

**Fixed rules v1 (example — adjustable):**

- Entry fee: host chooses `$X` (min/max by safety layer)  
- Settlement chain: host picks (default Arc)  
- Game: host picks from Tier A list  
- No-show: same as 1v1 (reporter photo path)  
- Platform fee: e.g. **7% of pot** (or of winnings — decide once)  
- Center/creator cut: taken from platform share or extra bps (see §3)

### 2.4 Example economics — 8-player, $10 entry

| Item | Amount |
|------|--------|
| Entries | 8 × $10 = **$80 pot** |
| Platform fee (7%) | $5.60 |
| Distributable | **$74.40** |

**Payout split (preset “standard”):**

| Place | Share of distributable | $ |
|-------|------------------------|---|
| 1st | 60% | $44.64 |
| 2nd | 25% | $18.60 |
| 3rd | 15% | $11.16 |

**Bracket flow (8):**

```
Quarterfinals (4 matches)
       ↓
Semifinals (2 matches)
       ├─→ Finalists → Final (1st vs 2nd)
       └─→ SF losers → 3rd-place match
```

**Who pays whom (implementation sketch):**

- **Option A (simple, recommended v1):**  
  All entries locked into a **tournament escrow vault** (or multi-match accounting).  
  After tournament resolved, one admin/resolver payout: 1st/2nd/3rd.  

- **Option B (reuse 1v1 only):**  
  Each bracket match is a normal 1v1 with stake = entry (or 0 stake + pot settles only at end).  
  Messier for 3rd place and multi-round accounting → **prefer Option A**.

### 2.5 4-player example (tight friend group)

Pot: 4 × $20 = $80 → fee $5.60 → $74.40  

| Place | % | $ |
|-------|---|---|
| 1st | 55% | $40.92 |
| 2nd | 30% | $22.32 |
| 3rd | 15% | $11.16 |

Matches: 2 semis + final + 3rd-place = **4 ClawStation matches**.

### 2.6 Lifecycle (state machine)

```
draft → open (collecting entry)
     → funded (N players paid)
     → seeding (random or host seed)
     → live (bracket matches)
     → finals
     → settled (payouts)
     → cancelled (refunds if not all locked into pot)
```

**Entry lock rule:** once status = `funded` / first match starts, **no refund** unless whole tournament cancelled by host **and** no match has locked, or mutual supermajority rule (define later).

### 2.7 Mini App screens (sketch)

1. **Create tournament** — size preset, game, entry, chain, visibility (group-only / public later)  
2. **Lobby** — paid / unpaid seats, countdown  
3. **Bracket** — tap match → opens bot flow for that node  
4. **Match room** — status, lock, submit (deep-link to bot)  
5. **Standings / payouts**  

Bot stays the **wallet + lock + proof** engine; Mini App is **orchestration UI**.

### 2.8 Integration with existing code

| Existing | Tournament use |
|----------|----------------|
| `challenges` + ClawEscrow | Each bracket node |
| Short `public_code` | Per match |
| AI vision | Per match proof |
| Settlement job | Per node, then tournament payout job |
| New tables (later) | `tournaments`, `tournament_entries`, `bracket_nodes`, `tournament_payouts` |

---

## 3. Gaming centers (Nigeria GTM)

### 3.1 Reality check

Thousands of cafes / “game centers” with PS5/Xbox. They already:

- Rent consoles by the hour  
- Host local 1v1s and side bets informally  
- Have trust in the room, not on-chain  

ClawStation becomes: **their cashier + fairness + remote payout**.

### 3.2 Center profile

| Field | Example |
|-------|---------|
| Business name | “Lagos Arena Ikeja” |
| Owner Telegram / phone | … |
| Location (city, area) | Ikeja |
| `center_code` / QR | `CS-CTR-IKEJA01` |
| Referral link | `t.me/ClawStationBot?start=ctr_IKEJA01` |
| Cut | 1–2% of **matched volume** they origin |
| Status | pending / active / suspended |

### 3.3 In-shop flow

1. Two players at the same center want to stake.  
2. Attendant shows **QR** (or shared link).  
3. Both open Telegram → `/start ctr_IKEJA01` → wallets created if needed.  
4. One creates challenge (or attendant creates via Mini App “desk mode”).  
5. Both lock on Arc (or Base).  
6. They play on the center’s console.  
7. Submit FT photo → settle as today.  
8. Ledger credits **center_id** with `volume_bps` (e.g. 150 bps = 1.5%).  

**Where does center cut come from?**

- Prefer: **from platform fee**, not on top of players  
  - Platform 7% → split e.g. 5.5% ClawStation + 1.5% center  
- Alternative: players see “shop fee” — worse UX  

### 3.4 Desk mode (later)

Mini App for attendant:

- Create 1v1 for two seated players  
- Show lock status on a big screen  
- Don’t need each player to be UI experts  

### 3.5 Why this drives adoption

- Centers already have **supply of players and hardware**  
- Revenue share = sales force  
- Offline trust + online escrow = product fit for NG  

---

## 4. Creators / streamers / “bragging rights” referrals

Same plumbing as centers, different skin.

| Partner type | Onboard | Cut idea (draft) |
|--------------|---------|------------------|
| Gaming center | QR, location | 1–2% of volume forever (while active) |
| Creator / Twitch | `?start=ref_xyz` | **Boosted early, then residual** |
| Organic friend | plain `/start` | none |

### 4.1 Example creator economics (adjustable)

- Games 1–5 of a referred user: **3%** of that user’s matched stake volume  
- Games 6+: **1%** lifetime (or until policy change)  
- Cap / sunset option: after 50 games, residual ends or drops to 0.5%  
- Always paid from **platform fee**, not extra tax if possible  

### 4.2 Attribution

- First-touch `ref` / `ctr` on profile (`referred_by`, `partner_id`)  
- Every settled match with volume → `partner_ledger` row  
- Payout cadence: weekly USDC to partner wallet  

### 4.3 Anti-abuse

- Self-referral ban  
- Same device / wallet clusters  
- Center only earns if **both** players attributed or challenge tagged `center_id`  
- Pause partner if chargeback / fraud flags  

---

## 5. Public challenges (“fastest fingers”)

### 5.1 Goal

Move from only private friend challenges → **open board**.

### 5.2 Flow

```
Creator: New public challenge
  game, stake, chain, optional note
       ↓
Broadcast (Telegram channel + in-bot “Open challenges” + optional push to opted-in users)
       ↓
First acceptor wins the seat (atomic accept)
       ↓
Both must LOCK within T hours (default 24h from accept)
       ↓
If either fails to lock → challenge void / reopen, no money stuck
       ↓
Both locked → HOME/AWAY → play → proof → settle
```

### 5.3 Time rules (your model, cleaned)

| Stage | Can leave? | Rule |
|-------|------------|------|
| **Open (no acceptor)** | Creator cancel free | Unilateral cancel |
| **Accepted, not both locked** | Yes | Either side can cancel / timeout 24h → void |
| **Both locked** | No unilateral | Must play or **mutual cancel** |
| **One wants cancel after lock** | Needs other to confirm | Else stays live → no-show / dispute paths |

### 5.4 Notifications

- Users toggle: **Public invites ON/OFF**  
- When ON: Telegram notification for public offers matching filters (game, max stake, chain)  
- Rate-limit spam  

### 5.5 Visibility flags (per challenge)

- `private` — invite only (current)  
- `public` — open board  
- (later) `center` — only that shop’s desk  
- (later) `group` — only tournament group members  

---

## 6. Cancel / forfeit rules (unified)

Applies to 1v1 and tournament nodes.

```
                ┌──────────────┐
                │   OPEN       │  creator cancel OK
                └──────┬───────┘
                       │ accept
                ┌──────▼───────┐
                │  ACCEPTED    │  either cancel OK / 24h lock deadline
                │  (0–1 lock)  │
                └──────┬───────┘
                       │ both locked
                ┌──────▼───────┐
                │   LOCKED     │  mutual cancel only
                │              │  else play / no-show / dispute
                └──────────────┘
```

**Mutual cancel after lock:**

1. Player A taps **Propose cancel**  
2. Player B must **Confirm cancel** within window (e.g. 6h)  
3. Escrow refunds both (minus optional tiny cancel fee?)  
4. If B refuses → match continues  

This matches: *“once money is locked, there must be an outcome unless both agree to stop.”*

---

## 7. How the pieces compose

```
                    ┌─────────────────────┐
                    │   Partner layer     │
                    │ centers · creators  │
                    │ QR / ref links      │
                    └──────────┬──────────┘
                               │ attributes volume
┌──────────────┐    ┌──────────▼──────────┐    ┌────────────────┐
│ Public board │───▶│  Challenge engine   │◀───│ Tournament     │
│ fastest      │    │  (lock · AI · pay)  │    │ bracket + pot  │
│ accept       │    └──────────┬──────────┘    └────────────────┘
└──────────────┘               │
                               ▼
                    ┌─────────────────────┐
                    │ Arc / Base / Fuji   │
                    │ ClawEscrow + USDC   │
                    └─────────────────────┘
```

**Adoption flywheel (NG-first):**

1. Centers + friend bragging rights → volume  
2. Creators amplify  
3. Public board → strangers  
4. Tournaments → retention / bigger pots  
5. Global when public + multi-language + more games  

---

## 8. Suggested build phases

### Phase 0 — now (done / almost)
- 1v1 private, multi-chain, AI proof, short codes, mutual safety basics  

### Phase 1 — cancel + public (product glue)
- Unilateral cancel pre-lock  
- Mutual cancel post-lock  
- Public challenge board + 24h lock window  
- `visibility` already partial  

### Phase 2 — partners (GTM)
- `partners` + QR deep links  
- Attribution on profile  
- Ledger + 1–2% from fee split  
- Center dashboard (simple)  

### Phase 3 — tournaments (retention)
- Presets 4 / 8 only (16 later)  
- Mini App bracket  
- Tournament pot escrow  
- Soft group-chat integration  

### Phase 4 — Tier A games catalog
- 2K, Madden packs + AI prompts  
- BO preset for fighters/RL  

### Phase 5 — polish
- Custom tournament rules  
- Auto kick from group  
- Global discovery, filters  

---

## 9. Data model sketch (for later implementation)

```
partners (
  id, type [center|creator], code, name, cut_bps,
  boost_cut_bps, boost_first_n_matches, owner_profile_id
)

profiles (
  ... existing ...,
  referred_by_partner_id,
  public_invites_enabled
)

tournaments (
  id, public_code, host_id, preset [4|8|16],
  game, entry_usdc, chain, status, group_chat_id,
  pot_usdc, fee_bps, payout_schema jsonb
)

tournament_entries (
  tournament_id, profile_id, paid_tx, seat, eliminated_at
)

bracket_nodes (
  tournament_id, round, slot,
  challenge_id null, player_a, player_b, winner_id
)

partner_ledger (
  partner_id, challenge_id, volume_usdc, cut_usdc, status
)
```

---

## 10. Decisions (frozen + open)

| Topic | Decision |
|-------|----------|
| **Center / partner cut** | **From platform fees only.** Never a second tax on players. Cap so winner still gets full post-fee payout. |
| **Creator residual** | **Lifetime until further notice.** Policy can change later via admin/config; keep documented. |
| **Architecture** | **Everything new reuses today’s 1v1 match.** |
| **Tournament pot** | See options A/B/C in `PHASES_1_2_3_SAFE_DESIGN.md` (prefer A when built). |
| **Group kick** | TBD (soft leave first). |
| **Public spam** | Opt-in for pushes; browse board always. |

**Safe build order detail:** `PHASES_1_2_3_SAFE_DESIGN.md`  
1. Cancel → 2. Public board + 24h lock → 3. Partners + QR  

---

## 11. What “success” looks like

| Metric | Signal |
|--------|--------|
| Center weekly volume | QR works IRL |
| % matches with partner_id | Affiliate flywheel |
| Tournament completion rate | Bracket not abandoned |
| Public accept → dual lock rate | 24h rule is right |
| Mutual cancels post-lock | Healthy safety valve |
| 2K/Madden share of matches | Tier A expansion |

---

## 12. Immediate next design steps (still not code)

1. **One-pager tournament preset table** (exact % for 4 and 8) frozen for v1.  
2. **Cancel UX wireframes** (pre-lock / post-lock mutual).  
3. **Partner QR mock** (`start=ctr_XXX` payload).  
4. **Public board mock** (list + accept race).  
5. **Pick first Tier A add-on:** NBA 2K (scoreline clone of FC).  

---

*This document is brainstorming for product integration. Implementation should follow after freezing presets and fee splits.*
