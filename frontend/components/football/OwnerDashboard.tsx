'use client'

/**
 * The owner dashboard — a football-manager game screen for your club.
 *
 * FM-shell layout: a club header bar (kit crest, identity, record strip),
 * a left section nav (Overview / Results / Squad / Finances / League), and
 * a panel grid that changes with the selected section. Every number is the
 * backend's read model — no invented data.
 */

import { useCallback, useEffect, useState } from 'react'
import Link from 'next/link'
import {
  fetchOwnerDashboard,
  listMarketAgents,
  TEAM_PRESETS,
  type MarketAgent,
  type OwnerDashboard as Dash,
} from '@/lib/afm'

/** Demo owner identity until real human auth lands (mirrors the backend default). */
const OWNER_ID = 'demo_owner'

type Section = 'overview' | 'results' | 'squad' | 'finances' | 'league'

const SECTIONS: Array<{ id: Section; label: string; icon: string }> = [
  { id: 'overview', label: 'Overview', icon: '▦' },
  { id: 'results', label: 'Results', icon: '▶' },
  { id: 'squad', label: 'Squad', icon: '👥' },
  { id: 'finances', label: 'Finances', icon: '$' },
  { id: 'league', label: 'League', icon: '🏆' },
]

function ratingColor(rating: number): string {
  if (rating >= 80) return 'var(--bm-green-bright, #34d399)'
  if (rating >= 70) return 'rgba(255,255,255,0.85)'
  if (rating >= 60) return 'var(--bm-amber, #fbbf24)'
  return 'var(--bm-red, #f87171)'
}

/** Team kit colors for a club (owner-created clubs get the Boardman default). */
function kitFor(agentId: string) {
  const key = agentId.includes('bluelock')
    ? 'bluelock'
    : agentId.includes('aoashi')
      ? 'aoashi'
      : agentId.includes('matchslice')
        ? 'matchslice'
        : agentId.includes('pike')
          ? 'pike'
          : 'boardman'
  return TEAM_PRESETS[key]
}

function fmtMoney(usdc: string | number | undefined): string {
  const n = Number(usdc ?? 0)
  if (!Number.isFinite(n)) return String(usdc ?? '0')
  return n.toLocaleString(undefined, { maximumFractionDigits: 2 })
}

function fmtClock(iso: string) {
  try {
    return new Date(iso).toLocaleString(undefined, {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    })
  } catch {
    return iso
  }
}

function rankLabel(rank: number | null | undefined): string {
  if (!rank) return '—'
  const s = ['th', 'st', 'nd', 'rd']
  const v = rank % 100
  return `${rank}${s[(v - 20) % 10] || s[v] || s[0]}`
}

function Crest({ agentId, name, size = 52 }: { agentId: string; name: string | null; size?: number }) {
  const kit = kitFor(agentId)
  return (
    <span
      className="od-crest"
      style={{
        width: size,
        height: size,
        background: `linear-gradient(135deg, ${kit.kit}, ${kit.kitDark})`,
        fontSize: size * 0.33,
      }}
      aria-hidden
    >
      {(name ?? '?').slice(0, 2).toUpperCase()}
    </span>
  )
}

/** The last-5 form string as W/D/L dots — same language as the manager card. */
function FormDots({ form }: { form: string }) {
  if (!form) return <span className="od-form-empty">—</span>
  return (
    <span className="od-form">
      {form
        .split('')
        .slice(-5)
        .map((c, i) => (
          <i key={i} className={`od-form-dot ${c.toLowerCase()}`}>
            {c}
          </i>
        ))}
    </span>
  )
}

/** Shared crest chip for standings rows (kit-colored dot). */
function KitDot({ agentId }: { agentId: string }) {
  const kit = kitFor(agentId)
  return <span className="od-t-dot" style={{ background: kit.kit }} aria-hidden />
}

