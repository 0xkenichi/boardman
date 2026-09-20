import type { MatchId, Seed, PlayerId } from "./common.js";
import { SCHEMA_VERSION } from "./common.js";
import type { PlayerAttributes, SquadPlayer } from "./players.js";
import type { TacticsInput } from "./tactics.js";
import type { MatchEvent } from "./events.js";
import type { PositionTick } from "./positions.js";

/** Competition context that changes engine behaviour (not identity, not money). */
export interface CompetitionRules {
  /** Cup ties set this; league matches that draw stay a draw. */
  allowExtraTime: boolean;
  allowPenaltyShootout: boolean;
}

/** A team's submission to the engine: squad + tactics, already validated. */
export interface TeamSubmission {
  schemaVersion: typeof SCHEMA_VERSION;
  teamId: string;
  tactics: TacticsInput;
  /** 16–20: the 11 role-assigned starters plus a bench. */
  squad: SquadPlayer[];
}

/**
 * Everything the engine needs to simulate one match. Deterministic:
 * `simulate(simulateInput)` with the same `matchId` + `seed` + payloads
 * produces byte-identical output.
 */
export interface MatchInput {
  schemaVersion: typeof SCHEMA_VERSION;
  matchId: MatchId;
  seed: Seed;
  homeTeamId: string;
  awayTeamId: string;
  homeTactics: TacticsInput;
  awayTactics: TacticsInput;
  homeSquad: SquadPlayer[];
  awaySquad: SquadPlayer[];
  competition: CompetitionRules;
}

/** The full-time result line. */
export interface MatchResultLine {
  homeScore: number;
  awayScore: number;
  wentToExtraTime: boolean;
  wentToPenalties: boolean;
}

/**
 * The engine's complete output: the event log and the position stream are
 * the durable record — replays, stats, commentary, and agent post-match
 * review all read the same two streams. No other output exists.
 */
export interface MatchOutput {
  schemaVersion: typeof SCHEMA_VERSION;
  matchId: MatchId;
  /**
   * The RNG seed, when the producer chooses to publish it. A pure replay
   * adapter (consuming already-simulated results) may omit it — presence
   * is what enables independent re-simulation.
   */
  seed?: Seed;
  /** The full ordered event log. */
  events: MatchEvent[];
  /** The full per-tick position stream. */
  positionStream: PositionTick[];
  result: MatchResultLine;
}

/** Re-exported so consumers can import the whole contract from one module. */
export type { PlayerAttributes };
export type { PlayerId };
