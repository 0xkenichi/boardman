/**
 * AFM roadmap status data — mirrored from `docs/games/AGENTIC_FOOTBALL_MANAGERS_ROADMAP.md`.
 *
 * This module is the product-facing projection of the master plan. When the
 * roadmap doc changes (per its own §11 rules), update the matching rows here
 * in the same change so the status board stays truthful.
 * * Last synced with doc: 2026-09-20
   */

export type RoadmapStatus = 'done' | 'needs-work' | 'must' | 'add-on' | 'parked'

export interface RoadmapItem {
  label: string
  status: RoadmapStatus
  note?: string
}

export interface RoadmapSection {
  id: string
  title: string
  tagline?: string
  /** Section-level banner, e.g. "PARKED" for cinema. */
  banner?: { text: string; status: RoadmapStatus }
  items: RoadmapItem[]
}

export interface Goal {
  id: string
  title: string
  proof: string
}

export interface BuildPhase {
  id: string
  name: string
  scope: string
  done: string
}

export const STATUS_META: Record<RoadmapStatus, { mark: string; label: string }> = {
  done: { mark: '🟢', label: 'Done' },
  'needs-work': { mark: '🟡', label: 'Needs work' },
  must: { mark: '🔴', label: 'Must' },
  'add-on': { mark: '➕', label: 'Add-on' },
  parked: { mark: '⏸️', label: 'Parked' },
}

export const OBJECTIVE =
  'Prove that one deterministic football engine can feed two products that never touch: ' +
  'agents live in Football Manager (a tool belt of text + numbers), humans live in a broadcast ' +
  '(2D pitch, named players, scorebug, replay), and the engine is the only thing both sides touch. ' +
  'If either side sees the other side’s UI, the fantasy breaks — that rule is the product.'

export const GOALS: Goal[] = [
  {
    id: 'G1',
    title: 'Engine honesty',
    proof:
      'Same seed → byte-identical feed for every viewer & settlement. Feed is spatial & timed: 100+ events carrying coordinates, xG, cards, tiredness. Post-match FM report (ratings, xG, heat, errors) derivable purely from the feed.',
  },
  {
    id: 'G2',
    title: 'Two products, zero leakage',
    proof:
      'An agent can run its club start-to-finish without ever seeing a camera. A human can follow a full matchday without ever seeing a slider or an attribute number. Test: mute every UI label — the agent still knows what to do from numbers; the human still understands who is winning and why the game flipped.',
  },
  {
    id: 'G3',
    title: '2D broadcast first',
    proof:
      'A spectator lands at /football/watch, sees “what’s on today”, and watches a full match on a 2D pitch board (scorebug, named players moving, goal replay, lineup graphic). 3D cinema is explicitly parked until this is proven.',
  },
  {
    id: 'G4',
    title: 'Consequences bite',
    proof:
      'Cards / injuries / tiredness from matchday N demonstrably change the options at matchday N+1’s lineup lock (not just a text line).',
  },
  {
    id: 'G5',
    title: 'Rules in code, not vibes',
    proof:
      'Lineup legality, discipline, market rules, determinism — enforced and covered by tests. Suite stays green (≥40 AFM tests).',
  },
]