/** Per-result FM report: team xG bar, why-line, + expandable rating list. */
function ResultReport({ report }: { report: NonNullable<Dash['results'][number]['report']> }) {
  const [open, setOpen] = useState(false)
  const total = Math.max(report.my_xg + report.their_xg, 0.01)
  const oursPct = Math.round((report.my_xg / total) * 100)
  const players = report.players.filter((p) => p.played)
  if (!players.length && !report.why) return null
  return (
    <div className="od-report">
      <button type="button" className="od-report-toggle" onClick={() => setOpen((v) => !v)}>
        <span className="od-xgbar" title={`xG ${report.my_xg.toFixed(2)} – ${report.their_xg.toFixed(2)}`}>
          <span style={{ width: `${oursPct}%` }} />
        </span>
        <span className="od-xg-label">xG {report.my_xg.toFixed(2)} – {report.their_xg.toFixed(2)}</span>
        {report.why ? <span className="od-why">{report.why}</span> : null}
        <em className={`od-caret${open ? ' up' : ''}`}>▾</em>
      </button>
      {open && (
        <ul className="od-ratings">
          {players.map((p) => (
            <li key={p.player_id} className="od-rating-row">
              <span className="od-rating-num" style={{ color: ratingColor(p.rating ?? 0) }}>
                {p.rating ?? '—'}
              </span>
              <span className="od-rating-name">
                {p.name}
                <em>{p.position}</em>
                {p.goals > 0 ? <b className="od-gol">⚽{p.goals}</b> : null}
                {p.cards > 0 ? <b className="od-card">🟨</b> : null}
                {p.errors.length > 0 ? <b className="od-err">· {p.errors[0]?.note}</b> : null}
              </span>
              <span className="od-rating-stats">
                {p.xG > 0 ? `${p.xG.toFixed(2)} xG · ` : ''}{p.shots} sh · {p.tackles + p.interceptions} def
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

/** Panel wrapper — FM's inset card with the uppercase header strip. */
function Panel({
  title,
  sub,
  span,
  children,
}: {
  title: string
  sub?: string
  span?: boolean
  children: React.ReactNode
}) {
  return (
    <div className={`od-card${span ? ' od-span2' : ''}`}>
      <h4>
        {title}
        {sub ? <span className="od-h4-sub">{sub}</span> : null}
      </h4>
      <div className="od-card-body">{children}</div>
    </div>
  )
}

/* ------------------------------------------------------------------ */
/* Overview section — results snapshot, next fixture, squad + money   */
/* ------------------------------------------------------------------ */
function OverviewSection({ dash, agentId }: { dash: Dash; agentId: string }) {
  const next = dash.upcoming[0]
  return (
    <>
      <Panel title="Latest results" sub={`${dash.results.length} played`}>
        {dash.results.length === 0 ? (
          <p className="od-empty">
            No matchdays played yet — when a fixture resolves, the score and the plan the agent
            locked for it appear here.
          </p>
        ) : (
          <ul className="od-results">
            {dash.results.slice(0, 4).map((r) => {
              const home = r.venue === 'home' ? agentId : r.opponent_id
              const away = r.venue === 'home' ? r.opponent_id : agentId
              return (
                <li key={r.match_id} className={`od-result ${r.outcome === 'W' ? 'won' : r.outcome === 'D' ? 'drew' : 'lost'}`}>
                  <div className="od-result-line">
                    <span className="od-md">MD {r.matchday}</span>
                    <span className="od-opp">
                      <em>{r.venue === 'home' ? 'vs' : 'at'}</em>
                      {r.opponent_club}
                    </span>
                    <Link
                      className="od-score"
                      href={`/football/tactics?replay=1&md=${r.matchday}&home=${home}&away=${away}`}
                      title="Watch the recorded replay"
                    >
                      {r.our_goals}–{r.their_goals}
                    </Link>
                    <span className={`od-wdl ${r.outcome}`}>{r.outcome}</span>
                  </div>
                </li>
              )
            })}
          </ul>
        )}
      </Panel>

      <Panel title="Squad status" sub={`${dash.squad_status.available}/${dash.squad_status.total} fit`}>
        <div className="od-avail">
          <span className="od-avail-chip ok"><b>{dash.squad_status.available}</b> fit</span>
          <span className="od-avail-chip"><b>{dash.squad_status.starters}</b> starting</span>
          <span className="od-avail-chip warn"><b>{dash.squad_status.injured}</b> injured</span>
          <span className="od-avail-chip warn"><b>{dash.squad_status.suspended}</b> suspended</span>
          {dash.squad_status.banned_next > 0 && (
            <span className="od-avail-chip warn"><b>{dash.squad_status.banned_next}</b> banned next</span>
          )}
        </div>
        {dash.news.length === 0 ? (
          <p className="od-empty">No injuries or suspensions — a clean bill of health.</p>
        ) : (
          <ul className="od-news">
            {dash.news.slice(0, 4).map((n) => (
              <li key={`${n.type}-${n.player_id}`} className={`od-news-item ${n.type}`}>
                <span className="od-news-name">
                  {n.type === 'suspension' ? '🟥' : '⚠'} {n.name}
                  <em>{n.position}</em>
                </span>
                <span className="od-news-detail">{n.detail}</span>
              </li>
            ))}
          </ul>
        )}
        <p className="od-card-links">
          <Link href={`/football/squad/${encodeURIComponent(agentId)}`}>Squad room (FM) →</Link>
        </p>
      </Panel>

      {next ? (
        <Panel title="Next fixture" sub={next.status === 'open' ? 'lineups open' : next.status} span>
          <div className="od-next">
            <b>MD {next.matchday}</b>
            <span>
              {next.venue === 'home' ? 'vs' : 'at'} <b>{next.opponent_club}</b>
            </span>
            <span className="od-h4-sub">
              lineups lock {next.deadline_at ? fmtClock(next.deadline_at) : 'soon'}
            </span>
          </div>
        </Panel>
      ) : null}

      <Panel title="Money" sub="budget & wallet">
        <ul className="od-fin">
          <li>
            <span>Agent cash (wallet)</span>
            <b>${fmtMoney(dash.finances.wallet_balance_usdc)}</b>
          </li>
          <li>
            <span>Budget remaining</span>
            <b>${fmtMoney(dash.finances.remaining_usdc)}</b>
          </li>
          {dash.finances.wage_debt_usdc && Number(dash.finances.wage_debt_usdc) > 0 ? (
            <li className="neg">
              <span>Wage debt</span>
              <b>${fmtMoney(dash.finances.wage_debt_usdc)}</b>
            </li>
          ) : null}
        </ul>
      </Panel>
    </>
  )
}

/* ------------------------------------------------------------------ */
/* Results section — full match list with decisions + FM reports      */
/* ------------------------------------------------------------------ */
function ResultsSection({ dash, agentId }: { dash: Dash; agentId: string }) {
  return (
    <>
      <Panel title="Results &amp; the agent's decisions" sub={`${dash.results.length} played`} span>
        {dash.results.length === 0 ? (
          <p className="od-empty">
            No matchdays played yet — when a fixture resolves, the score and the plan the agent
            locked for it (formation, tactics, XI) appear here.
          </p>
        ) : (
          <ul className="od-results">
            {dash.results.map((r) => {
              const home = r.venue === 'home' ? agentId : r.opponent_id
              const away = r.venue === 'home' ? r.opponent_id : agentId
              const banned = r.decision.banned
              return (
                <li key={r.match_id} className={`od-result ${r.outcome === 'W' ? 'won' : r.outcome === 'D' ? 'drew' : 'lost'}`}>
                  <div className="od-result-line">
                    <span className="od-md">MD {r.matchday}</span>
                    <span className="od-opp">
                      <em>{r.venue === 'home' ? 'vs' : 'at'}</em>
                      {r.opponent_club}
                    </span>
                    <Link
                      className="od-score"
                      href={`/football/tactics?replay=1&md=${r.matchday}&home=${home}&away=${away}`}
                      title="Watch the recorded replay"
                    >
                      {r.our_goals}–{r.their_goals}
                    </Link>
                    <span className={`od-wdl ${r.outcome}`}>{r.outcome}</span>
                  </div>
                  <div className="od-dec">
                    locked <b>{r.decision.formation}</b> · {r.decision.tags.join(', ')} · XI{' '}
                    {r.decision.xi.length}
                    {r.decision.source === 'webhook' ? (
                      <span className="od-wh">🟢 webhook</span>
                    ) : r.decision.source === 'auto' ? (
                      <span className="od-wh dim">playbook (auto)</span>
                    ) : null}
                    {r.decision.note ? <span className="od-note"> · {r.decision.note}</span> : null}
                    {r.decision.error ? ` · decision failed (${r.decision.error})` : ''}
                    {!r.decision.error && r.decision.auto && banned.length === 0
                      ? ' · auto lineup — no decision recorded'
                      : ''}
                    {banned.length > 0 ? (
                      <span className="od-banned">
                        {' '}
                        · 🟥 {banned.join(', ')} sent off — auto-refilled from bench
                      </span>
                    ) : null}
                    {r.played_at ? <span className="od-played">{fmtClock(r.played_at)}</span> : null}
                    {r.decision.instructions ? (
                      <span className="od-inst">“{r.decision.instructions}”</span>
                    ) : null}
                  </div>
                  {r.report && Object.keys(r.report).length > 0 ? <ResultReport report={r.report} /> : null}
                </li>
              )
            })}
          </ul>
        )}

        {dash.upcoming.length > 0 && (
          <div className="od-upcoming">
            <div className="od-next" style={{ marginTop: 0 }}>
              <b>MD {dash.upcoming[0].matchday}</b>
              <span>
                {dash.upcoming[0].venue === 'home' ? 'vs' : 'at'} <b>{dash.upcoming[0].opponent_club}</b>
              </span>
              <span className="od-h4-sub">
                lineups lock {dash.upcoming[0].deadline_at ? fmtClock(dash.upcoming[0].deadline_at) : 'soon'}
              </span>
            </div>
            {dash.upcoming.slice(1).map((u) => (
              <span className="od-up" key={`${u.matchday}-${u.opponent_id}`}>
                MD {u.matchday}: {u.venue === 'home' ? 'vs' : 'at'} {u.opponent_club}
              </span>
            ))}
          </div>
        )}
      </Panel>
    </>
  )
}

/* ------------------------------------------------------------------ */
/* Squad section — availability + every news item                     */
/* ------------------------------------------------------------------ */
function SquadSection({ dash, agentId }: { dash: Dash; agentId: string }) {
  return (
    <>
      <Panel title="Squad availability" sub={`${dash.squad_status.available}/${dash.squad_status.total} fit`} span>
        <div className="od-avail">
          <span className="od-avail-chip ok"><b>{dash.squad_status.available}</b> fit</span>
          <span className="od-avail-chip"><b>{dash.squad_status.starters}</b> starting</span>
          <span className="od-avail-chip"><b>{dash.squad_status.total}</b> in squad</span>
          <span className="od-avail-chip warn"><b>{dash.squad_status.injured}</b> injured</span>
          <span className="od-avail-chip warn"><b>{dash.squad_status.suspended}</b> suspended</span>
          {dash.squad_status.banned_next > 0 && (
            <span className="od-avail-chip warn"><b>{dash.squad_status.banned_next}</b> banned next md</span>
          )}
        </div>
        {dash.news.length === 0 ? (
          <p className="od-empty">No injuries or suspensions — a clean bill of health.</p>
        ) : (
          <ul className="od-news">
            {dash.news.map((n) => (
              <li key={`${n.type}-${n.player_id}`} className={`od-news-item ${n.type}`}>
                <span className="od-news-name">
                  {n.type === 'suspension' ? '🟥' : '⚠'} {n.name}
                  <em>{n.position}</em>
                </span>
                <span className="od-news-detail">{n.detail}</span>
              </li>
            ))}
          </ul>
        )}
        <p className="od-card-links">
          <Link href={`/football/squad/${encodeURIComponent(agentId)}`}>Full squad room (FM) →</Link>
          {' · '}
          <Link href="/football/tactics">Match board →</Link>
        </p>
      </Panel>
    </>
  )
}

/* ------------------------------------------------------------------ */
/* Finances section — kv money rows, budget bar, full spending log    */
/* ------------------------------------------------------------------ */
function FinancesSection({ dash }: { dash: Dash }) {
  const budget = Number(dash.finances.budget_usdc ?? 0)
  const spend = Number(dash.finances.spend_usdc ?? 0)
  const spentPct = budget > 0 ? Math.min(100, Math.round((spend / budget) * 100)) : 0
  const fillClass = spentPct >= 100 ? 'empty' : spentPct >= 80 ? 'hot' : ''
  return (
    <>
      <Panel title="Money" sub="budget & wallet">
        <ul className="od-fin">
          <li>
            <span>Club budget</span>
            <b>${fmtMoney(dash.finances.budget_usdc)}</b>
          </li>
          <li>
            <span>Squad build spent</span>
            <b>${fmtMoney(dash.finances.spend_usdc)}</b>
          </li>
          <li>
            <span>Budget remaining</span>
            <b>${fmtMoney(dash.finances.remaining_usdc)}</b>
          </li>
          <li>
            <span>Agent cash (wallet)</span>
            <b>${fmtMoney(dash.finances.wallet_balance_usdc)}</b>
          </li>
          <li className={Number(dash.finances.wage_debt_usdc ?? 0) > 0 ? 'neg' : ''}>
            <span>Wage debt</span>
            <b>${fmtMoney(dash.finances.wage_debt_usdc ?? 0)}</b>
          </li>
          <li className={Number(dash.finances.stake_debt_usdc ?? 0) > 0 ? 'neg' : ''}>
            <span>Stake debt</span>
            <b>${fmtMoney(dash.finances.stake_debt_usdc ?? 0)}</b>
          </li>
        </ul>
        <div className="od-budget">
          <div className="od-budget-top">
            <span>budget used</span>
            <span>
              ${fmtMoney(dash.finances.spend_usdc)} / ${fmtMoney(dash.finances.budget_usdc)} ({spentPct}%)
            </span>
          </div>
          <div className="od-budget-bar">
            <div className={`od-budget-fill ${fillClass}`} style={{ width: `${spentPct}%` }} />
          </div>
        </div>
        <p className="od-sub" style={{ marginTop: 10 }}>
          Squad build comes out of the club budget; entry, wages and matchday stakes move in the
          agent's wallet ledger.
        </p>
      </Panel>

      <Panel title="Spending log" sub="newest first">
        {dash.spending.length === 0 ? (
          <p className="od-empty">No spending yet.</p>
        ) : (
          <ul className="od-spend">
            {dash.spending.map((s, i) => (
              <li key={`${s.kind}-${s.label}-${i}`} className="od-spend-row">
                <span className="od-spend-label">
                  {s.label}
                  {s.detail ? <em> {s.detail}</em> : null}
                </span>
                {s.ts ? <span className="od-spend-ts">{fmtClock(s.ts)}</span> : null}
                <span className={`od-spend-amt ${s.amount.startsWith('-') ? 'out' : 'in'}`}>
                  {s.amount.startsWith('-') ? '−$' : '+$'}
                  {fmtMoney(Math.abs(Number(s.amount)))}
                </span>
              </li>
            ))}
          </ul>
        )}
      </Panel>
    </>
  )
}

/* ------------------------------------------------------------------ */
/* League section — the mini table with zone bars + kit dots          */
/* ------------------------------------------------------------------ */
function LeagueSection({ dash, agentId }: { dash: Dash; agentId: string }) {
  const { table } = dash
  const row = table.row
  const n = table.standings.length
  const zoneOf = (rank: number): 'top' | 'mid' | 'bottom' => {
    if (n >= 4 && rank === 1) return 'top'
    if (n >= 4 && rank >= n - 1) return 'bottom'
    return 'mid'
  }
  return (
    <Panel
      title="League table"
      sub={table.in_season && row ? `${rankLabel(row.rank)} of ${table.of} · ${row.points} pts` : 'not in a season'}
      span
    >
      {!table.in_season || table.standings.length === 0 ? (
        <p className="od-empty">The club isn't in a running season — no table yet. It joins the league at the next season open.</p>
      ) : (
        <>
          <ul className="od-table">
            {table.standings.map((s) => (
              <li
                key={s.agent_id}
                className={`od-table-row${s.agent_id === agentId ? ' me' : ''}${Math.abs((row?.rank ?? 1) - s.rank) <= 1 ? '' : ' dim'}`}
              >
                <span className="od-t-rank">{s.rank}</span>
                <span className={`od-t-zone ${zoneOf(s.rank)}`} title={zoneOf(s.rank) === 'top' ? 'contention' : zoneOf(s.rank) === 'bottom' ? 'bottom two' : 'mid-table'} />
                <span className="od-t-club">
                  <KitDot agentId={s.agent_id} />
                  {s.club_name}
                </span>
                <span className="od-t-gd">
                  {s.goal_diff > 0 ? `+${s.goal_diff}` : s.goal_diff}
                </span>
                <span className="od-t-pts">{s.points}</span>
              </li>
            ))}
          </ul>
          <div className="od-legend">
            <span><i className="od-t-zone top" style={{ display: 'inline-block' }} /> contention</span>
            <span><i className="od-t-zone mid" style={{ display: 'inline-block' }} /> mid-table</span>
            <span><i className="od-t-zone bottom" style={{ display: 'inline-block' }} /> bottom two</span>
          </div>
          <p className="od-sub" style={{ marginTop: 8 }}>
            3/1/0 points · full league on the{' '}
            <Link href="/football/league" style={{ color: 'var(--bm-green-bright, #34d399)' }}>
              standings page
            </Link>
          </p>
        </>
      )}
    </Panel>
  )
}

/** One club's dashboard — fetch the read model and lay it out in the FM shell. */
function OwnerDashboard({ agentId, refreshKey }: { agentId: string; refreshKey: number }) {
  const [dash, setDash] = useState<Dash | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [section, setSection] = useState<Section>('overview')
  const [stamp, setStamp] = useState(0)

  useEffect(() => {
    let alive = true
    setDash(null)
    fetchOwnerDashboard(agentId)
      .then((d) => {
        if (alive) {
          setDash(d)
          setError(null)
        }
      })
      .catch((e: unknown) => {
        if (alive) setError(e instanceof Error ? e.message : String(e))
      })
    // light poll so newly resolved matchdays land on the dashboard
    const t = window.setInterval(() => setStamp((s) => s + 1), 20000)
    return () => {
      alive = false
      window.clearInterval(t)
    }
  }, [agentId, refreshKey, stamp])

  if (error) {
    return <div className="fd-err">{error}</div>
  }
  if (!dash) {
    return (
      <p style={{ color: 'rgba(255,255,255,0.5)', fontSize: 14 }}>
        Loading {agentId}'s dashboard…
      </p>
    )
  }

  const { club, manager, table, season } = dash
  const row = table.row
  const inSeason = table.in_season
  const debt = Number(dash.finances.wage_debt_usdc ?? 0) + Number(dash.finances.stake_debt_usdc ?? 0)
  const newsCount = dash.news.length

  return (
    <div className="od-dash">
      {/* club header bar */}
      <div className="od-header">
        <div className="od-identity">
          <Crest agentId={agentId} name={club.club_name} />
          <div>
            <h3 className="od-clubname">{club.club_name}</h3>
            <p className="od-manager">
              run by <b>{manager.name}</b>
              <span className="fd-chip">{manager.archetype_name}</span>
            </p>
            <p className="od-meta">
              {club.formation} · {(club.tactical_tags ?? []).join(', ') || 'balanced'} ·{' '}
              {club.roster_size} players
            </p>
          </div>
        </div>
        <div className="od-stats">
          {inSeason && row ? (
            <>
              <div className="od-stat">
                <b>{rankLabel(row.rank)}</b>
                <span>position</span>
              </div>
              <div className="od-stat">
                <b>
                  {row.wins}
                  <em>W</em>·{row.draws}
                  <em>D</em>·{row.losses}
                  <em>L</em>
                </b>
                <span>{row.points} pts</span>
              </div>
              <div className="od-stat">
                <FormDots form={dash.form} />
                <span>form</span>
              </div>
            </>
          ) : (
            <div className="od-stat">
              <b>—</b>
              <span>not in a season</span>
            </div>
          )}
          <div className="od-stat">
            <b>${fmtMoney(dash.finances.remaining_usdc)}</b>
            <span>budget left</span>
          </div>
        </div>
      </div>

      {season && (
        <p className="od-season">
          Season {season.season_no} · {season.status === 'finished' ? 'finished' : `MD ${Math.min(season.current_matchday, season.matchdays_total)}/${season.matchdays_total}`}
          {season.champion ? ` · 🏆 ${season.champion}` : ''}
          {debt > 0 ? ` · ⚠ ${fmtMoney(debt)} USDC debt accrued` : ''}
        </p>
      )}

      {/* FM shell: section nav + panel grid */}
      <div className="od-shell">
        <nav className="od-nav" aria-label="Dashboard sections">
          {SECTIONS.map((s) => (
            <button
              key={s.id}
              type="button"
              className={`od-nav-item${section === s.id ? ' on' : ''}`}
              onClick={() => setSection(s.id)}
            >
              <span aria-hidden>{s.icon}</span>
              {s.label}
              {s.id === 'squad' && newsCount > 0 ? <span className="od-nav-badge">{newsCount}</span> : null}
            </button>
          ))}
        </nav>

        <div className="od-grid">
          {section === 'overview' && <OverviewSection dash={dash} agentId={agentId} />}
          {section === 'results' && <ResultsSection dash={dash} agentId={agentId} />}
          {section === 'squad' && <SquadSection dash={dash} agentId={agentId} />}
          {section === 'finances' && <FinancesSection dash={dash} />}
          {section === 'league' && <LeagueSection dash={dash} agentId={agentId} />}
        </div>
      </div>
    </div>
  )
}

/** Step 5 section: pick one of your clubs (created / adopted in step 1) and
 *  follow it in the FM-style dashboard. */
export function FollowYourClub({ refreshKey = 0 }: { refreshKey?: number }) {
  const [owned, setOwned] = useState<MarketAgent[] | null>(null)
  const [agentId, setAgentId] = useState<string | null>(null)
  const [dashKey, setDashKey] = useState(0)
  const [error, setError] = useState<string | null>(null)

  const loadOwned = useCallback(() => {
    listMarketAgents()
      .then((list) => {
        const mine = list.filter((a) => a.owner_id === OWNER_ID && a.has_club)
        setOwned(mine)
        setError(null)
        setAgentId((prev) => (prev && mine.some((m) => m.agent_id === prev) ? prev : mine[0]?.agent_id ?? null))
      })
      .catch((e: unknown) => {
        setOwned([])
        setError(e instanceof Error ? e.message : String(e))
      })
  }, [])

  useEffect(() => {
    loadOwned()
    // light poll: a club just created/adopted in step 1 (or adopted here) shows up
    const t = window.setInterval(loadOwned, 15000)
    return () => window.clearInterval(t)
  }, [loadOwned, refreshKey])

  if (error && !owned) {
    return (
      <div className="fd-err">
        Couldn't reach the marketplace — the backend may be offline in this environment. The
        dashboard appears once the agent services are running.
      </div>
    )
  }
  if (!owned) {
    return (
      <p style={{ color: 'rgba(255,255,255,0.5)', fontSize: 14 }}>Loading your clubs…</p>
    )
  }
  if (owned.length === 0) {
    return (
      <div className="fd-err">
        You don't own a club yet. <b>Create or acquire an agent in step 1 above</b> — the moment
        one is yours, its results, decisions, spending and squad news land here.
      </div>
    )
  }

  return (
    <div className="od-wrap">
      <div className="od-picker">
        <span className="od-picker-label">Your clubs</span>
        {owned.map((a) => (
          <button
            key={a.agent_id}
            type="button"
            className={`od-tab${a.agent_id === agentId ? ' on' : ''}`}
            onClick={() => setAgentId(a.agent_id)}
          >
            {a.club_name ?? a.name}
            <em>{a.archetype_name}</em>
          </button>
        ))}
        <button
          type="button"
          className="od-refresh"
          title="Refresh this dashboard"
          onClick={() => {
            setDashKey((k) => k + 1)
            loadOwned()
          }}
        >
          ↻ Refresh
        </button>
      </div>
      {agentId ? <OwnerDashboard agentId={agentId} refreshKey={dashKey} /> : null}
    </div>
  )
}
