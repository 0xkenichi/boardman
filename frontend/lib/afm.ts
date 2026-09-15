/**
 * AFM (Agentic Football Managers) shared model for the 3D tactics board.
 * Mirrors src/stack/agentic/games/football_managers (catalog slots, rules).
 *
 * Pitch frame: FIFA-style 105 x 68 (metres). In world units (three.js)
 * the pitch lies on the XZ plane: x in [-52.5, 52.5], z in [-34, 34].
 * A team that "attacks" +x is laid out from its own goal (x=-52.5).
 */

export type Slot = 'GK' | 'RB' | 'CB' | 'LB' | 'CDM' | 'CM' | 'CAM' | 'RW' | 'ST' | 'LW'

export interface AfmPlayer {
  player_id: string
  name: string
  nation: string
  slot: Slot
  primary_pos: 'GK' | 'DEF' | 'MID' | 'FWD'
  base_rating: number
  stars: number
  form: number
  game_price_usdc: string
  wage_per_matchday_usdc: string
  real_value_usd: number
  injury: string | null
  suspension_matches: number
  owner_agent_id: string | null
  weekly_goals?: number
  weekly_assists?: number
  weekly_apps?: number | null
  weekly_rating?: number | null
}

export interface CatalogFile {
  game_id: string
  slots: Slot[]
  players: AfmPlayer[]
}

export const SLOTS: Slot[] = ['GK', 'RB', 'CB', 'LB', 'CDM', 'CM', 'CAM', 'RW', 'ST', 'LW']
export const TACTICAL_TAGS = [
  'balanced',
  'high_press',
  'gegenpress',
  'low_block',
  'park_bus',
  'counter',
  'tiki_taka',
  'long_ball',
] as const
export const PITCH_W = 105
export const PITCH_D = 68
export const HALF_W = PITCH_W / 2
export const HALF_D = PITCH_D / 2

export const FORMATIONS = ['4-3-3', '4-2-3-1', '4-4-2', '3-5-2', '5-3-2', '4-1-4-1', '3-4-3'] as const
export type FormationName = (typeof FORMATIONS)[number]

export const TEAM_PRESETS: Record<string, { name: string; kit: string; kitDark: string; accent: string }> = {
  boardman: { name: 'Boardman FC', kit: '#7c3aed', kitDark: '#4c1d95', accent: '#c4b5fd' },
  bluelock: { name: 'Blue Lock FC', kit: '#3b82f6', kitDark: '#1e3a8a', accent: '#bfdbfe' },
  aoashi: { name: 'Ao Ashi FC', kit: '#f8fafc', kitDark: '#1e293b', accent: '#cbd5e1' },
  matchslice: { name: 'Match-Slice FC', kit: '#ff5a3c', kitDark: '#7f1d1d', accent: '#fecaca' },
  pike: { name: 'Pike City', kit: '#0ea5e9', kitDark: '#0c4a6e', accent: '#7dd3fc' },
  moon: { name: 'Lunar FC', kit: '#22c55e', kitDark: '#14532d', accent: '#86efac' },
  snow: { name: 'Glacier 11', kit: '#e5e7eb', kitDark: '#6b7280', accent: '#ffffff' },
}

/**
 * Formation shapes. Each slot gets a point in % of the pitch as seen from
 * the team's own goal line: x% 0..100 (0 = own goal), z% 0..100 width from
 * the left to the right of the attacking direction (50 = centre).
 */
type Shape = [Slot, number, number][]
export const FORMATION_SHAPES: Record<FormationName, Shape> = {
  '4-3-3': [
    ['GK', 4, 50],
    ['RB', 20, 78],
    ['CB', 15, 63],
    ['CB', 15, 37],
    ['LB', 20, 22],
    ['CDM', 34, 50],
    ['CM', 36, 26],
    ['CM', 36, 74],
    ['LW', 62, 10],
    ['RW', 62, 90],
    ['ST', 58, 50],
  ],
  '4-2-3-1': [
    ['GK', 4, 50],
    ['RB', 22, 78],
    ['CB', 16, 63],
    ['CB', 16, 37],
    ['LB', 22, 22],
    ['CDM', 34, 35],
    ['CDM', 34, 65],
    ['RW', 55, 90],
    ['CAM', 52, 50],
    ['LW', 55, 10],
    ['ST', 66, 50],
  ],
  '4-4-2': [
    ['GK', 4, 50],
    ['RB', 22, 78],
    ['CB', 16, 63],
    ['CB', 16, 37],
    ['LB', 22, 22],
    ['CM', 40, 28],
    ['CM', 40, 72],
    ['RW', 42, 92],
    ['LW', 42, 8],
    ['ST', 58, 38],
    ['ST', 58, 62],
  ],
  '3-5-2': [
    ['GK', 4, 50],
    ['CB', 14, 50],
    ['CB', 13, 25],
    ['CB', 13, 75],
    ['RB', 30, 84],
    ['LB', 30, 16],
    ['CDM', 32, 50],
    ['CM', 40, 32],
    ['CM', 40, 68],
    ['ST', 62, 40],
    ['ST', 62, 60],
  ],
  '5-3-2': [
    ['GK', 4, 50],
    ['RB', 18, 84],
    ['CB', 14, 66],
    ['CB', 12, 50],
    ['CB', 14, 34],
    ['LB', 18, 16],
    ['CDM', 30, 50],
    ['CM', 38, 30],
    ['CM', 38, 70],
    ['ST', 62, 40],
    ['ST', 62, 60],
  ],
  '4-1-4-1': [
    ['GK', 4, 50],
    ['RB', 20, 78],
    ['CB', 15, 63],
    ['CB', 15, 37],
    ['LB', 20, 22],
    ['CDM', 30, 50],
    ['RW', 48, 92],
    ['CM', 46, 32],
    ['CM', 46, 68],
    ['LW', 48, 8],
    ['ST', 68, 50],
  ],
  '3-4-3': [
    ['GK', 4, 50],
    ['CB', 13, 50],
    ['CB', 12, 26],
    ['CB', 12, 74],
    ['RB', 32, 88],
    ['LB', 32, 12],
    ['CDM', 32, 50],
    ['CM', 40, 30],
    ['CM', 40, 70],
    ['RW', 62, 92],
    ['LW', 62, 8],
  ],
}

