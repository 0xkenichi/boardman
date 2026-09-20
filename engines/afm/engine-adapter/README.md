# @afm/engine-adapter

Bridges the Python AFM engine's `MatchResult` (feed + phase stream, as serialized by `match_engine.to_dict()` and served by `season.get_replay()`) into schema-valid `@afm/match-contracts` `MatchOutput`.

**Nothing here simulates.** The adapter validates at the boundary and maps; where the Python engine cannot fill a contract field, the event is dropped into `diagnostics.dropped` + `diagnostics.commentary` rather than fabricated.

## Mapping decisions (ground-truthed against `match_engine.py`)

| Python feed event | Contract event | Why |
|---|---|---|
| `possession`, `pass` | `carry` | Python names only the actor (possession progression); contract `pass` requires a `toPlayerId` Python never emits |
| `shot` (`on_target`) | `shotOnTarget` (`saved: true`) | direct |
| `shot` (off target) | `shotOffTarget` | direct |
| `shot` (`blocked`) | `shotOffTarget` + commentary | Python never names the blocker; contract requires `blockedByPlayerId` |
| `goal` | `goal` | running score folded from goal events; `assist` → `assistPlayerId` |
| `yellow` / `red` | `yellowCard` / `redCard` | `secondYellow` derived from the text |
| `substitution` | `substitution` | `off`/`on` extras → `playerOffId`/`playerOnId` |
| `injury` | `injury` (`severity: "major"`) | in-match injuries always force the player off |
| `foul` | **dropped → commentary** | Python never names the fouled player; contract requires `fouledPlayerId` |
| `tackle` | `interception` | Python names only the tackler; contract `tackle` requires an `opponentId` |
| `corner`, `corner_delivery` | `corner` | contract corner carries no taker |
| `free_kick` | commentary + `carry` | no contract free-kick case yet |
| `goal_kick` / `throw_in` | `goalKick` / `throwIn` | direct |
| `halftime` / `full_time` | `halfTime` / `fullTime` | score from the `score` extra; full time guaranteed last |
| `penalty` (shootout) | `penaltyResult` | shootout kicks never move the 90-minute score |
| `added_time`, `tactical_change`, `penalties_start/end`, xG notes | commentary only | real content, no contract case |

## Positions

The Python phase stream measures metres from the home goal corner; the contract domain is 0–100 per axis — the adapter rescales. The phase stream has no actor id, so the ball carrier is derived **geometrically**: `phases.py` places the actor exactly on the ball.

## Honesty notes

- `seed` is **omitted**: the Python engine never serializes it, and publishing a fake one would falsely imply re-simulability. (Contract: `seed?`.)
- Squad players built from a replay envelope (`squadFromReplaySide`) carry placeholder (all-10s) attributes — real attributes live engine-side; the contract requires the shape, not the truth.

## Usage

```ts
import { adaptMatchResult, rosterFromReplay } from "@afm/engine-adapter";
import { MatchOutputRefined } from "@afm/match-contracts";

const { output, diagnostics } = adaptMatchResult(pyResult, {
  roster: rosterFromReplay(pyReplay),
});
// output already passed MatchOutputRefined inside the adapter — it throws
// rather than emitting an invalid payload.
```

```bash
npm run typecheck
npm test   # 17 tests: mapping table, drops, determinism, coordinate bounds
```
