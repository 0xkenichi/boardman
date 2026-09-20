# @afm/match-contracts

Phase 0 contracts for the agentic football manager match engine. This package is deliberately narrow: **types + runtime validation for the match engine's input and output, nothing else.** No simulation logic, no rendering, no networking. Every other service (the engine implementation, the agent runtime, the broadcast client) depends on this package; this package depends on nothing project-specific.

## What's in here

- `src/types/` — the TypeScript contracts:
  - `common.ts` — shared primitives (`Vector2`, IDs, `SCHEMA_VERSION`)
  - `players.ts` — `PlayerAttributes` (1–20 scale, visible + hidden), `SquadPlayer`
  - `tactics.ts` — `TacticsInput`: formation, roles+duties, per-phase instructions, set pieces, match budget
  - `events.ts` — `MatchEvent`, a **discriminated union** over every event type (goal, card, sub, etc.) — not a generic payload bag
  - `positions.ts` — `PositionTick`: per-tick x/y for all 22 players + the ball. This is what a broadcast client like the match-view mockups actually needs; the event log alone can't drive it.
  - `match.ts` — `MatchInput` / `MatchOutput`, the two top-level contracts the engine actually exposes
- `src/schemas/` — Zod schemas mirroring every type above, for validating payloads at runtime (agent submissions, engine output, anything crossing a service boundary). `schemaVersion` is pinned with `z.literal(SCHEMA_VERSION)` everywhere — a payload built against a different contract version fails at the boundary, not downstream.
- `src/fixtures/generate.ts` — a small worked example (`generateMatchInput`, `generateMatchOutput`) — deliberately tiny (6 events, 3 ticks) so it reads as documentation, not a stress test
- `tests/schema-validation.test.ts` — validates the fixtures against the schemas, and asserts the invariants that matter: bench size vs. substitution budget, ascending event sequence, 22 players per tick, determinism (same seed → identical output)

## Why a discriminated union for events, not `detail: Record<string, unknown>`

A generic payload bag pushes every consumer (renderer, commentary generator, agent post-match review) into runtime-only guessing about what fields exist for a given event type. The discriminated union in `events.ts` means `switch (event.type)` gives full type-checking on the fields that come with each case, in every consumer, for free.

## Why Zod on top of TypeScript types

TypeScript types disappear at runtime. Anything crossing a real boundary — an agent's tactics submission, the engine's own output before it hits the broadcast pipeline — needs to be validated against something that still exists at 2am in production. The Zod schemas in `src/schemas/` are hand-kept in sync with the types in `src/types/`; drift is caught two ways: the `SchemaEventCheck` tripwire in `match.schema.ts` refuses to compile if the event union and its schema diverge, and `tests/schema-validation.test.ts` exercises every case of the union plus the invariants the type system can't express at all (bench size vs. substitution budget, strictly-ascending sequence numbers, 22 distinct players per tick, fullTime score == result line).

## Versioning

`SCHEMA_VERSION` in `common.ts` is a single source of truth, embedded in every payload. Bump it on any breaking change. The match engine, agent runtime, and broadcast renderer are three independently-deployed consumers — they will not all upgrade at the same moment, so plan for at least one version to be readable by all three at once during a migration.

## Using this package

```bash
npm install
npm run typecheck   # tsc --noEmit
npm test            # vitest — validates fixtures against schemas
```

```ts
import { MatchInputSchema, generateMatchInput } from "@afm/match-contracts";

const input = generateMatchInput("match-001", "seed-abc");
const result = MatchInputSchema.safeParse(payloadFromAgent);
if (!result.success) {
  // reject at the boundary — the engine should never see a payload
  // that didn't pass this check
}
```

## What's deliberately NOT here

- The actual simulation loop (attribute resolution, movement AI, referee logic) — that's the Phase 0 engine implementation, which *consumes* this package.
- The broadcast pacing layer, WebSocket delivery, world-clock service — separate services per the Technical Architecture doc.
- Anything about money, ownership, or leagues — the engine (and this contracts package) has no knowledge of any of that, by design.