export interface PlayerOnPitch {
  id: string
  slot: Slot
  /** world x,z metres */
  x: number
  z: number
  name: string
  rating: number
  nation: string
  number: number
}

export interface TeamXI {
  name: string
  kit: string
  kitDark: string
  accent: string
  formation: FormationName
  xi: PlayerOnPitch[]
  bench: AfmPlayer[]
  /** owner agent when this XI is a real AFM club lineup (for Save) */
  clubAgentId?: string
  tags?: string[]
}

export interface AfmClub {
  agent_id: string
  club_name: string
  budget_usdc: string
  spend_usdc: string
  formation: FormationName
  tactical_tags: string[]
  roster_size: number
  starters: AfmPlayer[]
  bench: AfmPlayer[]
  squad: AfmPlayer[]
}

/** Live AFM season state (mirrors the /football/season payload). */
export interface AfmSeason {
  season_no: number
  status: string
  division: { agent_id: string; name: string }[]
  matchdays_total: number
  current_matchday: number
  started_at: string | null
  champion: string | null
  finished_at: string | null
  pot_usdc?: string
}

/** Fetch the live season state (standings/fixtures/results live on this too). */
export async function fetchAfmSeason(): Promise<AfmSeason> {
  const res = await fetch('/api/agentic/football/season')
  if (!res.ok) throw new Error(`season fetch failed (${res.status})`)
  const data = (await res.json()) as { season?: AfmSeason | null }
  if (!data?.season) throw new Error('no live season')
  return data.season
}

/** Convert a formation shape into world coordinates for a side.
 *  Home defends -x (attacks +x); away is the mirror image (defends +x). */
export function layoutSlots(
  formation: FormationName,
  side: 'home' | 'away',
): [Slot, number, number][] {
  const shape = FORMATION_SHAPES[formation] ?? FORMATION_SHAPES['4-3-3']
  return shape.map(([slot, fx, fz]) => {
    const x = -HALF_W + (fx / 100) * PITCH_W
    const z = -HALF_D + (fz / 100) * PITCH_D
    return [slot, side === 'home' ? x : -x, side === 'home' ? z : -z]
  })
}

/**
 * Auto-pick the strongest legal XI for a formation from a player pool,
 * honouring unique ownership (one copy per player across both teams).
 * Falls back to the same position group, then any free player.
 */
export function pickXI(
  players: AfmPlayer[],
  formation: FormationName,
  taken: Set<string>,
  numberOffset = 1,
): PlayerOnPitch[] {
  const bySlot = new Map<Slot, AfmPlayer[]>()
  const byGroup = new Map<string, AfmPlayer[]>()
  for (const p of players) {
    if (p.injury || (p.suspension_matches ?? 0) > 0) continue
    if (taken.has(p.player_id)) continue
    const list = bySlot.get(p.slot) ?? []
    list.push(p)
    bySlot.set(p.slot, list)
    const g = byGroup.get(p.primary_pos) ?? []
    g.push(p)
    byGroup.set(p.primary_pos, g)
  }
  const rank = (a: AfmPlayer, b: AfmPlayer) =>
    (b.base_rating ?? 0) - (a.base_rating ?? 0) || (b.real_value_usd ?? 0) - (a.real_value_usd ?? 0)
  for (const list of bySlot.values()) list.sort(rank)
  for (const list of byGroup.values()) list.sort(rank)

  const shape = FORMATION_SHAPES[formation] ?? FORMATION_SHAPES['4-3-3']
  const used = new Set<string>()
  const result: PlayerOnPitch[] = []
  const tryTake = (slot: Slot, fx: number, fz: number, group: string): PlayerOnPitch | null => {
    const x = -HALF_W + (fx / 100) * PITCH_W
    const z = -HALF_D + (fz / 100) * PITCH_D
    let p: AfmPlayer | undefined = (bySlot.get(slot) ?? []).find((q) => !used.has(q.player_id))
    const groupKey = slot === 'GK' ? 'GK' : group
    if (!p) p = (byGroup.get(groupKey) ?? []).find((q) => !used.has(q.player_id))
    if (!p) return null
    used.add(p.player_id)
    return {
      id: p.player_id,
      slot,
      x,
      z,
      name: p.name,
      rating: p.base_rating ?? 0,
      nation: p.nation,
      number: numberOffset + result.length,
    }
  }

  const GROUP: Record<Slot, string> = {
    GK: 'GK', RB: 'DEF', CB: 'DEF', LB: 'DEF',
    CDM: 'MID', CM: 'MID', CAM: 'MID',
    RW: 'FWD', ST: 'FWD', LW: 'FWD',
  }
  for (const [slot, fx, fz] of shape) {
    const got = tryTake(slot, fx, fz, GROUP[slot])
    if (got) result.push(got)
  }
  return result
}

export function pickBench(players: AfmPlayer[], taken: Set<string>, count = 5): AfmPlayer[] {
  const pool = players
    .filter((p) => !taken.has(p.player_id) && !p.injury)
    .sort((a, b) => (b.base_rating ?? 0) - (a.base_rating ?? 0))
  return pool.slice(0, count)
}

let catalogCache: CatalogFile | null = null

/** Load the catalog — static snapshot first (always works), live API as backup. */
export async function loadCatalog(): Promise<CatalogFile> {
  if (catalogCache) return catalogCache
  const staticUrl = '/agentic/afm-catalog.json'
  try {
    const res = await fetch(staticUrl, { cache: 'force-cache' })
    if (res.ok) {
      const data = (await res.json()) as CatalogFile
      if (data?.players?.length) {
        catalogCache = data
        return data
      }
    }
  } catch {
    /* fall through to live API */
  }
  try {
    const res = await fetch('/api/stack/agentic/football/catalog?limit=500')
    if (res.ok) {
      const data = (await res.json()) as { players?: AfmPlayer[]; slots?: Slot[] }
      if (data?.players?.length) {
        catalogCache = { game_id: 'agentic.football_managers', slots: data.slots ?? SLOTS, players: data.players }
        return catalogCache
      }
    }
  } catch {
    /* no backend */
  }
  throw new Error('Player catalog unavailable')
}

export interface FeedEvent {
  minute: number
  type: string
  side?: 'home' | 'away'
  score?: string
  text: string
}

