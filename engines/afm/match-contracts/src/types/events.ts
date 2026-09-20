import type { MatchId, PlayerId, Side, Vector2 } from "./common.js";
import { SCHEMA_VERSION } from "./common.js";

/**
 * Every event the engine emits, as a discriminated union over `type`.
 *
 * A generic payload bag would push every consumer (renderer, commentary
 * generator, agent post-match review) into runtime-only guessing about what
 * fields exist for a given event type. Here `switch (event.type)` gives full
 * type-checking on the fields that come with each case, in every consumer,
 * for free.
 *
 * `sequence` is strictly ascending within a match — the engine's write order
 * and the log's replay order. `position` is the event's pitch location.
 * Mirrors `../schemas/events.schema.ts` 1:1 — keep the two files in sync
 * (the compile-time tripwire in `match.schema.ts` + tests catch drift).
 */
export type MatchEvent =
  | KickoffEvent
  | PassEvent
  | CarryEvent
  | ShotOnTargetEvent
  | ShotOffTargetEvent
  | ShotBlockedEvent
  | GoalEvent
  | TackleEvent
  | InterceptionEvent
  | FoulEvent
  | YellowCardEvent
  | RedCardEvent
  | OffsideEvent
  | CornerEvent
  | ThrowInEvent
  | GoalKickEvent
  | SubstitutionEvent
  | InjuryEvent
  | HalfTimeEvent
  | FullTimeEvent
  | PenaltyAwardedEvent
  | PenaltyResultEvent;

interface EventBase {
  schemaVersion: typeof SCHEMA_VERSION;
  matchId: MatchId;
  /** Strictly ascending, 0-based, unique within the match. */
  sequence: number;
  /** Match clock in minutes; may carry a fraction (e.g. 9.8). */
  matchMinute: number;
  /** Where on the pitch the event happened. */
  position: Vector2;
}

export interface KickoffEvent extends EventBase {
  type: "kickoff";
  team: Side;
}

export interface PassEvent extends EventBase {
  type: "pass";
  team: Side;
  fromPlayerId: PlayerId;
  toPlayerId: PlayerId;
  completed: boolean;
}

/**
 * Ball progression by one player without a discrete recipient — a dribble,
 * a carry out of defence, possession kept ticking. Producers whose pass
 * events don't name a recipient (the Python engine's possession beats)
 * emit carries rather than fabricate a `toPlayerId`.
 */
export interface CarryEvent extends EventBase {
  type: "carry";
  team: Side;
  playerId: PlayerId;
}

export interface ShotOnTargetEvent extends EventBase {
  type: "shotOnTarget";
  team: Side;
  playerId: PlayerId;
  /** True if the keeper kept it out (a goal is its own event, not a shot). */
  saved: boolean;
}

export interface ShotOffTargetEvent extends EventBase {
  type: "shotOffTarget";
  team: Side;
  playerId: PlayerId;
}

export interface ShotBlockedEvent extends EventBase {
  type: "shotBlocked";
  team: Side;
  playerId: PlayerId;
  blockedByPlayerId: PlayerId;
}

export interface GoalEvent extends EventBase {
  type: "goal";
  team: Side;
  scorerId: PlayerId;
  assistPlayerId?: PlayerId;
  /** Score *after* this goal. */
  homeScore: number;
  awayScore: number;
}

export interface TackleEvent extends EventBase {
  type: "tackle";
  team: Side;
  playerId: PlayerId;
  opponentId: PlayerId;
  won: boolean;
}

export interface InterceptionEvent extends EventBase {
  type: "interception";
  team: Side;
  playerId: PlayerId;
}

export interface FoulEvent extends EventBase {
  type: "foul";
  /** The side that committed the foul. */
  team: Side;
  playerId: PlayerId;
  fouledPlayerId: PlayerId;
}

export interface YellowCardEvent extends EventBase {
  type: "yellowCard";
  team: Side;
  playerId: PlayerId;
}

export interface RedCardEvent extends EventBase {
  type: "redCard";
  team: Side;
  playerId: PlayerId;
  /** True when this red came from a second yellow. */
  secondYellow: boolean;
}

export interface OffsideEvent extends EventBase {
  type: "offside";
  team: Side;
  playerId: PlayerId;
}

export interface CornerEvent extends EventBase {
  type: "corner";
  /** The attacking side. */
  team: Side;
}

export interface ThrowInEvent extends EventBase {
  type: "throwIn";
  team: Side;
}

export interface GoalKickEvent extends EventBase {
  type: "goalKick";
  team: Side;
}

export interface SubstitutionEvent extends EventBase {
  type: "substitution";
  team: Side;
  /** Leaving the pitch. */
  playerOffId: PlayerId;
  /** Coming on. */
  playerOnId: PlayerId;
}

export interface InjuryEvent extends EventBase {
  type: "injury";
  team: Side;
  playerId: PlayerId;
  severity: "minor" | "major";
}

export interface HalfTimeEvent extends EventBase {
  type: "halfTime";
  homeScore: number;
  awayScore: number;
}

export interface FullTimeEvent extends EventBase {
  type: "fullTime";
  homeScore: number;
  awayScore: number;
}

export interface PenaltyAwardedEvent extends EventBase {
  type: "penaltyAwarded";
  /** The side taking the penalty. */
  team: Side;
  /** The side that conceded it. */
  againstTeam: Side;
}

export interface PenaltyResultEvent extends EventBase {
  type: "penaltyResult";
  team: Side;
  playerId: PlayerId;
  scored: boolean;
}
