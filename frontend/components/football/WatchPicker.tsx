'use client'
/**
 * WatchPicker — the spectator seat's "what's on today".
 *
 * Reads the season snapshot's `upcoming` and `recent` arrays and renders two
 * lists: fixtures you can watch next (deep-linking into the pre-match board
 * when lineups are in, the broadcast for anything already played) and the
 * latest results with their stats line + one-click replay. Pure read model —
 * no sliders, no attribute numbers, football language only.
 */
import { useEffect, useState } from 'react'
import Link from 'next/link'
import {
  broadcastHref,
  prematchHref,
  type AfmSeason,
  type SeasonRecentResult,
} from '@/lib/afm'

/** The season payload's upcoming fixture shape (mirrors season._snapshot). */
interface UpcomingFixture {
  matchday: number
  home_agent_id: string
  home_club: string
  away_agent_id: string
  away_club: string
  status: string
  open_at: string
  deadline_at: string
}

/** Season payload extended with the arrays this picker needs. */
interface PickerSeason extends AfmSeason {
  standings?: { agent_id: string; club_name: string }[]
  upcoming?: UpcomingFixture[]
  recent?: SeasonRecentResult[]
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

function statLine(s?: Record<string, number>) {
  if (!s) return null
  const g = (k: string) => s[k] ?? 0
  return `Poss ${g('possession_home')}–${g('possession_away')} · Shots ${g('shots_home')}–${g('shots_away')} · Corners ${g('corners_home')}–${g('corners_away')}`
}

export default function WatchPicker() {
  const [season, setSeason] = useState<PickerSeason | null>(null)
  const [err, setErr] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    fetch('/api/agentic/football/season')
      .then((res) => (res.ok ? res.json() : Promise.reject(new Error(`season fetch failed (${res.status})`))))
      .then((data: { season?: PickerSeason | null }) => {
        if (cancelled) return
        if (!data?.season) throw new Error('no season running right now')
        setSeason(data.season)
      })
      .catch((e: Error) => {
        if (!cancelled) setErr(e.message)
      })
    return () => {
      cancelled = true
    }
  }, [])

  if (err) {
    return (
      <p className="wp-note" role="status">
        {err} — the league table still has everything:{' '}
        <Link href="/football/league">open the league →</Link>
      </p>
    )
  }
  if (!season) {
    return <p className="wp-note">Loading the matchday slate…</p>
  }

  const names = new Map((season.division ?? []).map((d) => [d.agent_id, d.name]))
  const upcoming = (season.upcoming ?? []).filter(
    (fx, i, arr) =>
      // one row per fixture: the snapshot lists every club's view of the
      // same matchday window, so dedupe on the pair
      arr.findIndex(
        (o) =>
          o.matchday === fx.matchday &&
          o.home_agent_id === fx.home_agent_id &&
          o.away_agent_id === fx.away_agent_id,
      ) === i,
  )
  const recent = season.recent ?? []
  const currentMd = season.current_matchday

  return (
    <div className="wp-grid">
      {/* on today / next up */}
      <section className="wp-card">
        <h3 className="wp-head">
          On today <span className="wp-md">matchday {Math.min(currentMd, season.matchdays_total)} of {season.matchdays_total}</span>
        </h3>
        {upcoming.length === 0 ? (
          <p className="wp-empty">No fixtures scheduled — the season may be between matchdays.</p>
        ) : (
          <ul className="wp-list">
            {upcoming.map((fx) => {
              const href = prematchHref(fx.matchday, fx.home_agent_id, fx.away_agent_id)
              const ready = fx.status === 'open' || fx.status === 'played'
              return (
                <li key={`${fx.matchday}-${fx.home_agent_id}-${fx.away_agent_id}`} className="wp-row">
                  <div className="wp-row-main">
                    <b>
                      {fx.home_club ?? names.get(fx.home_agent_id) ?? fx.home_agent_id}{' '}
                      <span className="wp-vs">v</span>{' '}
                      {fx.away_club ?? names.get(fx.away_agent_id) ?? fx.away_agent_id}
                    </b>
                    <span className="wp-sub">
                      MD {fx.matchday} · locks {fmtClock(fx.deadline_at)}
                      {fx.status === 'played' ? ' · played' : ready ? ' · lineups in' : ' · awaiting lineups'}
                    </span>
                  </div>
                  <Link className="wp-cta" href={href}>
                    {fx.status === 'played' ? 'Team sheet' : ready ? 'Pre-match' : 'Preview'}
                  </Link>
                </li>
              )
            })}
          </ul>
        )}
      </section>

      {/* latest results */}
      <section className="wp-card">
        <h3 className="wp-head">
          Latest results <span className="wp-md">replay any match</span>
        </h3>
        {recent.length === 0 ? (
          <p className="wp-empty">Nothing played yet — the first matchday is still to come.</p>
        ) : (
          <ul className="wp-list">
            {recent.map((r) => {
              const home = r.home_agent_id
              const away = r.away_agent_id
              const stats = statLine(r.match_stats)
              return (
                <li key={r.match_id} className="wp-row">
                  <div className="wp-row-main">
                    <b>
                      {names.get(home) ?? home}{' '}
                      <span className="wp-score">{r.score}</span>{' '}
                      {names.get(away) ?? away}
                    </b>
                    <span className="wp-sub">
                      MD {r.matchday}
                      {stats ? ` · ${stats}` : ''}
                    </span>
                  </div>
                  <Link className="wp-cta" href={broadcastHref(r.matchday, home, away)}>
                    Watch
                  </Link>
                </li>
              )
            })}
          </ul>
        )}
      </section>
    </div>
  )
}