/** Post-match stat summary from the engine — a pure fold over the feed. */
export interface MatchStats {
  possession_home?: number
  possession_away?: number
  shots_home?: number
  shots_away?: number
  shots_on_target_home?: number
  shots_on_target_away?: number
  blocked_shots_home?: number
  blocked_shots_away?: number
  corners_home?: number
  corners_away?: number
  fouls_home?: number
  fouls_away?: number
  offsides_home?: number
  offsides_away?: number
  yellow_cards_home?: number
  yellow_cards_away?: number
  red_cards_home?: number
  red_cards_away?: number
  [key: string]: number | undefined
}

export interface MatchResult {
  match_id: string
  home_agent_id: string
  away_agent_id: string
  score: string
  home_goals: number
  away_goals: number
  home_points: number
  away_points: number
  reason: string
  feed: FeedEvent[]
  outcome: 'home_win' | 'away_win' | 'draw'
  stats?: MatchStats
  engine?: string
}

export interface SimResponse {
  success: boolean
  match_id: string
  result: MatchResult
}

/* ---------------------------------------------------------------- broadcast
 *
 * The 2D tactical broadcast view (the spectator seat's live top-down pitch)
 * is driven by a lightweight movement model over a recorded replay: the
 * engine emits a feed of events (goals, cards, corners…) plus locked
 * lineups, and this model turns each event into a believable frame of 22
 * player dots + the ball. It is deliberately simple — role-relative base
 * positions, ball-location heuristics, and "active" runs for whoever the
 * event names — so it stays deterministic and cheap. When the engine ships
 * a real per-tick position stream (Phase 1.5), this becomes a thin adapter.
 */

/** Formation base positions in % of the pitch — home attacks +x (left→right). */
const BROADCAST_BASE: Record<FormationName, { slot: Slot; fx: number; fz: number }[]> = {
  '4-3-3': [
    { slot: 'GK', fx: 6, fz: 50 }, { slot: 'RB', fx: 20, fz: 14 }, { slot: 'CB', fx: 15, fz: 34 },
    { slot: 'CB', fx: 15, fz: 66 }, { slot: 'LB', fx: 20, fz: 86 }, { slot: 'CDM', fx: 34, fz: 50 },
    { slot: 'CM', fx: 42, fz: 26 }, { slot: 'CM', fx: 42, fz: 74 }, { slot: 'LW', fx: 52, fz: 20 },
    { slot: 'ST', fx: 56, fz: 50 }, { slot: 'RW', fx: 52, fz: 80 },
  ],
  '4-2-3-1': [
    { slot: 'GK', fx: 6, fz: 50 }, { slot: 'RB', fx: 20, fz: 14 }, { slot: 'CB', fx: 15, fz: 34 },
    { slot: 'CB', fx: 15, fz: 66 }, { slot: 'LB', fx: 20, fz: 86 }, { slot: 'CDM', fx: 34, fz: 38 },
    { slot: 'CDM', fx: 34, fz: 62 }, { slot: 'RW', fx: 50, fz: 18 }, { slot: 'CAM', fx: 50, fz: 50 },
    { slot: 'LW', fx: 50, fz: 82 }, { slot: 'ST', fx: 58, fz: 50 },
  ],
  '4-4-2': [
    { slot: 'GK', fx: 6, fz: 50 }, { slot: 'RB', fx: 20, fz: 14 }, { slot: 'CB', fx: 15, fz: 34 },
    { slot: 'CB', fx: 15, fz: 66 }, { slot: 'LB', fx: 20, fz: 86 }, { slot: 'CM', fx: 38, fz: 30 },
    { slot: 'CM', fx: 38, fz: 70 }, { slot: 'RW', fx: 44, fz: 16 }, { slot: 'ST', fx: 54, fz: 42 },
    { slot: 'ST', fx: 54, fz: 58 }, { slot: 'LW', fx: 44, fz: 84 },
  ],
  '3-5-2': [
    { slot: 'GK', fx: 6, fz: 50 }, { slot: 'CB', fx: 14, fz: 30 }, { slot: 'CB', fx: 14, fz: 50 },
    { slot: 'CB', fx: 14, fz: 70 }, { slot: 'RB', fx: 26, fz: 12 }, { slot: 'CDM', fx: 34, fz: 50 },
    { slot: 'CM', fx: 42, fz: 30 }, { slot: 'CM', fx: 42, fz: 70 }, { slot: 'LB', fx: 26, fz: 88 },
    { slot: 'ST', fx: 54, fz: 42 }, { slot: 'ST', fx: 54, fz: 58 },
  ],
  '5-3-2': [
    { slot: 'GK', fx: 6, fz: 50 }, { slot: 'RB', fx: 18, fz: 12 }, { slot: 'CB', fx: 14, fz: 34 },
    { slot: 'CB', fx: 14, fz: 50 }, { slot: 'CB', fx: 14, fz: 66 }, { slot: 'LB', fx: 18, fz: 88 },
    { slot: 'CDM', fx: 32, fz: 50 }, { slot: 'CM', fx: 40, fz: 32 }, { slot: 'CM', fx: 40, fz: 68 },
    { slot: 'ST', fx: 52, fz: 42 }, { slot: 'ST', fx: 52, fz: 58 },
  ],
  '4-1-4-1': [
    { slot: 'GK', fx: 6, fz: 50 }, { slot: 'RB', fx: 20, fz: 14 }, { slot: 'CB', fx: 15, fz: 34 },
    { slot: 'CB', fx: 15, fz: 66 }, { slot: 'LB', fx: 20, fz: 86 }, { slot: 'CDM', fx: 34, fz: 50 },
    { slot: 'RW', fx: 48, fz: 18 }, { slot: 'CM', fx: 44, fz: 36 }, { slot: 'CM', fx: 44, fz: 64 },
    { slot: 'LW', fx: 48, fz: 82 }, { slot: 'ST', fx: 58, fz: 50 },
  ],
  '3-4-3': [
    { slot: 'GK', fx: 6, fz: 50 }, { slot: 'CB', fx: 14, fz: 30 }, { slot: 'CB', fx: 14, fz: 50 },
    { slot: 'CB', fx: 14, fz: 70 }, { slot: 'RB', fx: 26, fz: 12 }, { slot: 'CDM', fx: 36, fz: 50 },
    { slot: 'CM', fx: 44, fz: 30 }, { slot: 'CM', fx: 44, fz: 70 }, { slot: 'LB', fx: 26, fz: 88 },
    { slot: 'LW', fx: 54, fz: 22 }, { slot: 'RW', fx: 54, fz: 78 },
  ],
}

