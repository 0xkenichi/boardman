# Technical Architecture & Team Requirements

**Companion to:** Agentic Football Manager PRD, Phase 0 Scope Document
**Purpose:** The actual engineering path for building this as a game, not a website — what to build it with, and who you need to build it.

---

## 1. Why the HTML/CSS mockups stop here

The prototypes so far (DOM elements with CSS transitions) are wireframing tools — good for settling layout, information hierarchy, and interaction flow fast, in front of you, without engineering investment. They were never a candidate rendering technology for the shipped product, and shouldn't be judged as one. Below is what the shipped product should actually run on.

## 2. Client / Broadcast Rendering Stack

Plain DOM manipulation cannot hold up under many simultaneously animating sprites, camera work, and particle effects (crowd, weather, confetti) at broadcast quality. This is a rendering-engine problem, ranked by fit:

- **PixiJS** — WebGL-accelerated 2D renderer, the standard choice for exactly this shape of product (many moving sprites, camera pan/zoom, particle systems). Pairs with `pixi-viewport` for camera control and `pixi-particles` for crowd/weather/celebration effects. This is the recommended default.
- **Phaser 3** — built on Pixi, adds scene management, tweening, input, and audio out of the box. Worth it if the team wants game-engine ergonomics (scenes, prefabs, asset pipelines) rather than assembling those primitives by hand.
- **Three.js / Babylon.js** — the natural next step if/when the product moves toward an isometric or full 3D broadcast camera (this is the "later phase" 3D/VR path already flagged in the PRD, not a launch requirement).
- **Unity / Unreal** — the honest ceiling for FIFA/eFootball-grade 3D fidelity. That's a multi-year, heavily-resourced engineering program (this is literally what EA and Konami fund full studios to do) and implies a native or cloud-streamed client, not a browser tab. Name it as the aspirational long-term target, not a near-term plan — the achievable bar in the medium term is a **very well-produced 2D broadcast** (excellent camera work, motion, and sound design on top of Pixi/Phaser), which is a real, respected aesthetic in its own right, not a compromise.

## 3. Match Engine & Simulation Backend

- Keep the deterministic, event-sourced, seeded-RNG design from the Phase 0 scope doc — that doesn't change.
- **Language/runtime**: build the simulation service in TypeScript/Node to start — it's fast to iterate in and your team is already fluent in it. Structure the hot simulation loop as an isolated, swappable module from day one so it can be extracted into Rust (compiled to a native service, or to WebAssembly if you ever want the identical simulation running client-side for replay smoothing) once real load-testing shows Node isn't enough. Don't pre-optimize into Rust before you have a performance problem to justify it.
- The simulation service's only output is the event log + position stream (see the Phase 0 doc and the position-stream note from the match-broadcast discussion) — it should have zero knowledge of rendering, wallets, or leagues.

## 4. Real-Time Delivery to Spectators

- The engine emits a tick/event stream; deliver it to connected viewers over **WebSockets** (bidirectional, low-latency, well-supported) rather than polling.
- Persist the full event + position log for every match as the durable record — this is what makes late joiners, replays, and agent post-match review all trivially consistent with what was actually broadcast, since they're all reading the same log.
- A viewer joining mid-match should be able to fetch the log-so-far and catch up, then subscribe to the live stream — standard event-sourcing/replay pattern, not a special case to design separately.

## 5. Two different "AI" layers — don't conflate them

This distinction matters enough to call out explicitly, because it drives very different tooling choices:

1. **Agent/manager layer** — the club's "manager, sporting director, financial brain." This is where an LLM-based reasoning agent (or a rules-based one, per the marketplace's "build your own" path) belongs: tactical selection, transfer negotiation, wage decisions, in-match tactical changes. It talks to the platform only through the documented playbook/API.
2. **In-match player movement/behavior layer** — what the 22 dots actually do on the pitch each tick, given the tactics the manager layer chose. This is classical game AI, not an LLM's job: steering behaviors/flocking for spacing and movement, potential fields for positioning relative to the ball and teammates, finite-state machines or behavior trees for per-player decision states (press / hold shape / recover / support). This is well-trodden territory — sports games have solved "make 22 dots move convincingly" for decades without deep learning. A small trained movement-policy model is a reasonable later upgrade, not a launch requirement.

Keeping these separate means the manager-agent API surface never needs to know or care how movement is resolved, and the movement layer never needs to understand transfers or budgets.

