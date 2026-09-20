/**
 * Ground-truth types for the Python engine's serialized `MatchResult`
 * (`match_engine.to_dict()`). These describe what Python actually emits —
 * including fields the contracts don't carry (xG, player_stats, fatigue) —
 * so the adapter reads the producer honestly instead of pretending the
 * boundary is already clean.
 */

/** One entry of the Python feed (`emit()` shape, after spatialize_feed). */
export interface PyFeedEvent {
  minute: number;
  type: string;
  text: string;
  side?: "home" | "away";
  player_id?: string;
  /** Spatial overlay extras. */
  x?: number;
  y?: number;
  z?: number;
  facing?: number;
  actor_id?: string;
  /** Type-specific extras (score, xG, kind, off/on, made, added, formation…). */
  [key: string]: unknown;
}

/**
 * One phase of the Python phase stream (phases.py). The stream carries no
 * actor id — the actor is identified geometrically (placed exactly on the
 * ball), which the adapter reproduces.
 */
export interface PyPhase {
  t: number;
  minute: number;
  type?: string;
  event?: number;
  ball: { x: number; y: number; z: number };
  players: { id: string; side: "home" | "away"; x: number; y: number; facing: number }[];
  action?: "pass" | "carry" | "shot" | "cross";
  note?: string;
}

/**
 * The Python MatchResult as `to_dict()` serializes it. Lineups and squad
 * names live outside the result (the replay envelope carries them), so the
 * adapter resolves names from an optional roster map.
 */
export interface PyMatchResult {
  match_id: string;
  home_agent_id: string;
  away_agent_id: string;
  /** "2 – 1" (spaces around the dash) — adapter normalizes. */
  score: string;
  home_goals: number;
  away_goals: number;
  home_points: number;
  away_points: number;
  reason: string;
  home_pen_goals: number | null;
  away_pen_goals: number | null;
  stats: Record<string, number>;
  feed: PyFeedEvent[];
  phases: PyPhase[];
  outcome: "home_win" | "away_win" | "draw";
  engine: string;
  player_stats: Record<string, Record<string, unknown>>;
  fatigue: { home: Record<string, number>; away: Record<string, number> };
}

/** Optional context — what `season.get_replay()` wraps around the result. */
export interface PyReplaySide {
  agent_id: string;
  club_name: string;
  formation: string;
  tags: string[];
  xi: { player_id: string; name: string; slot: string; primary_pos: string; base_rating: number }[];
}

export interface PyReplay {
  match_id: string;
  matchday: number;
  result: PyMatchResult;
  home: PyReplaySide;
  away: PyReplaySide;
  decisions: Record<string, unknown>;
  press_conference?: unknown[];
  transcript?: unknown[];
}