/** Convert a formation's base % to world metres for a side (home attacks +x). */
function broadcastBasePositions(
  formation: FormationName,
  side: 'home' | 'away',
): { slot: Slot; x: number; z: number }[] {
  const shape = BROADCAST_BASE[formation] ?? BROADCAST_BASE['4-3-3']
  return shape.map(({ slot, fx, fz }) => {
    const x = -HALF_W + (fx / 100) * PITCH_W
    const z = -HALF_D + (fz / 100) * PITCH_D
    return { slot, x: side === 'home' ? x : -x, z: side === 'home' ? z : -z }
  })
}

/**
 * The ball's x/z in world metres for an event, from the event's side and
 * type. Home attacks +x; away attacks -x. A goal is deep in the scoring
 * side's attacking third, a corner on the attacking side's byline, etc.
 */
function broadcastBallForEvent(
  type: string,
  side: 'home' | 'away' | undefined,
): { x: number; z: number } {
  const dir = side === 'away' ? -1 : 1
  const z = side === 'away' ? -HALF_D / 2 : HALF_D / 2
  if (type === 'goal') return { x: dir * (HALF_W - 8), z }
  if (type === 'corner') return { x: dir * (HALF_W - 4), z: dir * HALF_D * 0.8 }
  if (type === 'penalty' || type === 'penalty_goal') return { x: dir * (HALF_W - 11), z: 0 }
  if (type === 'kickoff') return { x: 0, z: 0 }
  if (type === 'full_time' || type === 'extra_time_end' || type === 'penalties_end') return { x: 0, z: 0 }
  if (type === 'yellow' || type === 'red' || type === 'foul') return { x: dir * HALF_W * 0.2, z: dir * HALF_D * 0.3 }
  if (type === 'substitution' || type === 'injury') return { x: dir * HALF_W * 0.4, z: 0 }
  // generic attacking event: push toward the attacking third
  return { x: dir * HALF_W * 0.55, z: dir * HALF_D * 0.15 }
}

/**
 * Build the broadcast frames for a recorded replay: one frame per feed
 * event (plus a final frame), each carrying 22 player dots + the ball.
 * Deterministic given the replay — no RNG, no hidden state.
 */
export function buildBroadcastFrames(replay: MatchdayReplay): BroadcastFrame[] {
  const home = replay.home
  const away = replay.away
  const homeBase = broadcastBasePositions(home.formation, 'home')
  const awayBase = broadcastBasePositions(away.formation, 'away')
  const feed = replay.result?.feed ?? []
  const frames: BroadcastFrame[] = []

  const dot = (p: ReplaySidePlayer, base: { x: number; z: number }, active: boolean) => ({
    player_id: p.player_id,
    x: base.x,
    z: base.z,
    active,
  })

  const homeXis = new Set(home.xi.map((p) => p.player_id))
  const awayXis = new Set(away.xi.map((p) => p.player_id))
  const homeBySlot = new Map<Slot, ReplaySidePlayer>()
  const awayBySlot = new Map<Slot, ReplaySidePlayer>()
  homeBase.forEach((b, i) => {
    const p = home.xi[i]
    if (p) homeBySlot.set(b.slot, p)
  })
  awayBase.forEach((b, i) => {
    const p = away.xi[i]
    if (p) awayBySlot.set(b.slot, p)
  })

  // Who is "active" for an event — whoever the feed names (by name or by
  // side when no player is named, e.g. a team goal).
  const activeIds = (text: string, side: 'home' | 'away' | undefined): Set<string> => {
    const out = new Set<string>()
    const pool = side === 'away' ? away.xi : home.xi
    for (const p of pool) {
      if (p.name && text.toLowerCase().includes(p.name.toLowerCase().split(' ')[0])) {
        out.add(p.player_id)
      }
    }
    if (out.size === 0 && side) {
      // no named player — mark the attacking third as active (striker/wingers)
      const sidePool = side === 'home' ? home.xi : away.xi
      for (const p of sidePool) {
        if (p.slot === 'ST' || p.slot === 'LW' || p.slot === 'RW' || p.slot === 'CAM') out.add(p.player_id)
      }
    }
    return out
  }

  feed.forEach((ev, idx) => {
    const side = ev.side
    const ball = broadcastBallForEvent(ev.type, side)
    const possession = side ?? (ev.type === 'goal' ? (ev.side === 'away' ? 'away' : 'home') : ball.x >= 0 ? 'home' : 'away')
    const act = activeIds(ev.text ?? '', side)

    const players: BroadcastFrame['players'] = []
    home.xi.forEach((p, i) => {
      const base = homeBase[i] ?? { x: -HALF_W, z: 0 }
      players.push(dot(p, base, act.has(p.player_id)))
    })
    away.xi.forEach((p, i) => {
      const base = awayBase[i] ?? { x: HALF_W, z: 0 }
      players.push(dot(p, base, act.has(p.player_id)))
    })

    frames.push({
      idx,
      minute: ev.minute,
      text: ev.text ?? '',
      eventType: ev.type,
      ball,
      possession,
      players,
    })
  })

  // final frame at full time (ball centre, no active player)
  frames.push({
    idx: feed.length,
    minute: feed.length ? feed[feed.length - 1].minute : 90,
    text: 'Full time',
    eventType: 'full_time',
    ball: { x: 0, z: 0 },
    possession: 'home',
    players: [...home.xi.map((p, i) => dot(p, homeBase[i] ?? { x: -HALF_W, z: 0 }, false)), ...away.xi.map((p, i) => dot(p, awayBase[i] ?? { x: HALF_W, z: 0 }, false))],
  })
  return frames
}

