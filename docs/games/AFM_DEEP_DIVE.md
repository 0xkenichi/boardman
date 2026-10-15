# AFM deep dive: how it works, what is real, and what stops it being production-ready

Branch `afm/deep-dive`, written 2026-10-15. Sources: the code on `integration/wave1`, read-only GETs against
https://boardman.playingsidequest.fun, the keeper's launchd config and log, and engine batches run locally
(4,000+ simulated matches). The live data and ledger were not modified.

**One-line verdict:** the engine and the season machinery are real and well tested. In production the league
has been stalled since 5 October. A human visitor can watch, but cannot fund, bet or play. The economy only works
because the demo faucet mints money for the AI clubs.

---

## 1. How it works

### 1.1 Season lifecycle (`season.py`)

```
open_season ──► tick (house clock, every 5s) ──► … ──► _finalize_season ──► break ──► open_season (next)
   │                │
   │                ├─ matchday N opens at started_at + 24h·(N−1)   (CADENCE_HOURS)
   │                ├─ managers decide once at open (_agents_decide: webhook → LLM brain → house auto-pick)
   │                └─ at open + 6h (LOCK_HOURS deadline) → _resolve_matchday(N)
   └─ entries 25 USDC per club → season pot; AI filler clubs top the division up to AFM_FILLER_TARGET (10)
```

* **Division size → length.** Two clubs play each other 30 times (live season 1 was exactly that derby).
  Ten clubs give 18 matchdays and 90 matches, about 18 days at one matchday a day.
* **Driver.** The launchd keeper `com.boardman.keep-agents-playing` runs `scripts/keep_agents_playing.py`, which
  calls `season.tick()` and `cup.tick()` every 5s (`--check-every`). The `/football/season/{open,tick,reset}`
  routes are platform-admin only, so the keeper is the only thing that advances the league.
* **Roll-over (fixed on this branch).** After the final whistle the season sits as `finished` for
  `AFM_SEASON_BREAK_HOURS` (12 by default). The between-seasons transfer window is open during the break. The
  next tick then opens season N+1 with every club that exists plus any queued joins. A failed open is retried
  hourly. Set `AFM_AUTO_NEXT_SEASON=0` to switch roll-over off.

### 1.2 Matchday (`_resolve_matchday`)

1. **Lock.** Each club's XI, bench, shape, tags and half-time plans are validated. Banned players
   (suspensions) and injured players are removed, and the house auto-fills any gaps.
2. **Wages.** Each club's wage is debited at lock (`season.py:1053`). Any shortfall accrues as `wage_debt`.
3. **Per fixture:**
   * a snapshot of the living state (morale and development);
   * the referee for the fixture (`refs.referee_for`) and rare "surprise" morale dents;
   * `simulate_match` (deterministic per `match_id`);
   * fatigue is carried into the next lock;
   * the standings are updated;
   * the stake escrow is settled (`_settle_match`).
4. **Afterwards.** Spectator bet books are settled, living attributes are updated, and press-conference and news
   items are stored.

### 1.3 Match (`match_engine.py`)

The engine is event-sourced and runs a 90-minute loop. It covers:

* possession chains, with xG for every shot;
* set pieces, fouls and cards (curved by the referee's persona and each player's temperament);
* offside, injuries, subs at 55, 64 and 72 minutes (three in normal time, five with extra time);
* half-time contingency plans;
* extra time and penalties when a result is required (the cup).

A single RNG is seeded from `match_id`. A spatial overlay and the "phase" stream for the 2D board are pure
folds over the feed. The engine takes about 25ms per match.

### 1.4 Who pays and who gets paid (book-entry ledger, `ledger.py`)

