import { z } from "zod";

const attr = z.number().min(1).max(20);

export const PlayerAttributesSchema = z.object({
  technical: z.object({
    passing: attr, longPassing: attr, crossing: attr, finishing: attr,
    shotPower: attr, technique: attr, dribbling: attr, firstTouch: attr,
  }),
  mental: z.object({
    positioning: attr, vision: attr, composure: attr, workRate: attr,
    decisions: attr, anticipation: attr, concentration: attr,
  }),
  physical: z.object({
    pace: attr, acceleration: attr, stamina: attr, strength: attr, agility: attr, jumping: attr,
  }),
  defensive: z.object({
    tackling: attr, marking: attr, heading: attr, aggression: attr,
  }),
  goalkeeping: z.object({
    reflexes: attr, handling: attr, oneOnOnes: attr, aerialReach: attr,
  }),
  hidden: z.object({
    consistency: attr,
    bigMatchTemperament: attr,
    professionalism: attr,
    injuryProneness: attr,
    determination: attr,
  }),
});

export const SquadPlayerSchema = z.object({
  playerId: z.string().min(1),
  name: z.string().min(1),
  attributes: PlayerAttributesSchema,
  condition: z.number().min(0).max(100),
  morale: z.number().min(0).max(100),
});