export const SECTIONS: RoadmapSection[] = [
  {
    id: 'engine',
    title: 'Shared engine',
    tagline: 'The only thing both products touch — it eats FM inputs, emits a football match.',
    items: [
      {
        label: 'Deterministic seeded engine (simulate_match)',
        status: 'done',
        note: 'Same match_id → same match; replay endpoint reproduces. Typed engine boundary landed (2026-09-20): engines/afm/match-contracts (@afm/match-contracts) ships TS contracts + Zod schemas for MatchInput/MatchOutput, a 22-case discriminated-union event log, and PositionTick (per-tick x/y for all 22 + ball) — fixtures + 14 vitest tests enforce the invariants (bench vs sub budget, ascending sequences, 22 distinct players/tick) and a compile-time tripwire catches type/schema drift. engines/afm/engine-adapter (@afm/engine-adapter) bridges the Python engine’s MatchResult into schema-valid MatchOutput: ground-truthed mapping (pass→carry, tackle→interception, fouls dropped to a commentary channel rather than fabricated), metre→0–100 rescale, geometric carrier, 17 tests.',
      },
      {
        label: 'Full law set: offside, fouls, yellow/red, second-yellow→red (plays on with 10), corners, throw-ins, goal kicks, stoppage time',
        status: 'done',
        note: 'Set pieces play out since engine v1.4 (2026-09-20): corners / free kicks / in-play penalties resolve as real chances with named takers and kind-tagged goals. 183 AFM tests green',
      },
      {
        label: 'Extra time + penalty shootout when require_result=True',
        status: 'done',
        note: 'Cup ties settled; walk-off + sudden death',
      },
      {
        label: 'Injuries + forced subs; benches + manager-window subs',
        status: 'done',
        note: 'Windows at 55/64/70 (+HT break). In-match injury now costs the player the next matchday (v1.4 decide wiring: recorded at the final whistle, excluded at the next lock, flag decays after)',
      },
      {
        label: 'Player attribute model (10 attrs, deterministic per player)',
        status: 'done',
        note: 'attributes.py; same player → same profile',
      },
      {
        label: 'Tactics: formation, tags, mentality, instructions, HT adjustment (*_tactics_2h)',
        status: 'done',
        note: 'Shapes/tags measurably shift event patterns. HT contingency plans (v1.4): the matchday reply may pre-commit plans keyed trailing/level/leading; the engine applies the plan the HT score calls for — an explicit *_tactics_2h still wins',
      },
      {
        label: 'Post-match derive_stats (team fold over feed)',
        status: 'done',
        note: 'Possession, shots, cards, corners, etc.',
      },
      {
        label: 'Suspensions carry into next matchday lineup lock',
        status: 'done',
        note: 'Reds + 2nd-yellow → banned at next lock',
      },
      {
        label: 'Weekly real-world oracle → form/injury into attributes',
        status: 'done',
        note: 'weekly_oracle.py',
      },
      {
        label: 'Spatial events (coordinates / zones / ball movement)',
        status: 'needs-work',
        note: 'Shipped (engine v1.1 → v1.2): every event carries x/y/z/facing/actor_id via a pure deterministic overlay (spatialize_feed — never consumes the match RNG; 6 tests). Phase stream builder shipped (2026-09-05, engine v1.2): phases.py turns the log into a renderable stream — every event becomes { t, ball{x,y,z}, players[22], action? (pass/carry/shot/cross), note? } with strictly increasing t, the actor snapped to the ball, deterministic in-formation positioning for both XIs; every match result now carries phases (9 tests, replay-safe). Renderer consumption shipped (2026-09-20): the 2D broadcast plays the phase stream directly (buildPhaseFrames — real per-event positions, actor-on-ball highlight derived from geometry); the movement model remains the fallback for pre-spatial replays.',
      },
      {
        label: 'Player-layer decide(game_state) sandbox (optional, heavier)',
        status: 'add-on',
        note: 'AgentPitch-style: each outfield role runs a sandboxed decide(game_state) (pass/shoot/press/hold). Default is a cheap stats engine for the 90′ — LLMs only on the manager. The sanctioned answer to “players with a mind of their own.” Ratified (2026-09-20, tech architecture doc): the two AI layers never conflate — the LLM belongs on the manager agent only; the in-match movement/behavior layer (steering/potential fields, FSM or behavior trees) is classical game AI and is tracked work, not deferred indefinitely.',
      },
      {
        label: 'xG per shot',
        status: 'done',
        note: 'Shipped (engine v1.3, 2026-09-06): every shot/goal carries per-shot xG from finishing vs keeper, position and pressure — deterministic, same hash stream as the spatial overlay.',
      },
      {
        label: 'Per-player post-match ratings',
        status: 'done',
        note: 'Shipped (engine v1.3, 2026-09-06): MatchResult.player_stats folds the spatialized feed per actor (minutes, shots, goals, xG, tackles, cards, passes) into a 0–99 rating.',
      },
      {
        label: 'Error attribution (“why we lost”)',
        status: 'done',
        note: 'Shipped (engine v1.3, 2026-09-06): per-player high-xG misses + match-level critical errors; report.py turns them into one-line “why” attributions.',
      },
      {
        label: 'Manager action transcript',
        status: 'done',
        note: 'Shipped (2026-09-06): per-matchday action log (formation/tags/XI/instructions/source + press conference) exposed via get_matchday_transcript; sub events logged in the feed.',
      },
      {
        label: 'Individual player skill drives outcomes (not only team aggregates)',
        status: 'done',
        note: 'Shipped (engine v1.3, 2026-09-06): shot/goal odds are per-actor — the shooter’s finishing/positioning vs the opposing keeper anchors _shot_xg. v1.4 (2026-09-20): chances are weighted across the attacking pool — movement finds chances, finishing turns up more often — so chance distribution follows the squad instead of funneling to one best attacker.',
      },
      {
        label: 'Role/duty-level instructions',
        status: 'needs-work',
        note: 'Tags/mentality exist; per-role duties (press_forward, false_9…) don’t',
      },
      {
        label: 'Persistent tiredness across fixtures',
        status: 'done',
        note: 'Shipped (engine v1.3, 2026-09-06): simulate_match takes home/away fatigue and returns MatchResult.fatigue — the season stores it per club, feeds it into the next fixture with FATIGUE_RECOVERY rest, and surfaces it on the squad screen + the manager ask (own squad only). decide v2 (2026-09-20): auto XI selection is condition-aware — exhausted stars rotate to the bench while the XI stays legal (test_afm_decide_v2.py).',
      },
      {
        label: 'Substitution choice realism',
        status: 'done',
        note: 'Fixed (engine v1.3, 2026-09-06): the Mbappé-for-GK bug is gone — subs are match-type aware (chasing → attackers on; protecting → fresh legs in defence/midfield; injuries replace like-for-like) and position-sane (a keeper only ever replaces a keeper). Every sub event carries kind + match_type. Tested across seeds (test_afm_subs_fatigue.py).',
      },
      {
        label: 'Assist / save attribution',
        status: 'needs-work',
        note: 'Assists shipped (engine v1.4, 2026-09-20): ~62% of open-play goals carry an assister, folded into player_stats + the FM report; assist-only records are deliberately not created (minutes=0 would poison the rating sort). Save attribution still open',
      },
      {
        label: 'Dedicated set-piece subsystem (corners, free kicks, penalties)',
        status: 'needs-work',
        note: 'Half-shipped (engine v1.4, 2026-09-20): corners / free kicks / in-play penalties now resolve as real chances — named takers from tactics.set_pieces, kind-tagged goals — but still through the open-play probability chain; the distinct attribute mix (jumping/heading/technique) + assigned targets remain the plan',
      },
    ],
  },
  {
    id: 'fm',
    title: 'Product A — Agent FM tools',
    tagline: 'Football Manager. A manager’s whole life is a tool belt of text + numbers.',
    items: [
      {
        label: 'Club/squad data (attributes, positions, wages, form, injury, contract)',
        status: 'done',
        note: 'Lives in club_store.py / catalog — data exists, no screen',
      },
      {
        label: 'Squad screen (attrs, roles, fitness, morale, form, contract, wage)',
        status: 'done',
        note: 'Shipped V1 (2026-09-05): FM-style read-only screen at /football/squad/[agent_id] — sortable table (status, name, ability, form, condition, morale, injury, wage, value, contract), position filters + search, and a player detail panel with Physical / Technical / Mental attribute groups. Backed by club_store.squad_view(): derived attrs via attributes.py, status from the locked lineup (starter/bench/squad), deterministic 2–5y contract projection (no contract ledger yet — derived, like attributes); 4 tests, verified live. Transfers + in-match tools remain their own rows.',
      },
      {
        label: 'Pre-kickoff: set formation + roles + team instructions, submit XI',
        status: 'done',
        note: 'Shipped (2026-09-05): the manager protocol — the House asks each manager for its matchday plan (webhook POST) with the observable context (own squad + record + wallet, the opposition’s full lineup — never hidden sliders — and the legal rules); the manager replies {formation, xi, bench, tactical_tags, instructions}. Validated; dead webhook → deterministic decide_matchday fallback, source recorded. 18 tests (test_afm_manager_protocol.py)',
      },
      {
        label: 'Manager protocol mirrors chess /move (webhook ask→JSON reply)',
        status: 'done',
        note: 'Shipped (2026-09-05): manager_protocol.py — build_matchday_ask / request_matchday_plan / validate_matchday_plan, wired into season._agents_decide (webhook first, fallback recorded). Owner-set webhook via POST /football/agents/webhook. Plans extension (v1.4, 2026-09-20): the reply may carry optional plans {trailing|level|leading} — validated against the whitelists, persisted at lock, handed to the engine with the lineup.',
      },
      {
        label: 'See opposition lineup (not their sliders)',
        status: 'must',
        note: 'Needed for real decisions',
      },
      {
        label: 'In-match tools at natural breaks (HT, 60′, red card, injury): sub, change_instruction, change_shape',
        status: 'must',
        note: 'Engine consumes *_tactics_2h; no tool surface + no action log. NB: v1.4 HT contingency plans are pre-committed at lock, not live in-match tools — this row stays open',
      },
      {
        label: 'Inbox: board, press, player unrest, next fixture',
        status: 'must',
        note: 'Not started',
      },
      {
        label: 'Post-match report: ratings, xG, heat, errors that cost the game',
        status: 'done',
        note: 'Shipped (2026-09-06, engine v1.3 data): report.py folds the stored player_stats into a per-fixture FM report — per-player ratings, team xG, top/worst performer, error lists + one-line “why” attributions. Agent surface: GET /football/report/{agent_id} (+ season/report for both sides); owner dashboard result rows carry a report summary. v1.4 (2026-09-20): assists + true minutes-on-pitch flow into the report. Heat maps: not yet (needs spatial event density per player). 7 tests (test_afm_report.py)',
      },
      {
        label: 'Transfer list, shortlist, bids, wage structure',
        status: 'must',
        note: 'market.py backend exists; no agent tool/UI and no shortlist',
      },
      {
        label: 'Training / minutes management / injury list',
        status: 'add-on',
        note: 'Backend partial',
      },
      {
        label: 'Agent portal currently links the agent to the 3D theater',
        status: 'needs-work',
        note: 'Violates the split (“do not make the agent click a 3D camera”). Agent door must be repointed to FM tools',
      },
    ],
  },
  {
    id: 'broadcast',
    title: 'Product B — Human broadcast (2D first)',
    tagline: 'Real football. A spectator sits in the stand; humans never see a slider or an attribute number.',
    items: [
      {
        label: 'Front door + role hubs (/football, /watch, /owner, /agent)',
        status: 'done',
        note: 'Shell + journeys; watch-only chosen',
      },
      {
        label: 'League table + fixtures + recent results w/ mini stats',
        status: 'done',
        note: 'LeagueView, MatchStats on results',
      },
      {
        label: '“What’s on today” → pick a match → watch',
        status: 'done',
        note: 'Shipped (2026-09-20): the watch hub opens on the picker — upcoming fixtures (lock time + lineups-in state, deep-linking the pre-match board) and latest results (score + stats line, one-click replay). League/owner result rows also link one-click into the broadcast',
      },
      {
        label: '2D pitch board: scorebug, named players moving, ball',
        status: 'needs-work',
        note: 'Shipped V1 (2026-09-20): MatchBroadcast at /football/watch/broadcast — top-down 2D pitch, 22 named player dots + ball, scorebug with running score replayed from the feed, possession bar from the engine stats, commentary ticker, both lineups (name + slot), play/pause/speed/flip. Plays real recorded replays driven by the engine phase stream (buildPhaseFrames — real per-event positions from phases.py, actor-on-ball highlight from geometry); movement-model fallback for pre-spatial replays; deep-link ?md&home&away, auto-picks the latest finished fixture, league/owner watch pills link straight in; scripted demo when nothing resolves. Architecture ratified (2026-09-20): this DOM/CSS board is the wireframe — the shipping client is PixiJS (+ pixi-viewport / pixi-particles) per AFM_TECHNICAL_ARCHITECTURE.md §2, fed by the same phase stream, with the config-driven pacing layer (§7) compressing the full log to a 1–5 min broadcast. Still open: Pixi client, cameras, goal replay loop. 2D first — 3D parked as physics.',
      },
      {
        label: 'Pre-match tactics board (“how this manager wants to play”)',
        status: 'done',
        note: 'Shipped (2026-09-20): PreMatchBoard at /football/watch/prematch — both managers’ locked plans from season.prematch_view: formation shapes with named XI dots on a 2D pitch, tags, pre-committed HT contingency plans (trailing/level/leading), manager instructions + webhook/auto chip, ban/injury news. Spectator-safe by construction (no numbers, no edit controls). Backed by GET /football/season/prematch (7 tests). Tactics App remains the reference for richer animation later',
      },
      {
        label: 'Analyst skin (optional, for humans after kickoff / in review)',
        status: 'add-on',
        note: 'Top / Side / Follow-ball cams, phase list, pass arrows, “Havertz plays it to Saka.” TV analysis — not the manager’s laptop.',
      },
      {
        label: 'Goal replay',
        status: 'must',
        note: 'With the feed it’s a re-wind of events around the goal (6–10 phases per goal, loopable)',
      },
      {
        label: 'Team sheet / lineup graphic dropped ~1h before kickoff',
        status: 'must',
        note: 'Like a real TV lineup graphic',
      },
      {
        label: '“Manager said…” quotes pulled from the agent’s last instruction',
        status: 'must',
        note: 'Requires the action transcript — write it as speech',
      },
      {
        label: 'Remove attribute numbers + edit controls from any human surface',
        status: 'needs-work',
        note: 'Today the only match view is the 3D theater, which shows rating chips on players, hover “X rated”, and full FM editing. Theater stays as a dev sandbox only. Guard (ratified): humans never draw tactics that change the live match — that breaks settlement. Numbers hidden on the broadcast unless a graphic is opened. The 2D broadcast (2026-09-20) is leak-free by construction — names, slots and shirt numbers only.',
      },
      {
        label: 'Form guide, table, transfer rumours around the match',
        status: 'needs-work',
        note: 'Table/form exist; rumours/teasers don’t',
      },
      {
        label: 'Crowd swell / foul tension / second-yellow drama felt',
        status: 'must',
        note: 'Comes with the broadcast + voice layers',
      },
      {
        label: 'Stake / tip on the result (not on sliders)',
        status: 'add-on',
        note: 'Watch-only for now; spectator pool rails exist in the chess economy, not wired to AFM',
      },
    ],
  },
  {
    id: 'voice',
    title: 'Voice of the match',
    items: [
      {
        label: 'Commentary from events + agent actions (template or LLM)',
        status: 'must',
        note: 'Manifesto build order step 4',
      },
      {
        label: 'Football-language copy (“high line”, “he’s through”, “they’ve packed the box”)',
        status: 'must',
        note: 'Today humans read raw engine event text — accurate but flat',
      },
      {
        label: 'Narrative “why this match mattered”',
        status: 'add-on',
        note: 'Storylines after seasons of data',
      },
    ],
  },
  {
    id: 'cinema',
    title: 'Cinema / 3D — parked as physics, ratified as a spectator layer',
    banner: { text: 'PARKED as physics — ratified as an event-timeline spectator layer', status: 'parked' },
    items: [
      {
        label: 'Existing 3D theater (players, crowd, cameras, LED boards)',
        status: 'parked',
        note: 'Parked per direction: “the 3D is trash right now.” Mechanically functional but the source of product leakage (ratings on pitch + FM editors on the only match view). No 3D polish until the 2D broadcast + engine spatial data land.',
      },
      {
        label: 'WebGL context hardening (renderer robustness)',
        status: 'done',
        note: 'Shipped (2026-09-05): fixed the homepage scroll/desk/vault/hero scenes crashing in dev (Cannot read properties of null (reading “precision”)) — cleanup no longer force-loses the canvas context (a React StrictMode remount reuses it), and renderer creation is guarded so any WebGL failure falls back to the CSS board. Theater renderer (PitchView) hardened the same way: retry ladder (antialias+high-performance → plain → default), leak-free init failure, webglcontextlost pause / webglcontextrestored resume, crash-safe dispose. Verified in a real browser session (StrictMode double-mount, scene initializes, zero exceptions).',
      },
      {
        label: 'Reusable asset pipeline (Hunyuan3D / Trellis / Blender MCP → GLB)',
        status: 'add-on',
        note: 'Generate once: one stadium (or stand kits), a pitch, goals, a generic player body re-skinned per catalog player, ball, ads. No unique mesh per match. Export GLB into the engine.',
      },
      {
        label: '3D client renderer (Godot 4 or Three.js / R3F in-browser)',
        status: 'add-on',
        note: 'Map actor_id → generated player mesh, play canned run/shot/celebrate clips, cameras follow the ball. The Evans board’s camera set is the reference (Broadcast / Top / Goal / Side / Follow ball); EndorArena streams agent positions onto a 3D pitch in the browser. The board sits between the desks — it must not become either the manager’s workplace or a human editor.',
      },
      {
        label: 'Camera work, grass, kits, cinematic skin',
        status: 'add-on',
        note: '“Cinema skin — cameras, grass, kits. Last. Cosmetics on a dead engine are worthless.”',
      },
      {
        label: 'Closest product analogs',
        status: 'add-on',
        note: 'LLM FC (manager agents + voxel 3D pitch) and ClawFC (agents on a 3D stadium) — same idea, 3D as the watch layer.',
      },
    ],
  },
  {
    id: 'ops',
    title: 'World operations & rails',
    items: [
      {
        label: 'Season lifecycle (open → tick → standings), daily keeper',
        status: 'done',
        note: 'season.py + keep_agents_playing.py',
      },
      {
        label: 'Knockout cup with ET/pens',
        status: 'done',
        note: 'cup.py, 10 tests',
      },
      {
        label: 'Clubs API + lineup lock API',
        status: 'done',
        note: '/api/agentic/football/* routes',
      },
      {
        label: 'AFM API server responsiveness',
        status: 'needs-work',
        note: 'Ops flag: Python API on :8000 was listening but unresponsive to season/clubs probes (state is file-based; engine fine). Needs restart check before pages show live data. Ratified shape (2026-09-20, tech architecture §4/§8): spectators move from polling to WebSockets over the persisted event+position log (late joiners fetch log-so-far, then subscribe); a world-clock service becomes the single canonical schedule source agents query (GET /world-clock) — never agent-computed.',
      },
      {
        label: 'On-chain agent identity + escrow contracts',
        status: 'needs-work',
        note: 'Building blocks exist (Cardano mint scripts, Solidity escrow incl. SpectatorPool) but are not connected to any AFM match/odds/UI',
      },
      {
        label: 'Live league breadth',
        status: 'needs-work',
        note: 'Only 2 agent clubs in the live season (Season 4) — a league isn’t a league yet. More clubs/agent minds needed. Ratified path (2026-09-20, scheduling doc §7): publish the playbook/API ahead of launch and run a qualifying/builder period (sandbox exhibitions) to organically reach the 10–20 agent floor.',
      },
      {
        label: 'Human loop (alerts, “match starting now”, watch together)',
        status: 'add-on',
        note: 'After broadcast V1',
      },
    ],
  },
]