## 6. Data Requirements

- Player attribute dataset: structured records (JSON/Parquet, versioned schema matching the Phase 0 input contract) — generated/fictional at launch per the PRD's legal flag on real-player likeness rights.
- Match log storage: append-only event + position logs per match, keyed by match ID — this is your replay, stats, and agent-training data all at once.
- Keep the schema versioned explicitly from day one (a `schemaVersion` field on every record type) — you will change these shapes, and agents/renderers built against v1 shouldn't silently break on v2.
- **These shapes are code now** (2026-09-20): `engines/afm/match-contracts` (`@afm/match-contracts`) ships the TypeScript contracts + Zod schemas for the engine boundary — `MatchInput`/`MatchOutput`, events as a discriminated union (no payload bags), `PositionTick` (per-tick x/y for all 22 players + the ball), `SCHEMA_VERSION` embedded in every payload. Fixtures + tests enforce the invariants schemas can't express (bench vs. substitution budget, strictly-ascending sequences, 22 distinct players per tick) and catch type/schema drift. Deliberately excludes simulation, rendering, networking, and anything about money or leagues.

## 7. Broadcast Pacing Layer (compressed match runtime)

To get a full simulated match down to a 1–5 minute broadcast (your target, tunable), don't hack this into the renderer — build it as an explicit layer between the engine's full event log and playback:

- The engine still simulates and records a complete match at full fidelity (every tick, for competitive integrity, stats, and agent learning).
- A **pacing layer** decides playback speed per segment of the log: fast-forward uneventful build-up and midfield phases; drop to real-time (or a brief slow-motion beat) around shots on target, the few seconds before/after a goal, cards, and injuries; hold on goal celebrations for a fixed dwell time.
- Make the pacing rules data (a config the pacing layer reads), not hardcoded logic, and make total target runtime a parameter — you'll want to tune and A/B test match length.
- Injury time / stoppage time should be computed by the engine (from the actual stoppages that occurred) and simply reflected in both the full log and the compressed broadcast, not calculated separately by the pacing layer.

## 8. World-Clock Service (technical shape — operational rules are in the companion scheduling document)

- A single service is the canonical source of "what time it is" for the whole platform — every fixture, transfer window, and schedule exception is published through it.
- Agents query this service via an API (e.g. `GET /world-clock`) rather than inferring or tracking time themselves — this eliminates drift and ambiguity between what different agents "think" the schedule is.
- Schedule-change events (maintenance, server upgrades) are just another record type this service publishes, with a minimum-notice policy enforced at the API level (see companion doc §2).

## 9. Team Composition / Seniority Requirements

What it actually takes to build this at the standard you're describing:

- **Senior backend/simulation engineer** — owns the deterministic match engine, event sourcing, and the world-clock/scheduling service.
- **Real-time client/rendering engineer** — owns the Pixi/Phaser broadcast client: camera system, sprite animation, particle effects, the pacing-layer integration.
- **Gameplay/AI engineer** — owns the in-match player movement/behavior layer (steering, positioning, FSMs/behavior trees).
- **Agent-platform engineer** — owns the manager-agent SDK/playbook and the API surface agents integrate against.
- **Game UI/UX designer** — specifically someone with sports-management-game or broadcast-graphics experience, not a generic web/SaaS designer. This is its own discipline (you're right that it's what makes or breaks a game like this), and the hiring pool for it looks different from typical product-design hiring.
- **Sound designer** — for the SFX/ambience layer (whistle, crowd, goal reactions) flagged in the match-broadcast prototype.
- **DevOps/infra engineer** — for scaling WebSocket delivery to many concurrent viewers per live match, and for the maintenance-window/deployment process the scheduling policy depends on.

## 10. Suggested Build Order

1. Match engine (Phase 0, as scoped) — headless, deterministic, event + position output.
2. World-clock/scheduling service — needed before any real fixtures can exist.
3. Movement/behavior layer — makes the position stream meaningful.
4. Pixi/Phaser broadcast client, fed by a recorded match log (no live agents yet) — proves the presentation layer against real engine output.
5. Pacing layer — compress a full match log into a watchable broadcast length.
6. WebSocket live delivery — move from "replaying a recorded log" to "watching it happen."
7. Agent-platform API + sandbox league (PRD Phase 1) — now agents can actually produce the matches being broadcast.
