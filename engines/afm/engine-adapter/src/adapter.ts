/**
 * @afm/engine-adapter — Python engine → @afm/match-contracts bridge.
 *
 * Validates a Python `MatchResult` at the boundary and emits typed,
 * schema-valid `MatchOutput`. Nothing here simulates. Where the Python
 * engine cannot fill a contract field, the adapter drops the event into
 * the diagnostics' commentary channel rather than inventing data — the
 * known cases are: fouls (Python never names the fouled player) and the
 * sub-kind / second-yellow nuances the contract union doesn't carry.
 */
import {
  SCHEMA_VERSION,
  MatchOutputRefined,
  type MatchEvent,
  type MatchOutput,
  type MatchResultLine,
  type PositionTick,
  type SquadPlayer,
} from "@afm/match-contracts";
import type { PyFeedEvent, PyMatchResult, PyPhase, PyReplay } from "./pyTypes.js";

// ---------------------------------------------------------------------------
// diagnostics
// ---------------------------------------------------------------------------

export interface AdapterDiagnostics {
  /** Feed indices dropped from the event log (unmappable), with reasons. */
  dropped: { index: number; type: string; reason: string }[];
  /** Commentary-only text for dropped events (never silent, never invented). */
  commentary: string[];
  /** Number of position ticks emitted. */
  ticks: number;
}

export interface AdaptedMatch {
  output: MatchOutput;
  diagnostics: AdapterDiagnostics;
  /** Club labels for consumers that want them. */
  clubs: { home: string; away: string };
}

export interface AdapterOptions {
  /**
   * playerId → display name. Used to resolve "second yellow" contexts and
   * kept for future name-carrying consumers. Build via `rosterFromReplay`.
   */
  roster?: Map<string, string>;
}

// ---------------------------------------------------------------------------
// small helpers
// ---------------------------------------------------------------------------

/** "2 – 1" / "2-1" → [2, 1]. */
export function parseScore(s: string): [number, number] {
  const m = s.match(/(\d+)\s*[-–]\s*(\d+)/);
  if (!m) throw new Error(`unparseable Python score string: "${s}"`);
  return [Number(m[1]!), Number(m[2]!)];
}

function clamp100(v: number): number {
  return Math.max(0, Math.min(100, v));
}

/** Engine metres (home-goal origin, x goal-to-goal) → contract 0–100 domain. */
function rescale(v: number, span: number): number {
  return clamp100((v / span) * 100);
}

// ---------------------------------------------------------------------------
// roster helpers
// ---------------------------------------------------------------------------

/** playerId → name from a Python replay envelope. */
export function rosterFromReplay(replay: PyReplay): Map<string, string> {
  const m = new Map<string, string>();
  for (const side of [replay.home, replay.away]) {
    for (const p of side.xi) m.set(p.player_id, p.name);
  }
  return m;
}

/**
 * A minimal SquadPlayer list from a replay side. Real attributes live in
 * the Python engine; the contract requires the *shape*, so placeholders
 * (all 10s) are filled here and flagged in the README.
 */
export function squadFromReplaySide(side: PyReplay["home"]): SquadPlayer[] {
  return side.xi.map((p) => ({
    playerId: p.player_id,
    name: p.name,
    attributes: placeholderAttributes(),
    condition: 100,
    morale: 75,
  }));
}

function placeholderAttributes(): SquadPlayer["attributes"] {
  const t = 10;
  return {
    technical: { passing: t, longPassing: t, crossing: t, finishing: t, shotPower: t, technique: t, dribbling: t, firstTouch: t },
    mental: { positioning: t, vision: t, composure: t, workRate: t, decisions: t, anticipation: t, concentration: t },
    physical: { pace: t, acceleration: t, stamina: t, strength: t, agility: t, jumping: t },
    defensive: { tackling: t, marking: t, heading: t, aggression: t },
    goalkeeping: { reflexes: t, handling: t, oneOnOnes: t, aerialReach: t },
    hidden: { consistency: t, bigMatchTemperament: t, professionalism: t, injuryProneness: t, determination: t },
  };
}

// ---------------------------------------------------------------------------
// the adapter
// ---------------------------------------------------------------------------

/** Omit that distributes over unions — Omit<> alone collapses them. */
type DistributiveOmit<T, K extends PropertyKey> = T extends unknown ? Omit<T, K> : never;
type NewEvent = DistributiveOmit<MatchEvent, "sequence">;

