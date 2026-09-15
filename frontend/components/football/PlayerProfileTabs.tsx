'use client'

/**
 * FM-style player profile — Boardman-branded rebuild of the reference clip's
 * profile screen: underline tab strip (Overview / Contract / Development /
 * Stats), star ability rating, attribute groups, a percentile radar vs the
 * squad, ranked stat meters, and a contract timeline strip.
 *
 * Honesty rule (from the design brief): never fake precision. Everything shown
 * is real engine data; percentiles are explicitly "vs squad"; where the engine
 * tracks no history (development sparkline, season totals) we say so instead
 * of inventing numbers.
 */
import { useMemo, useState } from 'react'
import type { SquadPlayer } from '@/lib/afm'

type Tab = 'overview' | 'contract' | 'development' | 'stats'

const TABS: { id: Tab; label: string }[] = [
  { id: 'overview', label: 'Overview' },
  { id: 'contract', label: 'Contract' },
  { id: 'development', label: 'Development' },
  { id: 'stats', label: 'Stats' },
]

/** Attribute families the engine actually plays with (mirrors the engine's attributes.py). */
const FAMILIES: { label: string; keys: { key: string; label: string }[] }[] = [
  {
    label: 'Technical',
    keys: [
      { key: 'technical', label: 'Technique' },
      { key: 'shooting', label: 'Finishing' },
      { key: 'passing', label: 'Passing' },
      { key: 'tackling', label: 'Tackling' },
    ],
  },
  {
    label: 'Mental',
    keys: [
      { key: 'decision_making', label: 'Decisions' },
      { key: 'positioning', label: 'Positioning' },
    ],
  },
  {
    label: 'Physical',
    keys: [
      { key: 'pace', label: 'Pace' },
      { key: 'physicality', label: 'Strength' },
    ],
  },
]

const RADAR_KEYS = [
  'technical',
  'shooting',
  'passing',
  'tackling',
  'decision_making',
  'positioning',
  'pace',
  'physicality',
] as const

const STATUS_LABEL: Record<string, string> = { starter: 'STARTER', bench: 'BENCH', squad: 'SQUAD' }

function money(v: string | number | undefined): string {
  const n = Number(v ?? 0)
  return Number.isFinite(n) ? n.toLocaleString(undefined, { maximumFractionDigits: 2 }) : '—'
}

/** Percentile of `v` among `peers` (0–100, "top X%" style). */
function pct(v: number, peers: number[]): number {
  if (peers.length === 0) return 50
  const below = peers.filter((x) => x < v).length
  return Math.round((below / peers.length) * 100)
}

function barClass(v: number, good = 85, mid = 70): string {
  if (v >= good) return 'good'
  if (v >= mid) return 'mid'
  return 'low'
}

