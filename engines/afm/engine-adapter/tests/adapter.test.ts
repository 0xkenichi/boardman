import { describe, expect, it } from "vitest";

import {
  MatchOutputRefined,
  SCHEMA_VERSION,
  type MatchOutput,
} from "@afm/match-contracts";
import {
  adaptMatchResult,
  parseScore,
  rosterFromReplay,
  squadFromReplaySide,
  type PyMatchResult,
  type PyPhase,
  type PyReplay,
} from "../src/index.js";

/**
 * A faithful 22-token phase: 11 home + 11 away, deterministic in-formation
 * anchors — exactly what phases.py emits. `actorId` is snapped onto the
 * ball (the phase stream's geometric actor convention).
 */
function makePhase(
  t: number,
  minute: number,
  type: string,
  ballX: number,
  ballY: number,
  actorId: string | undefined,
  note?: string,
): PyPhase {
  const players = [
    ...Array.from({ length: 11 }, (_, i) => ({
      id: `h${i + 1}`,
      side: "home" as const,
      x: 5 + (i % 6) * 15,
      y: 8 + i * 5.2,
      facing: 90,
    })),
    ...Array.from({ length: 11 }, (_, i) => ({
      id: `a${i + 1}`,
      side: "away" as const,
      x: 100 - (i % 6) * 15,
      y: 60 - i * 5.2,
      facing: 270,
    })),
  ];
  if (actorId) {
    const actor = players.find((p) => p.id === actorId);
    if (actor) {
      actor.x = ballX;
      actor.y = ballY;
    }
  }
  return {
    t,
    minute,
    type,
    event: minute,
    ball: { x: ballX, y: ballY, z: 0 },
    players,
    ...(type === "goal" || type === "shot" ? { action: "shot" as const } : {}),
    ...(note ? { note } : {}),
  };
}

// ---------------------------------------------------------------------------
// fixtures — a faithful slice of what the Python engine actually emits
// ---------------------------------------------------------------------------

function pyResult(overrides: Partial<PyMatchResult> = {}): PyMatchResult {
  return {
    match_id: "afm_season_4_md3_blue_aoashi",
    home_agent_id: "blue",
    away_agent_id: "aoashi",
    score: "2 – 1",
    home_goals: 2,
    away_goals: 1,
    home_points: 3,
    away_points: 0,
    reason: "regulation",
    home_pen_goals: null,
    away_pen_goals: null,
    stats: { possession_home: 55 },
    engine: "afm-engine-v1.4",
    outcome: "home_win",
    player_stats: {},
    fatigue: { home: {}, away: {} },
    feed: [
      { minute: 0, type: "kickoff", text: "Kickoff · blue vs aoashi", side: "home", x: 52.5, y: 34, actor_id: "h9" },
      { minute: 4, type: "possession", text: "4' · Reyes keeps it ticking", side: "home", player_id: "h6", x: 40, y: 30 },
      { minute: 9, type: "pass", text: "9' · Novak works it forward", side: "home", player_id: "h7", x: 55, y: 40 },
      { minute: 12, type: "shot", text: "12' · shot on target — saved (home) · Martinez", side: "home", player_id: "h9", x: 88, y: 30, on_target: true, blocked: false, xG: 0.31 },
      { minute: 20, type: "goal", text: "20' · GOAL (home) · Martinez · 1 – 0", side: "home", player_id: "h9", x: 95, y: 32, score: "1 – 0", xG: 0.44, kind: "open_play", assist: "h10" },
      { minute: 27, type: "foul", text: "27' · foul (away): Doyle stops the break", side: "away", player_id: "a2", x: 60, y: 50 },
      { minute: 27, type: "yellow", text: "27' · yellow card (away) · Doyle", side: "away", player_id: "a2", x: 60, y: 50 },
      { minute: 35, type: "shot", text: "35' · shot blocked (away) · Aguirre", side: "away", player_id: "a9", x: 20, y: 40, on_target: false, blocked: true, xG: 0.12 },
      { minute: 41, type: "tackle", text: "41' · tackle by Osei (home) wins it back", side: "home", player_id: "h5", x: 45, y: 20 },
      { minute: 44, type: "goal", text: "44' · GOAL (away) · Aguirre · 1 – 1", side: "away", player_id: "a9", x: 8, y: 35, score: "1 – 1", xG: 0.29, kind: "open_play" },
      { minute: 45, type: "halftime", text: "45' · Half-time · 1 – 1", score: "1 – 1", x: 50, y: 34 },
      { minute: 58, type: "substitution", text: "58' · substitution (home): Sousa off, Adeyemi on", side: "home", x: 50, y: 34, off: "h11", on: "h12", kind: "tactical", match_type: "level" },
      { minute: 70, type: "injury", text: "70' · injury (away): Ngata needs treatment", side: "away", player_id: "a5", x: 30, y: 60 },
      { minute: 70, type: "substitution", text: "70' · substitution (away): Ngata off, Fischer on", side: "away", x: 50, y: 34, off: "a5", on: "a12", kind: "injury", match_type: "level" },
      { minute: 77, type: "goal", text: "77' · GOAL (home) · Petrov · 2 – 1", side: "home", player_id: "h10", x: 93, y: 28, score: "2 – 1", xG: 0.38, kind: "open_play" },
      { minute: 90, type: "full_time", text: "90' · FT · 2 – 1", score: "2 – 1", x: 50, y: 34 },
    ],
    phases: [
      makePhase(0, 0, "kickoff", 52.5, 34, undefined, "Kickoff · blue vs aoashi"),
      makePhase(20.5, 20, "goal", 100, 34, "h9", "20' · GOAL (home) · Martinez · 1 – 0"),
    ],
    ...overrides,
  };
}

