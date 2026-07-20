# Phases 1–3: Cancel · Public board · Partners — safe design

**Goal:** ship trust + discovery + GTM **without breaking** live 1v1 Arc escrow.  
**Hard rule:** every stake is still today’s **1v1 challenge** (`open → accepted → lock → play → proof → settle`).  
New features only add **buttons, timers, attribution, listing** — not a second money path.

**Status:** design only (implement later, behind flags where useful)

---

## Frozen product decisions

| Topic | Decision | Notes |
|-------|----------|--------|
| **Center cut** | **From platform fees only** | Players still see one fee (e.g. 7%). Split is internal. Never stack a second “shop tax” on the stake. |
| **Creator residual** | **Lifetime until further notice** | Documented policy; can be changed by admin config later, not by code hardcode. |
| **Tournaments** | Later | Pot options explained in §6; not in build order 1–3. |
| **Group kick** | TBD | Soft leave first when we get there. |

### Fee split example (illustrative)

Match pot after both lock: $20 → winner gets 93% = $18.60, **platform fee $1.40**.

If match attributed to a center at **1.5% of stake volume** (or of fee — pick one in impl; recommend **% of platform fee** so math always fits):

- Simpler rule for v1: **center/creator share = min(configured bps of volume, remaining platform fee)**  
- Or: **X% of the 7% fee** (e.g. center gets 20% of fee = 1.4% of pot).  

**Documented default proposal:**

- Platform fee: `700 bps` of pot (existing)  
- Partner cut: `partner.cut_bps` of **matched stake volume**, **paid only from fee**  
  - If partner cut would exceed fee, **cap at fee** (ClawStation takes $0 that match, partner takes fee).  
  - Never reduce winner payout below `(100% − fee_bps)`.

Creator boost (optional config, not code law):

- First `boost_first_n` settled matches for a referred user: higher `boost_cut_bps`  
- After that: `cut_bps` **lifetime until further notice**

---

## Non-break principles

1. **Additive only** — new columns optional; old challenges keep working.  
2. **No change to lock/join/resolve math** unless fixing a bug.  
3. **Feature flags** in env:  
   - `FEATURE_CANCEL_UI=1`  
   - `FEATURE_PUBLIC_BOARD=1`  
   - `FEATURE_PARTNERS=1`  
4. **Callbacks / statuses** stay the same names; only add new statuses if required:  
   - already have: `open`, `accepted`, `creator_locked`, `locked`, `playing`, `submitted`, `disputed`, `resolved`, `cancelled`, `expired`, `declined`  
5. **Reuse** existing `cancel_match()` (on-chain refund) for **post dual-lock** mutual cancel only.  
6. **Pre-lock cancel** = DB status flip only (no chain call if nothing locked).

---

## Phase 1 — Cancel rules

### 1.1 User rules (product)

| State | What “cancel” means | Who |
|-------|---------------------|-----|
| `open` | Withdraw invite | Creator only |
| `accepted` (0 locks) | Walk away, no money moved | Either party |
| `creator_locked` (only creator locked) | **Special** | See below |
| `locked` / `playing` / `submitted` | Propose stop | Either → other must confirm |
| `resolved` / `cancelled` | No | — |

### 1.2 Creator-only locked (critical, don’t break escrow)

Today: creator can `createMatch` → status `creator_locked` with **on-chain** stake.

If opponent never locks:

- **Timeout path (recommended, job already-ish):** after `LOCK_TIMEOUT_HOURS` (default 24 from accept or from creator lock), auto **on-chain cancel** → refund creator.  
- **Manual path:** creator taps **Cancel** → calls existing `cancel_match()` → refund creator (and opponent if any).  
- Opponent **cannot** cancel creator’s locked funds alone without timeout or creator action (or admin).

If we only set DB `cancelled` without chain cancel while `creator_lock_tx` exists → **funds stuck**. Design must always:

```
if any lock_tx present → cancel_match() on-chain
else → DB status cancelled only
```

### 1.3 Mutual cancel after both locked

```
A taps "Propose cancel"
  → status stays locked
  → fields: cancel_proposed_by, cancel_proposed_at
B taps "Confirm cancel"
  → cancel_match()  // existing escrow refund both
  → status cancelled
B ignores / rejects
  → after CANCEL_CONFIRM_HOURS clear proposal OR stay live
  → match continues (report / no-show paths unchanged)
```

