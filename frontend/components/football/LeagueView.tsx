'use client'

import { useCallback, useEffect, useState } from 'react'
import Link from 'next/link'
import { TEAM_PRESETS } from '@/lib/afm'

type StandingRow = {
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

type Fixture = {
  matchday: number
  home_agent_id: string
  home_club: string
  away_agent_id: string
  away_club: string
  status: string
  open_at: string
  deadline_at: string
}

type Result = {
  matchday: number
  match_id: string
  home_agent_id: string
  away_agent_id: string
  home_goals: number
  away_goals: number
  outcome: string
  score: string
  match_stats?: Record<string, number>
}

function statLine(s?: Record<string, number>) {
  if (!s) return null
  const g = (k: string) => s[k] ?? 0
  return `Poss ${g('possession_home')}–${g('possession_away')} · Shots ${g('shots_home')}–${g('shots_away')} · On tgt ${g('shots_on_target_home')}–${g('shots_on_target_away')} · Corners ${g('corners_home')}–${g('corners_away')} · Fouls ${g('fouls_home')}–${g('fouls_away')} · YC ${g('yellow_cards_home')}–${g('yellow_cards_away')} · RC ${g('red_cards_home')}–${g('red_cards_away')}`
}

type Season = {
  season_no: number
  status: string
  division: { agent_id: string; name: string }[]
  matchdays_total: number
  current_matchday: number
  started_at: string | null
  champion: string | null
  finished_at: string | null
  entries: Record<string, { paid: boolean; entry_usdc: string }>
  entry_usdc: string
  stake_usdc: string
  pot_usdc: string
  standings: StandingRow[]
  upcoming: Fixture[]
  recent: Result[]
}

function presetFor(agentId: string) {
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

export default function LeagueView() {
  const [season, setSeason] = useState<Season | null>(null)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState<string | null>(null)

  const load = useCallback(async () => {
    try {
      const res = await fetch('/api/agentic/football/season')
      const data = await res.json()
      setSeason(data.season ?? null)
    } catch {
      setSeason(null)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  const tick = useCallback(async () => {
    setBusy(true)
    setMsg(null)
    try {
      const res = await fetch('/api/agentic/football/season/tick', { method: 'POST' })
      const data = await res.json()
      const opened = (data.opened ?? []).length
      const resolved = (data.resolved ?? []).length
      if (data.season_status === 'finished') setMsg(`🏆 Season complete — ${data.champion ?? 'champion'} crowned!`)
      else if (resolved > 0) setMsg(`Matchday${resolved > 1 ? 's' : ''} ${(data.resolved ?? []).join(', ')} played.`)
      else if (opened > 0) setMsg(`Matchday ${(data.opened ?? []).join(', ')} opened — lineups lock at deadline.`)
      else setMsg('Nothing due yet — the season clock runs daily.')
    } catch {
      setMsg('Tick failed — is the stack API up?')
    } finally {
      setBusy(false)
      load()
    }
  }, [load])

  if (loading) {
    return (
      <div className="league-shell">
        <div className="league-card league-empty">Loading season…</div>
      </div>
    )
  }

  if (!season) {
    return (
      <div className="league-shell">
        <div className="league-card league-empty">
          <p className="league-empty-title">No season running</p>
          <p>The demo league hasn't opened yet. It opens with the daily scheduler — or head to the tactics board and watch the friendly.</p>
          <Link className="league-btn" href="/football/tactics">
            Open tactics board
          </Link>
        </div>
      </div>
    )
  }

  const totalPoints = season.standings.reduce((s, r) => s + r.points, 0)
  const isFinished = season.status === 'finished'
  const championColor = season.champion ? presetFor(season.champion).kit : '#7c3aed'

  return (
    <div className="league-shell">
      {/* season header */}
      <div className="league-card league-season">
        <div className="league-season-head">
          <div>
            <h1>
              Season {season.season_no}
              {season.champion ? (
                <span className="league-champ" style={{ color: championColor }}>
                  {' '}
                  · 🏆 {presetFor(season.champion).name}
                </span>
              ) : null}
            </h1>
            <p className="league-sub">
              {season.division.map((d) => d.name).join(' vs ')} · double round-robin ·{' '}
              {season.matchdays_total} matchdays · 1 matchday/day
            </p>
          </div>
          <div className="league-status-row">
            <span className={`league-badge ${isFinished ? 'is-finished' : 'is-open'}`}>
              {isFinished ? 'FINISHED' : '● LIVE SEASON'}
            </span>
            <span className="league-badge league-badge-quiet">
              MD {Math.min(season.current_matchday, season.matchdays_total)}/{season.matchdays_total}
            </span>
            <span className="league-badge league-badge-quiet">pot ${season.pot_usdc}</span>
          </div>
        </div>
        <div className="league-season-meta">
          <span>entry ${season.entry_usdc} · stake ${season.stake_usdc}/matchday</span>
          <span>started {season.started_at ? fmtClock(season.started_at) : '—'}</span>
          <span>{isFinished && season.finished_at ? `finished ${fmtClock(season.finished_at)}` : 'next deadline in the fixtures below'}</span>
        </div>
      </div>

      <div className="league-grid">
        {/* standings */}
        <div className="league-card">
          <h2>Standings</h2>
          <table className="league-table">
            <thead>
              <tr>
                <th>#</th>
                <th className="lg-zone-col" aria-label="zone" />
                <th>Club</th>
                <th className="lg-num">P</th>
                <th className="lg-num">W</th>
                <th className="lg-num">D</th>
                <th className="lg-num">L</th>
                <th className="lg-num">GF</th>
                <th className="lg-num">GA</th>
                <th className="lg-num">GD</th>
                <th className="lg-num">Pts</th>
              </tr>
            </thead>
            <tbody>
              {season.standings.map((r) => {
                const kit = presetFor(r.agent_id).kit
                const n = season.standings.length
                const zone = r.rank === 1 ? 'top' : n >= 4 && r.rank >= n - 1 ? 'bottom' : 'mid'
                return (
                  <tr key={r.agent_id} className={r.agent_id === season.champion ? 'league-row-champ' : ''}>
                    <td className="league-rank">{r.rank}</td>
                    <td className="lg-zone-col">
                      <span className={`lg-zone ${zone}`} title={zone === 'top' ? 'title race' : zone === 'bottom' ? 'bottom two' : 'mid-table'} />
                    </td>
                    <td className="league-club">
                      <span className="league-dot" style={{ background: kit }} />
                      {r.club_name}
                      {r.agent_id === season.champion ? ' 🏆' : ''}
                    </td>
                    <td className="lg-num">{r.played}</td>
                    <td className="lg-num">{r.wins}</td>
                    <td className="lg-num">{r.draws}</td>
                    <td className="lg-num">{r.losses}</td>
                    <td className="lg-num">{r.goals_for}</td>
                    <td className="lg-num">{r.goals_against}</td>
                    <td className="lg-num">{r.goal_diff > 0 ? `+${r.goal_diff}` : r.goal_diff}</td>
                    <td className="league-pts">{r.points}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
          <div className="league-legend">
            <span><i className="lg-zone top" /> title race</span>
            <span><i className="lg-zone mid" /> mid-table</span>
            <span><i className="lg-zone bottom" /> bottom two</span>
          </div>
          <p className="league-note">3/1/0 points · {totalPoints} total points awarded so far</p>
        </div>

        {/* upcoming */}
        <div className="league-card">
          <h2>Fixtures</h2>
          {season.upcoming.length === 0 ? (
            <p className="league-note">Season complete — rematch next season.</p>
          ) : (
            <ul className="league-fixtures">
              {season.upcoming.map((f) => {
                const live = f.status === 'open'
                const played = f.status === 'played'
                return (
                  <li key={`${f.matchday}-${f.home_agent_id}`} className="league-fixture">
                    <div className="league-fixture-md">MD {f.matchday}</div>
                    <div className="league-fixture-body">
                      <div className="league-fixture-clubs">
                        <span>
                          <span className="league-dot" style={{ background: presetFor(f.home_agent_id).kit }} /> {f.home_club}
                        </span>
                        <span className="league-vs">vs</span>
                        <span>
                          <span className="league-dot" style={{ background: presetFor(f.away_agent_id).kit }} /> {f.away_club}
                        </span>
                      </div>
                      <div className="league-fixture-meta">
                        {live ? (
                          <span className="league-badge is-open">lineup locks {fmtClock(f.deadline_at)}</span>
                        ) : played ? (
                          <span className="league-badge league-badge-quiet">played</span>
                        ) : (
                          <span className="league-badge league-badge-quiet">opens {fmtClock(f.open_at)}</span>
                        )}
                      </div>
                    </div>
                  </li>
                )
              })}
            </ul>
          )}
          {!isFinished && (
            <button className="league-btn" onClick={tick} disabled={busy}>
              {busy ? 'Advancing…' : '▶ Run due matchdays'}
            </button>
          )}
          {msg ? <p className="league-msg">{msg}</p> : null}
        </div>
      </div>

      {/* recent results */}
      {season.recent.length > 0 ? (
        <div className="league-card">
          <h2>Recent results</h2>
          <div className="league-results">
            {season.recent.map((r) => (
              <div key={r.match_id} className="league-result">
                <div className="league-result-top">
                  <span className="league-result-md">MD {r.matchday}</span>
                  <span>
                    {r.home_agent_id && presetFor(r.home_agent_id).name}
                  </span>
                  <span className="league-result-score">
                    {r.home_goals}–{r.away_goals}
                  </span>
                  <span>{r.away_agent_id && presetFor(r.away_agent_id).name}</span>
                  <Link
                    className="league-watch"
                    href={`/football/tactics?replay=1&md=${r.matchday}&home=${r.home_agent_id}&away=${r.away_agent_id}`}
                    title="Watch the recorded replay"
                  >
                    ▶
                  </Link>
                </div>
                {statLine(r.match_stats) ? (
                  <div className="league-result-stats" title="Phase 0 match stats">
                    {statLine(r.match_stats)}
                  </div>
                ) : null}
              </div>
            ))}
          </div>
        </div>
      ) : null}

      <div className="league-actions">
        <Link
          className="league-btn"
          href={
            season.recent.length
              ? `/football/tactics?replay=1&md=${season.recent[0].matchday}&home=${season.recent[0].home_agent_id}&away=${season.recent[0].away_agent_id}`
              : '/football/tactics'
          }
        >
          Watch matches in 3D
        </Link>
        <button className="league-btn league-btn-quiet" onClick={load} disabled={loading}>
          Refresh
        </button>
      </div>
    </div>
  )
}