function pyReplay(result: PyMatchResult): PyReplay {
  return {
    match_id: result.match_id,
    matchday: 3,
    result,
    home: {
      agent_id: "blue",
      club_name: "Blue Lock FC",
      formation: "4-3-3",
      tags: ["balanced"],
      xi: Array.from({ length: 11 }, (_, i) => ({
        player_id: `h${i + 1}`,
        name: `Home P${i + 1}`,
        slot: "MID",
        primary_pos: "MID",
        base_rating: 72,
      })),
    },
    away: {
      agent_id: "aoashi",
      club_name: "Ao Ashi FC",
      formation: "4-4-2",
      tags: ["counter"],
      xi: Array.from({ length: 11 }, (_, i) => ({
        player_id: `a${i + 1}`,
        name: `Away P${i + 1}`,
        slot: "MID",
        primary_pos: "MID",
        base_rating: 70,
      })),
    },
    decisions: {},
  };
}

// ---------------------------------------------------------------------------
// tests
// ---------------------------------------------------------------------------

describe("adaptMatchResult", () => {
  it("produces a MatchOutput that passes MatchOutputRefined at the boundary", () => {
    const { output } = adaptMatchResult(pyResult());
    const parsed = MatchOutputRefined.safeParse(output);
    expect(parsed.success).toBe(true);
  });

  it("maps the running score from goal events (2 – 1)", () => {
    const { output } = adaptMatchResult(pyResult());
    expect(output.result.homeScore).toBe(2);
    expect(output.result.awayScore).toBe(1);
    const goal = output.events.find((e) => e.type === "goal");
    expect(goal && goal.type === "goal" ? goal.homeScore : null).toBe(1); // first goal
  });

  it("ends the log at fullTime carrying the final score", () => {
    const { output } = adaptMatchResult(pyResult());
    const last = output.events.at(-1);
    expect(last?.type).toBe("fullTime");
    if (last?.type === "fullTime") {
      expect(last.homeScore).toBe(2);
      expect(last.awayScore).toBe(1);
    }
  });

  it("maps Python pass/possession → carry (Python never names a recipient)", () => {
    const { output } = adaptMatchResult(pyResult());
    const pass = output.events.find((e) => e.type === "carry" && e.matchMinute === 9);
    expect(pass).toBeDefined();
    expect(output.events.some((e) => e.type === "pass")).toBe(false);
  });

  it("maps shots by on_target/blocked extras", () => {
    const { output } = adaptMatchResult(pyResult());
    const saved = output.events.find((e) => e.type === "shotOnTarget");
    expect(saved).toBeDefined();
    // blocked shot → honest subset (off-target), never a fabricated blocker
    expect(output.events.some((e) => e.type === "shotBlocked")).toBe(false);
  });

  it("drops Python fouls to commentary (fouledPlayerId cannot be filled honestly)", () => {
    const { output, diagnostics } = adaptMatchResult(pyResult());
    expect(output.events.some((e) => e.type === "foul")).toBe(false);
    expect(diagnostics.dropped.some((d) => d.type === "foul")).toBe(true);
    expect(diagnostics.commentary.some((c) => c.includes("Doyle stops the break"))).toBe(true);
  });

  it("maps tackle → interception (Python never names the tackled opponent)", () => {
    const { output } = adaptMatchResult(pyResult());
    expect(output.events.some((e) => e.type === "tackle")).toBe(false);
    expect(output.events.some((e) => e.type === "interception" && e.matchMinute === 41)).toBe(true);
  });

  it("carries substitutions and injuries through with ids", () => {
    const { output } = adaptMatchResult(pyResult());
    const sub = output.events.find((e) => e.type === "substitution");
    expect(sub && sub.type === "substitution" ? sub.playerOffId : null).toBe("h11");
    const injury = output.events.find((e) => e.type === "injury");
    expect(injury && injury.type === "injury" ? injury.playerId : null).toBe("a5");
  });

  it("flags red cards from second-yellow text", () => {
    const py = pyResult();
    py.feed.splice(7, 0, {
      minute: 33, type: "red", side: "away", player_id: "a2",
      text: "33' · RED CARD (away) — second yellow · Doyle", x: 60, y: 50,
    });
    const { output } = adaptMatchResult(py);
    const red = output.events.find((e) => e.type === "redCard");
    expect(red && red.type === "redCard" ? red.secondYellow : null).toBe(true);
  });

  it("keeps shootout kicks out of the running score and marks the result line", () => {
    const py = pyResult({
      reason: "penalties after extra time",
      home_pen_goals: 4,
      away_pen_goals: 3,
    });
    py.feed = py.feed.filter((e) => e.type !== "full_time");
    py.feed.push(
      { minute: 121, type: "penalties_start", text: "Penalty shootout — best of five", x: 50, y: 34 },
      { minute: 122, type: "penalty", text: "PEN home · Martinez scores · 1-0", side: "home", player_id: "h9", x: 50, y: 34, made: true },
      { minute: 129, type: "penalties_end", text: "Shootout 4-3 · home win on penalties", side: "home", score: "4 – 3", x: 50, y: 34 },
    );
    const { output } = adaptMatchResult(py);
    expect(output.events.some((e) => e.type === "penaltyResult")).toBe(true);
    // shootout kicks never move the 90-minute score
    expect(output.result.homeScore).toBe(2);
    expect(output.result.wentToPenalties).toBe(true);
    expect(output.result.wentToExtraTime).toBe(true);
    const last = output.events.at(-1);
    expect(last?.type).toBe("fullTime"); // fallback appended
  });

  it("derives the ball carrier geometrically (actor placed exactly on the ball)", () => {
    const { output } = adaptMatchResult(pyResult());
    const goalTick = output.positionStream[1]!;
    expect(goalTick.ballCarrierId).toBe("h9");
  });

  it("rescales engine metres into the contract's 0–100 coordinate domain", () => {
    const { output } = adaptMatchResult(pyResult());
    for (const tick of output.positionStream) {
      expect(tick.ballPosition.x).toBeGreaterThanOrEqual(0);
      expect(tick.ballPosition.x).toBeLessThanOrEqual(100);
      for (const p of tick.players) {
        expect(p.position.x).toBeGreaterThanOrEqual(0);
        expect(p.position.x).toBeLessThanOrEqual(100);
        expect(p.position.y).toBeGreaterThanOrEqual(0);
        expect(p.position.y).toBeLessThanOrEqual(100);
      }
    }
  });

  it("is deterministic — same input, byte-identical output", () => {
    const a = adaptMatchResult(pyResult());
    const b = adaptMatchResult(pyResult());
    expect(JSON.stringify(a.output)).toBe(JSON.stringify(b.output));
    expect(JSON.stringify(a.diagnostics)).toBe(JSON.stringify(b.diagnostics));
  });

  it("records the schema version on every emitted record", () => {
    const { output } = adaptMatchResult(pyResult());
    expect(output.schemaVersion).toBe(SCHEMA_VERSION);
    for (const ev of output.events) expect(ev.schemaVersion).toBe(SCHEMA_VERSION);
    for (const tick of output.positionStream) expect(tick.schemaVersion).toBe(SCHEMA_VERSION);
  });
});

describe("helpers", () => {
  it("parseScore handles both dash styles", () => {
    expect(parseScore("2 – 1")).toEqual([2, 1]);
    expect(parseScore("0-0")).toEqual([0, 0]);
  });

  it("rosterFromReplay collects both XIs", () => {
    const roster = rosterFromReplay(pyReplay(pyResult()));
    expect(roster.get("h1")).toBe("Home P1");
    expect(roster.get("a11")).toBe("Away P11");
  });

  it("squadFromReplaySide emits contract-shaped squad players", () => {
    const squad = squadFromReplaySide(pyReplay(pyResult()).home);
    expect(squad).toHaveLength(11);
    expect(squad[0]!.playerId).toBe("h1");
  });
});
