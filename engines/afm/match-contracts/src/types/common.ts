/**
 * Shared primitives for the AFM match contracts.
 *
 * Every payload crossing a service boundary (agent → engine, engine →
 * broadcast) embeds `SCHEMA_VERSION` so consumers can reject shapes they
 * were never built to read. See `../../README.md` → Versioning.
 */

/** Bump on any breaking contract change. Single source of truth. */
export const SCHEMA_VERSION = 1;

/**
 * Pitch coordinates in metres, bounded 0–100 per axis (mirrors Vector2Schema).
 * Origin: the home goal corner — x runs goal-to-goal (0 = home goal line),
 * y runs touchline-to-touchline. The home side attacks +x.
 */
export interface Vector2 {
  x: number;
  y: number;
}

/** A unique match identifier, e.g. `afm_season_4_md3_trafford-fc_ashbury-town`. */
export type MatchId = string;

/** Deterministic RNG seed — same seed + same input → byte-identical output. */
export type Seed = string;

/** Stable per-player identifier within a match (e.g. `h6`, `a11`). */
export type PlayerId = string;

/** Which end of the ball a team defends. */
export type Side = "home" | "away";
