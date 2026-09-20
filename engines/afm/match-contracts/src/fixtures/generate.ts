import { SCHEMA_VERSION } from "../types/common.js";
import type { PlayerAttributes, SquadPlayer } from "../types/players.js";
import type { TacticsInput, PhaseInstructions } from "../types/tactics.js";
import type { MatchInput, MatchOutput } from "../types/match.js";
import type { MatchEvent } from "../types/events.js";
import type { PositionTick } from "../types/positions.js";

function baseAttributes(overrides: Partial<PlayerAttributes> = {}): PlayerAttributes {
  return {
    technical: { passing: 12, longPassing: 10, crossing: 9, finishing: 11, shotPower: 10, technique: 13, dribbling: 11, firstTouch: 12 },
    mental: { positioning: 12, vision: 11, composure: 12, workRate: 14, decisions: 11, anticipation: 11, concentration: 12 },
    physical: { pace: 12, acceleration: 12, stamina: 13, strength: 11, agility: 12, jumping: 11 },
    defensive: { tackling: 10, marking: 10, heading: 10, aggression: 10 },
    goalkeeping: { reflexes: 6, handling: 6, oneOnOnes: 6, aerialReach: 6 },
    hidden: { consistency: 12, bigMatchTemperament: 11, professionalism: 13, injuryProneness: 8, determination: 13 },
    ...overrides,
  };
}

function buildSquad(teamPrefix: string): SquadPlayer[] {
  const names = [
    "Reyes", "Kilic", "Bauer", "Dunn", "Osei", "Okafor", "Novak", "Ibarra",
    "Martinez", "Petrov", "Sousa", // starting XI (11)
    "Adeyemi", "Fischer", "Tanaka", "Moreau", "Haas", "Costa", "Lindberg", // bench (7)
  ];
  return names.map((name, i) => ({
    playerId: `${teamPrefix}${i + 1}`,
    name,
    attributes: baseAttributes(i === 0 ? { goalkeeping: { reflexes: 15, handling: 14, oneOnOnes: 14, aerialReach: 13 } } : {}),
    condition: 98,
    morale: 75,
  }));
}

const defaultPhase: PhaseInstructions = { width: 55, tempo: 50, pressingIntensity: 50, defensiveLineHeight: 50 };

function buildTactics(teamId: string, playerIds: string[]): TacticsInput {
  const roles: TacticsInput["roles"] = [
    { playerId: playerIds[0]!, role: "GK", duty: "defend" },
    { playerId: playerIds[1]!, role: "FB", duty: "support" },
    { playerId: playerIds[2]!, role: "CB", duty: "defend" },
    { playerId: playerIds[3]!, role: "CB", duty: "defend" },
    { playerId: playerIds[4]!, role: "FB", duty: "support" },
    { playerId: playerIds[5]!, role: "DM", duty: "defend" },
    { playerId: playerIds[6]!, role: "WM", duty: "support" },
    { playerId: playerIds[7]!, role: "WM", duty: "support" },
    { playerId: playerIds[8]!, role: "ST", duty: "attack" },
    { playerId: playerIds[9]!, role: "W", duty: "attack" },
    { playerId: playerIds[10]!, role: "W", duty: "attack" },
  ];
  return {
    schemaVersion: SCHEMA_VERSION,
    teamId,
    formation: "4-3-3",
    mentality: "balanced",
    roles,
    inPossession: { ...defaultPhase, tempo: 60 },
    inTransition: { ...defaultPhase, pressingIntensity: 70 },
    outOfPossession: { ...defaultPhase, defensiveLineHeight: 45 },
    setPieces: {
      cornerTakers: [playerIds[9]!, playerIds[10]!],
      freeKickTakers: [playerIds[6]!],
      penaltyTaker: playerIds[8]!,
    },
    matchBudget: { maxSubstitutions: 5, maxTacticalChanges: 3 },
  };
}

export function generateMatchInput(matchId: string, seed: string): MatchInput {
  const homeSquad = buildSquad("h");
  const awaySquad = buildSquad("a");
  return {
    schemaVersion: SCHEMA_VERSION,
    matchId,
    seed,
    homeTeamId: "trafford-fc",
    awayTeamId: "ashbury-town",
    homeTactics: buildTactics("trafford-fc", homeSquad.slice(0, 11).map((p) => p.playerId)),
    awayTactics: buildTactics("ashbury-town", awaySquad.slice(0, 11).map((p) => p.playerId)),
    homeSquad,
    awaySquad,
    competition: { allowExtraTime: false, allowPenaltyShootout: false },
  };
}

/**
 * A short, hand-authored MatchOutput fixture — kickoff, a pass, a shot, a
 * goal, half time, full time. Real engine output would have thousands of
 * events and ticks; this is deliberately small so it reads easily as a
 * worked example of the contract's shape.
 */
export function generateMatchOutput(matchId: string, seed: string): MatchOutput {
  const events: MatchEvent[] = [
    { schemaVersion: SCHEMA_VERSION, matchId, sequence: 0, matchMinute: 0, position: { x: 50, y: 32 }, type: "kickoff", team: "home" },
    { schemaVersion: SCHEMA_VERSION, matchId, sequence: 1, matchMinute: 3.2, position: { x: 40, y: 32 }, type: "pass", team: "home", fromPlayerId: "h6", toPlayerId: "h9", completed: true },
    { schemaVersion: SCHEMA_VERSION, matchId, sequence: 2, matchMinute: 9.8, position: { x: 86, y: 30 }, type: "shotOnTarget", team: "home", playerId: "h9", saved: false },
    { schemaVersion: SCHEMA_VERSION, matchId, sequence: 3, matchMinute: 9.8, position: { x: 91, y: 31 }, type: "goal", team: "home", scorerId: "h9", assistPlayerId: "h10", homeScore: 1, awayScore: 0 },
    { schemaVersion: SCHEMA_VERSION, matchId, sequence: 4, matchMinute: 45, position: { x: 50, y: 32 }, type: "halfTime", homeScore: 1, awayScore: 0 },
    { schemaVersion: SCHEMA_VERSION, matchId, sequence: 5, matchMinute: 90, position: { x: 50, y: 32 }, type: "fullTime", homeScore: 1, awayScore: 0 },
  ];

  const makeTick = (tick: number, matchMinute: number, ballPosition: { x: number; y: number }, ballCarrierId?: string): PositionTick => ({
    schemaVersion: SCHEMA_VERSION,
    matchId,
    tick,
    matchMinute,
    ballPosition,
    ...(ballCarrierId !== undefined ? { ballCarrierId } : {}),
    players: [
      ...["h1","h2","h3","h4","h5","h6","h7","h8","h9","h10","h11"].map((id, i) => ({ playerId: id, position: { x: 15 + i * 3, y: 20 + (i % 4) * 8 } })),
      ...["a1","a2","a3","a4","a5","a6","a7","a8","a9","a10","a11"].map((id, i) => ({ playerId: id, position: { x: 85 - i * 3, y: 20 + (i % 4) * 8 } })),
    ],
  });

  const positionStream: PositionTick[] = [
    makeTick(0, 0, { x: 50, y: 32 }, "h9"),
    makeTick(1, 3.2, { x: 40, y: 32 }, "h6"),
    makeTick(2, 9.8, { x: 91, y: 31 }, "h9"),
  ];

  return {
    schemaVersion: SCHEMA_VERSION,
    matchId,
    seed,
    events,
    positionStream,
    result: { homeScore: 1, awayScore: 0, wentToExtraTime: false, wentToPenalties: false },
  };
}
