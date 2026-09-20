'use client'
/**
 * MatchBroadcast — the spectator seat's 2D tactical broadcast.
 *
 * A top-down pitch with 22 named player dots + the ball, a scoreboard with a
 * running score, a momentum bar from the possession stats, both lineups, a
 * live commentary ticker and pause / speed / flip controls. Driven by
 * `buildBroadcastFrames` over a recorded replay (feed + locked lineups) —
 * deterministic, no hidden state.
 *
 * Pass `replay` to broadcast a real recorded fixture; with `replay={null}`
 * the component plays its scripted demo sequence (kickoff → foul → corner →
 * goal) so the board is never empty.
 */
import { useEffect, useMemo, useRef, useState } from 'react'
import {
  buildBroadcastFrames,
  buildPhaseFrames,
  type BroadcastFrame,
  type MatchdayReplay,
} from '@/lib/afm'

const KITS = {
  home: { crest: 'linear-gradient(135deg,#7c3aed,#4c1d95)', dot: '#7c3aed', dotDark: '#4c1d95' },
  away: { crest: 'linear-gradient(135deg,#2fe0c0,#159d85)', dot: '#2fe0c0', dotDark: '#159d85' },
}

interface Props {
  replay: MatchdayReplay | null
  homeLabel?: string
  awayLabel?: string
}

/** Demo roster for the scripted fallback sequence (ids prefixed "h" / "a"). */
const DEMO_HOME = [
  { id: 'h1', num: 1, name: 'J. Reyes', role: 'GK', x: 6, y: 50 },
  { id: 'h2', num: 2, name: 'S. Kilic', role: 'RB', x: 20, y: 14 },
  { id: 'h3', num: 3, name: 'M. Bauer', role: 'CB', x: 15, y: 34 },
  { id: 'h4', num: 4, name: 'L. Dunn', role: 'CB', x: 15, y: 66 },
  { id: 'h5', num: 5, name: 'T. Osei', role: 'LB', x: 20, y: 86 },
  { id: 'h6', num: 6, name: 'D. Okafor', role: 'CDM', x: 34, y: 50 },
  { id: 'h7', num: 7, name: 'F. Novak', role: 'CM', x: 42, y: 26 },
  { id: 'h8', num: 8, name: 'K. Ibarra', role: 'CM', x: 42, y: 74 },
  { id: 'h9', num: 9, name: 'H. Martinez', role: 'ST', x: 56, y: 50 },
  { id: 'h10', num: 10, name: 'A. Petrov', role: 'RW', x: 52, y: 80 },
  { id: 'h11', num: 11, name: 'R. Sousa', role: 'LW', x: 52, y: 20 },
]
const DEMO_AWAY = [
  { id: 'a1', num: 1, name: 'N. Farrow', role: 'GK', x: 94, y: 50 },
  { id: 'a2', num: 2, name: 'C. Doyle', role: 'RB', x: 80, y: 14 },
  { id: 'a3', num: 4, name: 'R. Marsh', role: 'CB', x: 84, y: 34 },
  { id: 'a4', num: 5, name: 'E. Vance', role: 'CB', x: 84, y: 66 },
  { id: 'a5', num: 3, name: 'P. Ngata', role: 'LB', x: 80, y: 86 },
  { id: 'a6', num: 6, name: 'J. Ferreira', role: 'CDM', x: 66, y: 50 },
  { id: 'a7', num: 7, name: 'O. Blake', role: 'CM', x: 58, y: 26 },
  { id: 'a8', num: 8, name: 'W. Choi', role: 'CM', x: 58, y: 74 },
  { id: 'a9', num: 9, name: 'D. Aguirre', role: 'ST', x: 45, y: 50 },
  { id: 'a10', num: 10, name: 'S. Lindqvist', role: 'RW', x: 50, y: 80 },
  { id: 'a11', num: 11, name: 'M. Torres', role: 'LW', x: 50, y: 20 },
]
/** Build a scripted demo sequence: kickoff → buildup → foul → corner → goal. */
function demoFrames(): BroadcastFrame[] {
  const toFrame = (minute: number, text: string, type: string, side: 'home' | 'away' | undefined, ball: { x: number; z: number }, active: string[], possession: 'home' | 'away'): BroadcastFrame => ({
    idx: 0,
    minute,
    text,
    eventType: type,
    ball,
    possession,
    players: [...DEMO_HOME, ...DEMO_AWAY].map((p) => ({
      player_id: p.id,
      x: (p.x / 100) * 105 - 52.5,
      z: (p.y / 100) * 68 - 34,
      active: active.includes(p.id),
    })),
  })
  return [
    toFrame(0, 'Kickoff — Trafford FC get us underway.', 'kickoff', undefined, { x: 0, z: 0 }, [], 'home'),
    toFrame(3, 'Okafor steps into space and starts the move.', 'pass', 'home', { x: -20, z: 0 }, [], 'home'),
    toFrame(5, 'Petrov gets to the byline down the right.', 'pass', 'home', { x: 30, z: 15 }, ['h10', 'h9', 'h7'], 'home'),
    toFrame(8, 'Blake goes in late on Novak — yellow card for the visitor.', 'yellow', 'away', { x: 20, z: 8 }, ['a7', 'h7'], 'home'),
    toFrame(9, 'Corner to Trafford FC after Marsh deflects it behind.', 'corner', 'home', { x: 48, z: -24 }, ['h10', 'h9', 'h4'], 'home'),
    toFrame(9, 'Petrov whips it in towards the far post…', 'cross', 'home', { x: 44, z: -12 }, ['h10', 'h9', 'h4'], 'home'),
    toFrame(9, 'GOAL! Martinez powers a header past Farrow. Trafford FC lead!', 'goal', 'home', { x: 46, z: -20 }, ['h9'], 'home'),
    toFrame(90, 'Full time — Trafford FC 1-0 Ashbury Town.', 'full_time', undefined, { x: 0, z: 0 }, [], 'home'),
  ]
}

