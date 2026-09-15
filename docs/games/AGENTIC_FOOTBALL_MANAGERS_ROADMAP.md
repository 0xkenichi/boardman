# AFM Master Plan — "One simulation. Two completely different products."

**File purpose:** the living todo for AFM. Every change to the game must update this file so anyone can see **what is done, what needs work, what is a must (not started), and what is an add-on** — and why a change was made. If you touched the engine, the agent tools, or the broadcast, update the relevant line's status + date here in the same change.

**Last updated:** 2026-09-06 (engine P1 completed: per-actor xG, per-player ratings, error attribution, manager action transcript, match-type/position-sane subs, persistent fatigue carried between fixtures — engine v1.3. Engine architecture boundary ratified — Layer 1 statistical core + spatial overlay, Layer 2 positional sim deferred; FM-depth systems tracked as inventory rows, game doc §6.1)

---

## 0. Objective

**Prove that one deterministic football engine can feed two products that never touch:**

- **Agents live in Football Manager.** A manager's entire life is a tool belt of text + numbers: squad, tactics, transfers, inbox, and a post-match report it can learn from. An agent should be able to lose a league by playing a striker at left back for 12 games — and if the tools can't express that mistake, they aren't FM.
- **Humans live in a broadcast.** A spectator sits in the stand: 2D pitch, named players, scorebug, goal replay, lineup graphic, "manager said…", a table. Humans never see a slider, an attribute number, or the inside of the engine.
- **The engine is the only thing both sides touch.** It eats FM inputs (tactics + XI + fitness + morale) and emits a football match (event log + result + player ratings). The same seed produces the same match for every spectator and for settlement. Agents cannot see future events; humans cannot change events; cards, injuries, and tiredness must bite the next fixture.

If either side sees the other side's UI, the fantasy breaks. That rule is the product.

---

## 1. Goals (measurable)

| # | Goal | Proof it's met |
|---|------|----------------|
| G1 | **Engine honesty** | Same seed → byte-identical feed for every viewer & settlement. Feed is spatial & timed: 100+ events carrying coordinates, xG, cards, tiredness. Post-match FM report (ratings, xG, heat, errors) is derivable purely from the feed. |
| G2 | **Two products, zero leakage** | An agent can run its club start-to-finish without ever seeing a camera. A human can follow a full matchday without ever seeing a slider or an attribute number. Test: **mute every UI label — the agent still knows what to do from numbers; the human still understands who is winning and why the game flipped.** |
| G3 | **2D broadcast first** | A spectator lands at `/football/watch`, sees "what's on today", and watches a full match on a 2D pitch board (scorebug, named players moving, goal replay, lineup graphic). 3D cinema is explicitly parked until this is proven. |
| G4 | **Consequences bite** | Cards / injuries / tiredness from matchday N demonstrably change the *options* at matchday N+1's lineup lock (not just a text line). Cards: ✅ bans enforced at lock (🟢). Tiredness: ✅ engine v1.3 (2026-09-06) — final condition stored per club, fed into the next fixture, surfaced on the squad screen + the manager ask. |
| G5 | **Rules in code, not vibes** | Lineup legality, discipline, market rules, determinism — enforced and covered by tests. Suite stays green (≥40 AFM tests). ✅ 140 AFM tests green (2026-09-06). |

---

## 2. Status legend

| Mark | Meaning |
|------|---------|
| 🟢 **Done** | Shipped and verified (tests / manual check) |
| 🟡 **Needs work** | Exists, but wrong shape, thin, or violates the split — must be changed |
| 🔴 **Must** | Not started — required to reach the objective |
| ➕ **Add-on** | Later / optional — gated behind the Musts |

---

## 3. Product doctrine (condensed from design brief)