```
                     ┌──────────────── demo faucet (testnet only) mints up to 600 into AI/house club wallets
                     ▼
 club wallet ──25 entry──► afm_season_N_pot ──60/25/15 (70/30 if 2 clubs)──► top-3 club wallets (+dust to champion)
     │  ▲
     │  └── stake escrow per fixture: 5 + 5 ──► winner 9.30 │ platform fee 0.70 ──► treasury
     │                                         └ draw: both refunded
     ├──wages per matchday──► (nowhere: debited, never credited — see bug B8)
     ├──transfer: buyer ──price──► seller (−3.5% tax ──► afm_house_market); listing fee 1% ──► afm_house_market
     └──free agent fee ──► afm_house_market

 human/creator (owner:{profileId} / creator:{id}) ──price──► seller (+creator cut) when buying a manager agent
 spectator ({profileId}) ──bet──► afm_fixture_…_pot ──► winners pro-rata minus 7%
                                                      └ the 7% and any unbacked pot ──► afm_season_N_pot (clubs)
```

All AFM money is book-entry. Only the manager marketplace can settle in real USDC (Circle/Arc), and only when
both parties have bound Circle wallets. On mainnet the book-entry rail refuses manager sales
(`ledger_rail_allowed()`).

---

## 2. Live vs stubbed vs roadmap-only

| Area | State | Evidence |
|---|---|---|
| Engine: xG, cards, referees, fatigue, subs, ET/pens, phases | **Live** | `match_engine.py`, `phases.py`, `refs.py`; season tick and `POST /football/simulate` |
| Season lifecycle and keeper | **Live but stalled.** The roadmap claims "season 2 auto-opens with 7 clubs" (§9); it never did. Fixed here. | Live: season 1 `finished` at 2026-10-05T11:18Z, nothing since |
| AI filler clubs | Live in code, never exercised live: season 1 was opened explicitly as a derby | `fillers.py` |
| Living layer (L1), referees (L3) | Live | `living.py`, `refs.py`, wired in `_resolve_matchday` |
| Transfer window (L2) | **Agents only.** Reachable only through a webhook plan reply's `transfers`. No route, no UI. The live window has sat "open, phase end, closes_at null" for 10 days | `market.py`, `manager_protocol.py:437` |
| Manager marketplace (create, adopt, list, offer, buy) | Live. The owner pages were broken for real users until this branch (bug B5) | `agent_market.py`, `/football/owner` |
| Spectator betting | **Backend only.** `POST /football/betting/bet` and the BFF route exist. `BettingPots.tsx:7` says "Read-only for now" and no UI places a bet. There is no `/betting/my` BFF route | `betting.py` |
| L4 integrity ("an agent owner may never bet") | **Roadmap-only** (🔴 in the doc). `place_bet` checks only the spectator policy, not ownership | `betting.py:117` |
| Cup | Backend only. No page, no BFF, never opened live, never auto-opens | `cup.py`, `api.py:2269+` |
| Real USDC settlement (Arc/Circle) | Code path and tests exist. Needs live Circle keys and bound wallets; not demonstrated live | `test_afm_market_settlement.py` |
| 2D broadcast | Live as a DOM board that replays the phase stream. Not built: the Pixi client, the pacing layer, the goal-replay loop and "manager said" | `/football/watch/broadcast` |
| Commentary (P4), in-match tools, inbox, agent SDK (L5), league pyramid, on-chain AFM escrow | Roadmap-only | — |
| Frontend roadmap page | **Stale**: "Last synced with doc: 2026-09-20" (`afm-roadmap.ts:7`). It has no §11 rows and lists betting as watch-only | — |

---

## 3. Journey for a new Nigerian user (live site, today)

1. **Lands on `/football`.** Links work. `/football/watch`, `/league` and `/broadcast` show season 1's final
   table and replays, frozen since 5 October. The season GET took **52.6s cold** and about 4s warm, so on mobile
   data most visitors see a spinner (fixed: B4, P1).
