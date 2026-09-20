'use client'
/**
 * PreMatchBoard — the pre-match tactics board ("how this manager wants to
 * play"), the P2 roadmap row the Tactics App inspired.
 *
 * One 2D pitch, both clubs' locked plans from `season.prematch_view`:
 * formation shapes with named players on their slots, tactical tags as the
 * "how", the pre-committed half-time contingency plans (trailing/level/
 * leading), the managers' own instructions and the ban/injury news beside
 * the team sheet. Spectator-safe by construction — formation, slots and
 * names only; no attribute numbers, no edit controls (humans never draw
 * tactics that change the live match).
 *
 * With `view={null}` (season API down, unknown fixture) it renders its
 * scripted demo plans so the board is never empty.
 */
import { useMemo, useState } from 'react'
import { FORMATION_SHAPES, type FormationName } from '@/lib/afm'
import type { PrematchView } from '@/lib/afm'

const KITS = {
  home: { crest: 'linear-gradient(135deg,#7c3aed,#4c1d95)', chip: '#7c3aed' },
  away: { crest: 'linear-gradient(135deg,#2fe0c0,#159d85)', chip: '#159d85' },
}

const TAG_LABELS: Record<string, string> = {
  balanced: 'Balanced',
  high_press: 'High press',
  gegenpress: 'Gegenpress',
  low_block: 'Low block',
  park_bus: 'Park the bus',
  counter: 'Counter',
  tiki_taka: 'Tiki-taka',
  long_ball: 'Long ball',
}

const STATE_LABELS: Record<string, string> = {
  trailing: 'If trailing',
  level: 'If level',
  leading: 'If leading',
}

const MENTALITY_LABELS: Record<string, string> = {
  attacking: 'attacking',
  balanced: 'balanced',
  defensive: 'defensive',
}

/** The board's uniform view of a side — real prematch payload or demo. */
interface BoardSide {
  club_name: string
  formation: string
  tags: string[]
  instructions?: string | null
  source?: 'webhook' | 'auto' | null
  plans: Record<string, { formation?: string; tags?: string[]; mentality?: string }>
  xi: { player_id: string; name: string; slot: string }[]
  news: { type: 'suspension' | 'injury'; player_id: string; name: string; detail: string }[]
  decided: boolean
}

function demoSide(which: 'home' | 'away'): BoardSide {
  return which === 'home'
    ? {
        club_name: 'Trafford FC',
        formation: '4-3-3',
        tags: ['high_press', 'counter'],
        instructions: 'Press high from the whistle, hit the channels early.',
        source: 'webhook',
        plans: {
          trailing: { formation: '4-2-3-1', tags: ['high_press'], mentality: 'attacking' },
          leading: { formation: '4-1-4-1', tags: ['low_block'], mentality: 'defensive' },
        },
        xi: [],
        news: [{ type: 'suspension', player_id: 'x1', name: 'K. Ibarra', detail: 'Suspended — sent off last matchday' }],
        decided: true,
      }
    : {
        club_name: 'Ashbury Town',
        formation: '5-3-2',
        tags: ['low_block'],
        instructions: 'Stay compact, soak, and break through Sousa’s side.',
        source: 'auto',
        plans: { trailing: { formation: '4-4-2', tags: ['long_ball'], mentality: 'attacking' } },
        xi: [],
        news: [],
        decided: true,
      }
}

/** Named XI arranged on their formation slots. Home attacks right. */
function slotPositions(formation: string, side: 'home' | 'away') {
  const shape = FORMATION_SHAPES[formation as FormationName] ?? FORMATION_SHAPES['4-3-3']
  return shape.map(([slot, fx, fz], i) => {
    // fx: 0 = own goal → 100 = opponent goal; mirror for the away side
    const xPct = side === 'home' ? fx : 100 - fx
    const zPct = fz
    return { i, slot, xPct, zPct }
  })
}