| | **Agents (Football Manager)** | **Humans (real football)** |
|---|---|---|
| Job | Run the club | Watch the match |
| Screen | Squad, tactics, training, inbox, finances | Pitch, scorebug, replay, crowd |
| Time | Days, windows, seasons | 90 minutes of football |
| Language | Roles, duties, pressing, minutes, wages | "high line", "he's through", "second yellow" |
| Hidden | Almost nothing about their own club | Almost everything under the hood |

**Information asymmetry is the product:** the agent knows Salah is on 4 yellows and 62 stamina; the human sees Salah start, look heavy after 70', and get booked. The agent knows they switched to a 5-4-1 at HT; the human sees the shape drop and hears "they've packed the box." Translate data into pictures and sentences. Never dump the database onto the pitch.

---

## 4. Shared engine — inventory

| Item | Status | Notes / gap |
|------|--------|-------------|
| Deterministic seeded engine (`simulate_match`) | 🟢 | Same `match_id` → same match; replay endpoint reproduces |
| Full law set: offside, fouls, yellow/red, second-yellow→red (plays on with 10), corners, throw-ins, goal kicks, stoppage time | 🟢 | 40 AFM tests green |
| Extra time + penalty shootout when `require_result=True` | 🟢 | Cup ties settled; walk-off + sudden death |
| Injuries + forced subs; benches + manager-window subs | 🟢 | Windows at 55/64/70 (+HT break) |
| Player attribute model (10 attrs, deterministic per player) | 🟢 | `attributes.py`; same player → same profile |
| Tactics: formation, tags, mentality, instructions, HT adjustment (`*_tactics_2h`) | 🟢 | Shapes/tags measurably shift event patterns |
| Post-match `derive_stats` (team fold over feed) | 🟢 | Possession, shots, cards, corners, etc. |
| Suspensions carry into next matchday lineup lock | 🟢 | Reds + 2nd-yellow → `banned` at next lock |
| Weekly real-world oracle → form/injury into attributes | 🟢 | `weekly_oracle.py` |
| **Spatial events (coordinates / zones / ball movement)** | 🟡 | **Shipped (engine v1.1 → v1.2):** every event carries `x / y / z / facing / actor_id` via a pure deterministic overlay (`spatialize_feed`, keyed on match_id + event index — never consumes the match RNG, so outcomes are byte-identical and replay-safe; `test_afm_spatial.py`, 6 tests). Placement is football-shaped: kickoff centre, goals in the attacking box, corners at the flag, penalties on the spot, throw-ins on the touchline. **Phase stream builder shipped (2026-09-05, engine v1.2):** `phases.py` turns the log into a renderable stream — every event becomes `{ t, ball{x,y,z}, players[22], action? (pass/carry/shot/cross), note? }` with strictly increasing `t`, the actor snapped to the ball, and deterministic in-formation positioning for both XIs; every match result now carries `phases` (9 tests, replay-safe). A goal builds from 2+ loopable build-up phases; a full match is a playable phase timeline. **Still needs:** per-shot xG (own row below) and renderer consumption (P2). Without xG + the board, the FM report / broadcast layers can't land. |
| **Player-layer `decide(game_state)` sandbox (optional, heavier)** | ➕ | AgentPitch-style: each outfield role runs a sandboxed `decide(game_state)` (pass/shoot/press/hold). Default is a cheap stats engine for the 90′ — LLMs only on the manager. This is the sanctioned answer to "players with a mind of their own": per-player preferences/personality live in the stats + agent hooks, not 22 live LLM ticks. |
| **xG per shot** | 🟢 | **Shipped (engine v1.3, 2026-09-06):** every shot/goal event carries per-shot `xG` from the shooter's finishing vs the keeper's quality, shot position (box vs range) and defensive pressure — deterministic per `match_id`, computed from the same hash stream as the spatial overlay so xG and coordinates agree; team xG totals fold in `derive_player_stats`. Tested (`test_afm_engine_phase0.py`). |
| **Per-player post-match ratings** | 🟢 | **Shipped (engine v1.3, 2026-09-06):** `MatchResult.player_stats` folds the spatialized feed per actor — minutes, shots/on target, goals, xG, tackles, interceptions, fouls, cards, passes — and derives a 0–99 `rating` (finishing vs xG strongest, defensive/passing involvement + discipline shape the rest). Tested. |
| **Error attribution ("why we lost")** | 🟢 | **Shipped (engine v1.3, 2026-09-06):** per-player `errors` (high-xG misses sorted by xG) + match-level critical errors (sending-offs, xG over/under-performance notes) — the post-match file the agent turn and commentary read. Tested. |
| **Manager action transcript** | 🟢 | **Shipped (2026-09-06):** the season stores a per-matchday action log — `formation` (set_shape), `tags`, `starters`/`bench` (xi [ids]), `instructions`, `source` (webhook or auto), `note`, plus the press-conference Q&A — exposed via `get_matchday_transcript` / `transcript_for_fixture` / `matchday_news_items` and tested (`test_afm_transcript.py`, 8 tests). Subs are logged as engine events (`off`/`on`/`kind`/`match_type`) in the feed. |
| Individual player skill drives outcomes (not only team aggregates) | 🟢 | **Shipped (engine v1.3, 2026-09-06):** shot/goal odds are per-actor — the shooter's finishing/positioning vs the opposing keeper anchors `_shot_xg` (team aggregates still shape possession/attack likelihood). "A 6.4-rated midfielder can score a worldie, rarely" now falls out of the per-actor xG roll. |
| Role/duty-level instructions | 🟡 | Tags/mentality exist; per-role duties (`press_forward`, `false_9`…) don't. FM-depth plan: a role+duty is a *behavior profile* (positioning/decision reweights per role, e.g. Advanced Playmaker–Support vs Inverted Wing-Back–Attack) built as a lookup table over the attribute model, not a hardcoded grid — separate from the formation shape, which only places players. Phase-of-play instructions (in-possession / transition / out-of-possession: width, tempo, press intensity, line height each independently tunable) supersede the single mentality dial when this lands |
| Persistent tiredness across fixtures (G4) | 🟢 | **Shipped (engine v1.3, 2026-09-06):** `simulate_match` accepts `home_fatigue`/`away_fatigue` (condition 0..1 per player) and returns `MatchResult.fatigue` — the final condition of every involved player. The season stores it per club after each fixture (`record_match_fatigue`), feeds it into the next matchday's engine call with `FATIGUE_RECOVERY` rest between fixtures (`current_condition`), and surfaces it on the squad screen (`condition`) and the manager-protocol ask (own squad rows only — the opposition never sees it). Tested (`test_afm_subs_fatigue.py`, 9 tests incl. end-to-end MD1→MD2 carry). |
| Substitution *choice* realism | 🟢 | **Fixed (engine v1.3, 2026-09-06):** the Mbappé-for-GK bug is gone. Subs are match-type aware (chasing → attackers on; protecting → fresh legs in defence/midfield; injuries replace like-for-like) and position-sane (a keeper only ever replaces a keeper; like replaces like where the bench allows). Every sub event carries `kind` (tactical/injury) + `match_type` (chasing/protecting/level). Tested across seeds (`test_afm_subs_fatigue.py`). |
| Assist / save attribution | ➕ | For FM report depth later |
| Hidden personality attributes (consistency, big-match temperament, professionalism, injury proneness, determination) | ➕ | FM-depth plan: hidden attrs affect *reliability/variance*, not skill — consistent with the existing unscouted-range mechanic (an agent learns them only through repeated observation). Deterministic per player like `attributes.py`, consumed as variance multipliers on duels/decisions rather than new visible stats |
| Dedicated set-piece subsystem (corners, free kicks, penalties) | ➕ | FM-depth plan: own resolution path using a different attribute mix (jumping/heading/technique) with assigned takers/targets — treats set pieces as the distinct variance source they are instead of open-play events. Today the law set fires corners/penalties as feed events but resolves them through the open-play probability chain |
| Matchup-based duels (winger vs full-back, striker vs CB) | ➕ | FM-depth plan: resolve individual contests as attribute differentials scaled by the consistency hidden attr, replacing the global randomness pool for duels — makes specific matchups meaningful. Related shipped work: per-actor shot xG (v1.3) already pits one shooter's finishing against the opposing keeper |
| Team familiarity / cohesion over time | ➕ | FM-depth plan: a slow-building understanding stat between players who start together — rewards squad continuity over raw attribute buying and gives agents a long-horizon lever beyond single-window optimization. Zero state exists today |
| Development curves feeding back into the engine | ➕ | FM-depth plan: training focus + minutes actually move attributes season-over-season (making youth minutes vs proven quality a real trade-off). The squad screen already derives per-player profiles and the Development tab shows form vs base — the missing piece is the write path into `base_rating`/attributes over time, which must stay deterministic per player identity |
| **Engine layering (statistical core vs spatial overlay vs Layer-2 simulation)** | 🟢 | **Ratified (2026-09-06, game doc §6.1):** the engine is Layer 1 — a statistical/event-chain simulation with the spatial phase stream as a pure deterministic overlay. Layer 2 (per-tick positional sim, movement AI, events emerging from position) is a later phase, not part of any current DoD. The FM-depth rows above are inventory, not phase gates |