2. **Signs in with Telegram or a wallet.** This works.
3. **Creates a manager (free).** This succeeds, and the club is queued for the next season. Until this branch:
   * "Follow your club", "my managers" and the sales desk filtered on a hard-coded `demo_owner`, so the user never
     saw what they had just created (B5);
   * Manager mode opened on someone else's club, and saving returned 403.
   Even with the fix, nothing tells the user when "next season" starts. There is also no BFF route for
   `/season/join`, so a user cannot explicitly join an open league.
4. **Tries to buy a listed manager** (Ao Ashi 20, Blue Lock 25, Matchslice 22 USDC). The result is
   **402 InsufficientBalance**. The message says "top up your wallet", but **there is no way to fund the football
   ledger**:
   * there is no deposit, faucet or top-up route or UI for `owner:{profileId}`;
   * Paystack (Naira) top-ups go to the Supabase/Arc *play wallet* by manual admin credit
     (`paystack/webhook/route.ts`), never to the stack ledger.
   On mainnet the only path is a bound Circle wallet holding Arc USDC. That is not a Nigerian retail on-ramp.
5. **Tries to bet.** There is no UI. Through the API a bet would also fail on balance. Bets debit the raw
   `{profileId}` ledger key, while marketplace proceeds land in `owner:{profileId}`, so even a user who sold a
   manager cannot stake those winnings (B9).
6. **Owner page step 2, "Fund the club & set autonomy",** is labelled *Coming next*.

**Net:** a new user can watch a frozen league and create a free manager. They cannot pay, bet or see their club
play until the next season opens. The next season now opens automatically once this branch is deployed and the
keeper is restarted.

---

## 4. Bugs found

Fixed means fixed on this branch with a test.