function TeamPanel({ side, which }: { side: BoardSide; which: 'home' | 'away' }) {
  const kit = KITS[which]
  return (
    <div className={`pb-side pb-side-${which}`}>
      <div className="pb-side-head">
        <span className="pb-crest" style={{ background: kit.crest }} />
        <b>{side.club_name}</b>
        {side.source ? (
          <span className={`pb-src ${side.source === 'webhook' ? 'is-webhook' : 'is-auto'}`}>
            {side.source === 'webhook' ? 'via webhook' : 'playbook auto'}
          </span>
        ) : null}
      </div>
      <div className="pb-formation">{side.formation || '—'}</div>
      {side.tags.length > 0 && (
        <div className="pb-tags">
          {side.tags.map((t) => (
            <span key={t} className="pb-tag" style={{ borderColor: kit.chip }}>
              {TAG_LABELS[t] ?? t}
            </span>
          ))}
        </div>
      )}
      {side.instructions ? <p className="pb-quote">“{side.instructions}”</p> : null}
      {Object.keys(side.plans).length > 0 && (
        <div className="pb-plans">
          {['trailing', 'level', 'leading'].map((k) => {
            const p = side.plans[k]
            if (!p) return null
            const bits = [p.formation, p.mentality ? MENTALITY_LABELS[p.mentality] : null, (p.tags ?? []).map((t) => TAG_LABELS[t] ?? t).join(' + ')]
              .filter(Boolean)
              .join(' · ')
            return (
              <div key={k} className="pb-plan">
                <span className="pb-plan-state">{STATE_LABELS[k]}</span>
                <span className="pb-plan-detail">{bits || '—'}</span>
              </div>
            )
          })}
        </div>
      )}
      {side.news.length > 0 && (
        <ul className="pb-news">
          {side.news.map((n) => (
            <li key={n.player_id} className={`pb-news-${n.type}`}>
              {n.name} — {n.detail}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

export default function PreMatchBoard({ view }: { view: PrematchView | null }) {
  const [flipped, setFlipped] = useState(false)
  const home = useMemo(() => (view ? view.home : demoSide('home')), [view])
  const away = useMemo(() => (view ? view.away : demoSide('away')), [view])

  const homeSlots = useMemo(() => slotPositions(home.formation || '4-3-3', 'home'), [home.formation])
  const awaySlots = useMemo(() => slotPositions(away.formation || '4-3-3', 'away'), [away.formation])

  // XI dots: when the payload carries the named XI, place its players on the
  // slots in order (the lock stores the XI slot-ordered, same as the engine
  // lineup); when it doesn't (demo / not yet decided), place generic dots.
  const dots = (s: BoardSide, which: 'home' | 'away') => {
    const slots = which === 'home' ? homeSlots : awaySlots
    const kit = KITS[which]
    return slots.map((sl) => {
      const p = s.xi[sl.i]
      return (
        <div
          key={`${which}-${sl.i}`}
          className={`pb-dot pb-dot-${which}`}
          style={{
            left: `${flipped ? 100 - sl.xPct : sl.xPct}%`,
            top: `${sl.zPct}%`,
            background: kit.chip,
          }}
          title={p ? `${p.name} (${sl.slot})` : sl.slot}
        >
          {sl.slot}
        </div>
      )
    })
  }

  const statusLine = view
    ? view.status === 'played'
      ? 'Played — this was the shape it was played in'
      : view.status === 'open'
        ? 'Lineups locked at the deadline — this is the plan'
        : 'Projected window — lineups drop when the matchday opens'
    : 'Demo plans — live data unavailable'

  return (
    <div className="pb-wrap">
      <div className="pb-scoreboard">
        <div className="pb-team">
          <span className="pb-crest" style={{ background: KITS.home.crest }} />
          <span className="pb-team-name">{home.club_name}</span>
        </div>
        <div className="pb-mid">
          <div className="pb-kickoff">vs</div>
          <div className="pb-md">Matchday {view?.matchday ?? '—'}</div>
        </div>
        <div className="pb-team pb-away">
          <span className="pb-team-name">{away.club_name}</span>
          <span className="pb-crest" style={{ background: KITS.away.crest }} />
        </div>
      </div>
      <p className="pb-status">{statusLine}</p>

      <div className="pb-body">
        <TeamPanel side={home} which="home" />

        <div className={`pb-pitch ${flipped ? 'pb-flip' : ''}`}>
          <svg className="pb-pitch-lines" viewBox="0 0 100 64" preserveAspectRatio="none" aria-hidden>
            <rect x="1" y="1" width="98" height="62" fill="none" stroke="rgba(255,255,255,.3)" strokeWidth="0.4" />
            <line x1="50" y1="1" x2="50" y2="63" stroke="rgba(255,255,255,.3)" strokeWidth="0.4" />
            <circle cx="50" cy="32" r="9" fill="none" stroke="rgba(255,255,255,.3)" strokeWidth="0.4" />
            <rect x="1" y="16" width="15" height="32" fill="none" stroke="rgba(255,255,255,.3)" strokeWidth="0.4" />
            <rect x="1" y="24" width="6" height="16" fill="none" stroke="rgba(255,255,255,.3)" strokeWidth="0.4" />
            <rect x="84" y="16" width="15" height="32" fill="none" stroke="rgba(255,255,255,.3)" strokeWidth="0.4" />
            <rect x="93" y="24" width="6" height="16" fill="none" stroke="rgba(255,255,255,.3)" strokeWidth="0.4" />
          </svg>
          {/* half-space shading — the "where the plan wants the game played" layer */}
          <div className="pb-zone pb-zone-l" />
          <div className="pb-zone pb-zone-r" />
          {dots(home, 'home')}
          {dots(away, 'away')}
        </div>

        <TeamPanel side={away} which="away" />
      </div>

      <div className="pb-controls">
        <button className="pb-btn" onClick={() => setFlipped((f) => !f)} title="Flip pitch orientation" aria-label="Flip pitch orientation">
          ⇄
        </button>
        {!home.decided || !away.decided ? (
          <span className="pb-pending">Awaiting lineups — the managers decide when the matchday opens</span>
        ) : null}
      </div>
    </div>
  )
}
