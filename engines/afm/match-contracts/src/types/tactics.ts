import type { PlayerId } from "./common.js";
import { SCHEMA_VERSION } from "./common.js";

/** Formation shapes the engine accepts — closed enum, mirrors FormationShapeSchema. */
export type FormationName =
  | "4-4-2"
  | "4-3-3"
  | "4-2-3-1"
  | "3-5-2"
  | "5-3-2"
  | "4-5-1"
  | "3-4-3";

/**
 * A role the player is asked to perform in the shape. The formation places
 * players; the role+duty is the *behavior profile* layered on top
 * (positioning/decision reweights per role) — per the roadmap's FM-depth plan.
 * Mirrors PlayerRoleSchema.
 */
export type PlayerRole =
  | "GK"
  | "CB"
  | "FB" // full-back
  | "WB" // wing-back
  | "DM"
  | "CM"
  | "AM"
  | "WM" // wide midfielder
  | "W" // wide forward
  | "IF" // inside forward
  | "ST"
  | "AF" // advanced forward
  | "DLF" // deep-lying forward
  | "TQ" // trequartista
  | "PM";

export type PlayerDuty = "defend" | "support" | "attack";

/** Tunables for one phase of play — each independent, superseding the single mentality dial. */
export interface PhaseInstructions {
  /** 0–100: 0 = narrow, 100 = maximal width. */
  width: number;
  /** 0–100: 0 = slow build-up, 100 = direct/fast. */
  tempo: number;
  /** 0–100: 0 = drop off, 100 = all-out press. */
  pressingIntensity: number;
  /** 0–100: 0 = deep block, 100 = high line. */
  defensiveLineHeight: number;
}

export interface RoleAssignment {
  playerId: PlayerId;
  role: PlayerRole;
  duty: PlayerDuty;
  /** Per-player overrides on top of the team's phase instructions. */
  individualInstructions?: Partial<PhaseInstructions>;
}

export interface SetPieceAssignments {
  /** Ordered preference — first available taker takes it. */
  cornerTakers: PlayerId[];
  freeKickTakers: PlayerId[];
  penaltyTaker: PlayerId;
}

/** What the manager is allowed to do from the bench during the match. */
export interface MatchBudget {
  maxSubstitutions: number;
  maxTacticalChanges: number;
}

export type Mentality =
  | "very-defensive"
  | "defensive"
  | "balanced"
  | "attacking"
  | "very-attacking";

/**
 * One side's tactical plan. The manager agent produces this through the
 * playbook API; the engine never sees a hidden slider — everything here is
 * also what the broadcast's pre-match tactics board renders.
 * Mirrors TacticsInputSchema.
 */
export interface TacticsInput {
  schemaVersion: typeof SCHEMA_VERSION;
  teamId: string;
  formation: FormationName;
  mentality: Mentality;
  /** Exactly 11 assignments — one per XI slot. */
  roles: RoleAssignment[];
  inPossession: PhaseInstructions;
  inTransition: PhaseInstructions;
  outOfPossession: PhaseInstructions;
  setPieces: SetPieceAssignments;
  matchBudget: MatchBudget;
}