### 1.4 UI (additive)

On **My match** menu, only when allowed:

- `open` / `accepted`: button **Cancel match**  
- `creator_locked`: creator sees **Cancel & refund my lock**  
- `locked`/`playing`: **Propose cancel** / **Confirm cancel**  

No change to lock or submit buttons.

### 1.5 What we do **not** touch in phase 1

- Settlement / AI / resolve  
- Arc wallet binding  
- Fee % on win  

### 1.6 Implementation order (safe)

1. Helper `can_cancel(profile, challenge) → {mode: free|refund_creator|mutual_propose|mutual_confirm|none}`  
2. Handler `ui:cancel:*` + `/cancel MATCH_CODE`  
3. Wire refund only through existing `cancel_match`  
4. Job: expire `accepted` / `creator_locked` after 24h  
5. Tests: private 1v1 still locks and settles  

---

## Phase 2 — Public board + 24h lock

### 2.1 What already exists (don’t rewrite)

- Challenges already have `visibility` = `public` | `private`  
- Create path in `/challenge` and UI can set public  
- Accept already sets `opponent_id` + `accepted`  

**Gap today:** no good **browse list**, no **race-safe accept**, weak **24h lock deadline** UX.

### 2.2 Public flow (reuse 1v1)

```
Creator creates challenge visibility=public, opponent_id=null
  → appears on "Open challenges"
First successful accept (atomic)
  → opponent_id set, status=accepted, accepted_at=now
  → removed from board
Both have until accepted_at + 24h to complete dual lock
  → if not both locked → cancel_match if needed + status expired/cancelled
Both locked → same as private forever after
```

### 2.3 Race safety (don’t break private)

```sql
-- conceptual: only one acceptor
UPDATE challenges
SET opponent_id = $accepter, status = 'accepted', accepted_at = now()
WHERE id = $id AND status = 'open' AND opponent_id IS NULL
  AND (visibility = 'public' OR opponent_id was already intended)
```

Private keeps: only intended `opponent_id` may accept (existing check).

### 2.4 24h lock window

| Clock starts | When status becomes `accepted` (or first of accept / creator_lock — pick **accepted**) |
| Deadline | `accepted_at + LOCK_WINDOW_HOURS` (24) |
| On expiry | If not `locked`: cancel + refund any single-side lock |

**Does not apply** to pure private until you opt in — or apply to all for consistency.  
**Proposal:** apply **same 24h after accept** to **all** matches (private + public). Predictable, one code path. Private friends can re-create if slow.

### 2.5 Board UX (bot first, Mini App later)

- Main menu: **Open challenges**  
- List: game, stake, chain, age, short code  
- **Accept** button → same accept handler with atomic update  
- Creator: still sees **My match**  

Optional: `public_invites_enabled` on profile for push — **off by default** so we don’t spam.

### 2.6 What we don’t do in phase 2

- No separate “public escrow”  
- No changing fee  
- No auto-notify everyone on earth without opt-in  

---

## Phase 3 — Partners + QR (centers & creators)

### 3.1 Mental model

Partner does **not** run a different bet. They **tag volume**.

```
User opens t.me/Bot?start=ctr_IKEJA01  or  ref_TWITCHBOB
  → profile.referred_by_partner_id set (first-touch, sticky)
Challenge settled
  → if partner attributed → partner_ledger credit FROM FEE ONLY
```

### 3.2 Attribution rules

| Event | Attribution |
|-------|-------------|
| `/start <payload>` | Set partner if empty (first touch wins) |
| Challenge has `partner_id` override | Desk mode later (center forces tag) |
| Settled match | Volume = `2 * stake` (both sides) or `stake` — **define once: use `2 * amount_usdc` matched volume** |
| Cut | `cut_usdc = min(volume * cut_bps/10000, fee_usdc)` |

**Lifetime (creators):** keep earning on every later settled match of that user until admin changes policy (“until further notice”).

**Centers:** same ledger; may also require physical presence later; v1 = same ref link.

### 3.3 Deep link format (Telegram)

