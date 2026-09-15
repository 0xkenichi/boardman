/**
 * AFM roadmap status data — mirrored from `docs/games/AGENTIC_FOOTBALL_MANAGERS_ROADMAP.md`.
 *
 * This module is the product-facing projection of the master plan. When the
 * roadmap doc changes (per its own §11 rules), update the matching rows here
 * in the same change so the status board stays truthful.
 *
 * Last synced with doc: 2026-09-05
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
        note: 'Same match_id → same match; replay endpoint reproduces',
      },
      {
        label: 'Full law set: offside, fouls, yellow/red, second-yellow→red (plays on with 10), corners, throw-ins, goal kicks, stoppage time',
        status: 'done',
        note: '40 AFM tests green',
      },
      {
        label: 'Extra time + penalty shootout when require_result=True',
        status: 'done',
        note: 'Cup ties settled; walk-off + sudden death',
      },
      {
        label: 'Injuries + forced subs; benches + manager-window subs',
        status: 'done',
        note: 'Windows at 55/64/70 (+HT break)',
      },
      {
        label: 'Player attribute model (10 attrs, deterministic per player)',
        status: 'done',
        note: 'attributes.py; same player → same profile',
      },
      {
        label: 'Tactics: formation, tags, mentality, instructions, HT adjustment (*_tactics_2h)',
        status: 'done',
        note: 'Shapes/tags measurably shift event patterns',
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
        note: 'Shipped (engine v1.1 → v1.2): every event carries x/y/z/facing/actor_id via a pure deterministic overlay (spatialize_feed — never consumes the match RNG; 6 tests). Phase stream builder shipped (2026-09-05, engine v1.2): phases.py turns the log into a renderable stream — every event becomes { t, ball{x,y,z}, players[22], action? (pass/carry/shot/cross), note? } with strictly increasing t, the actor snapped to the ball, deterministic in-formation positioning for both XIs; every match result now carries phases (9 tests, replay-safe). Still needs: per-shot xG (own row) and renderer consumption (P2).',
      },
      {
        label: 'Player-layer decide(game_state) sandbox (optional, heavier)',
        status: 'add-on',
        note: 'AgentPitch-style: each outfield role runs a sandboxed decide(game_state) (pass/shoot/press/hold). Default is a cheap stats engine for the 90′ — LLMs only on the manager. The sanctioned answer to “players with a mind of their own.”',
      },
      {
        label: 'xG per shot',
        status: 'must',
        note: 'Shots carry on_target only. Need per-shot xG from position/angle/defensive pressure.',
      },
      {
        label: 'Per-player post-match ratings',
        status: 'must',
        note: 'No ratings anywhere. Feed has player_id per event, so a fold is feasible — but the manifesto needs ratings, xG, heat, and “errors that cost the game.”',
      },
      {
        label: 'Error attribution (“why we lost”)',
        status: 'must',
        note: 'Post-match file for the next agent turn: which mistakes/events cost the match',
      },
      {
        label: 'Manager action transcript',
        status: 'must',
        note: 'Decisions exist as a plan dict only (decide.py). Need a discrete logged action log: set_shape 4-3-3, role ST press_forward, instruction defensive_line high, xi [11 ids], sub 67′ 9 off 21 on. Every action becomes commentary fuel + the “why we lost” file.',
      },
      {
        label: 'Individual player skill drives outcomes (not only team aggregates)',
        status: 'needs-work',
        note: 'Shot/goal odds mostly use team aggregates; player skill selects the actor and shootout kicker. Needs per-actor resolution so “a 6.4-rated midfielder can score a worldie, rarely.”',
      },
      {
        label: 'Role/duty-level instructions',
        status: 'needs-work',
        note: 'Tags/mentality exist; per-role duties (press_forward, false_9…) don’t',
      },
      {
        label: 'Persistent tiredness across fixtures',
        status: 'needs-work',
        note: 'In-match fitness exists; fatigue that makes N+1 decisions harder doesn’t yet',
      },
      {
        label: 'Substitution choice realism',
        status: 'needs-work',
        note: 'Known bug: engine subbed Mbappé off for a GK while winning 2-0 (pure fitness rotation). Needs match-type subs (defensive/holding sub when leading, attacking when chasing) + position-sane replacement',
      },
      {
        label: 'Assist / save attribution',
        status: 'add-on',
        note: 'For FM report depth later',
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
        status: 'must',
        note: 'decide.py does this automatically; the agent has no tool to express its own plan',
      },
      {
        label: 'Manager protocol mirrors chess /move (webhook ask→JSON reply)',
        status: 'needs-work',
        note: 'Pattern exists (runtime/webhook.py + decide_matchday); not exposed as an ask→reply contract: Boardman asks for lineup/tactics, the agent replies JSON. Same shape as the chess move loop.',
      },
      {
        label: 'See opposition lineup (not their sliders)',
        status: 'must',
        note: 'Needed for real decisions',
      },
      {
        label: 'In-match tools at natural breaks (HT, 60′, red card, injury): sub, change_instruction, change_shape',
        status: 'must',
        note: 'Engine consumes *_tactics_2h; no tool surface + no action log',
      },
      {
        label: 'Inbox: board, press, player unrest, next fixture',
        status: 'must',
        note: 'Not started',
      },
      {
        label: 'Post-match report: ratings, xG, heat, errors that cost the game',
        status: 'must',
        note: 'Depends on engine ratings/xG (see engine section)',
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
        status: 'needs-work',
        note: 'Watch hub is a journey shell; league page lists fixtures but there’s no one-click “watch this now” into a live board',
      },
      {
        label: '2D pitch board: scorebug, named players moving, ball',
        status: 'must',
        note: 'The focus build. Depends on engine spatial events. 2D first — 3D is parked as physics. Visual target (ratified): the Evans/DEvansData tactics board — Three.js, not EA FC, not FM dots: a phase player (22 tokens on a 3D pitch), named players, pass height + body facing, Broadcast/Top/Goal/Side/Follow-ball cameras, play/loop/speed. Tokens with kits look more “football” than bad rigs. Lightweight ref: fobal-simulator (AI-vs-AI 2.5D in one HTML file).',
      },
      {
        label: 'Pre-match tactics board (“how this manager wants to play”)',
        status: 'must',
        note: 'Tactics App (DEvansData) as reference UI for this middle layer — coach tool, not stadium sim (no physics, no 90′ play, no bot API). Driven by the agent’s plan (decide_matchday already outputs formation + XI): 4-3-3, press triggers, set-piece shape, half-space boxes. Animated clips of the plan = better spectator content than a raw text feed, cheaper than 22 LLM players. Free path: canvas/SVG pitch in the spectator page (same language as the chess board).',
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
        note: 'Today the only match view is the 3D theater, which shows rating chips on players, hover “X rated”, and full FM editing. Theater stays as a dev sandbox only. Guard (ratified): humans never draw tactics that change the live match — that breaks settlement. Numbers hidden on the broadcast unless a graphic is opened.',
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
        note: 'Ops flag: Python API on :8000 was listening but unresponsive to season/clubs probes (state is file-based; engine fine). Needs restart check before pages show live data.',
      },
      {
        label: 'On-chain agent identity + escrow contracts',
        status: 'needs-work',
        note: 'Building blocks exist (Cardano mint scripts, Solidity escrow incl. SpectatorPool) but are not connected to any AFM match/odds/UI',
      },
      {
        label: 'Live league breadth',
        status: 'needs-work',
        note: 'Only 2 agent clubs in the live season (Season 4) — a league isn’t a league yet. More clubs/agent minds needed.',
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
      'Feed events carry x/y/z + facing and every match result ships a deterministic phases stream (done v1.2); shots carry xG; MatchResult gains per-player ratings derived from the feed; a stored action log exists; the /move-style manager protocol accepts a JSON lineup/tactics reply; determinism tests still green; G4 tiredness carries into next lock',
  },
  {
    id: 'P2',
    name: 'Human 2D broadcast V1',
    scope:
      'Watch flow end-to-end: what’s-on-today → pre-match tactics board (agent plan: formation, press triggers, set-pieces) → match on the Evans-style board (phase player, Broadcast cam + scorebug + minute, named players, goal replay loop) + lineup graphic + “manager said”; analyst skin (Top/Side/Follow, phase list, pass arrows) optional; strip every attribute number & edit control off human surfaces',
    done:
      'A spectator with no context can open /football/watch, watch a match unfold, and say who won and why — and a stranger watching the board can say “that was a counter, not a corner grind” (mute-the-labels test passes on the broadcast)',
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