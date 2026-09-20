import type { PlayerId } from "./common.js";

/**
 * Player attributes on a 1–20 scale (FM convention).
 *
 * `hidden` attributes are never shown to managers or spectators; they shape
 * *reliability/variance* (consistency, temperament, proneness), not skill,
 * and an agent learns them only through repeated observation.
 */
export interface PlayerAttributes {
  technical: {
    passing: number;
    longPassing: number;
    crossing: number;
    finishing: number;
    shotPower: number;
    technique: number;
    dribbling: number;
    firstTouch: number;
  };
  mental: {
    positioning: number;
    vision: number;
    composure: number;
    workRate: number;
    decisions: number;
    anticipation: number;
    concentration: number;
  };
  physical: {
    pace: number;
    acceleration: number;
    stamina: number;
    strength: number;
    agility: number;
    jumping: number;
  };
  defensive: {
    tackling: number;
    marking: number;
    heading: number;
    aggression: number;
  };
  goalkeeping: {
    reflexes: number;
    handling: number;
    oneOnOnes: number;
    aerialReach: number;
  };
  hidden: {
    consistency: number;
    bigMatchTemperament: number;
    professionalism: number;
    /** High = injury prone. Deterministic per player identity. */
    injuryProneness: number;
    determination: number;
  };
}

/** A squad member as the engine receives it — 18 per side (11 + 7). */
export interface SquadPlayer {
  playerId: PlayerId;
  name: string;
  attributes: PlayerAttributes;
  /** Match fitness, 0–100. */
  condition: number;
  /** Morale, 0–100. */
  morale: number;
}