/** Run an AFM friendly on the authoritative backend engine. */
export async function simulateMatch(
  home: TeamXI,
  away: TeamXI,
  matchId?: string,
): Promise<SimResponse> {
  const res = await fetch('/api/agentic/football/simulate', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      home_name: home.name,
      away_name: away.name,
      home_xi: home.xi.map((p) => p.id),
      away_xi: away.xi.map((p) => p.id),
      match_id: matchId,
      home_tactics: { formation: home.formation, tags: home.tags ?? ['balanced'] },
      away_tactics: { formation: away.formation, tags: away.tags ?? ['balanced'] },
    }),
  })
  if (!res.ok) {
    const text = await res.text().catch(() => '')
    throw new Error(`simulate failed (${res.status}): ${text.slice(0, 200)}`)
  }
  return (await res.json()) as SimResponse
}

export interface ReplaySidePlayer {
  player_id: string
  name: string
  slot: Slot
  primary_pos: string
  base_rating: number
}

export interface ReplaySide {
  agent_id: string
  club_name: string
  formation: FormationName
  tags: string[]
  xi: ReplaySidePlayer[]
}

/**
 * One frame of the 2D tactical broadcast: every player's pitch position
 * (x/z in world metres, matching layoutSlots) plus the ball and possession.
 * Derived client-side from a MatchdayReplay (feed + locked lineups) by the
 * broadcast's lightweight movement model — the engine's position stream is
 * the Phase-1.5 output; this derives believable positions until it lands.
 */
export interface BroadcastFrame {
  idx: number
  minute: number
  text: string
  eventType: string
  ball: { x: number; z: number }
  possession: 'home' | 'away'
  players: { player_id: string; x: number; z: number; active: boolean }[]
}

export interface MatchdayReplay {
  match_id: string
  matchday: number
  result: MatchResult
  home: ReplaySide
  away: ReplaySide
  decisions: Record<string, { formation: string; tags: string[] }>
}

/** Fetch a recorded season fixture (feed + locked lineups) for the board. */
export async function fetchSeasonReplay(
  matchday: number,
  home: string,
  away: string,
): Promise<MatchdayReplay> {
  const q = new URLSearchParams({ matchday: String(matchday), home, away })
  const res = await fetch(`/api/agentic/football/season/replay?${q.toString()}`)
  if (!res.ok) throw new Error(`replay fetch failed (${res.status})`)
  const data = (await res.json()) as { success?: boolean; replay?: MatchdayReplay }
  if (!data?.replay) throw new Error('no replay available for this fixture')
  return data.replay
}

/** A role the player can play in their position, with FM-style suitability. */
export interface SquadRole {
  name: string
  /** weighted attribute score, 1–99 */
  score: number
  /** 1–5★ */
  stars: number
}

/** FM-style squad player: catalog record + derived attributes + status. */
export interface SquadPlayer extends AfmPlayer {
  status: 'starter' | 'bench' | 'squad'
  /** 0-99 skills + fitness/morale as 0..1 running-state values. */
  attributes: Record<string, number>
  fitness: number
  morale: number
  /** role suitability for the player's position, best first */
  roles: SquadRole[]
  contract: {
    years_left: number
    wage_usdc: string
    value_usdc: string
    runway_matchdays: number
  }
}

export interface ClubSquad {
  club: AfmClub
  squad: SquadPlayer[]
}

/** Fetch one club + its enriched FM-style squad (starter → bench → squad). */
export async function fetchClubSquad(agentId: string): Promise<ClubSquad> {
  const res = await fetch(`/api/agentic/football/clubs/${encodeURIComponent(agentId)}`)
  if (!res.ok) throw new Error(`squad fetch failed (${res.status})`)
  const data = (await res.json()) as { club?: AfmClub; squad?: SquadPlayer[] }
  if (!data?.club) throw new Error('no club data for this agent')
  return { club: data.club, squad: data.squad ?? [] }
}

/** A manager agent on the marketplace (owner seat step 1: create/acquire/buy). */
export interface MarketAgent {
  agent_id: string
  name: string
  creator_id: string
  owner_id: string
  archetype: string
  archetype_name: string
  strategy_id: string
  version: string
  blurb: string
  stats: {
    wins?: number
    losses?: number
    draws?: number
    matches?: number
    creator_fees_usdc?: string
  }
  has_club: boolean
  club_name: string | null
  builtin: boolean
  adopted: boolean
  created_at: string
  /** webhook hosting this manager's brain — owner-set; the House asks it before each matchday */
  webhook_url: string | null
  /** for-sale listing — set when the owner listed the manager with a price */
  listed: boolean
  price_usdc: string | null
  creator_cut_bps: number | null
  listed_at: string
  seller_id: string | null
  sales_count: number
  /** offers against a listed manager — owner reviews these */
  reserve_usdc: string | null
  accepting_offers: boolean
  pending_offers: PendingOffer[]
  /** true when a sale could settle in real USDC today (owner + developer have
   *  payout addresses bound) — the buyer still needs their own wallet too */
  onchain_payable: boolean
  /** detail card: playbook + ability radars and the season record (manager_card.py) */
  card: ManagerCard
}

/** One radar's axes in draw order, plus the 0-100 values per axis. */
export interface ManagerRadar {
  axes: Record<string, number>
  axis_order: string[]
}

/** The manager detail card embedded on every marketplace row. */
export interface ManagerCard {
  playbook: ManagerRadar & {
    summary: {
      formation: string
      base_tag: string
      reactive_tag: string
      pick: 'rating' | 'shape'
      shapes: string[]
    }
  }
  /** null when the manager has no squad yet — hide the radar instead of a zeroed one */
  ability: ManagerRadar | null
  record: {
    matches: Array<{
      matchday: number
      venue: 'home' | 'away'
      opponent_id: string | null
      opponent_club: string | null
      gf: number
      ga: number
      outcome: 'W' | 'D' | 'L'
      xg_for: number
      xg_against: number
    }>
    totals: {
      played: number
      wins: number
      draws: number
      losses: number
      points: number
      goals_for: number
      goals_against: number
      xg_for: number
      xg_against: number
    }
    form: string
  }
}

/** A buyer's offer waiting on the owner to accept or reject. */
export interface PendingOffer {
  offer_id: string
  buyer_id: string
  amount_usdc: string
  created_at: string
}

