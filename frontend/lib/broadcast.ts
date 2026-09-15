/**
 * Broadcast model: the AFM match feed (authoritative, from the backend
 * engine) → a per-minute pose timeline the 3D view can interpolate.
 *
 * The engine resolves events per minute; this model synthesises *where* the
 * bodies are (the engine has no position model yet) from the formation
 * shapes, the score state and the events — deterministic per match_id so a
 * replay looks the same.
 */
import {
  PlayerOnPitch,
  TeamXI,
  MatchResult,
  FeedEvent,
  PITCH_W,
  PITCH_D,
  HALF_W,
  HALF_D,
  FORMATION_SHAPES,
} from './afm'

export interface Pose {
  x: number
  z: number
}

export interface MinuteState {
  minute: number
  /** poses parallel to the XI arrays */
  home: Pose[]
  away: Pose[]
  ball: Pose
  /** side whose box a goal flash belongs to, if any */
  flash: 'home' | 'away' | null
  /** 0..1 "excitement" driving camera pull-in & commentary emphasis */
  heat: number
}

function hash01(seed: string): number {
  let h = 2166136261
  for (let i = 0; i < seed.length; i++) {
    h ^= seed.charCodeAt(i)
    h = Math.imul(h, 16777619)
  }
  return ((h >>> 0) % 10000) / 10000
}

function jitter(matchId: string, minute: number, idx: number, amp: number): { x: number; z: number } {
  const a = (hash01(`${matchId}:${minute}:${idx}`) - 0.5) * 2
  const b = (hash01(`${matchId}:${minute}:${idx}:z`) - 0.5) * 2
  return { x: a * amp, z: b * amp }
}

function shapeFor(side: 'home' | 'away', team: TeamXI, matchId: string, minute: number): Pose[] {
  const dir = side === 'home' ? 1 : -1
  const shape = FORMATION_SHAPES[team.formation] ?? FORMATION_SHAPES['4-3-3']
  // defence-first anchor: home defends -x, away defends +x
  const anchorX = side === 'home' ? -HALF_W : HALF_W
  const anchorZ = side === 'home' ? -HALF_D : HALF_D
  return team.xi.map((_, idx) => {
    const s = shape[Math.min(idx, shape.length - 1)]
    if (!s) return { x: 0, z: 0 }
    const fx = (s[1] - 50) / 50 // -1 (own goal) .. 1 (opp goal)
    const fz = (s[2] - 50) / 50 // -1 .. 1 across the width
    const x = anchorX + dir * fx * HALF_W
    const z = anchorZ + (side === 'home' ? fz : -fz) * HALF_D
    return { x, z }
  })
}

function clampX(x: number, margin = 0.5): number {
  return Math.max(-HALF_W + margin, Math.min(HALF_W - margin, x))
}
function clampZ(z: number, margin = 0.5): number {
  return Math.max(-HALF_D + margin, Math.min(HALF_D - margin, z))
}

/**
 * Build the per-minute broadcast states for the two XIs from a finished sim.
 * `lengthMinutes` states for minute 0..90 — the view interpolates between them.
 */
