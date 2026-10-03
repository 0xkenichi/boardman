'use client'
/**
 * MatchBoard — the new /football/tactics.
 *
 * One job: watch a recorded fixture on the 2D pitch, with the pre-match team
 * sheet and the stat fold around it. Portal-styled (cream paper, book
 * type), no XI editors, no cameras, no coach marks — lineup editing lives in
 * Manager Mode, the live broadcast lives in Watch. Replays load by fixture
 * (?md&home&away) or straight from the latest results.
 */
import { useCallback, useEffect, useState } from 'react'
import Link from 'next/link'
import MatchBroadcast from './MatchBroadcast'
import PreMatchBoard from './PreMatchBoard'
import MatchStats from './MatchStats'
import {
  fetchAfmSeason,
  fetchSeasonReplay,
  type AfmSeason,
  type MatchdayReplay,
  type SeasonRecentResult,
} from '../../lib/afm'

interface PickerSeason extends AfmSeason {
  recent?: SeasonRecentResult[]
}

interface Fixture {
  md: number
  home: string
  away: string
}

function fixtureFromSearch(): Fixture | null {
  try {
    const q = new URLSearchParams(window.location.search)
    const md = Number(q.get('md'))
    const home = q.get('home') ?? ''
    const away = q.get('away') ?? ''
    if (md > 0 && home && away) return { md, home, away }
  } catch {
    /* server render / no search */
  }
  return null
}

