# Agentic Football Managers — Game of Record (v1)

> Game id: `agentic.football_managers`
> Status: design locked — v1 implementation in progress
> Decision log at the bottom. This doc is the source of truth for v1 rules;
> the older `AGENTIC_FOOTBALL_MANAGERS_V1.md` is treated as exploratory notes.

## 1. What the game is

AI **manager agents** own football clubs in a persistent league. Each club has
a real roster of unique star players, a formation + tactical style, and a
USDC budget. Every matchday the division's fixtures are locked, resolved by
the deterministic match engine, and settled on Boardman USDC rails — while
humans watch the matches broadcast and (later) stake on them.

Chess (Raja vs Nero) is the deterministic skill demo. AFM is the long-horizon
economy + decision demo: agents play the *manager*, not the match.

## 2. Foundational decisions (locked)

| Decision | Choice | Implication |
|---|---|---|
| Game loop | **Season league with discrete matchdays** | Round-robin fixtures per round; standings; champion; next season |
| Pace (v1) | **1 matchday per day** | Agent decisions due before each day's lock |
| Accelerated loop | **Separate later product** | 24/7 "fast table" needs its own agents, table & schedule — not bolted onto the daily league |
| Money | **USDC-native from day one** | Club budgets, entries, wages & matchday stakes are USDC on Boardman agent wallets |
| Field (v1) | **Two managers, league-ready** | Blue Lock vs Ao Ashi derby division; league plumbing handles any N |
| Demo managers | **Blue Lock / Ao Ashi only** | Raja & Nero are chess-only and never own AFM clubs |

## 3. Entities & state

```
Agent (registry)                 # manager identity; game_ids ⊇ football_managers
 └─ Club (afm_clubs.json)        # club_name, budget_usdc (USDC), formation, tactics
     ├─ Roster                   # owned players (unique universe-wide)
     │    ├─ Starter XI (11)     # slots GK..LW — set per matchday
     │    └─ Bench (≤5)
     ├─ wages                     # per-player wage_per_matchday_usdc, auto-debited
     └─ season participation      # entry paid → plays current season
Player (catalog)                 # unique player_id; real-world valuations & form
Season (afm_season.json)         # season_no, division ids, schedule, standings, pots
Fixture                          # matchday, round, home/away, result
Ledger (shared)                  # USDC balances, escrows, payout txs
```

All persistence lives in `data/agentic/` under the shared JSON store; the
ledger is the Boardman ledger already used by chess (demo_ledger by default,
Arc onchain when enabled).

## 4. Season & matchday flow

### 4.1 Season structure
- A **season** is `R` matchdays over the division.
  - `M ≥ 3`: double round-robin → `R = 2·(M−1)`.
  - `M = 2` (derby division): a configured run of `DERBY_MATCHDAYS` (default
    30) home/away alternating days, so a two-club season has real length.
- Each matchday every club plays exactly once (odd `M` → one club rests on a
  bye; no fixture, no points).

### 4.2 The daily beat (the agent loop)
1. **Decide** — when a matchday opens, the House **asks each manager for its
   plan** over the manager protocol (same shape as the chess `/move` loop):
   `POST {webhook_url}` with `protocol:
   boardman.agent.football_managers.matchday.v1` and the *observable*
   context — own squad + record + wallet, the **opposition's full lineup**
   (XI, bench, formation, tags, record), and the `legal` rules
   (formations, starters, max bench, tag whitelist, deadline). The
   opponent's hidden mind sliders are never sent. The manager replies JSON:
   `{formation, xi[11], bench[≤5], tactical_tags, instructions}`. The reply
   is validated against the hard rules (squad membership, GK, no overlaps);
   any missing / malformed / illegal reply falls back to the deterministic
   `decide_matchday` (mind + opponent + standings) — the matchday records
   which source each plan came from. The decision runs once per matchday at
   open; a human edit after open — before the deadline — still wins for
   that matchday.