export function buildTimeline(
  result: MatchResult,
  home: TeamXI,
  away: TeamXI,
  lengthMinutes = 90,
): MinuteState[] {
  const states: MinuteState[] = []
  const matchId = result.match_id || 'afm'
  const events = [...result.feed].filter((e) => e.type !== 'full_time')
  const evAt = new Map<number, FeedEvent[]>()
  for (const e of events) {
    const list = evAt.get(e.minute) ?? []
    list.push(e)
    evAt.set(e.minute, list)
  }

  // Sustained shape bias from the scoreline: losing side pushes up, winning
  // side drops a touch deeper, both eased over ~4 minutes.
  const homeLead = () => result.home_goals - result.away_goals
  const leadNow = (m: number): number => {
    let h = 0
    let a = 0
    for (const e of events) {
      if (e.minute > m) break
      if (e.type === 'goal' && e.side === 'home') h++
      if (e.type === 'goal' && e.side === 'away') a++
    }
    return h - a
  }

  const pushX = (m: number, idx: number, side: 'home' | 'away'): number => {
    const lead = leadNow(m)
    let push = 0
    if (lead > 0) push = side === 'home' ? -4 : 4 // winners sit a touch deeper
    if (lead < 0) push = side === 'home' ? 5 : -5 // losers push up
    return push + jitter(matchId, m, idx, 2.2).x
  }

  const allEvents = events
  let lastHeat = 0
  let decay = 0

  for (let minute = 0; minute <= lengthMinutes; minute++) {
    const baseHome = shapeFor('home', home, matchId, minute)
    const baseAway = shapeFor('away', away, matchId, minute)
    const homePose = baseHome.map((p, i) => ({
      x: clampX(p.x + pushX(minute, i, 'home'), 1),
      z: clampZ(p.z + jitter(matchId, minute, i + 100, 1.6).z, 1),
    }))
    const awayPose = baseAway.map((p, i) => ({
      x: clampX(p.x + pushX(minute, i, 'away'), 1),
      z: clampZ(p.z + jitter(matchId, minute, i + 200, 1.6).z, 1),
    }))

    const evs = evAt.get(minute) ?? []
    let flash: 'home' | 'away' | null = null
    let ball: Pose = { x: 0, z: 0 }
    let heat = lastHeat * 0.55

    if (evs.some((e) => e.type === 'goal')) {
      const side = evs.find((e) => e.type === 'goal')!.side ?? 'home'
      flash = side
      heat = 1
      // scorer & mates surge into the attacking third; goal side concedes deep
      const goalX = side === 'home' ? HALF_W - 9 : -(HALF_W - 9)
      for (let i = 0; i < homePose.length; i++) {
        const target = side === 'home' ? goalX : -goalX * 0.15
        homePose[i].x = clampX(homePose[i].x * 0.6 + target * 0.4)
      }
      for (let i = 0; i < awayPose.length; i++) {
        const target = side === 'away' ? goalX : -goalX * 0.15
        awayPose[i].x = clampX(awayPose[i].x * 0.6 + target * 0.4)
      }
      ball = { x: goalX, z: 0 }
    } else if (evs.some((e) => e.type === 'shot')) {
      const side = evs.find((e) => e.type === 'shot')!.side ?? 'home'
      heat = 0.75
      const boxX = side === 'home' ? HALF_W - 19 : -(HALF_W - 19)
      const surge = (list: Pose[]) => {
        for (let i = 0; i < list.length; i++) list[i].x = clampX(list[i].x * 0.75 + boxX * 0.25)
      }
      ;(side === 'home' ? homePose : awayPose).forEach((p, i) => {
        p.x = clampX(p.x * 0.7 + boxX * 0.3 + jitter(matchId, minute, i + 300, 3).x)
      })
      ball = { x: boxX, z: jitter(matchId, minute, 900, 12).z }
      void surge
    } else if (evs.some((e) => e.type === 'attack_broken')) {
      heat = 0.25
      ball = { x: jitter(matchId, minute, 901, 18).x, z: jitter(matchId, minute, 902, 16).z }
    } else {
      // idle ball drifts with the neutral third
      ball = {
        x: jitter(matchId, minute, 903, 8).x,
        z: jitter(matchId, minute, 904, 16).z,
      }
    }
    decay = Math.min(1, decay + 1)
    void decay
    // ease heat across minutes after a spike
    states.push({ minute, home: homePose, away: awayPose, ball, flash, heat })
    lastHeat = heat
  }

  // Spread the goal flash over a couple of minutes around the event so the
  // animation reads (event minute + 1 keeps the surge; return to shape after).
  const goalMinute = (s: 'home' | 'away') => {
    const ev = allEvents.find((e) => e.type === 'goal' && e.side === s)
    return ev ? ev.minute : null
  }
  const hg = goalMinute('home')
  if (hg != null && hg + 1 <= lengthMinutes) states[hg + 1].flash = 'home'
  const ag = goalMinute('away')
  if (ag != null && ag + 1 <= lengthMinutes) states[ag + 1].flash = 'away'

  return states
}

export function commentaryFor(result: MatchResult): FeedEvent[] {
  return result.feed.filter((e) => e.type !== 'attack_broken')
}

export function pitchUnits(w: number, d: number): [number, number] {
  return [w / 100 * PITCH_W - HALF_W, d / 100 * PITCH_D - HALF_D]
}

export function playerAt(team: TeamXI, idx: number): PlayerOnPitch | undefined {
  return team.xi[idx]
}