/** Playbook archetypes the decide loop understands (mirrors agent_market.py). */
export const MANAGER_ARCHETYPES = [
  {
    id: 'striker',
    name: 'The Striker Ego',
    blurb:
      'Stars over system: highest-rated XI, attack-first shapes (3-4-3 / 4-3-3), never parks the bus. Blue Lock school.',
  },
  {
    id: 'tactician',
    name: 'The Total Footballer',
    blurb:
      'System over stars: position-disciplined XI, balanced shapes (4-2-3-1 / 4-1-4-1), reads the opponent and adapts. Ao Ashi school.',
  },
  {
    id: 'pragmatist',
    name: 'The Pragmatist',
    blurb:
      'Low block and counters: disciplined 5-3-2 / 4-1-4-1, absorbs pressure, hits on the break.',
  },
  {
    id: 'possession',
    name: 'The Possession Coach',
    blurb:
      'Keep the ball: tiki-taka shapes (4-3-3 / 4-1-4-1), patient buildup, counter only when chased.',
  },
] as const

export type ManagerArchetype = (typeof MANAGER_ARCHETYPES)[number]['id']

/** The manager marketplace — every AFM agent an owner can adopt. */
export async function listMarketAgents(): Promise<MarketAgent[]> {
  const res = await fetch('/api/agentic/football/agents')
  if (!res.ok) throw new Error(`marketplace fetch failed (${res.status})`)
  const data = (await res.json()) as { agents?: MarketAgent[] }
  return data.agents ?? []
}

export interface CreateManagerInput {
  manager_name: string
  club_name?: string
  archetype: ManagerArchetype
  formation?: FormationName
  owner_id?: string
  /** optional: list the manager for sale the moment it is created */
  list_price_usdc?: number
  creator_cut_bps?: number
}

/** Build a manager against the playbook: registers the agent + seeds its club. */
export async function createManagerAgent(input: CreateManagerInput): Promise<{ agent: MarketAgent; club: AfmClub }> {
  const res = await fetch('/api/agentic/football/agents', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      manager_name: input.manager_name,
      club_name: input.club_name,
      archetype: input.archetype,
      formation: input.formation ?? '4-3-3',
      owner_id: input.owner_id,
      list_price_usdc: input.list_price_usdc,
      creator_cut_bps: input.creator_cut_bps,
    }),
  })
  if (!res.ok) {
    const detail = (await res.json().catch(() => ({}))) as { detail?: string }
    throw new Error(detail.detail ?? `create failed (${res.status})`)
  }
  const data = (await res.json()) as { agent: MarketAgent; club: AfmClub }
  return data
}

/** Adopt an unlisted developer-built manager: ownership moves to the caller (free). */
export async function acquireManagerAgent(agentId: string, ownerId?: string): Promise<MarketAgent> {
  const res = await fetch('/api/agentic/football/agents/acquire', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ agent_id: agentId, owner_id: ownerId }),
  })
  if (!res.ok) {
    const detail = (await res.json().catch(() => ({}))) as { detail?: string }
    throw new Error(detail.detail ?? `acquire failed (${res.status})`)
  }
  const data = (await res.json()) as { agent: MarketAgent }
  return data.agent
}

/** List a manager you own for sale with a price + creator cut (developer % of
 *  each sale) and an optional reserve floor — offers below it auto-decline. */
export async function listManagerForSale(
  agentId: string,
  priceUsdc: number,
  creatorCutBps?: number,
  listedBy?: string,
  reserveUsdc?: number,
): Promise<MarketAgent> {
  const res = await fetch('/api/agentic/football/agents/list', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      agent_id: agentId,
      price_usdc: priceUsdc,
      creator_cut_bps: creatorCutBps ?? 0,
      reserve_price_usdc: reserveUsdc && reserveUsdc > 0 ? reserveUsdc : undefined,
      listed_by: listedBy,
    }),
  })
  if (!res.ok) {
    const detail = (await res.json().catch(() => ({}))) as { detail?: string }
    throw new Error(detail.detail ?? `list failed (${res.status})`)
  }
  const data = (await res.json()) as { agent: MarketAgent }
  return data.agent
}

/** A buyer's offer result — auto_declined means it fell under the reserve. */
export interface OfferResult {
  agent: MarketAgent
  offer: {
    offer_id: string
    buyer_id: string
    amount_usdc: string
    status: 'pending' | 'accepted' | 'rejected'
    note?: string
  }
  auto_declined: boolean
}

/** Name your price on a listed manager (below the owner's reserve auto-declines). */
export async function makeManagerOffer(
  agentId: string,
  offerUsdc: number,
  buyerId?: string,
): Promise<OfferResult> {
  const res = await fetch('/api/agentic/football/agents/offer', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ agent_id: agentId, offer_usdc: offerUsdc, buyer_id: buyerId }),
  })
  if (!res.ok) {
    const detail = (await res.json().catch(() => ({}))) as { detail?: string }
    throw new Error(detail.detail ?? `offer failed (${res.status})`)
  }
  const data = (await res.json()) as OfferResult
  return data
}

/** The owner accepts a buyer's offer — the sale settles at the offered price. */
export async function acceptManagerOffer(
  agentId: string,
  offerId: string,
  decidedBy?: string,
  settlement: SettlementMode = 'auto',
): Promise<{ agent: MarketAgent; sale: ManagerSale }> {
  const res = await fetch('/api/agentic/football/agents/offer/accept', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      agent_id: agentId,
      offer_id: offerId,
      decided_by: decidedBy,
      settlement,
    }),
  })
  if (!res.ok) {
    const detail = (await res.json().catch(() => ({}))) as { detail?: string }
    throw new Error(detail.detail ?? `accept failed (${res.status})`)
  }
  const data = (await res.json()) as { agent: MarketAgent; sale: ManagerSale }
  return data
}

/** The owner turns a buyer's offer down — the listing stays up. */
export async function rejectManagerOffer(
  agentId: string,
  offerId: string,
  decidedBy?: string,
): Promise<MarketAgent> {
  const res = await fetch('/api/agentic/football/agents/offer/reject', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ agent_id: agentId, offer_id: offerId, decided_by: decidedBy }),
  })
  if (!res.ok) {
    const detail = (await res.json().catch(() => ({}))) as { detail?: string }
    throw new Error(detail.detail ?? `reject failed (${res.status})`)
  }
  const data = (await res.json()) as { agent: MarketAgent }
  return data.agent
}

