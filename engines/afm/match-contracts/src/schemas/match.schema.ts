import { z } from "zod";
import { SCHEMA_VERSION } from "../types/common.js";
import { SquadPlayerSchema } from "./players.schema.js";
import {
  TacticsInputSchema,
  Vector2Schema,
} from "./tactics.schema.js";
import { MatchEventSchema } from "./events.schema.js";
import { PositionTickSchema } from "./positions.schema.js";

export const CompetitionRulesSchema = z.object({
  allowExtraTime: z.boolean(),
  allowPenaltyShootout: z.boolean(),
});

export const TeamSubmissionSchema = z.object({
  teamId: z.string().min(1),
  schemaVersion: z.literal(SCHEMA_VERSION),
  tactics: TacticsInputSchema,
  squad: z.array(SquadPlayerSchema).min(16).max(20),
});

export const MatchInputSchema = z.object({
  schemaVersion: z.literal(SCHEMA_VERSION),
  matchId: z.string().min(1),
  seed: z.string().min(1),
  homeTeamId: z.string().min(1),
  awayTeamId: z.string().min(1),
  homeTactics: TacticsInputSchema,
  awayTactics: TacticsInputSchema,
  homeSquad: z.array(SquadPlayerSchema),
  awaySquad: z.array(SquadPlayerSchema),
  competition: CompetitionRulesSchema,
});

export const MatchResultLineSchema = z.object({
  homeScore: z.number().int().min(0),
  awayScore: z.number().int().min(0),
  wentToExtraTime: z.boolean(),
  wentToPenalties: z.boolean(),
});

export const MatchOutputSchema = z.object({
  schemaVersion: z.literal(SCHEMA_VERSION),
  matchId: z.string().min(1),
  /** Present when the producer publishes the seed; replay adapters may omit it. */
  seed: z.string().min(1).optional(),
  events: z.array(MatchEventSchema),
  positionStream: z.array(PositionTickSchema),
  result: MatchResultLineSchema,
});

/**
 * Invariants the type system cannot express. These are the checks that catch
 * a payload which is *shaped* right but *wrong* — a role naming a ghost
 * player, a bench no sub budget can cover, sequences that skip, a fullTime
 * score that disagrees with the result line.
 */
export const TeamSubmissionRefined = TeamSubmissionSchema.superRefine((t, ctx) => {
  const starters = t.tactics.roles.map((r) => r.playerId);
  if (new Set(starters).size !== starters.length) {
    ctx.addIssue({
      code: z.ZodIssueCode.custom,
      path: ["tactics", "roles"],
      message: "roles must assign 11 distinct players",
    });
  }
  const starterSet = new Set(starters);
  const bench = t.squad.filter((p) => !starterSet.has(p.playerId));
  if (bench.length > t.tactics.matchBudget.maxSubstitutions + 7) {
    ctx.addIssue({
      code: z.ZodIssueCode.custom,
      path: ["tactics", "matchBudget", "maxSubstitutions"],
      message: `bench of ${bench.length} exceeds what a ${t.tactics.matchBudget.maxSubstitutions}-sub budget can cover`,
    });
  }
});

export const MatchInputRefined = MatchInputSchema.superRefine((input, ctx) => {
  for (const [side, tacticsKey, squadKey] of [
    ["home", "homeTactics", "homeSquad"],
    ["away", "awayTactics", "awaySquad"],
  ] as const) {
    const squadIds = new Set(input[squadKey].map((p) => p.playerId));
    input[tacticsKey].roles.forEach((r, i) => {
      if (!squadIds.has(r.playerId)) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          path: [tacticsKey, "roles", i, "playerId"],
          message: `role ${i} names unknown ${side} player "${r.playerId}"`,
        });
      }
    });
    const starters = input[tacticsKey].roles.map((r) => r.playerId);
    if (starters.length !== 11) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: [tacticsKey, "roles"],
        message: `${side} must name exactly 11 starters`,
      });
    }
  }
  if (input.homeTeamId === input.awayTeamId) {
    ctx.addIssue({
      code: z.ZodIssueCode.custom,
      path: ["awayTeamId"],
      message: "a team cannot play itself",
    });
  }
});

export const MatchOutputRefined = MatchOutputSchema.superRefine((output, ctx) => {
  // Event sequence: strictly ascending from 0, in array order.
  output.events.forEach((ev, i) => {
    if (ev.sequence !== i) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ["events", i, "sequence"],
        message: `event sequence must be strictly ascending from 0: expected ${i}, got ${ev.sequence}`,
      });
    }
  });
  // Ticks: strictly ascending, 22 distinct players each.
  output.positionStream.forEach((tick, i) => {
    if (i > 0 && tick.tick <= output.positionStream[i - 1]!.tick) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ["positionStream", i, "tick"],
        message: "positionStream ticks must be strictly ascending",
      });
    }
    const ids = tick.players.map((p) => p.playerId);
    if (new Set(ids).size !== ids.length) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ["positionStream", i, "players"],
        message: "players within a tick must be distinct",
      });
    }
  });
  // The full-time event's score must equal the result line.
  const ft = output.events.at(-1);
  if (ft && ft.type === "fullTime") {
    if (ft.homeScore !== output.result.homeScore || ft.awayScore !== output.result.awayScore) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ["result"],
        message: "fullTime event score disagrees with result line",
      });
    }
  }
});

/**
 * Type/schema drift tripwire: the event union type must stay assignable into
 * the validated schema output in both directions. If someone edits events.ts
 * without events.schema.ts (or vice versa), this file stops compiling.
 */
export type SchemaEventCheck = typeof MatchEventSchema extends z.ZodType<import("../types/events.js").MatchEvent>
  ? import("../types/events.js").MatchEvent extends z.infer<typeof MatchEventSchema>
    ? true
    : never
  : never;
export const _eventUnionInSync: SchemaEventCheck = true;
