import { z } from "zod";
import { SCHEMA_VERSION } from "../types/common.js";

/** Pitch coordinates in metres (0–100 per axis, origin: centre spot). */
export const Vector2Schema = z.object({
  x: z.number().min(0).max(100),
  y: z.number().min(0).max(100),
});

export const MentalitySchema = z.enum([
  "very-defensive",
  "defensive",
  "balanced",
  "attacking",
  "very-attacking",
]);

export const FormationShapeSchema = z.enum([
  "4-4-2",
  "4-3-3",
  "4-2-3-1",
  "3-5-2",
  "5-3-2",
  "4-5-1",
  "3-4-3",
]);

export const PlayerRoleSchema = z.enum([
  "GK", "CB", "FB", "WB", "DM", "CM", "AM", "WM", "W", "IF", "ST", "AF", "DLF", "TQ", "PM",
]);

export const RoleDutySchema = z.enum(["defend", "support", "attack"]);

export const PhaseInstructionsSchema = z.object({
  width: z.number().min(0).max(100),
  tempo: z.number().min(0).max(100),
  pressingIntensity: z.number().min(0).max(100),
  defensiveLineHeight: z.number().min(0).max(100),
});

export const RoleAssignmentSchema = z.object({
  playerId: z.string().min(1),
  role: PlayerRoleSchema,
  duty: RoleDutySchema,
  individualInstructions: PhaseInstructionsSchema.partial().optional(),
});

export const SetPieceAssignmentsSchema = z.object({
  cornerTakers: z.array(z.string().min(1)).min(1),
  freeKickTakers: z.array(z.string().min(1)).min(1),
  penaltyTaker: z.string().min(1),
});

export const MatchBudgetSchema = z.object({
  maxSubstitutions: z.number().int().min(0),
  maxTacticalChanges: z.number().int().min(0),
});

export const TacticsInputSchema = z.object({
  schemaVersion: z.literal(SCHEMA_VERSION),
  teamId: z.string().min(1),
  formation: FormationShapeSchema,
  mentality: MentalitySchema,
  roles: z.array(RoleAssignmentSchema).length(11),
  inPossession: PhaseInstructionsSchema,
  inTransition: PhaseInstructionsSchema,
  outOfPossession: PhaseInstructionsSchema,
  setPieces: SetPieceAssignmentsSchema,
  matchBudget: MatchBudgetSchema,
});