---

## 5. Product A — Agent FM tools (Football Manager)

| Item | Status | Notes / gap |
|------|--------|-------------|
| Club/squad data (attributes, positions, wages, form, injury, contract) | 🟢 | Lives in `club_store.py` / catalog — data exists, no screen |
| Squad screen (attrs, roles, fitness, morale, form, contract, wage) | 🟢 | **Shipped V1 (2026-09-05):** FM-style read-only screen at `/football/squad/[agent_id]` — sortable table (status, name, ability, form, condition, morale, injury, wage, value, contract), position filters + search, and a player detail panel with Physical / Technical / Mental attribute groups. Backed by `club_store.squad_view()`: derived attrs via `attributes.py`, status from the locked lineup (starter/bench/squad), deterministic 2–5y contract projection (no contract ledger yet — derived, like attributes); 4 tests, verified live against the club store. Transfers + in-match tools remain their own rows |
| **Owner seat: create or acquire a manager agent** | 🟢 | **Shipped (2026-09-05):** `/football/owner` step 1 live — "build your own manager against the playbook" (pick a mind archetype, name it, get a registered agent identity + wallet and a club with an affordable auto-roster + legal XI; it joins the league at the next season open) or "take one from the marketplace of agent developers" (adopt any registered AFM agent — ownership moves to the caller). Backed by `agent_market.py` (`list/create/acquire`) + `/api/.../football/agents*`; new playbook archetypes `pragmatist` (5-3-2 low block + counter) and `possession` (tiki-taka) now drive the decide loop; `seed_demo_clubs` re-seed no longer prunes owner-created clubs (only registered non-AFM owners). 6 tests (`test_afm_agent_market.py`). **Marketplace upgrade (same day): created managers are now sellable** — the current owner (typically the developer who built it) lists with a **price** and a **creator cut** (0–20% of each sale, same cap as the win cut); listed managers can no longer be adopted free — a buyer *purchases*, the price settles on the demo ledger (buyer wallet → seller payout + creator cut to `creator:{id}`, the pseudo-wallet the match fee router already uses) and ownership moves. Developer selling their own build keeps the full price; later owners reselling pay the original developer their cut. Blue Lock / Ao Ashi ship listed by their developers so the marketplace has priced inventory (25.00/20.00, 5% cut). API `POST /football/agents/list, delist, purchase`; `create` accepts optional `list_price_usdc`/`creator_cut_bps`. 10 tests (`test_afm_agent_market.py`). **Offers + reserve (same day):** the listing can carry a **reserve price** — the owner's floor. Buyers *make offers* on any listed manager; offers below the reserve auto-decline, the rest queue in the owner's inbox to **accept or reject**. Accepting settles a sale at the offered price through the same creator-cut rails (a later owner accepting still pays the original developer their cut); rejecting keeps the listing live. Buy-now and delist void outstanding offers. API `POST /football/agents/offer`, `…/offer/accept`, `…/offer/reject` (+ `reserve_price_usdc` on list). 14 tests (`test_afm_agent_market.py`). **Real buyer wallet / on-chain settlement (same day):** sales move **real Arc USDC** instead of the demo pseudo-wallet faucet whenever the rail is ready — parties bind a payout address (and, to pay, a Circle wallet id) via `POST /football/agents/wallet/bind` (`party_wallets.json`; registered agent parties resolve to their registry wallet automatically). With Circle configured and every party bound, `settlement=auto` transfers real USDC from the buyer's Circle wallet to the seller (+ the developer's creator cut as a second leg on resale) and never touches the ledger; `mode` + tx receipts are recorded on each sale. `onchain` forces the rail (raises when not ready), `ledger` forces demo — and a short balance / failed / unconfirmed transfer fails closed (ownership never moves). Wallet status: `GET /football/agents/wallet?party_id=…`. 10 tests (`test_afm_market_settlement.py`). **Sales desk (same day):** every list/relist/delist/sale now appends a `market_history` event to the manager record; `GET /football/agents/sales?party_id=…` (`party_sales_view`, a read-only projection) feeds the owner dashboard's money view — total earned split into seller proceeds vs developer creator cuts, portfolio rows with live listing state + per-manager earnings, and a list/relist/delist/sold timeline. Managers that predate the event log fall back to their demo-ledger rows (never both). 5 tests (`test_afm_sales_view.py`) |
| **Owner dashboard: results, decisions, spending log, squad news (owner seat step 5)** | 🟢 | **Shipped (2026-09-05):** `/football/owner` step 5 live — pick a club you own (created/adopted in step 1) and follow it from `FollowYourClub` + `dashboard.py`: table position & form, every result with the plan the agent locked for that matchday (formation / tags / XI from the recorded per-matchday decisions — incl. red-card bans auto-refilled at lock), a spending log (club-budget build + the agent wallet's ledger: faucet, season entry, matchday wages, stakes locked/settled/refunded, season payouts) and suspension/injury news (oracle flags + "sent off last matchday" bans). Pure read model — the agent's FM surfaces stay separate. API `GET /football/owner/{agent_id}`; 6 tests (`test_afm_dashboard.py`) |
| Pre-kickoff: set formation + roles + team instructions, submit XI | 🟢 | **Shipped (2026-09-05):** the manager protocol — the House *asks* each manager for its matchday plan (webhook POST, `boardman.agent.football_managers.matchday.v1`) with the observable context (own squad + record + wallet, the **opposition's full lineup** — never hidden sliders — and the `legal` rules) and the manager replies `{formation, xi, bench, tactical_tags, instructions}`. Validated (squad membership, 11 with a GK, ≤5 bench no overlaps, whitelists); dead/malformed webhook → deterministic `decide_matchday` fallback, `source: webhook or auto` recorded per matchday. Demo managers Blue Lock / Ao Ashi ship webhook servers that answer from the ask payload (`agents/*/serve.py`, ports 18771/18772, booted by the house). `decide.py` refactored into `matchday_context` + `plan_for_strategy` + `decide_from_ask` (one shared strategy core). 18 tests (`test_afm_manager_protocol.py`), live round trip verified |
| Manager protocol mirrors chess `/move` (webhook ask→JSON reply) | 🟢 | **Shipped (2026-09-05):** `manager_protocol.py` — `build_matchday_ask` / `request_matchday_plan` / `validate_matchday_plan` / `ask_matchday_plan`, wired into `season._agents_decide` (webhook first, `decide_matchday` fallback, `source` recorded). Same shape as the chess move loop: builder-hosted webhook (`serve_builder_webhook`), House POSTs context, agent replies JSON — now for lineup/tactics (`boardman.agent.football_managers.matchday.v1`) instead of a chess move. **Owner-set webhook (same day):** `POST /football/agents/webhook` (owner-only, URL validated, empty clears) binds an owned manager to a builder-hosted brain; the dashboard surfaces the plan source (🟢 answered via webhook / playbook auto chip), the manager's `instructions`, and fallback `note` |
| See opposition lineup (not their sliders) | 🔴 | Needed for real decisions |
| In-match tools at natural breaks (HT, 60', red card, injury): `sub`, `change_instruction`, `change_shape` | 🔴 | Engine consumes `*_tactics_2h`; no tool surface + no action log |
| Inbox: board, press, player unrest, next fixture | 🔴 | Not started |
| Post-match report: ratings, xG, heat, errors that cost the game | 🟢 | **Shipped (2026-09-06, engine v1.3 data):** `report.py` folds the stored `player_stats` into a per-fixture FM report — per-player minutes/goals/xG/tackles/cards + 0–99 rating, team xG, top/worst performer, per-player error lists and one-line "why" attributions. Agent surface: `GET /football/report/{agent_id}` (latest or `?matchday=N`) + `GET /football/season/report?season_no&matchday&home&away` (both sides). Owner dashboard: every result row now carries a report summary (xG bar + one-line why, expandable per-player rating list). Heat maps: not yet (needs spatial event density per player). 7 tests (`test_afm_report.py`) |
| Transfer list, shortlist, bids, wage structure | 🔴 | `market.py` backend exists; no agent tool/UI and no shortlist |
| Training / minutes management / injury list | ➕ | Backend partial |
| **Agent portal currently links the agent to the 3D theater** | 🟡 | Violates the split ("do not make the agent click a 3D camera"). Agent door must be repointed to FM tools |

---

## 6. Product B — Human broadcast (2D first)

| Item | Status | Notes / gap |
|------|--------|-------------|
| Front door + role hubs (`/football`, `/watch`, `/owner`, `/agent`) | 🟢 | Shell + journeys; watch-only chosen |
| League table + fixtures + recent results w/ mini stats | 🟢 | `LeagueView`, MatchStats on results |
| "What's on today" → pick a match → watch | 🟡 | Watch hub is a journey shell; league page lists fixtures but there's no one-click "watch this now" into a live board |
| **2D pitch board**: scorebug, named players moving, ball | 🔴 | **The focus build.** Depends on engine spatial events (§4). 2D first — 3D is parked as *physics* (§8). **Visual target (ratified): the Evans/DEvansData tactics board** — Three.js, not EA FC, not FM dots: a phase player (22 tokens on a 3D pitch), named players, pass height + body facing, Broadcast / Top / Goal / Side / Follow-ball cameras, play/loop/speed. Tokens with kits look more "football" than bad rigs. Lightweight ref: fobal-simulator (full AI-vs-AI 2.5D match in one HTML file) |
| Pre-match tactics board ("how this manager wants to play") | 🔴 | The Tactics App (DEvansData) as reference UI for this middle layer — coach tool, not stadium sim (no physics, no 90′ play, no bot API). Driven by the agent's plan (`decide_matchday` already outputs formation + XI): 4-3-3, press triggers, set-piece shape, half-space boxes. Animated clips of the manager's plan = better spectator content than a raw text feed, cheaper than 22 LLM players. Free path: canvas/SVG pitch in the spectator page (same language as the chess board) |
| Analyst skin (optional, for humans after kickoff / in review) | ➕ | Top / Side / Follow-ball cams, phase list, pass arrows, "Havertz plays it to Saka." TV analysis — not the manager's laptop |
| Goal replay | 🔴 | With the feed it's a re-wind of events around the goal (6–10 phases per goal, loopable) |
| Team sheet / lineup graphic dropped ~1h before kickoff | 🔴 | Like a real TV lineup graphic |
| "Manager said…" quotes pulled from the agent's last instruction | 🔴 | Requires the action transcript (§4) — write it as speech |
| **Remove attribute numbers + edit controls from any human surface** | 🟡 | Today the *only* match view is the 3D theater, which shows rating chips on players, hover "X rated", and full FM editing (formation pickers, drag players). That is FM-for-humans + stats on the pitch — the exact leak the doctrine forbids. Theater stays as a dev sandbox only. **Guard (ratified): humans never draw tactics that change the live match — that breaks settlement.** Numbers hidden on the broadcast unless a graphic is opened |
| Form guide, table, transfer rumours around the match | 🟡 | Table/form exist; rumours/teasers don't |
| Crowd swell / foul tension / second-yellow drama *felt* | 🔴 | Comes with the broadcast + voice layers |
| Stake / tip on the result (not on sliders) | ➕ | Watch-only for now; spectator pool rails exist in the chess economy, not wired to AFM |

---

## 7. Voice of the match

| Item | Status | Notes |
|------|--------|-------|
| Commentary from events + agent actions (template or LLM) | 🔴 | Manifesto build order step 4 |
| Football-language copy ("high line", "he's through", "they've packed the box") | 🔴 | Today humans read raw engine event text — accurate but flat |
| Narrative "why this match mattered" | ➕ | Storylines after seasons of data |

---

## 8. Cinema / 3D — **PARKED as physics, ratified as a spectator layer**

**Approach (ratified):** keep the match as an event sim (goals, cards, minutes, 2–5 min). 3D is a **spectator layer the agents drive** — a rendered event timeline, *not* a live physics reconstruction of a real game. One sim → one spatial event log → any client (2D board, Godot, R3F) renders it.

| Item | Status | Notes |
|------|--------|-------|
| Existing 3D theater (players, crowd, cameras, LED boards) | 🟡 | **Parked per direction: "perfect the 2D before the 3D; the 3D is trash right now."** Mechanically functional but it is the source of product leakage (ratings on pitch + FM editors on the only match view). No 3D polish until the 2D broadcast + engine spatial data land |
| WebGL context hardening (renderer robustness) | 🟢 | **Shipped (2026-09-05):** fixed the homepage scroll/desk/vault/hero scenes crashing in dev (`Cannot read properties of null (reading 'precision')`) — cleanup no longer force-loses the canvas context (a React StrictMode remount reuses it), and renderer creation is guarded so any WebGL failure falls back to the CSS board instead of a page crash. Theater renderer (`PitchView`) hardened the same way: retry ladder (antialias+high-performance → plain → default), leak-free init failure, `webglcontextlost` pause / `webglcontextrestored` resume, crash-safe dispose. Verified in a real browser session (StrictMode double-mount, scene initializes, zero exceptions) |
| Reusable asset pipeline (Hunyuan3D / Trellis / Blender MCP → GLB) | ➕ | Generate *once*: one stadium (or stand kits), a pitch, goals, a generic player body re-skinned per catalog player, ball, ads. No unique mesh per match. Export GLB into the engine |
| 3D client renderer (Godot 4 or Three.js / R3F in-browser) | ➕ | Map `actor_id → generated player mesh`, play canned run/shot/celebrate clips, cameras follow the ball. **The Evans board's camera set is the reference (Broadcast / Top / Goal / Side / Follow ball)**; EndorArena streams agent positions onto a 3D pitch in the browser. The board sits between the desks — it must not become either the manager's workplace or a human editor |
| Camera work, grass, kits, cinematic skin | ➕ | Manifesto: *"Cinema skin — cameras, grass, kits. Last. Cosmetics on a dead engine are worthless."* |
| Closest product analogs | ➕ | LLM FC (manager agents + voxel 3D pitch) and ClawFC (agents on a 3D stadium) — same idea, 3D as the watch layer |

---

## 9. World operations & rails

| Item | Status | Notes |
|------|--------|-------|
| Season lifecycle (open → tick → standings), daily keeper | 🟢 | `season.py` + `keep_agents_playing.py` |
| Knockout cup with ET/pens | 🟢 | `cup.py`, 10 tests |
| Clubs API + lineup lock API | 🟢 | `/api/agentic/football/*` routes |
| AFM API server responsiveness | 🟡 | **Ops flag:** Python API on :8000 was listening but unresponsive to season/clubs probes (state is file-based; engine fine). Needs restart check before pages show live data |
| On-chain agent identity + escrow contracts | 🟡 | Building blocks exist (Cardano mint scripts, Solidity escrow incl. `SpectatorPool`) but are **not connected** to any AFM match/odds/UI |
| Live league breadth | 🟡 | Only 2 agent clubs in the live season (Season 4) — a league isn't a league yet. More clubs/agent minds needed |
| Human loop (alerts, "match starting now", watch together) | ➕ | After broadcast V1 |

---

## 10. Build order (phases, with definition of done)

Per current direction: **2D broadcast is the focus; 3D is parked.** The engine spatial work is the honest prerequisite for *both* products, so it is Phase 1.

| Phase | Scope | Definition of done |
|-------|-------|--------------------|
| **P1 — Engine spatial + FM report data** ✅ **DONE (2026-09-06, engine v1.3)** | Emit the ratified phase stream: tick/event log `(minute, type, actor_id, x, y, z, facing)` feeding `Phase = {t, ball, players[], action?, note?}`; xG per shot; per-player post-match ratings + errors; manager action transcript; sub-choice fix; expose the manager webhook ask→reply contract | Feed events carry x/y/z + facing and every match result ships a deterministic `phases` stream (done v1.2); shots carry xG (v1.3); `MatchResult` carries per-player ratings + errors (v1.3); the action log is stored per matchday (decisions + press conference + sub events); the `/move`-style manager protocol accepts a JSON lineup/tactics reply (shipped 2026-09-05); determinism tests still green; G4 tiredness carries into the next lock (v1.3: fatigue in/out + season wiring). 140 AFM tests green |
| **P2 — Human 2D broadcast V1** | Watch flow end-to-end: what's-on-today → pre-match tactics board (agent plan: formation, press triggers, set-pieces) → match on the Evans-style board (phase player, Broadcast cam + scorebug + minute, named players, goal replay loop) + lineup graphic + "manager said"; analyst skin (Top/Side/Follow, phase list, pass arrows) optional; strip every attribute number & edit control off human surfaces | A spectator with no context can open `/football/watch`, watch a match unfold, and say who won and why — and a stranger watching the board can say "that was a counter, not a corner grind" (mute-the-labels test passes on the broadcast) |
| **P3 — Agent FM tools** | Repoint agent door off the 3D theater; squad screen; submit XI + tactics; see opp lineup; in-match tool calls at breaks; post-match report; inbox v1 | An agent can run its club and explain a loss from its report — without ever opening a camera (mute-the-labels test passes on the tools) |
| **P4 — Voice of the match** | Commentary (template/LLM) from events + action transcript; football language | A goal, a red, a shape change all *read* like football, not event dumps |
| **P5 — Cinema / 3D spectator layer** | Revisit 3D only after P2 is proven — as a rendered event timeline over the spatial log, with the one-time GLB asset pipeline; never as physics | Gated: nothing here until broadcast V1 ships; reuse P1's spatial log so this stays cheap |

**Acceptance test for the whole split (run it every phase):** mute every UI label. The agent still knows what to do from numbers and reports (FM). The human still understands who is winning and why the game flipped (football).

---

## 11. How to update this file

- Same commit as the code change it describes.
- Move the row's status and add a one-line note (what changed + date).
- If the change is cosmetic/refactor with no product effect: note it under the row, don't invent new statuses.
- If a 🔴 becomes 🟢, tick its Goal's proof (G1–G5) when applicable.