2. **Deadline** — lineups + tactics lock at kickoff time each day (agent may
   submit any time before).
3. **Auto-fallback** — a manager who fails to decide (or misses the
   deadline) is fielded with its saved lineup/tactics (last legal XI). A
   legal XI is always maintained; a club can never be defaulted for
   non-submission, only for insolvency (below).
3. **Lock** — both XIs frozen, wages for the matchday are debited from each
   club's budget.
4. **Resolve** — `simulate_match(match_id, …)` deterministic engine:
   formation + XI quality + tactical tags decide the result; feed recorded.
5. **Settle** — matchday stakes move on Boardman USDC rails (5.4).
6. **Standings** — 3/1/0 points, GD, GF; published for the next matchday's
   decisions.

### 4.3 Between matchdays (agents manage)
- Scout the catalog, buy/sell free agents within budget (market v1 = simple
  offers; auction market is a later phase).
- Set formation / XI / bench / tactical tag for the next fixture.
- Fund the club budget from the owner wallet when it runs low.

## 5. Money model (USDC-native)

All numbers below are v1 defaults, configurable per league.

### 5.1 Club budget
- Each club's budget is USDC held by the agent (Boardman wallet; demo ledger
  default, onchain when enabled). Starting demo budget: configurable
  (currently $140 used by seeds; v1 league may rebalance).

### 5.2 Season entry
- To enter a season a club pays `SEASON_ENTRY_USDC` (default **$25**) into
  the **season pot** escrow at registration/season start. Unpaid → not
  entered (club idles that season).

### 5.3 Wages
- Wages (`wage_per_matchday_usdc` summed over XI + bench) are debited from
  the club budget each matchday at lock.
- **Insolvency:** if the budget cannot cover wages + stake, the club enters a
  protected state: no transfers, auto XI from owned players, wages accrue as
  debt; it is dropped from the standings race only if debt > budget for a
  full week (then it misses fixtures until the owner funds it).

### 5.4 Matchday settlement
- Each fixture auto-stakes `MATCH_STAKE_USDC` (default **$5**) per club into
  a match escrow.
- Payout on result, reusing Boardman fee rails:
  - pot = 2 × stake
  - platform fee, creator fees (each manager's `creator_fee_bps`) split from
    winner proceeds — identical shape to chess skill escrows.
  - win → winner takes pot after fees; draw → escrow returned to both (no
    house edge on draws).

### 5.5 Season end
- At the final matchday the **season pot** (all entries + optional prize
  sponsorship) pays:
  - Champion: 60% · Runner-up: 25% · Third (M≥3): 15% (M=2: 70/30).
- Champion agent record is credited via the ledger; standings archived.

### 5.6 Spectator money (later phase)
- Human staking on fixtures reuses the spectator-pot machinery (seed pots,
  bet placement, payout). Not in v1 daily-league scope.

## 6. Engine contract (Phase 0: `afm-engine-v1.0`)

`football_managers.match_engine.simulate_match(match_id, *, home_agent_id,
away_agent_id, home_xi, away_xi, home_tactics, away_tactics, home_bench =
[], away_bench = [], home_tactics_2h = None, away_tactics_2h = None,
require_result = False)`:
- deterministic per `match_id` (same seed → same match, same feed),
- **player attributes** (pace, technical, physicality, decision_making,
  positioning, shooting, passing, tackling, gk, fitness, morale) are derived
  deterministically from player identity + `base_rating` + slot + form
  (`attributes.py`) and measurably change outcomes — materially better
  squads outscore weaker ones across seeds,
- **tactics schema**: formation, tactical tags, mentality
  (balanced/attacking/defensive), role instructions (pressing / tempo /
  line height) and set-piece takers. Tags and shape are tested to move
  expected goals; `*_tactics_2h` swaps a side's tactics at half-time (only
  the second half changes);
- benches enable substitutions (manager windows 55'/64'/72', forced changes
  for injuries and red cards, fresh legs refill fitness); subs are match-type
  aware (chasing → attackers on, protecting → fresh legs at the back) and
  position-sane (a keeper only ever replaces a keeper);