```
?start=ctr_IKEJA01     → partner type center, code IKEJA01
?start=ref_CREATOR99   → partner type creator
?start=                → normal
```

Store partners in table; invalid code → ignore, still onboard user.

### 3.4 Tables (additive)

```
gaming.partners (
  id uuid PK,
  code text UNIQUE,          -- IKEJA01
  kind text,                 -- center | creator
  name text,
  owner_profile_id uuid,
  cut_bps int,               -- e.g. 150 = 1.5% of volume, capped by fee
  boost_cut_bps int null,    -- e.g. 300 for first N
  boost_first_n int null,    -- e.g. 5
  lifetime_until_notice bool default true,
  active bool
)

-- profiles
referred_by_partner_id uuid null
partner_attributed_at timestamptz null

gaming.partner_ledger (
  id, partner_id, challenge_id, profile_id,
  volume_usdc, fee_usdc, cut_usdc, status [pending|payable|paid]
)
```

### 3.5 Settlement hook (minimal, safe)

In `_notify_result` / after successful `resolve` **only**:

```
if challenge resolved with winner:
  fee = pot * fee_bps
  partner = profile.referred_by or challenge.partner_id
  if partner active:
    insert ledger row (idempotent by challenge_id + partner_id)
```

**Do not** change payout amount to winner.  
**Do not** fail settlement if ledger insert fails (log + retry job).

### 3.6 Payout to partners

- Separate weekly job / admin export  
- Not automatic on every match in v1 (reduces risk)  
- Partner balance = sum(payable) − paid  

### 3.7 QR for centers

- Generate URL → QR image (static)  
- Printed at desk: “Both open Telegram → scan → play”  
- Same as deep link; no new money rail  

---

## Phase order & flags

```
Phase 1 cancel     FEATURE_CANCEL_UI
Phase 2 public     FEATURE_PUBLIC_BOARD  (+ shared 24h lock job)
Phase 3 partners   FEATURE_PARTNERS
```

Ship **1 → 2 → 3**. Each behind flag; default off on production until smoke-tested on Arc testnet with stillkenichi / osaborme.

---

## Regression checklist (run after each phase)

| Flow | Must still work |
|------|-----------------|
| Private challenge create / accept | ✓ |
| Dual lock Arc | ✓ |
| AI screenshot + settle | ✓ |
| Winner payout correct address (chain wallet) | ✓ |
| Short match codes | ✓ |
| Dispute + support_id | ✓ |
| New cancel | Only when allowed; no stuck funds |
| Public accept | Atomic; second user fails cleanly |
| Partner | Zero impact if `FEATURE_PARTNERS=0` |

---

## Tournament pot options (for later — not phases 1–3)

Still **1v1 matches per bracket node**. Difference is only **where entry money sits**.

### Option A — **End pot vault** (recommended when we build tournaments)

- Everyone pays **entry** into a **tournament pot** (one escrow account or contract).  
- Bracket matches are **$0 stake** or **symbolic** 1v1 for result only.  
- After finals: pay 1st/2nd/3rd from pot (minus fee from pot).  

**Pros:** clean 3rd place, one fee, simple payouts.  
**Cons:** needs pot accounting / maybe small contract or custodial pot wallet.

### Option B — **Each match is a real 1v1 stake**

- QF/SF/F are full stake locks.  
- Winner takes each match pot.  

**Pros:** zero new money system.  
**Cons:** **breaks** 1st/2nd/3rd prize model (3rd-place match economics weird; early exits lose more).

### Option C — **Hybrid**

- Entry to pot for 1st/2nd/3rd.  
- Optional small side-stake on final only.  

**Pros:** flexible.  
**Cons:** two money concepts for users.

**Recommendation when ready:** **Option A**, still using today’s 1v1 **only for result + proof**, pot for money.

---

## What we will not implement in this pass

- Tournament Mini App  
- Group auto-kick  
- Changing on-chain fee bps  
- Breaking private-only users  

---

## Suggested first code slice (when you say go)

**Slice 1a only:** pre-lock cancel (DB) + creator_locked refund via existing `cancel_match` + button on My match.  
No public board, no partners yet. Smallest risk, biggest trust win.

---

*Partners: fee-only. Creators: lifetime residual until further notice. Everything reuses 1v1.*
