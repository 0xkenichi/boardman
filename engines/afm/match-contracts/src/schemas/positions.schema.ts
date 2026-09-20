import { z } from "zod";
import { SCHEMA_VERSION } from "../types/common.js";
import { Vector2Schema } from "./tactics.schema.js";

export const PlayerPositionSchema = z.object({
  playerId: z.string().min(1),
  position: Vector2Schema,
});

export const PositionTickSchema = z.object({
  schemaVersion: z.literal(SCHEMA_VERSION),
  matchId: z.string().min(1),
  tick: z.number().int().min(0),
  matchMinute: z.number().min(0),
  ballPosition: Vector2Schema,
  ballCarrierId: z.string().min(1).optional(),
  players: z.array(PlayerPositionSchema).length(22),
});
