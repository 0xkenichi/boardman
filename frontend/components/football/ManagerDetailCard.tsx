'use client'

/**
 * Manager detail card — the marketplace's at-a-glance view of a manager,
 * in the same visual language as the player profile tabs (Boardman brand):
 *
 * - Playbook radar: how the mind actually sets up, computed backend-side from
 *   the live decide.STRATEGIES table (attack/press/defence/counter/system/
 *   stars) so it can never drift from real matchday behaviour.
 * - Ability radar: what the manager has to work with — squad-average derived
 *   attributes. Hidden entirely when the manager has no squad (never fake a
 *   zeroed radar).
 * - Record charts: per-matchday results (points bar, GF-GA and xG bars),
 *   a last-5 form strip, and season totals — all folds over stored results.
 *
 * Honesty rules (same as the player profile): every number is real engine or
 * stored-season data; an empty record renders as an empty record, not a guess.
 */

import { useMemo } from 'react'
import type { ManagerCard, ManagerRadar } from '@/lib/afm'

const PLAYBOOK_LABEL: Record<string, string> = {
  attack: 'Attack',
  press: 'Press',
  defence: 'Defence',
  counter: 'Counter',
  system: 'System',
  stars: 'Stars',
}

const ABILITY_LABEL: Record<string, string> = {
  attack: 'Attacking',
  pace: 'Pace',
  defence: 'Defending',
  passing: 'Passing',
  physical: 'Physical',
  keeper: 'Keeping',
}

const PICK_LABEL: Record<string, string> = {
  rating: 'stars over system',
  shape: 'system over stars',
}

const TAG_LABEL: Record<string, string> = {
  gegenpress: 'gegenpress',
  high_press: 'high press',
  tiki_taka: 'tiki-taka',
  low_block: 'low block',
  park_bus: 'park the bus',
  balanced: 'balanced',
  counter: 'counter',
}

/** Radar geometry over 0-100 axes in the given draw order. */
function useRadarPoly(
  order: string[],
  values: Record<string, number>,
  radius = 52,
  center = 60,
): { points: string; axes: Array<{ k: string; x: number; y: number; lx: number; ly: number }> } {
  return useMemo(() => {
    const n = Math.max(order.length, 1)
    const pt = (i: number, r: number): [number, number] => {
      const a = (Math.PI * 2 * i) / n - Math.PI / 2
      return [center + r * Math.cos(a), center + r * Math.sin(a)]
    }
    const points =
      order
        .map((k, i) => {
          const v = Math.max(0, Math.min(100, values?.[k] ?? 0)) / 100
          const [x, y] = pt(i, radius * Math.max(0.06, v))
          return `${x.toFixed(1)},${y.toFixed(1)}`
        })
        .join(' ')
    const axes = order.map((k, i) => {
      const [x, y] = pt(i, radius)
      const [lx, ly] = pt(i, radius + 14)
      return { k, x, y, lx, ly }
    })
    return { points, axes }
  }, [order, values, radius, center])
}

function Radar({
  order,
  values,
  labels,
  fillClass,
  title,
}: {
  order: string[]
  values: Record<string, number>
  labels: Record<string, string>
  fillClass: string
  title: string
}) {
  const rings = useMemo(() => {
    const n = Math.max(order.length, 1)
    const pt = (i: number, r: number): [number, number] => {
      const a = (Math.PI * 2 * i) / n - Math.PI / 2
      return [60 + r * Math.cos(a), 60 + r * Math.sin(a)]
    }
    return [0.25, 0.5, 0.75, 1].map((f) =>
      order
        .map((_, i) => {
          const [x, y] = pt(i, 52 * f)
          return `${x.toFixed(1)},${y.toFixed(1)}`
        })
        .join(' '),
    )
  }, [order])
  const { points, axes } = useRadarPoly(order, values)

  return (
    <div className="mc-radar" role="img" aria-label={title}>
      <svg viewBox="0 0 120 120">
        {rings.map((ring, i) => (
          <polygon key={i} points={ring} className="mc-radar-ring" />
        ))}
        <polygon points={points} className={fillClass} />
        {axes.map((a) => (
          <g key={a.k}>
            <line x1="60" y1="60" x2={a.x} y2={a.y} className="mc-radar-axis" />
            <text x={a.lx} y={a.ly} className="mc-radar-label">
              {labels[a.k] ?? a.k}
            </text>
          </g>
        ))}
      </svg>
    </div>
  )
}

/** Last-5 form strip: W/D/L dots, newest last. */
function FormStrip({ form }: { form: string }) {
  if (!form) return <span className="mc-form-empty">no matches yet</span>
  return (
    <span className="mc-form">
      {form.split('').map((c, i) => (
        <i key={i} className={`mc-form-dot ${c.toLowerCase()}`} title={c === 'W' ? 'win' : c === 'D' ? 'draw' : 'loss'}>
          {c}
        </i>
      ))}
    </span>
  )
}

