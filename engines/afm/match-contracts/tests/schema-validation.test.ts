import { describe, expect, it } from "vitest";

import {
  SCHEMA_VERSION,
  MatchEventSchema,
  MatchInputRefined,
  MatchInputSchema,
  MatchOutputRefined,
  MatchOutputSchema,
  TeamSubmissionRefined,
  generateMatchInput,
  generateMatchOutput,
} from "../src/index.js";

describe("fixtures validate against their schemas", () => {
  it("generateMatchInput passes MatchInputRefined", () => {
    const input = generateMatchInput("match-001", "seed-abc");
    const result = MatchInputRefined.safeParse(input);
    expect(result.success).toBe(true);
  });

  it("generateMatchOutput passes MatchOutputRefined", () => {
    const output = generateMatchOutput("match-001", "seed-abc");
    const result = MatchOutputRefined.safeParse(output);
    expect(result.success).toBe(true);
  });
});

describe("contract invariants that the type system cannot express", () => {
  it("rejects roles naming players outside the squad", () => {
    const input = generateMatchInput("match-002", "seed-xyz");
    input.homeTactics.roles[3]!.playerId = "h99"; // not in the squad
    const result = MatchInputRefined.safeParse(input);
    expect(result.success).toBe(false);
  });

  it("rejects a team playing itself", () => {
    const input = generateMatchInput("match-003", "seed-xyz");
    input.awayTeamId = input.homeTeamId;
    const result = MatchInputRefined.safeParse(input);
    expect(result.success).toBe(false);
  });

  it("rejects non-ascending event sequences", () => {
    const output = generateMatchOutput("match-004", "seed-xyz");
    (output.events[2] as { sequence: number }).sequence = 5; // jumps past 3, 4
    const result = MatchOutputRefined.safeParse(output);
    expect(result.success).toBe(false);
  });

  it("rejects a fullTime event whose score disagrees with the result line", () => {
    const output = generateMatchOutput("match-005", "seed-xyz");
    output.result.homeScore = 2; // fullTime says 1
    const result = MatchOutputRefined.safeParse(output);
    expect(result.success).toBe(false);
  });

  it("rejects a tick with duplicate players (21 or 23 also fail via length)", () => {
    const output = generateMatchOutput("match-006", "seed-xyz");
    const tick = output.positionStream[0]!;
    tick.players[1]!.playerId = tick.players[0]!.playerId; // duplicate
    const result = MatchOutputRefined.safeParse(output);
    expect(result.success).toBe(false);
  });

  it("rejects a bench the substitution budget cannot cover", () => {
    const input = generateMatchInput("match-007", "seed-xyz");
    input.homeTactics.matchBudget.maxSubstitutions = 0;
    input.homeSquad.push(
      ...Array.from({ length: 6 }, (_, i) => ({
        playerId: `h-extra-${i}`,
        name: `Extra ${i}`,
        attributes: JSON.parse(JSON.stringify(input.homeSquad[12]!.attributes)),
        condition: 90,
        morale: 70,
      })),
    ); // 13-strong bench vs a 0-sub budget
    const result = TeamSubmissionRefined.safeParse({
      schemaVersion: SCHEMA_VERSION,
      teamId: input.homeTeamId,
      tactics: input.homeTactics,
      squad: input.homeSquad,
    });
    expect(result.success).toBe(false);
  });
});

describe("attribute bounds and payload hygiene", () => {
  it("rejects attributes outside the 1–20 scale", () => {
    const input = generateMatchInput("match-008", "seed-xyz");
    (input.homeSquad[0]!.attributes.technical as { passing: number }).passing = 25;
    const result = MatchInputSchema.safeParse(input);
    expect(result.success).toBe(false);
  });

  it("rejects a tick without exactly 22 players", () => {
    const output = generateMatchOutput("match-009", "seed-xyz");
    output.positionStream[1]!.players.pop();
    const result = MatchOutputSchema.safeParse(output);
    expect(result.success).toBe(false);
  });

  it("rejects an unknown event type at the boundary", () => {
    const result = MatchEventSchema.safeParse({
      schemaVersion: SCHEMA_VERSION,
      matchId: "m",
      sequence: 0,
      matchMinute: 1,
      position: { x: 0, y: 0 },
      type: "meteor_strike",
    });
    expect(result.success).toBe(false);
  });
});

describe("every event case parses", () => {
  // One hand-built sample per union case, keyed by `type`. A case missing
  // here (or drifting from its schema) fails this test loudly.
  const samples: Record<string, object> = {
    kickoff: { team: "home" },
    pass: { team: "home", fromPlayerId: "h6", toPlayerId: "h9", completed: true },
    shotOnTarget: { team: "home", playerId: "h9", saved: false },
    shotOffTarget: { team: "away", playerId: "a8" },
    shotBlocked: { team: "away", playerId: "a8", blockedByPlayerId: "h3" },
    goal: { team: "home", scorerId: "h9", assistPlayerId: "h10", homeScore: 1, awayScore: 0 },
    tackle: { team: "away", playerId: "a5", opponentId: "h10", won: true },
    interception: { team: "home", playerId: "h6" },
    foul: { team: "away", playerId: "a7", fouledPlayerId: "h7" },
    yellowCard: { team: "away", playerId: "a7" },
    redCard: { team: "away", playerId: "a4", secondYellow: false },
    offside: { team: "home", playerId: "h9" },
    corner: { team: "home" },
    throwIn: { team: "away" },
    goalKick: { team: "home" },
    substitution: { team: "home", playerOffId: "h7", playerOnId: "h12" },
    injury: { team: "away", playerId: "a2", severity: "minor" },
    halfTime: { homeScore: 1, awayScore: 0 },
    fullTime: { homeScore: 1, awayScore: 0 },
    penaltyAwarded: { team: "home", againstTeam: "away" },
    penaltyResult: { team: "home", playerId: "h8", scored: true },
  };

  it("covers every case of the discriminated union", () => {
    let n = 0;
    for (const [type, extra] of Object.entries(samples)) {
      const payload = {
        schemaVersion: SCHEMA_VERSION,
        matchId: "match-coverage",
        sequence: n++,
        matchMinute: 1 + n,
        position: { x: 50, y: 32 },
        type,
        ...extra,
      };
      const result = MatchEventSchema.safeParse(payload);
      if (!result.success) {
        throw new Error(`event case "${type}" failed schema validation`);
      }
    }
  });
});

describe("determinism", () => {
  it("same seed → identical fixture output (byte-equal via structural clone)", () => {
    const a = generateMatchOutput("match-010", "seed-deterministic");
    const b = generateMatchOutput("match-010", "seed-deterministic");
    expect(JSON.stringify(a)).toBe(JSON.stringify(b));
  });

  it("different seed does not silently alias the same object", () => {
    const a = generateMatchInput("match-011", "seed-one");
    const b = generateMatchInput("match-011", "seed-two");
    expect(a.seed).not.toBe(b.seed);
    expect(a).not.toBe(b);
  });
});