- **referee logic**: offside calls, fouls, yellow cards (second yellow =
  red, team plays on with ten), stoppage time derived from each half's
  events;
- `require_result=True` sends a level match to extra time and, if still
  level, a penalty shootout (walk-off rules + sudden death) — no drawn
  decider ever leaks out;
- returns score, outcome, points, and the minute `feed` used by the
  broadcast — an event-sourced log (`kickoff … possession/pass/tackle /
  interception/shot/corner/throw_in/goal_kick/foul/yellow/red/offside /
  goal/substitution/injury/halftime/added_time/full_time`, plus extra-time
  and shootout events) plus a `stats` summary that is a pure fold over the
  feed (possession, shots/on target/blocked, corners, fouls, offsides,
  cards, tackles, interceptions, passes, restarts, subs, injuries);
- shots and goals carry per-shot `xG` (shooter finishing vs keeper, shot
  position, defensive pressure — deterministic per `match_id`), and the
  result carries `player_stats` (per-player minutes/goals/xG/rating 0–99 +
  errors) and `fatigue` (final condition 0..1 per player). The season feeds
  that condition into the next fixture (`home_fatigue`/`away_fatigue`) so
  tiredness — like cards — bites across matchdays;

Future: real-world match form as an oracle adjusts ratings weekly; the engine
stays deterministic given the oracle snapshot.

### 6.1 The two-layer boundary (what "done" means for the engine)

The engine is explicitly **Layer 1: a statistical / event-chain simulation** —
attributes + tactics feed probabilities, outcomes are discrete events on a
deterministic log. The spatial coordinates on every event and the renderable
phase stream are a *pure deterministic overlay* over that log (keyed on
`match_id` + event index; they never consume the match RNG and never change
outcomes) — football-*shaped* placement, not physics.

**Layer 2 — positional/spatial simulation** (every player has x/y each tick,
movement driven by role + instructions + a lightweight movement AI, and events
*emerge from position* — a through ball is "on" because a striker's coordinates
beat the offside line) is a **later phase, not part of any current definition
of done**. Layer 1 is fast, deterministic, replay-safe, and sufficient for the
stats/FM-report/broadcast products; Layer 2 would be a rewrite of the event
loop, not an increment, and is only justified if a product need demands
physical plausibility the overlay cannot fake.

Everything in §6 above is the Layer-1 contract. The FM-depth systems beyond it
(hidden personality attributes, role/duty behavior profiles, phase-of-play
instructions, dedicated set-piece resolution, matchup duels, team cohesion,
development curves) are each listed in the roadmap inventory with their honest
status — none of them is required for P1–P5 as written.

## 7. Human surfaces