/** Per-matchday rows: points bar + score + xG comparison. */
function RecordRows({ card }: { card: ManagerCard }) {
  const matches = card.record.matches
  const maxPts = Math.max(1, ...matches.map((m) => (m.outcome === 'W' ? 3 : m.outcome === 'D' ? 1 : 0)))
  return (
    <div className="mc-record">
      <div className="mc-record-head">
        <span>md</span>
        <span>result</span>
        <span>xG</span>
      </div>
      {matches.map((m) => (
        <div className="mc-record-row" key={m.matchday}>
          <span className="mc-record-md">
            {m.matchday}
            <em>{m.venue === 'home' ? 'H' : 'A'}</em>
          </span>
          <span className="mc-record-score">
            <b className={`mc-outcome ${m.outcome.toLowerCase()}`}>{m.outcome}</b>
            {m.gf}–{m.ga}
            <em className="mc-opp">{m.opponent_club ?? m.opponent_id ?? ''}</em>
          </span>
          <span className="mc-record-xg" title={`xG for ${m.xg_for.toFixed(2)} · against ${m.xg_against.toFixed(2)}`}>
            <i className="mc-xgbar">
              <i style={{ width: `${Math.min(100, (m.xg_for / Math.max(m.xg_for, m.xg_against, 0.01)) * 100)}%` }} className="for" />
              <i style={{ width: `${Math.min(100, (m.xg_against / Math.max(m.xg_for, m.xg_against, 0.01)) * 100)}%` }} className="against" />
            </i>
            <em>
              {m.xg_for.toFixed(2)}–{m.xg_against.toFixed(2)}
            </em>
          </span>
        </div>
      ))}
    </div>
  )
}

export function ManagerDetailCard({ card }: { card: ManagerCard }) {
  const pb = card.playbook
  const totals = card.record.totals
  const winPct = totals.played > 0 ? Math.round((totals.wins / totals.played) * 100) : null

  return (
    <div className="mc-card">
      <div className="mc-radar-row">
        <div className="mc-radar-block">
          <h5>
            Playbook <em>what the mind runs on matchday</em>
          </h5>
          <Radar
            order={pb.axis_order}
            values={pb.axes}
            labels={PLAYBOOK_LABEL}
            fillClass="mc-radar-fill"
            title="Playbook radar"
          />
          <p className="mc-playbook-note">
            {pb.summary.formation} · {TAG_LABEL[pb.summary.base_tag] ?? pb.summary.base_tag} →{' '}
            {TAG_LABEL[pb.summary.reactive_tag] ?? pb.summary.reactive_tag} · {PICK_LABEL[pb.summary.pick] ?? pb.summary.pick}
          </p>
        </div>

        {card.ability ? (
          <div className="mc-radar-block">
            <h5>
              Squad ability <em>average of the players it can pick</em>
            </h5>
            <Radar
              order={card.ability.axis_order}
              values={card.ability.axes}
              labels={ABILITY_LABEL}
              fillClass="mc-radar-fill alt"
              title="Squad ability radar"
            />
          </div>
        ) : (
          <div className="mc-radar-block mc-ability-empty">
            <h5>Squad ability</h5>
            <p className="mc-playbook-note">no squad seeded yet — the radar appears once the club has players</p>
          </div>
        )}
      </div>

      <div className="mc-totals">
        <div>
          <b>{totals.played}</b>
          <span>played</span>
        </div>
        <div>
          <b>
            {totals.wins}
            <em>–{totals.draws}–{totals.losses}</em>
          </b>
          <span>W–D–L</span>
        </div>
        <div>
          <b>{totals.points}</b>
          <span>points</span>
        </div>
        <div>
          <b>
            {totals.goals_for}
            <em>:{totals.goals_against}</em>
          </b>
          <span>goals</span>
        </div>
        <div>
          <b>
            {totals.xg_for.toFixed(2)}
            <em>:{totals.xg_against.toFixed(2)}</em>
          </b>
          <span>xG for:against</span>
        </div>
        <div>
          <b>{winPct != null ? `${winPct}%` : '—'}</b>
          <span>win rate</span>
        </div>
      </div>

      <div className="mc-record-wrap">
        <div className="mc-record-top">
          <h5>
            Season record <em>from stored results</em>
          </h5>
          <FormStrip form={card.record.form} />
        </div>
        {card.record.matches.length > 0 ? (
          <RecordRows card={card} />
        ) : (
          <p className="mc-playbook-note">No matches played yet — the record charts fill in as the season runs.</p>
        )}
      </div>
    </div>
  )
}