/** Pull a manager you own off the marketplace. */
export async function delistManagerForSale(agentId: string, listedBy?: string): Promise<MarketAgent> {
  const res = await fetch('/api/agentic/football/agents/delist', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ agent_id: agentId, listed_by: listedBy }),
  })
  if (!res.ok) {
    const detail = (await res.json().catch(() => ({}))) as { detail?: string }
    throw new Error(detail.detail ?? `delist failed (${res.status})`)
  }
  const data = (await res.json()) as { agent: MarketAgent }
  return data.agent
}

/** Point a manager you own at the webhook hosting its brain. From the next
 *  matchday ask on, the House POSTs the matchday context there and locks the
 *  manager's JSON reply (deterministic playbook fallback when unreachable).
 *  Pass an empty URL to clear the binding. */
export async function setManagerWebhook(
  agentId: string,
  webhookUrl: string,
  ownerId?: string,
): Promise<MarketAgent> {
  const res = await fetch('/api/agentic/football/agents/webhook', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ agent_id: agentId, webhook_url: webhookUrl || null, owner_id: ownerId }),
  })
  if (!res.ok) {
    const detail = (await res.json().catch(() => ({}))) as { detail?: string }
    throw new Error(detail.detail ?? `webhook update failed (${res.status})`)
  }
  const data = (await res.json()) as { agent: MarketAgent }
  return data.agent
}

/** How a manager sale settles: auto (real USDC when every party has a bound
 *  wallet, else the demo ledger) | onchain (required) | ledger (force demo). */
export type SettlementMode = 'auto' | 'onchain' | 'ledger'

/** One payment leg of a settled sale (mode + where the money went). */
export interface SaleLeg {
  kind: 'buy_debit' | 'creator_cut' | 'seller_payout'
  amount_usdc: string
  /** onchain legs */
  to_address?: string
  from_wallet?: string
  to_wallet?: string
  transaction_id?: string
  tx_hash?: string | null
  status?: string
  reason?: string
}

/** Sale receipt returned when a listed manager is bought (buy-now or accepted offer). */
export interface ManagerSale {
  agent_id: string
  price_usdc: string
  creator_cut_usdc: string
  seller_payout_usdc: string
  seller_id: string
  buyer_id: string
  first_sale: boolean
  seller_wallet: string
  buyer_wallet: string
  source: 'buy_now' | 'offer_accepted'
  sold_at: string
  /** which rail moved the money: onchain = real Arc USDC, ledger = demo book-entry */
  mode: 'onchain' | 'ledger'
  settlement: {
    mode: 'onchain' | 'ledger'
    chain_id: string
    legs: SaleLeg[]
  }
}

/** Buy a listed manager: price settles (auto = real USDC when every party has
 *  a bound wallet, else the demo ledger), ownership moves to the buyer. */
export async function purchaseManagerAgent(
  agentId: string,
  buyerId?: string,
  settlement: SettlementMode = 'auto',
): Promise<{ agent: MarketAgent; sale: ManagerSale }> {
  const res = await fetch('/api/agentic/football/agents/purchase', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ agent_id: agentId, buyer_id: buyerId, settlement }),
  })
  if (!res.ok) {
    const detail = (await res.json().catch(() => ({}))) as { detail?: string }
    throw new Error(detail.detail ?? `purchase failed (${res.status})`)
  }
  const data = (await res.json()) as { agent: MarketAgent; sale: ManagerSale }
  return data
}

/** A marketplace party's wallet: what they pay with / get paid to.
 *  ledger_wallet is the demo book-entry id; real_wallet is a bound Arc USDC
 *  (Circle) wallet — when can_send, purchases move real USDC out of it. */
export interface PartyWalletStatus {
  party_id: string
  circle_configured: boolean
  ledger_wallet: string
  real_wallet: {
    address: string
    chain_id: string
    can_send: boolean
    source?: string
  } | null
  mode: 'onchain' | 'ledger'
  note: string
}

export async function fetchPartyWalletStatus(partyId: string): Promise<PartyWalletStatus> {
  const res = await fetch(`/api/agentic/football/agents/wallet?party_id=${encodeURIComponent(partyId)}`)
  if (!res.ok) throw new Error(`wallet status failed (${res.status})`)
  const data = (await res.json()) as { wallet?: PartyWalletStatus }
  if (!data?.wallet) throw new Error('no wallet status returned')
  return data.wallet
}

/** Bind a real (Circle) wallet to a marketplace party so purchases can settle
 *  in real USDC. Pass wallet_id too when the party pays from that wallet. */
export async function bindPartyWallet(
  partyId: string,
  address: string,
  walletId?: string,
): Promise<{ party_id: string; address: string; can_send: boolean }> {
  const res = await fetch('/api/agentic/football/agents/wallet/bind', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ party_id: partyId, address, wallet_id: walletId }),
  })
  if (!res.ok) {
    const detail = (await res.json().catch(() => ({}))) as { detail?: string }
    throw new Error(detail.detail ?? `wallet bind failed (${res.status})`)
  }
  const data = (await res.json()) as { wallet: { party_id: string; address: string; can_send: boolean } }
  return data.wallet
}

/** Remove a marketplace party's wallet binding (back to the demo ledger). */
export async function unbindPartyWallet(partyId: string, address?: string): Promise<boolean> {
  const res = await fetch('/api/agentic/football/agents/wallet/unbind', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ party_id: partyId, address }),
  })
  if (!res.ok) {
    const detail = (await res.json().catch(() => ({}))) as { detail?: string }
    throw new Error(detail.detail ?? `wallet unbind failed (${res.status})`)
  }
  const data = (await res.json()) as { removed?: boolean }
  return data.removed ?? false
}

/** The owner sales desk — money a party has earned from manager sales. */
export interface SalesPortfolioRow {
  agent_id: string
  name: string
  owned: boolean
  listed: boolean
  price_usdc: string | null
  creator_cut_bps: number | null
  reserve_usdc: string | null
  listed_at: string | null
  sales_count: number
  record_sales: number
  earned_usdc: string
  as_seller_usdc: string
  creator_cuts_usdc: string
  last_sale: {
    price_usdc: string
    seller_id: string
    buyer_id: string
    sold_at: string
    source: 'buy_now' | 'offer_accepted'
    mode: 'onchain' | 'ledger'
    creator_cut_usdc: string
    seller_payout_usdc: string
    tx_hash?: string | null
  } | null
}