export function adaptMatchResult(py: PyMatchResult, opts: AdapterOptions = {}): AdaptedMatch {
  const dropped: AdapterDiagnostics["dropped"] = [];
  const commentary: string[] = [];
  const events: MatchEvent[] = [];
  let seq = 0;

  const sideOr = (s: "home" | "away" | undefined): "home" | "away" => s ?? "home";
  const evBase = (ev: PyFeedEvent) => ({
    schemaVersion: SCHEMA_VERSION as typeof SCHEMA_VERSION,
    matchId: py.match_id,
    matchMinute: ev.minute,
    position:
      typeof ev.x === "number" && typeof ev.y === "number"
        ? { x: clamp100(ev.x), y: clamp100(ev.y) }
        : { x: 50, y: 50 },
  });

  function push(ev: NewEvent): void {
    // sequence is assigned here so callers can't desync it
    events.push({ ...ev, sequence: seq } as MatchEvent);
    seq++;
  }

  function drop(i: number, ev: PyFeedEvent, reason: string): void {
    dropped.push({ index: i, type: ev.type, reason });
    commentary.push(ev.text);
  }

  // --- running score ---------------------------------------------------------
  let home = 0;
  let away = 0;
  const wentToPens = py.home_pen_goals !== null && py.away_pen_goals !== null;
  const wentToET = wentToPens || /extra time/i.test(py.reason);
  const scoreAfter = (): MatchResultLine => ({
    homeScore: home,
    awayScore: away,
    wentToExtraTime: wentToET,
    wentToPenalties: wentToPens,
  });

  py.feed.forEach((ev, i) => {
    const side = ev.side;
    const pid = ev.player_id ?? ev.actor_id;
    const base = evBase(ev);

    switch (ev.type) {
      case "kickoff":
        push({ ...base, type: "kickoff", team: sideOr(side) });
        return;

      case "possession":
      case "pass": {
        // Python's pass names only the passer (possession progression) —
        // the contract's pass requires a recipient, so this maps to carry.
        if (!pid) {
          drop(i, ev, "possession/pass without an actor");
          return;
        }
        push({ ...base, type: "carry", team: sideOr(side), playerId: pid });
        return;
      }

      case "shot": {
        if (!pid) {
          drop(i, ev, "shot without a shooter");
          return;
        }
        const blocked = ev.blocked === true;
        const onTarget = ev.on_target === true;
        if (blocked) {
          // Python never names the blocker — contract requires blockedByPlayerId,
          // so a blocked shot maps to the honest subset: off-target shot.
          push({ ...base, type: "shotOffTarget", team: sideOr(side), playerId: pid });
          commentary.push(`BLOCKED: ${ev.text}`);
          return;
        }
        if (onTarget) {
          push({ ...base, type: "shotOnTarget", team: sideOr(side), playerId: pid, saved: true });
          return;
        }
        push({ ...base, type: "shotOffTarget", team: sideOr(side), playerId: pid });
        return;
      }

      case "goal": {
        if (!pid) {
          drop(i, ev, "goal without a scorer");
          return;
        }
        if (side === "away") away++;
        else home++;
        push({
          ...base,
          type: "goal",
          team: sideOr(side),
          scorerId: pid,
          ...(typeof ev.assist === "string" ? { assistPlayerId: ev.assist } : {}),
          homeScore: home,
          awayScore: away,
        });
        return;
      }

      case "yellow":
        if (!pid) {
          drop(i, ev, "yellow card without a player");
          return;
        }
        push({ ...base, type: "yellowCard", team: sideOr(side), playerId: pid });
        return;

      case "red": {
        if (!pid) {
          drop(i, ev, "red card without a player");
          return;
        }
        const secondYellow = /second yellow/i.test(ev.text);
        push({ ...base, type: "redCard", team: sideOr(side), playerId: pid, secondYellow });
        return;
      }

      case "substitution": {
        const off = ev.off;
        const on = ev.on;
        if (typeof off !== "string" || typeof on !== "string") {
          drop(i, ev, "substitution without off/on ids");
          return;
        }
        push({ ...base, type: "substitution", team: sideOr(side), playerOffId: off, playerOnId: on });
        return;
      }

      case "injury":
        if (!pid) {
          drop(i, ev, "injury without a player");
          return;
        }
        // Python treats all in-match injuries as forced-off; "major" is the
        // honest mapping (the player left the pitch).
        push({ ...base, type: "injury", team: sideOr(side), playerId: pid, severity: "major" });
        return;

      case "foul":
        // Python never names the fouled player; the contract requires
        // fouledPlayerId — drop to commentary rather than fabricate.
        drop(i, ev, "foul cannot fill fouledPlayerId (Python never names the victim)");
        return;

      case "tackle":
        if (!pid) {
          drop(i, ev, "tackle without a player");
          return;
        }
        // Python tackles name only the tackler; the contract's tackle case
        // requires an opponent — map to interception (a defensive win).
        push({ ...base, type: "interception", team: sideOr(side), playerId: pid });
        return;

      case "interception":
        if (!pid) {
          drop(i, ev, "interception without a player");
          return;
        }
        push({ ...base, type: "interception", team: sideOr(side), playerId: pid });
        return;

      case "offside":
        if (!pid) {
          drop(i, ev, "offside without a player");
          return;
        }
        push({ ...base, type: "offside", team: sideOr(side), playerId: pid });
        return;

      case "corner":
      case "corner_delivery":
        push({ ...base, type: "corner", team: sideOr(side) });
        return;

      case "free_kick":
        // The contract union has no free-kick case yet — commentary + a
        // possession carry by the named taker keeps the log connected.
        commentary.push(`FREE KICK: ${ev.text}`);
        if (pid) push({ ...base, type: "carry", team: sideOr(side), playerId: pid });
        return;

      case "goal_kick":
        push({ ...base, type: "goalKick", team: sideOr(side) });
        return;

      case "throw_in":
        push({ ...base, type: "throwIn", team: sideOr(side) });
        return;

      case "halftime": {
        const parsed = parseScore(String(ev.score ?? py.score));
        home = parsed[0];
        away = parsed[1];
        push({ ...base, type: "halfTime", homeScore: home, awayScore: away });
        return;
      }

      case "full_time": {
        const parsed = parseScore(String(ev.score ?? py.score));
        home = parsed[0];
        away = parsed[1];
        push({ ...base, type: "fullTime", homeScore: home, awayScore: away });
        return;
      }

      case "penalty": {
        // Shootout kick. Contract penaltyResult fits; shootout kicks are not
        // open-play goals so the running score is untouched.
        if (!pid) {
          drop(i, ev, "penalty kick without a kicker");
          return;
        }
        push({ ...base, type: "penaltyResult", team: sideOr(side), playerId: pid, scored: ev.made === true });
        return;
      }

      case "added_time":
      case "tactical_change":
      case "penalties_start":
      case "penalties_end":
      case "xG_over_performance":
      case "xG_under_performance":
        // Real content, no contract case — preserved as commentary only.
        commentary.push(ev.text);
        return;

      default:
        drop(i, ev, `unmapped Python event type "${ev.type}"`);
    }
  });

  // Guarantee the log ends at full time so consumers can rely on it.
  const last = events.at(-1);
  if (!last || last.type !== "fullTime") {
    // full_time was dropped or unreachable — fall back to the envelope score.
    const parsed = parseScore(py.score);
    push({
      schemaVersion: SCHEMA_VERSION,
      matchId: py.match_id,
      matchMinute: 90,
      position: { x: 50, y: 50 },
      type: "fullTime",
      homeScore: parsed[0],
      awayScore: parsed[1],
    });
  }

  // --- phases → position stream ----------------------------------------------
  const L = 105;
  const W = 68;
  const tickFromPhase = (ph: PyPhase, i: number): PositionTick => {
    // The phase's actor is placed exactly on the ball — the closest player
    // to the ball is the carrier.
    let carrier: string | undefined;
    let best = Number.POSITIVE_INFINITY;
    for (const p of ph.players) {
      const d = Math.hypot(p.x - ph.ball.x, p.y - ph.ball.y);
      if (d < best) {
        best = d;
        carrier = p.id;
      }
    }
    return {
      schemaVersion: SCHEMA_VERSION,
      matchId: py.match_id,
      tick: i,
      matchMinute: ph.minute,
      ballPosition: { x: rescale(ph.ball.x, L), y: rescale(ph.ball.y, W) },
      ...(carrier !== undefined ? { ballCarrierId: carrier } : {}),
      players: ph.players.map((p) => ({
        playerId: p.id,
        position: { x: rescale(p.x, L), y: rescale(p.y, W) },
      })),
    };
  };
  const positionStream: PositionTick[] = py.phases.map(tickFromPhase);

  // --- envelope -----------------------------------------------------------------
  // seed is omitted: the Python engine does not serialize it — publishing a
  // fake one would falsely imply re-simulability.
  const output: MatchOutput = {
    schemaVersion: SCHEMA_VERSION,
    matchId: py.match_id,
    events,
    positionStream,
    result: scoreAfter(),
  };

  // The boundary is the boundary: refuse to emit an invalid payload.
  const parsed = MatchOutputRefined.safeParse(output);
  if (!parsed.success) {
    const first = parsed.error.issues[0];
    throw new Error(
      `adapter produced an invalid MatchOutput: ${first?.path.join(".")} — ${first?.message}`,
    );
  }

  return {
    output: parsed.data as MatchOutput,
    diagnostics: { dropped, commentary, ticks: positionStream.length },
    clubs: { home: py.home_agent_id, away: py.away_agent_id },
  };
}