export const BUILD_ORDER: BuildPhase[] = [
  {
    id: 'P1',
    name: 'Engine spatial + FM report data',
    scope:
      'Emit the ratified phase stream: tick/event log (minute, type, actor_id, x, y, z, facing) feeding Phase = {t, ball, players[], action?, note?}; xG per shot; per-player post-match ratings + errors; manager action transcript; sub-choice fix; expose the manager webhook ask→reply contract',
    done:
      'Feed events carry x/y/z + facing and every match result ships a deterministic phases stream (done v1.2); shots carry xG; MatchResult gains per-player ratings derived from the feed; a stored action log exists; the /move-style manager protocol accepts a JSON lineup/tactics reply; determinism tests still green; G4 tiredness carries into next lock. Extended by engine v1.4 + decide v2 (2026-09-20): chance spread, assists, set pieces that play out, score-state modelling, HT contingency plans, true minutes, injury carry-over — 183 AFM tests green',
  },
  {
    id: 'P2',
    name: 'Human 2D broadcast V1',
    scope:
      'Watch flow end-to-end: what’s-on-today → pre-match tactics board (agent plan: formation, press triggers, set-pieces) → match on the Evans-style board (phase player, Broadcast cam + scorebug + minute, named players, goal replay loop) + lineup graphic + “manager said”; analyst skin (Top/Side/Follow, phase list, pass arrows) optional; strip every attribute number & edit control off human surfaces',
    done:
      'A spectator with no context can open /football/watch, watch a match unfold, and say who won and why — and a stranger watching the board can say “that was a counter, not a corner grind” (mute-the-labels test passes on the broadcast). Progress (2026-09-20): the 2D board is live, plays real recorded replays from the engine phase stream (/football/watch/broadcast); the watch-hub picker + pre-match tactics board shipped the same day (/football/watch/prematch from season.prematch_view) — still open: PixiJS client + pacing layer (per the ratified tech architecture), goal replay loop, “manager said”',
  },
  {
    id: 'P3',
    name: 'Agent FM tools',
    scope:
      'Repoint agent door off the 3D theater; squad screen; submit XI + tactics; see opp lineup; in-match tool calls at breaks; post-match report; inbox v1',
    done:
      'An agent can run its club and explain a loss from its report — without ever opening a camera (mute-the-labels test passes on the tools)',
  },
  {
    id: 'P4',
    name: 'Voice of the match',
    scope: 'Commentary (template/LLM) from events + action transcript; football language',
    done: 'A goal, a red, a shape change all read like football, not event dumps',
  },
  {
    id: 'P5',
    name: 'Cinema / 3D spectator layer',
    scope:
      'Revisit 3D only after P2 is proven — as a rendered event timeline over the spatial log, with the one-time GLB asset pipeline; never as physics',
    done: 'Gated: nothing here until broadcast V1 ships; reuse P1’s spatial log so this stays cheap',
  },
]

export function sectionCounts(section: RoadmapSection): Record<RoadmapStatus, number> {
  const out: Record<RoadmapStatus, number> = {
    done: 0,
    'needs-work': 0,
    must: 0,
    'add-on': 0,
    parked: 0,
  }
  for (const it of section.items) out[it.status] += 1
  return out
}

export function overallCounts(): Record<RoadmapStatus, number> {
  const out: Record<RoadmapStatus, number> = {
    done: 0,
    'needs-work': 0,
    must: 0,
    'add-on': 0,
    parked: 0,
  }
  for (const s of SECTIONS) {
    const c = sectionCounts(s)
    for (const k of Object.keys(out) as RoadmapStatus[]) out[k] += c[k]
  }
  return out
}