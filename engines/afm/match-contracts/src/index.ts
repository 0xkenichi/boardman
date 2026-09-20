/**
 * @afm/match-contracts — types + runtime validation for the AFM match
 * engine's input and output. Nothing else: no simulation, no rendering,
 * no networking. Every other service depends on this package; this
 * package depends on nothing project-specific.
 */
export * from "./types/common.js";
export * from "./types/players.js";
export * from "./types/tactics.js";
export * from "./types/events.js";
export * from "./types/positions.js";
export * from "./types/match.js";

export * from "./schemas/common.schema.js";
export * from "./schemas/players.schema.js";
export * from "./schemas/tactics.schema.js";
export * from "./schemas/events.schema.js";
export * from "./schemas/positions.schema.js";
export * from "./schemas/match.schema.js";

export * from "./fixtures/generate.js";
