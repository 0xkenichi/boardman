import { z } from "zod";
import { SCHEMA_VERSION } from "../types/common.js";
import { Vector2Schema } from "./tactics.schema.js";

const base = {
  schemaVersion: z.literal(SCHEMA_VERSION),
  matchId: z.string().min(1),
  sequence: z.number().int().min(0),
  matchMinute: z.number().min(0),
  position: Vector2Schema,
};
const team = z.enum(["home", "away"]);
const id = z.string().min(1);

/**
 * z.discriminatedUnion mirrors the MatchEvent type in events.ts exactly —
 * keep these two files in sync by construction (see tests/schema-validation.test.ts,
 * which fails loudly if a fixture drifts from either).
 */
export const MatchEventSchema = z.discriminatedUnion("type", [
  z.object({ ...base, type: z.literal("kickoff"), team }),
  z.object({ ...base, type: z.literal("pass"), team, fromPlayerId: id, toPlayerId: id, completed: z.boolean() }),
  z.object({ ...base, type: z.literal("carry"), team, playerId: id }),
  z.object({ ...base, type: z.literal("shotOnTarget"), team, playerId: id, saved: z.boolean() }),
  z.object({ ...base, type: z.literal("shotOffTarget"), team, playerId: id }),
  z.object({ ...base, type: z.literal("shotBlocked"), team, playerId: id, blockedByPlayerId: id }),
  z.object({
    ...base, type: z.literal("goal"), team, scorerId: id,
    assistPlayerId: id.optional(), homeScore: z.number().int().min(0), awayScore: z.number().int().min(0),
  }),
  z.object({ ...base, type: z.literal("tackle"), team, playerId: id, opponentId: id, won: z.boolean() }),
  z.object({ ...base, type: z.literal("interception"), team, playerId: id }),
  z.object({ ...base, type: z.literal("foul"), team, playerId: id, fouledPlayerId: id }),
  z.object({ ...base, type: z.literal("yellowCard"), team, playerId: id }),
  z.object({ ...base, type: z.literal("redCard"), team, playerId: id, secondYellow: z.boolean() }),
  z.object({ ...base, type: z.literal("offside"), team, playerId: id }),
  z.object({ ...base, type: z.literal("corner"), team }),
  z.object({ ...base, type: z.literal("throwIn"), team }),
  z.object({ ...base, type: z.literal("goalKick"), team }),
  z.object({ ...base, type: z.literal("substitution"), team, playerOffId: id, playerOnId: id }),
  z.object({ ...base, type: z.literal("injury"), team, playerId: id, severity: z.enum(["minor", "major"]) }),
  z.object({ ...base, type: z.literal("halfTime"), homeScore: z.number().int().min(0), awayScore: z.number().int().min(0) }),
  z.object({ ...base, type: z.literal("fullTime"), homeScore: z.number().int().min(0), awayScore: z.number().int().min(0) }),
  z.object({ ...base, type: z.literal("penaltyAwarded"), team, againstTeam: team }),
  z.object({ ...base, type: z.literal("penaltyResult"), team, playerId: id, scored: z.boolean() }),
]);
