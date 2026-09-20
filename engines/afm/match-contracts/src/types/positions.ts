import type { MatchId, PlayerId, Vector2 } from "./common.js";
import { SCHEMA_VERSION } from "./common.js";

/**
 * One tick of the position stream — the broadcast client's lifeblood.
 *
 * The event log alone can't drive a renderer: it says *what happened and
 * when*, not *where everyone was*. The position stream is per-tick x/y for
 * all 22 players plus the ball, on the same clock as the events.
 * Mirrors `../schemas/positions.schema.ts`.
 */
export interface PlayerPosition {
  playerId: PlayerId;
  position: Vector2;
}

export interface PositionTick {
  schemaVersion: typeof SCHEMA_VERSION;
  matchId: MatchId;
  /** Strictly ascending tick index within the match. */
  tick: number;
  /** Match clock in minutes at this tick (fractions allowed). */
  matchMinute: number;
  ballPosition: Vector2;
  /** The player in possession, when there is one. */
  ballCarrierId?: PlayerId;
  /** Always 22 — both starting XIs, every tick. */
  players: PlayerPosition[];
}