/** The broadcast's uniform view of a side — demo or real replay. */
interface SideView {
  formation: string
  rows: { player_id: string; num: number | string; name: string; role: string }[]
}

function replaySideView(side: MatchdayReplay['home']): SideView {
  return {
    formation: side.formation,
    rows: side.xi.map((p, i) => ({ player_id: p.player_id, num: i + 1, name: p.name, role: p.slot })),
  }
}

function demoSideView(which: 'home' | 'away'): SideView {
  const roster = which === 'home' ? DEMO_HOME : DEMO_AWAY
  return {
    formation: '4-3-3',
    rows: roster.map((p) => ({ player_id: p.id, num: p.num, name: p.name, role: p.role })),
  }
}

export default function MatchBroadcast({ replay, homeLabel = 'Home', awayLabel = 'Away' }: Props) {
  const frames = useMemo(() => {
    if (replay) {
      // Prefer the engine's own phase stream (real positions per event);
      // fall back to the client-side movement model for replays recorded
      // before the spatial engine, then to the scripted demo.
      const phaseFrames = buildPhaseFrames(replay)
      if (phaseFrames.length) return phaseFrames
      return buildBroadcastFrames(replay)
    }
    return demoFrames()
  }, [replay])

  /** True when this replay is being played from the engine phase stream. */
  const phaseDriven = useMemo(
    () => !!replay && (replay.result.phases?.length ?? 0) > 0,
    [replay],
  )

  const homeView = useMemo(
    () => (replay ? replaySideView(replay.home) : demoSideView('home')),
    [replay],
  )
  const awayView = useMemo(
    () => (replay ? replaySideView(replay.away) : demoSideView('away')),
    [replay],
  )
  const rowById = useMemo(() => {
    const m = new Map<string, SideView['rows'][number]>()
    for (const r of [...homeView.rows, ...awayView.rows]) m.set(r.player_id, r)
    return m
  }, [homeView, awayView])
  const homeIds = useMemo(() => new Set(homeView.rows.map((r) => r.player_id)), [homeView])

  const [idx, setIdx] = useState(0)
  const [paused, setPaused] = useState(false)
  const [speed, setSpeed] = useState(2)
  const [flipped, setFlipped] = useState(false)
  const timer = useRef<ReturnType<typeof setInterval> | null>(null)

  // A new replay resets playback to kickoff.
  useEffect(() => {
    setIdx(0)
  }, [replay])

  const frame = frames[Math.min(idx, frames.length - 1)] ?? frames[0]

  // Running score: goals up to and including the current frame — from the
  // feed for a real replay, from the scripted demo's own goal frames else.
  const score = useMemo(() => {
    const events = replay
      ? replay.result.feed.slice(0, idx + 1).map((ev) => ({ type: ev.type, side: ev.side }))
      : frames.slice(0, idx + 1).map((f) => ({ type: f.eventType, side: f.possession as 'home' | 'away' | undefined }))
    let h = 0
    let a = 0
    for (const ev of events) {
      if (ev.type === 'goal') {
        if (ev.side === 'away') a++
        else h++
      }
    }
    return `${h} – ${a}`
  }, [replay, frames, idx])

  // Momentum: live possession split from the engine stats, 50/50 until they land.
  const possession = replay?.result?.stats?.possession_home
  const homePct = typeof possession === 'number' ? Math.round(possession) : 50
  const awayPct = 100 - homePct

  useEffect(() => {
    if (paused) return
    timer.current = setInterval(() => {
      setIdx((i) => (i + 1) % frames.length)
    }, 2600 / speed)
    return () => {
      if (timer.current) clearInterval(timer.current)
    }
  }, [paused, speed, frames.length])

  // flip is a CSS transform on the container — no need to re-render positions
  const pitchClass = flipped ? 'mb-pitch mb-flip' : 'mb-pitch'

  const lineup = (view: SideView, active: (id: string) => boolean) => (
    <div className="mb-rows">
      {view.rows.map((r) => (
        <div key={r.player_id} className={`mb-row ${active(r.player_id) ? 'mb-active' : ''}`}>
          <span className="mb-num">{r.num}</span>
          <span className="mb-row-name">{r.name}</span>
          <span className="mb-row-role">{r.role}</span>
        </div>
      ))}
    </div>
  )

  // Active highlight: movement-model frames carry it explicitly; phase-driven
  // frames derive it from geometry — the engine snaps the phase's actor exactly
  // onto the ball, so "on the ball" is the actor.
  const isActive = (id: string) => {
    const p = frame.players.find((q) => q.player_id === id)
    if (!p) return false
    return phaseDriven
      ? Math.abs(p.x - frame.ball.x) < 0.5 && Math.abs(p.z - frame.ball.z) < 0.5
      : p.active
  }

  return (
    <div className="mb-wrap">
      {/* scoreboard */}
      <div className="mb-scoreboard">
        <div className="mb-team">
          <span className="mb-crest" style={{ background: KITS.home.crest }} />
          <span className="mb-team-name">{homeLabel}</span>
        </div>
        <div className="mb-mid">
          <div className="mb-score" aria-live="polite">{score}</div>
          <div className="mb-clock">
            {String(Math.floor(frame.minute)).padStart(2, '0')}:00
          </div>
        </div>
        <div className="mb-team mb-away">
          <span className="mb-team-name">{awayLabel}</span>
          <span className="mb-crest" style={{ background: KITS.away.crest }} />
        </div>
      </div>

      {/* momentum bar — possession split from the engine stats */}
      <div className="mb-momentum">
        <span className="mb-mom-lbl">{homePct}</span>
        <div className="mb-mom-track">
          <div className="mb-mom-home" style={{ width: `${homePct}%` }} />
          <div className="mb-mom-away" style={{ width: `${awayPct}%` }} />
        </div>
        <span className="mb-mom-lbl">{awayPct}</span>
      </div>

      <div className="mb-body">
        <div className="mb-lineup">
          <h4>{homeLabel}</h4>
          <div className="mb-formation">{homeView.formation}</div>
          {lineup(homeView, isActive)}
        </div>

        <div className={pitchClass}>
          <svg className="mb-pitch-lines" viewBox="0 0 100 64" preserveAspectRatio="none">
            <rect x="1" y="1" width="98" height="62" fill="none" stroke="rgba(255,255,255,.35)" strokeWidth="0.4" />
            <line x1="50" y1="1" x2="50" y2="63" stroke="rgba(255,255,255,.35)" strokeWidth="0.4" />
            <circle cx="50" cy="32" r="9" fill="none" stroke="rgba(255,255,255,.35)" strokeWidth="0.4" />
            <circle cx="50" cy="32" r="0.5" fill="rgba(255,255,255,.5)" />
            <rect x="1" y="16" width="15" height="32" fill="none" stroke="rgba(255,255,255,.35)" strokeWidth="0.4" />
            <rect x="1" y="24" width="6" height="16" fill="none" stroke="rgba(255,255,255,.35)" strokeWidth="0.4" />
            <rect x="84" y="16" width="15" height="32" fill="none" stroke="rgba(255,255,255,.35)" strokeWidth="0.4" />
            <rect x="93" y="24" width="6" height="16" fill="none" stroke="rgba(255,255,255,.35)" strokeWidth="0.4" />
          </svg>
          {/* ball */}
          <div
            className="mb-ball"
            style={{
              left: `${((frame.ball.x + 52.5) / 105) * 100}%`,
              top: `${((frame.ball.z + 34) / 68) * 100}%`,
            }}
          />
          {/* 22 dots */}
          {frame.players.map((p) => {
            const row = rowById.get(p.player_id)
            const isHome = homeIds.has(p.player_id)
            const kit = isHome ? KITS.home : KITS.away
            return (
              <div
                key={p.player_id}
                className={`mb-player ${isHome ? 'mb-player-home' : 'mb-player-away'} ${isActive(p.player_id) ? 'mb-has-ball' : ''}`}
                style={{
                  left: `${((p.x + 52.5) / 105) * 100}%`,
                  top: `${((p.z + 34) / 68) * 100}%`,
                  background: isHome ? kit.dot : kit.dotDark,
                  color: isHome ? '#fff' : '#062820',
                }}
                title={row ? `${row.name} (${row.role})` : p.player_id}
              >
                {row ? row.num : '·'}
              </div>
            )
          })}
        </div>

        <div className="mb-lineup mb-lineup-away">
          <h4>{awayLabel}</h4>
          <div className="mb-formation">{awayView.formation}</div>
          {lineup(awayView, isActive)}
        </div>
      </div>

      <div className="mb-ticker" aria-live="polite">{frame.text}</div>

      <div className="mb-controls">
        <button
          className="mb-btn"
          onClick={() => setFlipped((f) => !f)}
          title="Flip pitch orientation"
          aria-label="Flip pitch orientation"
        >
          ⇄
        </button>
        <button
          className="mb-btn"
          onClick={() => setPaused((p) => !p)}
          title={paused ? 'Play' : 'Pause'}
          aria-label={paused ? 'Play' : 'Pause'}
        >
          {paused ? '▶' : '❚❚'}
        </button>
        {[1, 2, 3].map((s) => (
          <button
            key={s}
            className={`mb-btn ${speed === s ? 'mb-active' : ''}`}
            onClick={() => setSpeed(s)}
          >
            {s}x
          </button>
        ))}
      </div>
    </div>
  )
}