export function PlayerProfileTabs({ player: p, squad }: { player: SquadPlayer; squad: SquadPlayer[] }) {
  const [tab, setTab] = useState<Tab>('overview')

  /** Squad-average per attribute among same-position peers — the radar's second series. */
  const peers = useMemo(() => squad.filter((q) => q.primary_pos === p.primary_pos && q.player_id !== p.player_id), [squad, p])
  const peerAvg = useMemo(() => {
    const m: Record<string, number> = {}
    for (const k of RADAR_KEYS) {
      const vals = peers.map((q) => q.attributes?.[k] ?? 0)
      m[k] = vals.length ? vals.reduce((a, b) => a + b, 0) / vals.length : (p.attributes?.[k] ?? 0)
    }
    return m
  }, [peers, p])

  const radar = useMemo(() => {
    const n = RADAR_KEYS.length
    const pt = (i: number, r: number): [number, number] => {
      const a = (Math.PI * 2 * i) / n - Math.PI / 2
      return [60 + r * Math.cos(a), 60 + r * Math.sin(a)]
    }
    const poly = (vals: Record<string, number>, radius: number) =>
      RADAR_KEYS.map((k, i) => pt(i, radius * Math.max(0.06, Math.min(1, (vals[k] ?? 0) / 99)))).map(
        ([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`,
      ).join(' ')
    return {
      me: poly(p.attributes ?? {}, 52),
      cohort: poly(peerAvg, 52),
      rings: [0.25, 0.5, 0.75, 1].map((f) => poly(
        Object.fromEntries(RADAR_KEYS.map((k) => [k, 99 * f])) as Record<string, number>,
        52,
      )),
      axes: RADAR_KEYS.map((k, i) => {
        const [x, y] = pt(i, 52)
        const [lx, ly] = pt(i, 68)
        return { k, x, y, lx, ly }
      }),
    }
  }, [p, peerAvg])

  const attr = (k: string): number => Math.round(p.attributes?.[k] ?? 0)

  return (
    <div className="sq-profile">
      {/* header — identity + ability stars + season stat row (the clip's player header) */}
      <div className="sq-profile-top">
        <div>
          <h3>
            {p.name} <span className="sq-slot">{p.slot}</span>
          </h3>
          <p className="sq-profile-meta">
            ability {p.base_rating} · form {p.form?.toFixed(1) ?? '—'}
            {p.nation ? ` · ${p.nation}` : ''}
          </p>
        </div>
        <div className="sq-profile-badges">
          <span className={`sq-status ${p.status}`}>{STATUS_LABEL[p.status]}</span>
          {p.injury && <span className="sq-flag bad">⚠ {p.injury}</span>}
          {(p.suspension_matches ?? 0) > 0 && (
            <span className="sq-flag bad">🟥 suspended {p.suspension_matches} md</span>
          )}
          <span className="sq-stars" title={`Ability ${p.base_rating}/99`}>
            {'★'.repeat(p.stars ?? 0)}
            <span className="dim">{'☆'.repeat(Math.max(0, 5 - (p.stars ?? 0)))}</span>
          </span>
        </div>
      </div>

      {/* season totals strip */}
      <div className="sq-headline">
        <div><b>{p.weekly_apps ?? 0}</b><span>apps (md)</span></div>
        <div><b>{p.weekly_goals ?? 0}</b><span>goals</span></div>
        <div><b>{p.weekly_assists ?? 0}</b><span>assists</span></div>
        <div><b>{p.weekly_rating != null ? Number(p.weekly_rating).toFixed(1) : '—'}</b><span>avg rating</span></div>
        <div><b>{money(p.game_price_usdc)}</b><span>value USDC</span></div>
      </div>

      {/* underline tab strip — text only, thin active underline */}
      <div className="sq-tabs" role="tablist">
        {TABS.map((t) => (
          <button
            key={t.id}
            role="tab"
            aria-selected={tab === t.id}
            className={tab === t.id ? 'on' : ''}
            onClick={() => setTab(t.id)}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === 'overview' && (
        <div className="sq-tab-body sq-ov">
          <section className="sq-prof-col">
            {FAMILIES.map((f) => (
              <div key={f.label}>
                <h4>{f.label}</h4>
                {f.keys.map(({ key, label }) => (
                  <AttrRow key={key} label={label} value={attr(key)} vs={pct(attr(key), peers.map((q) => q.attributes?.[key] ?? 0))} />
                ))}
              </div>
            ))}
            {p.slot === 'GK' && (
              <div>
                <h4>Goalkeeping</h4>
                <AttrRow label="Handling" value={attr('gk')} vs={pct(attr('gk'), peers.map((q) => q.attributes?.gk ?? 0))} />
              </div>
            )}
          </section>

          <section className="sq-prof-col">
            <h4>Percentile rank <em>vs {peers.length} same-position squad players</em></h4>
            <div className="sq-radar">
              <svg viewBox="0 0 120 120" role="img" aria-label="Attribute radar vs squad">
                {radar.rings.map((ring, i) => (
                  <polygon key={i} points={ring} className="sq-radar-ring" />
                ))}
                <polygon points={radar.cohort} className="sq-radar-cohort" />
                <polygon points={radar.me} className="sq-radar-me" />
                {radar.axes.map((a) => (
                  <g key={a.k}>
                    <line x1="60" y1="60" x2={a.x} y2={a.y} className="sq-radar-axis" />
                    <text x={a.lx} y={a.ly} className="sq-radar-label">
                      {RADAR_LABEL[a.k]}
                    </text>
                  </g>
                ))}
              </svg>
              <div className="sq-radar-key">
                <span><i className="me" /> {p.name}</span>
                <span><i className="cohort" /> position average</span>
              </div>
            </div>
            <ConditionRows p={p} />
          </section>

          <section className="sq-prof-col">
            <h4>Role suitability ({p.slot})</h4>
            <div className="sq-role-list">
              {p.roles.map((r) => (
                <div key={r.name} className="sq-role">
                  <span className="sq-role-name">{r.name}</span>
                  <span className="sq-role-stars" title={`${r.score} suitability`}>
                    <span className={r.stars >= 4 ? 'hi' : r.stars >= 3 ? 'mid' : ''}>{'★'.repeat(r.stars)}</span>
                    <span className="dim">{'☆'.repeat(Math.max(0, 5 - r.stars))}</span>
                  </span>
                </div>
              ))}
              {p.roles.length === 0 && <p className="sq-empty">No roles mapped for this position yet.</p>}
            </div>
            <p className="sq-note">
              Attributes and percentiles come from the same deterministic numbers the engine plays
              with — no hidden ratings, no scout fiction.
            </p>
          </section>
        </div>
      )}

      {tab === 'contract' && <ContractTab p={p} />}

      {tab === 'development' && <DevelopmentTab p={p} />}

      {tab === 'stats' && <StatsTab p={p} />}
    </div>
  )
}

const RADAR_LABEL: Record<string, string> = {
  technical: 'TEC',
  shooting: 'FIN',
  passing: 'PAS',
  tackling: 'TKL',
  decision_making: 'DEC',
  positioning: 'POS',
  pace: 'PAC',
  physicality: 'STR',
  gk: 'GK',
}

function AttrRow({ label, value, vs }: { label: string; value: number; vs: number }) {
  return (
    <div className="sq-attr">
      <span className="sq-attr-name">{label}</span>
      <span className={`sq-attr-bar ${barClass(value)}`}>
        <span style={{ width: `${Math.min(100, value)}%` }} />
      </span>
      <span className="sq-attr-val">{value}</span>
      <span className="sq-attr-pct" title={`top ${100 - vs}% of squad at this position`}>
        {vs}th
      </span>
    </div>
  )
}

function ConditionRows({ p }: { p: SquadPlayer }) {
  const rows: { label: string; v: number; good: number; mid: number; suffix?: string }[] = [
    { label: 'Condition', v: Math.round((p.fitness ?? 0) * 100), good: 90, mid: 70, suffix: '%' },
    { label: 'Morale', v: Math.round((p.morale ?? 0) * 100), good: 80, mid: 60, suffix: '%' },
  ]
  return (
    <div className="sq-cond">
      {rows.map((r) => (
        <div key={r.label}>
          <span>{r.label}</span>
          <span className={`sq-bar ${barClass(r.v, r.good, r.mid)}`}>
            <span style={{ width: `${Math.min(100, r.v)}%` }} />
          </span>
          <b>{r.v}{r.suffix}</b>
        </div>
      ))}
    </div>
  )
}

function ContractTab({ p }: { p: SquadPlayer }) {
  const c = p.contract
  const years = c?.years_left ?? 0
  const total = Math.max(years, 1)
  return (
    <div className="sq-tab-body">
      <div className="sq-key3">
        <div>
          <b>{money(p.wage_per_matchday_usdc)}</b>
          <span>USDC / matchday wage</span>
        </div>
        <div>
          <b>{years}y</b>
          <span>contract left</span>
        </div>
        <div>
          <b>{money(p.game_price_usdc)}</b>
          <span>market value USDC</span>
        </div>
      </div>

      <h4>Time at the club</h4>
      <div className="sq-timeline">
        {Array.from({ length: total }, (_, i) => (
          <div key={i} className={i === 0 ? 'seg now' : 'seg'}>
            <span className="fill" style={{ height: `${Math.max(18, 100 - i * 22)}%` }} />
            <em>{i === 0 ? 'now' : `+${i}y`}</em>
          </div>
        ))}
      </div>

      <div className="sq-contract">
        <div><span>Wage</span><b>{money(p.wage_per_matchday_usdc)} USDC / md</b></div>
        <div><span>Value</span><b>{money(p.game_price_usdc)} USDC</b></div>
        <div><span>Contract</span><b>{years}y left</b></div>
        <div><span>Wage runway</span><b>{c?.runway_matchdays ?? 0} matchdays</b></div>
      </div>
    </div>
  )
}

function DevelopmentTab({ p }: { p: SquadPlayer }) {
  const form = p.form ?? 0
  const rating = p.weekly_rating != null ? Number(p.weekly_rating) : null
  const trend = rating == null ? null : rating - (p.base_rating ?? 0) / 10
  const trendText =
    trend == null
      ? 'no rated matchday yet — form settles after the first outing'
      : trend > 0.5
        ? 'playing above his attribute base — hot streak'
        : trend < -0.5
          ? 'playing below his attribute base — needs a run of games'
          : 'performing right at his attribute level'
  return (
    <div className="sq-tab-body">
      <div className="sq-key3">
        <div>
          <b>{p.form?.toFixed(1) ?? '—'}</b>
          <span>form (running)</span>
        </div>
        <div>
          <b>{rating != null ? rating.toFixed(1) : '—'}</b>
          <span>last matchday rating</span>
        </div>
        <div>
          <b>{Math.round((p.fitness ?? 0) * 100)}%</b>
          <span>condition</span>
        </div>
      </div>
      <p className="sq-dev-note">{trendText}</p>
      <ConditionRows p={p} />
      <p className="sq-note">
        The engine tracks running form and condition per matchday; season-over-season development
        history isn&apos;t recorded yet, so there&apos;s no projection fan here — we don&apos;t
        invent one.
      </p>
    </div>
  )
}

function StatsTab({ p }: { p: SquadPlayer }) {
  const meters: { label: string; v: number; max: number; note?: string }[] = [
    { label: 'Minutes (apps)', v: p.weekly_apps ?? 0, max: 1 },
    { label: 'Goals', v: p.weekly_goals ?? 0, max: 3 },
    { label: 'Assists', v: p.weekly_assists ?? 0, max: 2 },
  ]
  return (
    <div className="sq-tab-body">
      <div className="sq-key3">
        <div><b>{p.weekly_apps ?? 0}</b><span>apps</span></div>
        <div><b>{p.weekly_goals ?? 0}</b><span>goals</span></div>
        <div><b>{p.weekly_assists ?? 0}</b><span>assists</span></div>
      </div>
      <h4>Recent matchday</h4>
      <div className="sq-stat-meters">
        {meters.map((m) => (
          <div key={m.label} className="sq-stat-meter">
            <span className="sq-attr-name">{m.label}</span>
            <span className={`sq-attr-bar ${barClass((m.v / m.max) * 100, 66, 33)}`}>
              <span style={{ width: `${Math.min(100, (m.v / m.max) * 100)}%` }} />
            </span>
            <span className="sq-attr-val">{m.v}</span>
          </div>
        ))}
        <div className="sq-stat-meter">
          <span className="sq-attr-name">Avg rating</span>
          <span className={`sq-attr-bar ${barClass(((p.weekly_rating ?? 0) / 10) * 100, 75, 55)}`}>
            <span style={{ width: `${Math.min(100, ((p.weekly_rating ?? 0) / 10) * 100)}%` }} />
          </span>
          <span className="sq-attr-val">{p.weekly_rating != null ? Number(p.weekly_rating).toFixed(1) : '—'}</span>
        </div>
      </div>
      <p className="sq-note">
        Totals are per recent matchday — the engine reports per-match stats; cumulative season
        aggregates land with the season-report work.
      </p>
    </div>
  )
}