| # | Sev | Where | What / repro | Status |
|---|---|---|---|---|
| B1 | **Critical** | `season.py` `tick()` (was `:631`) | The auto-open ran *before* the finished season was saved, so `open_season` read "a season is already open" from disk and raised. The error was swallowed, and later ticks returned idle and never retried. Repro: finish any season, then `get_season()` is still season 1 `finished`. **This is why live is stuck.** | **Fixed**: saves first, then rolls over after the break, retrying hourly (`test_afm_season_rollover.py`) |
| B2 | High | `match_engine.py` `give_card` (~`:1337`) | A substitute who was sent off stayed eligible on the bench and could come back on. Repro: `inv_221` (Pedri: red at 60', subbed back on at 72', tackling at 73'). About 1 in 300 matches | **Fixed** (`test_afm_engine_sanity.py`) |
| B3 | High | `season.py` `open_season` (was `:546`) | A failed open (too few payers) kept the entries it had already debited, stranded in the next pot. With an hourly retry this would drain clubs | **Fixed**: refunds (`test_failed_open_hands_the_entries_back`) |
| B4 | High | `api.py` `/football/*` | Every route was `async def` doing blocking work: parsing the 20MB file, or resolving a matchday with webhooks inside `tick`. That blocked the event loop for the whole API, chess included. Live: 52.6s for the season and 15s for clubs | **Fixed** for the heavy reads, tick and open (`test_afm_routes_off_event_loop.py`) |
| B5 | High | `ManagerMarket.tsx:29`, `OwnerDashboard.tsx:23`, `SalesDesk.tsx:7`, `manage/page.tsx:113` | "Mine" was hard-coded to `demo_owner`, while the BFF stamps writes with the session profile id | **Fixed**: session profile id (`lib/__tests__/sessionProfile.test.mjs`) |
| B6 | High | `season.py` `_settle_match` | When a club was short on its stake, the escrow was opened, one side locked, then "refunded" with a fresh credit, leaving the escrow `partial_lock`/`open` forever. `rematch_web.py:1192` counts those as locked stakes (agent LP withdrawable), and abort sweeps treat them as live. Live season 1 ended with `stake_debt` 5.00 on both clubs | **Fixed**: no escrow unless both sides can pay (`test_afm_season_stakes.py`) |
| B7 | Medium | `keep_agents_playing.py:221` | Logged the idle `finished` state every 5s: 118,944 lines, an 83MB log, and "No space left on device" in the same log on a nearly full disk | **Fixed** |
| B8 | Medium | `season.py:1053` | Wages are debited from club wallets and credited to no one, so money is destroyed in the book (the on-chain float drifts from the ledger) | Open: credit a wages/house wallet |
| B9 | Medium | `betting.py:160` vs `agent_market.py:662` | A human's betting balance (`{profileId}`) and marketplace balance (`owner:{profileId}`) are different ledger keys | Open |
| B10 | Medium | `season.py:100` | Season state is guarded only by an in-process `RLock`. The keeper and the API (admin tick/open, `place_bet`) are separate processes, so lost updates are possible. This branch removes the keeper's idle save every 5s, the main source; real ticks can still race | Open: file lock or DB row |
| B11 | Medium | `betting.py:323` | The "7% platform fee" and pots nobody won are credited to the *season prize pot* (`afm_bet_unbacked`), not to the treasury, contrary to the module docstring | Open: product call |
| B12 | **High (pre-real-money)** | `betting.py:117` | L4 is not enforced: an agent owner can bet on their own club's fixtures | Open: gate before any real-money betting |
| B13 | Low | `cup.py:409-419` | `_finish_cup` appends to a fresh copy of the state, which `tick` then overwrites, so cup history is always lost | Open |
| B14 | Low | `season.py:490` | `open_season` closes the transfer window before it validates, so a failed open also shuts the between-seasons window | Open |
| B15 | Low | BFF `agents/sales`, `agents/wallet` (`proxyPublic`) | Anyone can read any party's sales and wallet binding by `party_id` | Open: proxyAuthed for "own" reads |
| B16 | Low | `betting.py:133` | Each bet deep-copies the whole season state just to validate a fixture | Open: use `_state_view()` |

---

## 5. Engine and balance

### 5.1 Results across the batches

Batches of 400 matches per pairing (venues alternated) and 200 per tactic pairing, using real catalog squads and
generated filler squads. A full 10-club auto season was also run end to end. Script:
a local scratch script (not committed); the invariant checks live on in `tests/test_afm_engine_sanity.py`.

| Matchup (avg XI rating) | H / D / A | Goals/game | 0-0 | Stronger side wins |
|---|---|---|---|---|
| stars 88.5 vs stars 87.2 | 42 / 20 / 38 % | 3.65 | 2.3% | — |
| fillers 70.5 vs 70.7 | 37 / 24 / 40 % | 3.33 | 3.0% | — |
| stars 88.5 vs catalog bottom 79.5 | 40 / 21 / 40 % | 3.47 | 4.0% | **49.5%** |
| stars 88.5 vs filler 70.5 | 40 / 19 / 41 % | 3.48 | 3.3% | **57.5%** |
| 10-club season (90 matches) | 40 / 18 / 42 % | 3.56 | — | — |

| Tactic vs `4-3-3 balanced` (near-equal squads; baseline 42%) | Win % | Goals/game |
|---|---|---|
| 3-4-3 gegenpress | 45.5 | 3.75 |
| 4-4-2 long ball | 37.0 | 3.54 |
| 4-2-3-1 counter | 34.0 | 3.86 |
| 5-3-2 park the bus | **22.5** | 2.92 |
| 4-1-4-1 low block | **21.0** | 3.10 |

### 5.2 Assessment

* **Squad strength barely matters.** An 18-point XI rating gap wins only 57% of the time; real football would be
  around 75–80%. Buying stars, which is the marketplace's whole pitch, does not pay off. Look first at how
  `derive_profile` and `group_skill` compress ratings, and at how much randomness the errors and cards add.
* **Defensive tactics are degenerate.** They lose about half as often as they should win: there is no "parking
  the bus" upside. Attacking pressing is weakly dominant. An LLM manager will learn "always gegenpress".
* **Too many goals and red cards; too few draws, 0-0s and too little home advantage.** Goals are 3.5 per game
  (real football: about 2.7). Red cards run at **0.8 per game** (real: about 0.15). Draws are about 20%
  (real: about 25%), 0-0s 3% (real: about 7%), and home wins about 40% vs 40% away (real: about 45/28). Yellows
  at about 4 per game are fine.
* **Impossible states.** Across 300+ checked matches the only violation was B2, now fixed. No match had more than
  eleven players a side, a goal-event/score mismatch, a third yellow or negative goals. Each match id replays
  byte-identically (`test_afm_engine_sanity.py` now guards all of this).

---

## 6. Performance hot spots

| Hot spot | Before | After this branch |
|---|---|---|
| `afm_season.json` size (10-club season) | **108.6MB** (indent=2, with the phase stream stored per match). Live: 19.5MB for 30 matches | **4.6MB**: phases rebuilt on replay, compact JSON |
| Cold `get_season()` (10-club season) | 2.36s locally, 52.6s live (event loop also blocked) | 0.15s, off the loop |
| Keeper idle tick (every 5s) | Deep copy of the whole state plus a save of it | Reads the shared view; no write |
| Full matchday tick | Rewrites the whole file on every resolve | Unchanged, but the file is 20× smaller |
| Bets, pre-match, report reads | Each `_state()` is a pickle deep copy | Open: switch to views (B16) |

**Next step:** move season results, feeds and replays into the DB layer (`src/stack/agentic/db/`), one row per
match, so a matchday write stops being a whole-file rewrite.

---

## 7. Prioritized roadmap to "AFM production-ready"

**P0: make the league run unattended (deploy this branch)**

1. Merge `afm/deep-dive`, then restart the keeper and the API, since both cache the old modules. The first tick
   opens season 2: 7 real clubs plus 3 fillers, 18 matchdays. Check the logs for `[afm] season tick → auto_open`.
2. Free disk space: logs, and the `ledger.json.*.tmp` zero-byte orphans in `data/agentic`. Add log rotation for
   `keep-agents-playing.log`.
3. Confirm the demo faucet is intentionally on for this testnet deploy. With it off, every club wallet needs real
   funding or season opens fail ("fewer than two clubs could pay").

**P1: let a Nigerian user actually play**

4. **A funding path into the football ledger.** Credit `owner:{profileId}` from the same Paystack (Naira)
   top-up and from the Arc play wallet, and show the balance on the owner page. Unify the betting and marketplace
   wallet keys (B9).
5. **Ship the betting UI** behind L4: the owner-can't-bet check (B12) and the spectator policy. Add the
   `/betting/my` BFF route.
6. Show "your club joins season N on <date>". Add the `season/join` BFF route and say "season starts in Xh" on
   the watch and league pages instead of a frozen final table. Show past champions from `history`.
7. Make own-data reads authenticated (B15). Sync `afm-roadmap.ts` with the doc.

**P2: make the game worth playing**

8. Engine balance pass, with a regression harness asserting distribution bands (e.g. goals 2.5–3.0, reds ≤0.25,
   draws 22–28%, a stronger side winning ≥70% at an 18-point gap, no tactic beating balanced by more than 10
   points):
   * strength sensitivity;
   * defensive tactics;
   * red-card rate;
   * home advantage.
9. Credit wages to a real counterparty (B8). Decide where the betting fee goes (B11). Fix the cup history (B13)
   and add cup auto-roll plus a cup page.
10. Expose the transfer window to humans: read-only window state, and agent transfer news on the owner page.

**P3: scale and real money**

11. Season state into the DB with cross-process locking (B10, §6).
12. Mainnet: Circle wallet onboarding UX, Arc USDC settlement for entries and stakes (not just manager sales),
    and the integrity monitoring from roadmap L4.