| Surface | Status |
|---|---|
| Create / acquire / **buy, sell & negotiate** a manager agent (owner seat step 1) | **exists** (`/football/owner` → `ManagerMarket`: build your own manager against the playbook archetypes; adopt an unlisted developer-built one free; or **buy a listed one** — owners list their managers with a price + creator cut and the sale settles in **real USDC when every party has a bound wallet, else on the demo ledger** (buyer wallet → seller payout + creator cut to the developer). Listings can carry a **reserve price** and buyers can **make offers**: below-reserve offers auto-decline, the rest queue in the owner's inbox to accept (sale settles at the offered price) or reject. Blue Lock / Ao Ashi ship listed by their developers. Backed by `agent_market.py` (`list/delist/purchase/offer/bind_party_wallet`) + `/api/…/football/agents/list, delist, purchase, offer, wallet (+ bind/unbind)`) |
| Owner dashboard: results, decisions, spending, news (owner seat step 5) | **exists** (`/football/owner` → `FollowYourClub`: pick a club you own and follow it — table position + form, recent results with the plan the agent locked per matchday (formation/tags/XI incl. red-card bans), a spending log (club-budget build + agent-wallet ledger: entry, wages, stakes, payouts) and suspension/injury news; backed by `dashboard.py` + `GET /football/owner/{agent_id}`) |
| Catalog / market browse | exists (`football-catalog.html`, API) |
| Club + lineup + tactics (setup/coach) | exists (`/football/tactics`, Save writes agent lineup) |
| Match broadcast (TV rig) | exists (`/football/tactics` → Kick off) |
| **Standings + fixtures** | **exists** (`/football/league`, live season data + tick button) |
| Season schedule + results archive | **exists** (`/football/league` recent results, season snapshot API) |
| Season service (open/join/tick/resolve/pot) | **exists** (API + keeper heartbeat, 1 matchday/day) |
| Agent decision loop | **exists** (managers set lineups + tactics per matchday from mind + context) |
| Recorded match replays | **exists** (`/football/season/replay` + board deep-link `?replay=1&md=N&home=..&away=..`, replay of every fixture incl. deterministic reconstruction of pre-feed matchdays) |
| Live staking | later phase |

## 8b. Season service (v1, live)

- `src/stack/agentic/games/football_managers/season.py` — open season
  (USDC entries → pot), daily tick (open due matchdays, lock XIs at deadline
  with legal-XI fallback, debit wages, resolve via the deterministic engine,
  settle matchday stakes through the ledger escrows, update standings),
  season end (70/30 or 60/25/15 pot payout, pot debited). Insolvency never
  fatal: shortfalls accrue as `wage_debt` / `stake_debt`.
- Heartbeat: `scripts/keep_agents_playing.py` calls `tick()` every loop;
  matchdays resolve automatically when their deadline passes. Ticks are
  idempotent (a played matchday never re-resolves) so API, keeper and humans
  can all trigger them safely.
- **Decide loop:** at each matchday's open the managers actively set their
  lineup + tactics (`decide.py`, driven by each mind's archetype — Blue Lock
  striker ego: highest-rated XI, 3-4-3/4-3-3, gegenpress, never parks; Ao
  Ashi total football: position-disciplined XI, 4-2-3-1/4-1-4-1, reads the
  opponent's tag — counter an aggressive side, keep the ball vs a bus).
  Decisions are recorded per matchday and genuinely change results.
- **Discipline carries between matchdays:** a player sent off (straight red
  or second yellow → red) in a club's last fixture is excluded from the next
  matchday's locked XI and bench (`banned` on the stored lineups), with the
  XI refilled to a legal 11 that keeps a keeper. Decisions/replays below are
  all post-discipline.
- **Match stats on the boards:** every result carries the engine's stat fold
  (`stats`), shown as a possession bar + shots/on-target/corners/fouls/
  offsides/cards panel on the tactics board at full time and as a compact
  stat line under each recent result on the league page.
- **Replays:** every resolved fixture stores the full engine result (feed +
  locked lineups + decisions); `GET /football/season/replay?matchday&home&away`
  serves it, reconstructing pre-feed-storage matchdays deterministically
  (same seeded match_id → same match). The tactics board deep-links into
  replay mode from the league page (`▶` per result, and the main watch
  button opens the latest played fixture).
- API: `GET /football/season` (snapshot), `POST /football/season/join|open|tick|reset`,
  `GET /football/market` (free agents). Tools map: `afm_view_season` → GET
  season, `afm_join_season` → join, `afm_set_lineup` → PUT lineup,
  `afm_market` → market, `afm_club` → GET club.
- Tests: `tests/test_afm_season.py` (entries, tick, full-season pot payout,
  idempotency), plus `test_afm_league.py` / `test_afm_clubs.py` / `test_afm_engine_phase0.py`
  (Phase 0 acceptance: reproducibility, attribute impact, referee rules,
  stoppage time, subs/injuries, half-time adjustments, ET + shootouts,
  stats as a fold of the feed).

### 8c. Knockout cup (draws must produce a winner)

- `src/stack/agentic/games/football_managers/cup.py` — single-elimination
  cup on the same daily clock as the season (open → per-round open/deadline
  → tick). Entrants default to every club with an AFM roster; first-round
  byes top up non-power-of-two fields; rounds pair the previous round's
  ordered winners down to a final.
- **Every tie resolves on the deterministic engine with `require_result=True`:**
  a draw after 90' goes to extra time and, if still level, a penalty
  shootout (walk-off + sudden death) — a knockout tie is never drawn. The
  stored result carries the deciding `reason` (`extra_time` / `penalties`),
  the full feed, stats, and locked lineups; replays reconstruct
  deterministically from the seeded match_id.
- No money in v0: ties reuse the clubs' saved legal XI + bench + tactics at
  the round deadline (the managers' decide loop keeps them fresh). The
  keeper heartbeat ticks the cup alongside the season, and API mirrors the
  season (`GET/POST /football/cup`, `cup/open`, `cup/tick`, `cup/reset`,
  `cup/replay?round&home&away`).
- Tests: `tests/test_afm_cup.py` (bracket structure + byes, 2- and
  8-club knockouts run to a single champion, every tie decisive, seeded
  draws genuinely reach ET / penalties, replay determinism).

## 8. Agent tool API (v1)

Tools an AFM manager agent can call (route: `/api/stack/agentic/football/…`):

| Tool | Purpose |
|---|---|
| `afm_join_season` | pay entry, enter the season (or renew) |
| `afm_view_season` | season state: standings, fixtures, next opponent |
| `afm_set_lineup` | formation + XI + bench + tactical tags (exists) |
| `afm_market` | list free agents; make offer / release player |
| `afm_club` | own club state: budget, wages, squad value |

House never plays. Every decision is the agent's.

## 9. N-ready architecture

- The scheduler is division-generic (M=2 works, M≥3 double RR, odd-M byes).
- Any registered agent whose `game_ids` includes `agentic.football_managers`
  can be invited to the division; demo seed owns Blue Lock/Ao Ashi.
- Expansion mechanics (promotion/relegation across divisions, cup) are
  explicitly **not v1**.

## 10. Out of scope (v1) / later phases

- 24/7 **accelerated fast table** (separate product + separate manager
  agents; drives spectator bet volume).
- Human staking / spectator pots.
- Transfer market auctions & multi-bid rounds.
- Real-world form oracle, promotion/relegation, cups, youth/condition.
- **Engine Layer 2** (per-tick positional simulation with movement AI and
  events emerging from position — see §6.1) and the FM-depth systems beyond
  the Layer-1 contract (hidden personality attributes, dedicated set-piece
  subsystem, full matchup-duel matrix, team familiarity/cohesion,
  development curves feeding back into attributes).

## Decision log

- 2026-09-06 — **Engine architecture boundary ratified:** the engine is
  Layer 1 (statistical/event-chain + deterministic spatial *overlay*); Layer
  2 (per-tick positional simulation, movement AI, events emerge from
  position) is explicitly a later phase and out of scope for v1 (§6.1).
  This pins what "done" means: P1's DoD was met by Layer 1 + overlay, and no
  current product requirement demands physics. The FM-depth systems
  (personality attributes, role/duty profiles, phase-of-play instructions,
  set-piece subsystem, matchup duels, cohesion, development curves) are
  tracked as inventory rows, not phase gates.
- 2026-09-04 — Restart from the beginning. Locked: season-league loop, 1
  matchday/day, USDC-native economy, two managers (Blue Lock FC vs Ao Ashi
  FC) on league-ready plumbing; Raja/Nero stay chess-only.
- 2026-09-04 — Demo managers are dedicated AFM silo agents
  (`agent_bluelock_demo`, `agent_aoashi_demo`); old Raja/Nero clubs pruned.
- 2026-09-04 — Season service shipped and verified live: USDC entries into a
  season pot, daily tick under the keeper (1 matchday/day), wages + matchday
  escrows settled through the ledger, season pot paid out at the end. League
  page `/football/league` (standings, fixtures, results, run-due-matchdays)
  and `afm_*` season/market API endpoints live.
- 2026-09-05 — Owner seat step 5 live: follow-your-club dashboard
  (`dashboard.py` read model + `GET /football/owner/{agent_id}` + the
  `FollowYourClub` UI on `/football/owner`). Results carry the agent's
  recorded per-matchday decision (formation/tags/XI + bans auto-refilled at
  lock); the spending log folds the club-budget build with the agent
  wallet's AFM ledger movements; news surfaces oracle injuries/suspensions
  and red-card bans for the next fixture. No writes — the agent's own FM
  surfaces remain the only place decisions change.
- 2026-09-05 — Managers are sellable on the marketplace. An owner lists a
  manager with a price and creator cut (`creator_cut_bps`, 0–20%); a listed
  manager can no longer be adopted free. Buying settles on the demo ledger:
  buyer wallet → seller payout, plus the developer's cut to the
  `creator:{creator_id}` pseudo-wallet (the same wallet match creator fees
  use) on resale — a developer selling their own build keeps the full
  price. Blue Lock/Ao Ashi ship listed by their developers. Adoption
  remains the free path only for unlisted managers.
- 2026-09-05 — Listings accept **offers** and can carry a **reserve price**
  (floor, ≤ buy-now). Offers below the reserve auto-decline; at/above it
  they queue as `pending` for the owner to accept (sale settles at the
  offered price through the same creator-cut rails — a later owner
  accepting still pays the original developer) or reject (listing stays
  live). Buy-now, relisting and delisting void outstanding offers. API:
  `POST /football/agents/offer|offer/accept|offer/reject`.
- 2026-09-05 — Purchases get a **real buyer wallet / on-chain USDC rail**
  (dual mode, ledger stays default). Parties **bind** a payout address (and,
  to pay, a Circle wallet id) via `POST /football/agents/wallet/bind`
  (`party_wallets.json` store; a registered agent party resolves to its
  registry `wallet_address` automatically). With Circle configured and every
  party bound, `settlement=auto` moves **real Arc USDC** from the buyer's
  Circle wallet (`transfer_usdc` + confirm, balance-checked before any leg)
  to the seller — plus the developer's creator cut as a second leg on
  resale — and never touches the demo ledger; `mode` + tx receipts land on
  the sale. `settlement=onchain` forces the rail (errors when not ready);
  `ledger` forces demo. Fail-closed: short balance / failed / unconfirmed
  transfer raises and ownership does NOT move. API:
  `POST /football/agents/purchase|offer/accept` carry `settlement`; wallet
  status at `GET /football/agents/wallet?party_id=…`. 10 tests
  (`test_afm_market_settlement.py`).
- 2026-09-05 — **Owner sales desk** on the dashboard: every list, relist,
  delist and completed sale now appends a `market_history` event to the
  manager record, and `GET /football/agents/sales?party_id=…`
  (`party_sales_view` — read-only projection) turns them into the money
  view: total earned (as seller + as the developer taking creator cuts),
  portfolio rows with the live listing state and per-manager earnings, and
  a list/relist/delist/sold timeline (each sale shows its rail — real USDC
  vs demo ledger). Managers that predate the event log fall back to their
  demo-ledger rows so a sale is never counted twice. New BFF routes fill
  the previously-missing marketplace client paths (`agents/list|delist|
  purchase|offer|offer/accept|offer/reject|wallet|wallet/bind|wallet/unbind`).
  5 tests (`test_afm_sales_view.py`).
- 2026-09-05 — **Manager protocol shipped: the agent expresses its own
  plan.** Pre-kickoff is an ask→reply contract mirroring chess `/move`
  (`manager_protocol.py`): the House POSTs `boardman.agent.football_managers.matchday.v1`
  with the observable context — own squad + record + wallet, the
  **opposition's full lineup** (XI/bench/formation/tags/record; hidden mind
  sliders never leave the agent) and the `legal` rules — and the manager
  replies `{formation, xi, bench, tactical_tags, instructions}`. Replies are
  validated (squad membership, exactly 11 with a GK, ≤5 bench with no
  overlaps, formation/tag whitelists); a dead or malformed webhook falls
  back to deterministic `decide_matchday` and the matchday records
  `source: webhook|auto` (+ `instructions` + `note`). `decide.py` was
  refactored into `matchday_context` + `plan_for_strategy` (one shared
  strategy core) plus `decide_from_ask` — the demo managers now ship
  **webhook servers** (`agents/bluelock|aoashi/serve.py`, ports 18771/18772,
  booted by the house; manifests bumped to 1.1.0 with `runtime.webhook_url`)
  that answer purely from the ask payload with their archetype mind (Blue
  Lock: 3-4-3 gegenpress "never settle for a draw"; Ao Ashi: shape XI,
  reads the opponent, counters pressure). 18 tests
  (`test_afm_manager_protocol.py`) + live round trip: a real season tick
  asked both servers over HTTP and locked their replies.
- 2026-09-05 — **Owners point their manager at their own brain.**
  `POST /football/agents/webhook` (`set_manager_webhook`, owner-only, URL
  validated, empty clears) binds any owned AFM manager to a builder-hosted
  webhook — from the next matchday ask on, the House asks *that* server and
  locks its reply (playbook fallback when unreachable). The binding is
  logged on the manager's `market_history` and projected on marketplace
  rows (`webhook_url`). The owner dashboard now shows where each locked
  plan came from: a **🟢 answered via webhook** vs **playbook (auto)** chip,
  the manager's own `instructions` quote, and the fallback `note` when a
  webhook was down/invalid (`dashboard.py` decision + `OwnerDashboard` UI).
  2 tests added (`test_afm_manager_protocol.py`).
- 2026-09-06 — **Manager detail card on the marketplace.** Every market row
  now embeds an expandable card (`manager_card.py`, projected through
  `_market_row` — no new endpoint): a **playbook radar** computed from the
  live `decide.STRATEGIES` table (attack/press/defence from the first-choice
  formation's slot weights blended with the base tag's aggression, counter
  from the reactive tag, system-vs-stars from the pick style — it can never
  drift from real matchday behaviour) with the concrete shape/tag/pick
  summary; a **squad-ability radar** (squad-average derived attributes,
  healthy + unsuspended like the decide loop; hidden when the manager has no
  squad); and **record charts** folded from stored season results — season
  totals (W–D–L, points, goals, xG for/against, win rate), a last-5 form
  strip, and per-matchday rows with score + xG-for/against split bar.
  Frontend: `ManagerDetailCard` component on each marketplace card
  (collapsed by default), styled on the `--bm-*` Boardman tokens. 7 tests
  (`test_afm_manager_card.py`).
- 2026-09-06 — **FM-style dashboard + league restyle.** The owner dashboard
  is rebuilt as a football-manager game screen on the Boardman tokens: club
  header bar (kit crest with initials, manager + archetype chip, big-number
  record strip: position, W·D·L, form dots, budget left) above a left
  section nav (**Overview / Results / Squad / Finances / League** — squad
  news count shows as a red nav badge) driving a two-column panel grid of
  dark inset cards with uppercase header strips. Overview: compact result
  rows with outcome-tinted left borders, score chips (replay links) and a
  highlighted next-fixture notice; Squad: availability chips + injury /
  suspension items with colored spines; Finances: kv money rows (negative
  rows red), a budget-used bar (emerald → amber at 80% → red at 100%) and
  the spending log; League: mini table with kit dots, promotion/relegation
  **zone bars** and a legend. League page restyled onto the same tokens:
  numeric columns right-aligned tabular, zone chips + legend on standings,
  emerald primary buttons matching the portal, amber champion/finished
  states, emerald live badge.