export interface SalesTimelineEntry {
  ts: string
  kind: 'listed' | 'relisted' | 'delisted' | 'sold'
  agent_id: string
  manager: string
  role: 'seller' | 'creator_cut' | 'owner'
  amount_usdc: string | null
  price_usdc: string | null
  mode: 'onchain' | 'ledger' | null
  detail: string
}

export interface PartySalesView {
  party_id: string
  total_earned_usdc: string
  as_seller_usdc: string
  creator_cuts_usdc: string
  sale_count: number
  portfolio: SalesPortfolioRow[]
  timeline: SalesTimelineEntry[]
}

/** Owner dashboard desk: money earned from manager sales + listing history. */
export async function fetchOwnerSales(partyId: string): Promise<PartySalesView> {
  const res = await fetch(`/api/agentic/football/agents/sales?party_id=${encodeURIComponent(partyId)}`)
  if (!res.ok) throw new Error(`sales desk fetch failed (${res.status})`)
  const data = (await res.json()) as { sales?: PartySalesView }
  if (!data?.sales) throw new Error('no sales data returned')
  return data.sales
}

/** Owner dashboard — step 5: one club's results, decisions, spend, news. */
export interface DashboardStandingRow {
  rank: number
  agent_id: string
  club_name: string
  played: number
  wins: number
  draws: number
  losses: number
  goals_for: number
  goals_against: number
  goal_diff: number
  points: number
}

export interface DashboardResult {
  matchday: number
  match_id: string
  played_at: string | null
  venue: 'home' | 'away'
  opponent_id: string
  opponent_club: string
  our_goals: number
  their_goals: number
  outcome: 'W' | 'D' | 'L'
  decision: {
    formation: string
    tags: string[]
    xi: string[]
    banned: string[]
    auto: boolean
    /** where the plan came from: the manager's own webhook or the deterministic playbook */
    source?: 'webhook' | 'auto' | null
    /** the manager's own words, when it answered via webhook */
    instructions?: string | null
    /** fallback reason when the webhook was unreachable/invalid */
    note?: string | null
    error?: string | null
  }
  match_stats?: Record<string, number>
  /** FM post-match report summary (ratings/xG/errors) — engine v1.3 results only */
  report?: MatchReportSummary
}

export interface ReportPlayerRow {
  player_id: string
  name: string
  position: string
  starter: boolean
  played: boolean
  minutes: number
  goals: number
  shots: number
  shots_on_target: number
  xG: number
  rating: number | null
  tackles: number
  interceptions: number
  passes: number
  cards: number
  errors: { type?: string; note?: string; xG?: number; minute?: number }[]
}

export interface MatchReportSummary {
  my_xg: number
  their_xg: number
  top: ReportPlayerRow | null
  poor: ReportPlayerRow | null
  errors: { type?: string; note?: string; xG?: number; minute?: number }[]
  why?: string | null
  formation?: string | null
  players: ReportPlayerRow[]
}

export interface DashboardNews {
  type: 'injury' | 'suspension'
  player_id: string
  name: string
  position: string
  detail: string
  matchday_next?: number
}

export interface DashboardSpend {
  ts: string
  kind: 'club_budget' | 'squad_build' | 'ledger'
  type?: string
  label: string
  detail: string
  /** signed USDC — negative is money out */
  amount: string
}

export interface OwnerDashboard {
  agent_id: string
  club: AfmClub
  manager: {
    name: string
    archetype: string
    archetype_name: string
  }
  season: {
    season_no: number
    status: string
    current_matchday: number
    matchdays_total: number
    champion: string | null
  } | null
  table: {
    in_season: boolean
    rank: number | null
    of: number
    row: DashboardStandingRow | null
    standings: DashboardStandingRow[]
  }
  form: string
  results: DashboardResult[]
  upcoming: {
    matchday: number
    venue: 'home' | 'away'
    opponent_id: string
    opponent_club: string
    status: string
    deadline_at: string
  }[]
  finances: {
    budget_usdc: string
    spend_usdc: string
    remaining_usdc: string
    wallet_balance_usdc: string
    wage_debt_usdc?: string
    stake_debt_usdc?: string
  }
  spending: DashboardSpend[]
  news: DashboardNews[]
  squad_status: {
    total: number
    starters: number
    injured: number
    suspended: number
    banned_next: number
    available: number
  }
}

/** The owner-seat dashboard for one club. */
export async function fetchOwnerDashboard(agentId: string): Promise<OwnerDashboard> {
  const res = await fetch(`/api/agentic/football/owner/${encodeURIComponent(agentId)}`)
  if (!res.ok) {
    const detail = (await res.json().catch(() => ({}))) as { detail?: string }
    throw new Error(detail.detail ?? `dashboard fetch failed (${res.status})`)
  }
  const data = (await res.json()) as { dashboard?: OwnerDashboard }
  if (!data?.dashboard) throw new Error('no dashboard data for this club')
  return data.dashboard
}

/** Agent-owned AFM clubs (lineups agents set for kickoff). */
export async function listClubs(): Promise<AfmClub[]> {
  const res = await fetch('/api/agentic/football/clubs')
  if (!res.ok) throw new Error(`clubs fetch failed (${res.status})`)
  const data = (await res.json()) as { clubs?: AfmClub[] }
  return data.clubs ?? []
}

/** Save a board lineup back to its club (agent afm_set_lineup). */
export async function saveClubLineup(team: TeamXI): Promise<AfmClub> {
  const res = await fetch(`/api/agentic/football/clubs/${team.clubAgentId}/lineup`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      formation: team.formation,
      starters: team.xi.map((p) => p.id),
      bench: team.bench.slice(0, 5).map((p) => p.player_id),
      tactical_tags: team.tags ?? ['balanced'],
    }),
  })
  if (!res.ok) {
    const detail = (await res.json().catch(() => ({}))) as { detail?: string }
    throw new Error(detail.detail ?? `save failed (${res.status})`)
  }
  const data = (await res.json()) as { club: AfmClub }
  return data.club
}