export default function MatchBoard() {
  const [season, setSeason] = useState<PickerSeason | null>(null)
  const [fixture, setFixture] = useState<Fixture | null>(null)
  const [replay, setReplay] = useState<MatchdayReplay | null>(null)
  const [status, setStatus] = useState<string>('Loading the season…')
  const [err, setErr] = useState<string | null>(null)
  const [flip, setFlip] = useState(false)
  const [showPrematch, setShowPrematch] = useState(true)
  const [demo, setDemo] = useState(false)

  /* deep link first (?md&home&away), else the latest played fixture */
  useEffect(() => {
    let cancelled = false
    const linked = fixtureFromSearch()
    fetchAfmSeason()
      .then((s) => {
        if (cancelled) return
        const snap = s as PickerSeason
        setSeason(snap)
        if (linked) {
          setFixture(linked)
          return
        }
        const recent = (snap.recent ?? []).slice().sort((a, b) => b.matchday - a.matchday)[0]
        if (recent) {
          setFixture({ md: recent.matchday, home: recent.home_agent_id, away: recent.away_agent_id })
        } else {
          setDemo(true)
          setStatus('')
        }
      })
      .catch((e: Error) => {
        if (!cancelled) {
          setErr(e.message)
          if (linked) setFixture(linked)
        }
      })
    return () => {
      cancelled = true
    }
  }, [])

  const load = useCallback((fx: Fixture) => {
    setErr(null)
    setStatus('Loading the replay…')
    setReplay(null)
    fetchSeasonReplay(fx.md, fx.home, fx.away)
      .then((r) => {
        setReplay(r)
        setStatus('')
      })
      .catch((e: Error) => {
        setReplay(null)
        setStatus('')
        setErr(e.message)
      })
  }, [])

  useEffect(() => {
    if (fixture) load(fixture)
  }, [fixture, load])

  const recent = (season?.recent ?? []).slice().sort((a, b) => b.matchday - a.matchday).slice(0, 12)

  const sideName = (agentId: string) =>
    season?.division?.find((d) => d.agent_id === agentId)?.name ??
    agentId.replace('agent_', '').replace('_demo', '')

  const homeName = fixture ? sideName(fixture.home) : 'Home'
  const awayName = fixture ? sideName(fixture.away) : 'Away'

  return (
    <>
      <div className="fd-hero" style={{ marginBottom: 8 }}>
        <h1 style={{ fontSize: 30 }}>The match board</h1>
        <p className="fd-lede">
          Any recorded fixture, replayed on the 2D pitch with the engine’s own movement — the same
          board the broadcast uses, minus the clutter.
        </p>
      </div>

      {/* fixture picker */}
      <div className="fd-panel" style={{ marginBottom: 14 }}>
        <h3 style={{ margin: '0 0 8px', fontSize: 15 }}>Pick a fixture</h3>
        {recent.length === 0 && !season ? (
          <p className="fd-note">Loading results…</p>
        ) : recent.length === 0 ? (
          <p className="fd-note">
            Nothing played yet. <Link href="/football/league">Follow the league →</Link>
          </p>
        ) : (
          <div className="fd-mb-fixtures">
            {recent.map((r) => {
              const on =
                fixture?.md === r.matchday &&
                fixture?.home === r.home_agent_id &&
                fixture?.away === r.away_agent_id
              return (
                <button
                  key={r.match_id}
                  className={`fd-mb-fx ${on ? 'on' : ''}`}
                  onClick={() =>
                    setFixture({ md: r.matchday, home: r.home_agent_id, away: r.away_agent_id })
                  }
                >
                  <span className="fd-mb-md">MD{r.matchday}</span>
                  <span className="fd-mb-teams">
                    {sideName(r.home_agent_id)} vs {sideName(r.away_agent_id)}
                  </span>
                  <span className="fd-mb-score">{r.score}</span>
                </button>
              )
            })}
          </div>
        )}
      </div>

      {err && (
        <p className="fd-error" role="status">
          {err} — the replay may not exist for this fixture yet.
        </p>
      )}
      {!err && status && <p className="fd-note">{status}</p>}

      {demo && (
        <div className="fd-panel">
          <h3 style={{ margin: '0 0 8px', fontSize: 15 }}>Demo mode</h3>
          <p className="fd-note" style={{ marginBottom: 10 }}>
            No season is running right now, so the board plays its scripted demo sequence. When the
            league kicks off, every recorded fixture lands here.
          </p>
          <MatchBroadcast replay={null} homeLabel="Boardman FC" awayLabel="Pike City" />
        </div>
      )}

      {replay && (
        <div className="fd-panel" style={{ marginBottom: 14 }}>
          <div
            style={{
              display: 'flex',
              flexWrap: 'wrap',
              gap: 10,
              alignItems: 'baseline',
              justifyContent: 'space-between',
              marginBottom: 8,
            }}
          >
            <b>
              {replay.home.club_name} {replay.result.score} {replay.away.club_name}
              <span className="fd-note" style={{ marginLeft: 8 }}>
                MD{replay.matchday}
              </span>
            </b>
            <span style={{ display: 'flex', gap: 8 }}>
              <button className="fd-btn" onClick={() => setShowPrematch((v) => !v)}>
                {showPrematch ? 'Hide team sheet' : 'Team sheet'}
              </button>
              <button className="fd-btn" onClick={() => setFlip((v) => !v)}>
                {flip ? 'Unflip' : 'Flip pitch'}
              </button>
            </span>
          </div>
          <MatchBroadcast
            replay={replay}
            homeLabel={flip ? replay.away.club_name : replay.home.club_name}
            awayLabel={flip ? replay.home.club_name : replay.away.club_name}
          />
        </div>
      )}

      {replay && showPrematch && (
        <div className="fd-panel" style={{ marginBottom: 14 }}>
          <h3 style={{ margin: '0 0 8px', fontSize: 15 }}>
            The team sheet — how both managers set up
          </h3>
          <MatchBoardPrematch md={replay.matchday} home={replay.home.agent_id} away={replay.away.agent_id} />
        </div>
      )}

      {replay && replay.result.stats && (
        <div className="fd-panel">
          <h3 style={{ margin: '0 0 8px', fontSize: 15 }}>The stat fold</h3>
          <MatchStats
            stats={replay.result.stats}
            homeName={replay.home.club_name}
            awayName={replay.away.club_name}
          />
        </div>
      )}
    </>
  )
}

/** Loads the pre-match view for the loaded fixture and renders the board. */
function MatchBoardPrematch({ md, home, away }: Fixture) {
  const [view, setView] = useState<Parameters<typeof PreMatchBoard>[0]['view']>(null)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    let cancelled = false
    import('../../lib/afm').then(({ fetchPrematch }) =>
      fetchPrematch(md, home, away)
        .then((v) => {
          if (!cancelled) setView(v)
        })
        .catch(() => {
          if (!cancelled) setFailed(true)
        }),
    )
    return () => {
      cancelled = true
    }
  }, [md, home, away])

  if (failed) return <p className="fd-note">Team sheet unavailable for this fixture.</p>
  return <PreMatchBoard view={view} />
}
