'use client'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  AfmClub,
  AfmPlayer,
  CatalogFile,
  fetchSeasonReplay,
  FORMATIONS,
  FormationName,
  layoutSlots,
  listClubs,
  loadCatalog,
  MatchdayReplay,
  pickBench,
  pickXI,
  PlayerOnPitch,
  ReplaySide,
  saveClubLineup,
  simulateMatch,
  SimResponse,
  TACTICAL_TAGS,
  TEAM_PRESETS,
  TeamXI,
} from '../../lib/afm'
import { buildTimeline, MinuteState, commentaryFor } from '../../lib/broadcast'
import MatchStats from './MatchStats'
import { PitchView, ViewTeamSpec, CamMode, BoardTool, PitchStyle } from './PitchView'

type Mode = 'setup' | 'match' | 'coach'
type Side = 'home' | 'away'

interface CoachMarkUI {
  kind: 'arrow' | 'zone' | 'cone'
  color: string
  ax: number
  az: number
  bx: number
  bz: number
}

const DEFAULT_MPS = 0.6
const SPEEDS = [0.3, 0.6, 1.5, 4, 90]
const PITCH_STYLES: PitchStyle[] = ['night', 'classic', 'obsidian', 'chalkboard', 'blueprint', 'winter']
const STYLE_LABEL: Record<PitchStyle, string> = {
  night: 'Night',
  classic: 'Classic',
  obsidian: 'Obsidian',
  chalkboard: 'Chalkboard',
  blueprint: 'Blueprint',
  winter: 'Winter',
}

const CLAMP = { minX: -52.5 + 0.9, maxX: 52.5 - 0.9, minZ: -34 + 0.9, maxZ: 34 - 0.9 }

export default function TacticsTheater() {
  /* ------------------------------------------------ data */
  const [catalog, setCatalog] = useState<CatalogFile | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)

  /* ------------------------------------------------ teams */
  const [home, setHome] = useState<TeamXI | null>(null)
  const [away, setAway] = useState<TeamXI | null>(null)
  const [clubs, setClubs] = useState<AfmClub[] | null>(null)
  const [saveStatus, setSaveStatus] = useState<string | null>(null)

  /* ------------------------------------------------ ui state */
  const [mode, setMode] = useState<Mode>('setup')
  const [style, setStyle] = useState<PitchStyle>('classic')
  const [cam, setCam] = useState<CamMode>('tactical')
  const [tool, setTool] = useState<BoardTool>('select')
  const [editableSide, setEditableSide] = useState<Side>('home')
  const [coachMarks, setCoachMarks] = useState<CoachMarkUI[]>([])
  const [hoverInfo, setHoverInfo] = useState<string | null>(null)

  /* ------------------------------------------------ match */
  const [match, setMatch] = useState<SimResponse | null>(null)
  const [timeline, setTimeline] = useState<MinuteState[] | null>(null)
  const [minute, setMinute] = useState(0)
  const [playing, setPlaying] = useState(false)
  const [mps, setMps] = useState(DEFAULT_MPS)
  const [busy, setBusy] = useState(false)
  const [busyLineup, setBusyLineup] = useState(false)
  const [simError, setSimError] = useState<string | null>(null)
  const [goalFlash, setGoalFlash] = useState<string | null>(null)
  const [matchLabel, setMatchLabel] = useState<string | null>(null)

  /* ------------------------------------------------ refs / view */
  const stageRef = useRef<HTMLDivElement>(null)
  const viewRef = useRef<PitchView | null>(null)
  const minuteRef = useRef(0)
  const mpsRef = useRef(DEFAULT_MPS)
  const matchRef = useRef<SimResponse | null>(null)
  const homeRef = useRef<TeamXI | null>(null)
  const awayRef = useRef<TeamXI | null>(null)
  const toolRef = useRef<BoardTool>('select')
  const modeRef = useRef<Mode>('setup')

  useEffect(() => {
    mpsRef.current = mps
  }, [mps])
  useEffect(() => {
    minuteRef.current = minute
  }, [minute])
  useEffect(() => {
    matchRef.current = match
  }, [match])
  useEffect(() => {
    homeRef.current = home
    awayRef.current = away
  }, [home, away])
  useEffect(() => {
    toolRef.current = tool
  }, [tool])
  useEffect(() => {
    modeRef.current = mode
  }, [mode])

  /* ------------------------------------------------ runtime error capture (dev aid) */
  useEffect(() => {
    const onErr = (e: ErrorEvent) => setLoadError((s) => s ?? `runtime: ${e.message}`)
    const onRej = (e: PromiseRejectionEvent) => setLoadError((s) => s ?? `rejected: ${String(e.reason)}`)
    window.addEventListener('error', onErr)
    window.addEventListener('unhandledrejection', onRej)
    return () => {
      window.removeEventListener('error', onErr)
      window.removeEventListener('unhandledrejection', onRej)
    }
  }, [])

  /* ------------------------------------------------ boot catalog + clubs + default teams */
  useEffect(() => {
    let alive = true
    loadCatalog()
      .then(async (cat) => {
        if (!alive) return
        setCatalog(cat)
        let clubList: AfmClub[] | null = null
        try {
          clubList = await listClubs()
        } catch {
          clubList = null // backend offline — board still works standalone
        }
        if (!alive) return
        setClubs(clubList)
        // the demo AFM manager clubs (what the agents set) are the default matchup
        const full = clubList?.filter((c) => c.starters.length >= 11) ?? []
        const homeClub =
          full.find((c) => c.agent_id.toLowerCase().includes('bluelock')) ??
          full.find((c) => c.club_name.toLowerCase().includes('blue lock'))
        const awayClub =
          full.find((c) => c.agent_id.toLowerCase().includes('aoashi')) ??
          full.find((c) => c.club_name.toLowerCase().includes('ao ashi'))
        if (homeClub && awayClub) {
          setHome(teamFromClub(homeClub, 'home'))
          setAway(teamFromClub(awayClub, 'away'))
        } else if (full.length >= 2) {
          // any two live agent-owned clubs are still watchable
          setHome(teamFromClub(full[0], 'home'))
          setAway(teamFromClub(full[1], 'away'))
        } else {
          const { h, a } = defaultTeams(cat)
          setHome(h)
          setAway(a)
        }
        // deep-linked replay: /football/tactics?replay=1&md=N&home=..&away=..
        const params = new URLSearchParams(window.location.search)
        const md = params.get('md')
        const homeId = params.get('home')
        const awayId = params.get('away')
        if (md && homeId && awayId) {
          fetchSeasonReplay(Number(md), homeId, awayId)
            .then((replay) => {
              if (!alive) return
              playReplay(replay)
            })
            .catch((e) => alive && setSimError(String((e as Error)?.message ?? e)))
        }
      })
      .catch((e) => alive && setLoadError(String(e?.message ?? e)))
    return () => {
      alive = false
    }
  }, [])

  const sceneReady = !loadError && Boolean(catalog && home && away)

  /* ------------------------------------------------ pitch mount (once the stage exists) */
  useEffect(() => {
    if (!sceneReady) return
    const el = stageRef.current
    if (!el) return
    let view: PitchView | null = null
    try {
      view = new PitchView(el, style, {
        onTokenDrag: (side, idx, x, z) => {
          const setter = side === 'home' ? setHome : setAway
          setter((team) => {
            if (!team) return team
            const xi = team.xi.map((p, i) => (i === idx ? { ...p, x, z } : p))
            return { ...team, xi }
          })
        },
        onTokenHover: (side, idx) => {
          if (side == null || idx == null) {
            setHoverInfo(null)
            return
          }
          const team = side === 'home' ? homeRef.current : awayRef.current
          const p = team?.xi[idx]
          if (p) setHoverInfo(`${p.name} · ${p.slot} · ${p.rating} rated`)
        },
        onCoachCommit: (mark) => {
          if (modeRef.current !== 'coach') return
          setCoachMarks((prev) => [
            ...prev,
            { kind: mark.kind, color: mark.color, ax: mark.a.x, az: mark.a.z, bx: mark.b.x, bz: mark.b.z },
          ])
        },
      }).init()
      viewRef.current = view
    } catch (e) {
      setLoadError(`WebGL unavailable: ${String((e as Error)?.message ?? e)}`)
      return
    }
    return () => {
      view?.dispose()
      viewRef.current = null
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sceneReady])

  /* ------------------------------------------------ re-render teams to the scene */
  const teamIdSig = useMemo(() => {
    const mk = (t: TeamXI | null) =>
      t ? `${t.name}|${t.formation}|${t.kit}|${t.xi.map((p) => `${p.id}:${p.number}`).join(',')}` : 'none'
    return `${mk(home)}||${mk(away)}`
  }, [home, away])

  useEffect(() => {
    const view = viewRef.current
    if (!view || !home || !away) return
    view.setTeams(toViewTeam(home), toViewTeam(away))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sceneReady, teamIdSig])

  /* ------------------------------------------------ mode / tool / camera wiring */
  useEffect(() => {
    const view = viewRef.current
    if (!view) return
    if (mode === 'match' && match && timeline) {
      view.setTimeline(timeline)
      view.setSimTime(minute)
    } else {
      view.setTimeline(null)
    }
    view.setCamera(cam)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode, match, timeline, cam, sceneReady])

  useEffect(() => {
    const view = viewRef.current
    if (!view) return
    const editing = mode === 'setup' ? editableSide : null
    view.setEditable(editing)
    view.setTool(mode === 'coach' ? tool : 'select')
    const marks =
      mode === 'coach'
        ? coachMarks.map((m) => ({
            kind: m.kind,
            color: m.color,
            a: { x: m.ax, z: m.az },
            b: { x: m.bx, z: m.bz },
          }))
        : []
    view.setCoachMarks(marks)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode, editableSide, tool, coachMarks])

  useEffect(() => {
    viewRef.current?.setStyle(style)
  }, [style])

  /* ------------------------------------------------ broadcast clock */
  useEffect(() => {
    if (mode !== 'match' || !playing || !match || !timeline) return
    const id = setInterval(() => {
      const prev = minuteRef.current
      const next = Math.min(90, prev + mpsRef.current * 0.1)
      // goal banners for events crossed this tick
      for (const ev of match.result.feed) {
        if (ev.type === 'goal' && ev.minute > prev && ev.minute <= next) {
          setGoalFlash(ev.side === 'home' ? homeRef.current?.name ?? 'Home' : awayRef.current?.name ?? 'Away')
          setTimeout(() => setGoalFlash(null), 2400)
        }
      }
      setMinute(next)
      viewRef.current?.setSimTime(next)
      if (next >= 90) setPlaying(false)
    }, 100)
    return () => clearInterval(id)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode, playing, match, timeline])

  /* ------------------------------------------------ derived */
  const score = useMemo(() => {
    if (!match) return { home: 0, away: 0 }
    const m = Math.floor(minute)
    let h = 0
    let a = 0
    for (const ev of match.result.feed) {
      if (ev.minute > m) break
      if (ev.type === 'goal') {
        if (ev.side === 'home') h++
        else a++
      }
    }
    return { home: h, away: a }
  }, [match, minute])

  const feed = useMemo(() => {
    if (!match) return []
    const m = Math.floor(minute)
    return commentaryFor(match.result).filter((e) => e.minute <= m).slice(-9)
  }, [match, minute])

  const minuteLabel =
    minute >= 90 ? "FT" : minute >= 45 ? `${Math.floor(minute)}'` : `${Math.floor(minute)}'`

  /* ------------------------------------------------ actions */
  /** Player pool a manager may legally pick from: the club's own squad when
   *  this side is a live agent club, otherwise the full catalog. */
  const poolFor = (side: Side): AfmPlayer[] => {
    const team = side === 'home' ? home : away
    if (team?.clubAgentId) {
      const club = clubs?.find((c) => c.agent_id === team.clubAgentId)
      if (club?.squad?.length) return club.squad
    }
    return catalog?.players ?? []
  }

  const setFormation = (side: Side, f: FormationName) => {
    const players = poolFor(side)
    const other = side === 'home' ? away : home
    const otherTaken = new Set((other?.xi ?? []).map((p) => p.id))
    const picked = pickXI(players, f, otherTaken, side === 'home' ? 1 : 12)
    // away defends the other goal: mirror the home-frame layout
    const xi = picked.map((p) => (side === 'away' ? { ...p, x: -p.x, z: -p.z } : p))
    const full = [...otherTaken, ...picked.map((p) => p.id)]
    const bench = pickBench(players, new Set(full), 5)
    const base = side === 'home' ? home : away
    const setter = side === 'home' ? setHome : setAway
    setter({ ...(base ?? (side === 'home' ? emptyTeam('bluelock') : emptyTeam('aoashi'))), formation: f, xi, bench })
  }

  const applyPreset = (side: Side, key: string) => {
    const preset = TEAM_PRESETS[key]
    if (!preset) return
    const setter = side === 'home' ? setHome : setAway
    setter((team) => (team ? { ...team, name: preset.name, kit: preset.kit, kitDark: preset.kitDark, accent: preset.accent } : team))
  }

  const setName = (side: Side, name: string) => {
    const setter = side === 'home' ? setHome : setAway
    setter((team) => (team ? { ...team, name } : team))
  }

  const shuffle = (side: Side) => {
    const f = (side === 'home' ? home?.formation : away?.formation) ?? '4-3-3'
    setFormation(side, f)
  }

  const autoReloadSide = (side: Side) => {
    const players = poolFor(side)
    const other = side === 'home' ? away : home
    const otherTaken = new Set((other?.xi ?? []).map((p) => p.id))
    const f = (side === 'home' ? home?.formation : away?.formation) ?? '4-3-3'
    const picked = pickXI(players, f, otherTaken, side === 'home' ? 1 : 12)
    const xi = picked.map((p) => (side === 'away' ? { ...p, x: -p.x, z: -p.z } : p))
    const setter = side === 'home' ? setHome : setAway
    setter((t) =>
      t
        ? {
            ...t,
            xi,
            bench: pickBench(players, new Set([...otherTaken, ...picked.map((p) => p.id)]), 5),
            clubAgentId: undefined,
            tags: ['balanced'],
          }
        : t,
    )
  }

  const loadClubSide = (side: Side, agentId: string) => {
    if (agentId === 'auto') {
      autoReloadSide(side)
      return
    }
    const club = clubs?.find((c) => c.agent_id === agentId)
    if (!club) return
    const setter = side === 'home' ? setHome : setAway
    setter(teamFromClub(club, side))
  }

  const setTag = (side: Side, tag: string) => {
    const setter = side === 'home' ? setHome : setAway
    setter((t) => (t ? { ...t, tags: [tag] } : t))
  }

  const saveLineups = async () => {
    const teams = [home, away].filter((t): t is TeamXI => Boolean(t?.clubAgentId))
    if (!teams.length) {
      setSaveStatus('pick a club for a side first — then Save writes its lineup')
      return
    }
    setBusyLineup(true)
    setSaveStatus(null)
    const parts: string[] = []
    for (const t of teams) {
      try {
        const club = await saveClubLineup(t)
        parts.push(`${club.club_name}: saved ✓`)
      } catch (e) {
        parts.push(`${t.name}: ${String((e as Error)?.message ?? e)}`)
      }
    }
    setSaveStatus(parts.join(' · '))
    setBusyLineup(false)
    try {
      setClubs(await listClubs())
    } catch {
      /* backend offline */
    }
  }

  const runSim = useCallback(async () => {
    const h = homeRef.current
    const a = awayRef.current
    if (!h || !a) return
    setBusy(true)
    setSimError(null)
    setMinute(0)
    setPlaying(false)
    try {
      const res = await simulateMatch(h, a)
      const tl = buildTimeline(res.result, h, a)
      setMatchLabel(null)
      setMatch(res)
      setTimeline(tl)
      viewRef.current?.setTimeline(tl)
      viewRef.current?.setSimTime(0)
      // humans watch the games: open on the TV broadcast rig
      setCam('broadcast')
      setMode('match')
      setTimeout(() => setPlaying(true), 350)
    } catch (e) {
      setSimError(String((e as Error)?.message ?? e))
    } finally {
      setBusy(false)
    }
  }, [])

  /** Replay a recorded season fixture — the agents' locked lineups + feed. */
  const playReplay = useCallback(async (replay: MatchdayReplay) => {
    const h = teamFromReplaySide(replay.home, 'home')
    const a = teamFromReplaySide(replay.away, 'away')
    setHome(h)
    setAway(a)
    const res: SimResponse = { success: true, match_id: replay.match_id, result: replay.result }
    const tl = buildTimeline(replay.result, h, a)
    setMatchLabel(`REPLAY · MD ${replay.matchday}`)
    setMatch(res)
    setTimeline(tl)
    setMinute(0)
    setPlaying(false)
    viewRef.current?.setTimeline(tl)
    viewRef.current?.setSimTime(0)
    // humans watch the games: open on the TV broadcast rig
    setCam('broadcast')
    setMode('match')
    setTimeout(() => setPlaying(true), 350)
  }, [])

  const resetMatchUi = () => {
    setPlaying(false)
    setMinute(0)
  }

  const clearMarks = () => {
    setCoachMarks([])
  }

  /* ------------------------------------------------ render */
  if (loadError) {
    return (
      <div className="tc-loading">
        <div className="tc-error">{loadError}</div>
      </div>
    )
  }
  if (!home || !away) {
    return <div className="tc-loading">Loading player catalog…</div>
  }

  const teamPanel = (side: Side, team: TeamXI) => (
    <div className="tc-card" key={side}>
      <h3>
        <span className="k" style={{ background: team.kit }} />
        {side === 'home' ? 'Home XI' : 'Away XI'}
      </h3>
      <input
        className="tc-teamname-input"
        value={team.name}
        onChange={(e) => setName(side, e.target.value)}
        aria-label="team name"
      />
      {team.clubAgentId && (
        <div className="tc-ownerline">
          club of <b>{team.clubAgentId}</b>
        </div>
      )}
      <div className="tc-presets">
        {Object.entries(TEAM_PRESETS).map(([key, p]) => (
          <button key={key} className="tc-preset" onClick={() => applyPreset(side, key)} title={p.name}>
            <span className="sw" style={{ background: p.kit }} />
            {p.name}
          </button>
        ))}
      </div>
      <div className="tc-formation-row" style={{ marginBottom: 8 }}>
        {FORMATIONS.map((f) => (
          <button
            key={f}
            className={`tc-chip ${team.formation === f ? 'on' : ''}`}
            onClick={() => setFormation(side, f)}
          >
            {f}
          </button>
        ))}
      </div>
      <div className="tc-xi">
        {team.xi.map((p) => (
          <div className="tc-player" key={p.id}>
            <span className="no" style={{ background: team.kit }}>
              {p.number}
            </span>
            <span className="nm">{p.name}</span>
            <span className="sl">{p.slot}</span>
            <span className="rt">{p.rating}</span>
          </div>
        ))}
      </div>
      <div className="tc-tags">
        {TACTICAL_TAGS.map((t) => (
          <button
            key={t}
            className={`tc-chip ${(team.tags ?? ['balanced']).includes(t) ? 'on' : ''}`}
            onClick={() => setTag(side, t)}
            title={`tactical style: ${t}`}
          >
            {t.replaceAll('_', ' ')}
          </button>
        ))}
      </div>
      {team.bench.length > 0 && (
        <div style={{ marginTop: 8, fontSize: '0.7rem', color: 'var(--tc-dim)' }}>
          Bench: {team.bench.map((b) => b.name).join(' · ')}
        </div>
      )}
      <div style={{ marginTop: 10, display: 'flex', gap: 6 }}>
        <button
          className="tc-btn"
          onClick={() => shuffle(side)}
          style={{ width: team.clubAgentId ? 'auto' : '100%', flex: team.clubAgentId ? 1 : undefined }}
        >
          Re-pick best XI
        </button>
        {team.clubAgentId && (
          <button className="tc-btn primary" onClick={saveLineups} disabled={busyLineup}>
            {busyLineup ? 'Saving…' : 'Save lineup'}
          </button>
        )}
      </div>
    </div>
  )

  return (
    <div className="tc-page">
      <div className="tc-top">
        <a className="tc-back" href="/agentic/football-managers.html">
          ← AFM
        </a>
        <div className="tc-logo">
          Boardman <b>·</b> Tactics
        </div>
        <div className="tc-title">
          Agentic Football Managers <small>3D tactics theater</small>
        </div>
        <div className="tc-spacer" />
        <div className="tc-pitchstyle">
          {PITCH_STYLES.map((s) => (
            <button key={s} className={`tc-chip ${style === s ? 'on' : ''}`} onClick={() => setStyle(s)}>
              {STYLE_LABEL[s]}
            </button>
          ))}
        </div>
      </div>

      <div className="tc-tabs">
        <button className={`tc-tab ${mode === 'setup' ? 'on' : ''}`} onClick={() => setMode('setup')}>
          Setup XI
        </button>
        <button className={`tc-tab ${mode === 'match' ? 'on' : ''}`} onClick={() => setMode('match')}>
          {match ? 'Match' : 'Watch a match'}
        </button>
        <button className={`tc-tab ${mode === 'coach' ? 'on' : ''}`} onClick={() => setMode('coach')}>
          Coach board
        </button>
        <span className="tc-spacer" />
        {['broadcast', 'tactical', 'behind'].map((c) => (
          <button key={c} className={`tc-chip ${cam === c ? 'on' : ''}`} onClick={() => setCam(c as CamMode)}>
            {c} cam
          </button>
        ))}
      </div>

      <div className="tc-main">
        <div className="tc-stage">
          <div className="tc-scoreboard">
            <div className="tc-score-home">
              <span className="tc-kit" style={{ background: home.kit }} />
              <span className="tc-teamname">{home.name}</span>
            </div>
            <div className="tc-score">
              {match ? `${score.home}–${score.away}` : 'vs'}
              {match && mode === 'match' && (
                <small className={playing ? 'tc-live' : ''}>
                  {playing && '● '}
                  {minuteLabel}
                </small>
              )}
              {matchLabel && <small className="tc-replay-tag">{matchLabel}</small>}
              {!match && <small>Kick off from the match tab</small>}
            </div>
            <div className="tc-score-away">
              <span className="tc-kit" style={{ background: away.kit }} />
              <span className="tc-teamname">{away.name}</span>
            </div>
          </div>

          <div className="tc-canvas">
            <div ref={stageRef} className="pitch-root" />
            {goalFlash && <div className="tc-goalflash">{goalFlash.toUpperCase()}</div>}
            {hoverInfo && <div className="tc-overlay-note">{hoverInfo}</div>}
            <div className="tc-canvas-overlay">
              <div className="tc-hint">
                {mode === 'setup'
                  ? `Drag players on the pitch · editing ${editableSide}`
                  : mode === 'coach'
                    ? `Drag to draw ${tool} · double-click to swap camera`
                    : 'Watch live · drag the timeline to scrub'}
              </div>
            </div>
          </div>

          <div className="tc-timeline">
            <button
              className="tc-btn primary"
              disabled={mode === 'match' && match !== null}
              onClick={runSim}
              style={mode === 'match' && match ? { display: 'none' } : undefined}
            >
              {busy ? 'Simulating…' : 'Kick off ▶'}
            </button>
            {simError && (
              <span style={{ color: 'var(--tc-red)', fontSize: '0.72rem' }}>sim failed — is the Boardman API up? ({simError})</span>
            )}
            {mode === 'match' && match && (
              <>
                <button className="tc-btn" disabled={!playing} onClick={() => setPlaying(false)}>
                  {playing ? 'Pause' : 'Play'}
                </button>
                <input
                  className="tc-scrub"
                  type="range"
                  min={0}
                  max={90}
                  step={0.1}
                  value={minute}
                  disabled={playing}
                  onChange={(e) => {
                    const v = Number(e.target.value)
                    setMinute(v)
                    viewRef.current?.setSimTime(v)
                  }}
                />
                <div className="tc-speed">
                  {SPEEDS.map((s) => (
                    <button key={s} className={`tc-chip ${mps === s ? 'on' : ''}`} onClick={() => setMps(s)}>
                      {s === 90 ? '⏭' : `${s}×`}
                    </button>
                  ))}
                </div>
                <button className="tc-btn" onClick={resetMatchUi}>
                  Reset
                </button>
                <button className="tc-btn" onClick={runSim} disabled={busy}>
                  Rematch
                </button>
              </>
            )}
          </div>
        </div>

        <div className="tc-rail">
          {mode === 'setup' && (
            <>
              <div className="tc-card">
                <h3>Agent clubs</h3>
                {!clubs || clubs.length === 0 ? (
                  <div className="tc-empty">
                    No live clubs — seed demo clubs on the Boardman API, or just edit freely below.
                  </div>
                ) : (
                  <div className="tc-clubrows">
                    {clubs.map((c) => {
                      const cls = [
                        home?.clubAgentId === c.agent_id ? 'home' : '',
                        away?.clubAgentId === c.agent_id ? 'away' : '',
                      ]
                        .filter(Boolean)
                        .join(' ')
                      return (
                        <div key={c.agent_id} className={`tc-clubrow ${cls}`}>
                          <div className="nm">
                            {c.club_name}
                            <small>
                              {c.formation} · {(c.tactical_tags ?? ['balanced']).join(', ')} · {c.roster_size} squad
                            </small>
                          </div>
                          <div className="acts">
                            <button
                              className="tc-chip"
                              disabled={home?.clubAgentId === c.agent_id}
                              onClick={() => loadClubSide('home', c.agent_id)}
                            >
                              Home
                            </button>
                            <button
                              className="tc-chip"
                              disabled={away?.clubAgentId === c.agent_id}
                              onClick={() => loadClubSide('away', c.agent_id)}
                            >
                              Away
                            </button>
                          </div>
                        </div>
                      )
                    })}
                  </div>
                )}
                <p style={{ color: 'var(--tc-muted)', fontSize: '0.72rem', lineHeight: 1.5, marginTop: 8 }}>
                  These are the real agent-owned clubs and the XIs they set. Load one per side, tweak the
                  shape, choose a tactical style, then <b>Save lineup</b> writes it back as the agent's choice.
                </p>
              </div>
              <div className="tc-card">
                <h3>Editing</h3>
                <div className="tc-formation-row">
                  <button className={`tc-chip ${editableSide === 'home' ? 'on' : ''}`} onClick={() => setEditableSide('home')}>
                    Home (drag)
                  </button>
                  <button className={`tc-chip ${editableSide === 'away' ? 'on' : ''}`} onClick={() => setEditableSide('away')}>
                    Away (drag)
                  </button>
                </div>
                <p style={{ color: 'var(--tc-muted)', fontSize: '0.72rem', lineHeight: 1.5 }}>
                  Pick a formation for each side and drag players anywhere on the pitch. One copy of each
                  player exists — two unique XIs are auto-selected from the live catalog.
                </p>
              </div>
              {teamPanel('home', home)}
              {teamPanel('away', away)}
              {saveStatus && <div className="tc-savestatus">{saveStatus}</div>}
            </>
          )}

          {mode === 'match' && match && (
            <>
              <div className="tc-card">
                <h3>Match feed</h3>
                <div className="tc-feed">
                  {feed.length === 0 && <div className="tc-empty">Waiting for kickoff…</div>}
                  {feed.map((e, i) => (
                    <div key={i} className={`tc-feed-item ${e.type === 'goal' ? 'goal' : e.type === 'yellow' ? 'yellow' : e.type === 'shot' ? 'shot' : ''}`}>
                      <b>{e.minute}'</b> {e.text}
                    </div>
                  ))}
                </div>
              </div>
              {match.result.stats && minute >= 90 ? (
                <div className="tc-card">
                  <h3>Match stats</h3>
                  <MatchStats
                    stats={match.result.stats}
                    homeName={home?.name ?? 'Home'}
                    awayName={away?.name ?? 'Away'}
                  />
                </div>
              ) : null}
              <div className="tc-card">
                <h3>On the pitch</h3>
                <div style={{ fontSize: '0.74rem', color: 'var(--tc-muted)', lineHeight: 1.6 }}>
                  {home.name}: {home.formation} · {(home.tags ?? ['balanced']).join(', ')}
                  <br />
                  {away.name}: {away.formation} · {(away.tags ?? ['balanced']).join(', ')}
                  <br />
                  <br />
                  The backend engine (seeded by match id) resolved this fixture. Bodies are synthesized
                  from the formations — a full position model lands with the engine v1.
                </div>
              </div>
            </>
          )}

          {mode === 'match' && !match && (
            <div className="tc-card">
              <h3>Watch a match</h3>
              <p style={{ color: 'var(--tc-muted)', fontSize: '0.78rem', lineHeight: 1.6 }}>
                Two agent XIs are set. Kick off to simulate a friendly on the Boardman engine and
                broadcast it here — goals, chances and shape shifts animated in 3D.
              </p>
              <button className="tc-btn primary" onClick={runSim} disabled={busy} style={{ width: '100%', marginTop: 6 }}>
                {busy ? 'Simulating…' : 'Kick off ▶'}
              </button>
            </div>
          )}

          {mode === 'coach' && (
            <>
              <div className="tc-card">
                <h3>Coach tools</h3>
                <div className="tc-tools">
                  <button className={`tc-tool ${tool === 'arrow' ? 'on' : ''}`} onClick={() => setTool('arrow')}>
                    <span className="ico">➜</span>
                    <span>
                      Arrow <small>run / pass</small>
                    </span>
                  </button>
                  <button className={`tc-tool ${tool === 'zone' ? 'on' : ''}`} onClick={() => setTool('zone')}>
                    <span className="ico">▭</span>
                    <span>
                      Zone <small>area / shape</small>
                    </span>
                  </button>
                  <button className={`tc-tool ${tool === 'cone' ? 'on' : ''}`} onClick={() => setTool('cone')}>
                    <span className="ico">△</span>
                    <span>
                      Cone <small>marker</small>
                    </span>
                  </button>
                  <button className={`tc-tool ${tool === 'select' ? 'on' : ''}`} onClick={() => setTool('select')}>
                    <span className="ico">✥</span>
                    <span>
                      Select <small>tap a player</small>
                    </span>
                  </button>
                </div>
                <p style={{ color: 'var(--tc-muted)', fontSize: '0.72rem', lineHeight: 1.5, marginTop: 8 }}>
                  Draw the move on the frozen XI, phase by phase — arrows for runs/passes, zones for
                  blocks and pressing areas, cones for drills. Boardman ships the canvas; builder agents
                  ship the ideas.
                </p>
                <div style={{ display: 'flex', gap: 6, marginTop: 4 }}>
                  <button className="tc-btn ghost-warn" onClick={clearMarks} disabled={coachMarks.length === 0}>
                    Clear marks ({coachMarks.length})
                  </button>
                </div>
              </div>
              <div className="tc-card">
                <h3>Annotations</h3>
                {coachMarks.length === 0 ? (
                  <div className="tc-empty">Nothing drawn yet</div>
                ) : (
                  <div style={{ fontSize: '0.72rem', color: 'var(--tc-muted)', lineHeight: 1.7 }}>
                    {coachMarks.map((m, i) => (
                      <div key={i}>
                        {i + 1}. {m.kind}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  )
}

/* ---------------------------------------------------------------- helpers */

const CLUB_PRESET: Record<string, string> = {
  bluelock: 'bluelock',
  aoashi: 'aoashi',
  matchslice: 'matchslice',
  pike: 'pike',
}

/** Turn a live agent club (backend afm_clubs.json) into a board TeamXI.
 *  Starters[i] rides slot[i] of the club's formation — the same pairing the
 *  match engine uses — so the 3D shape always matches what agents set. */
/** Turn a recorded replay side (locked lineup + feed) into a board TeamXI. */
function teamFromReplaySide(side: ReplaySide, which: Side): TeamXI {
  const presetKey = Object.keys(CLUB_PRESET).find((k) => side.agent_id.toLowerCase().includes(k))
  const preset = TEAM_PRESETS[presetKey ?? 'boardman'] ?? TEAM_PRESETS.boardman
  const slots = layoutSlots(side.formation, which)
  const xi: PlayerOnPitch[] = side.xi.map((p, i) => {
    const [slot, x, z] = slots[i] ?? slots[0]
    return { id: p.player_id, slot, x, z, name: p.name, rating: p.base_rating ?? 0, nation: '', number: i + 1 }
  })
  return {
    name: side.club_name,
    kit: preset.kit,
    kitDark: preset.kitDark,
    accent: preset.accent,
    formation: side.formation,
    xi,
    bench: [],
    tags: side.tags?.length ? [...side.tags] : ['balanced'],
  }
}

function teamFromClub(club: AfmClub, side: Side): TeamXI {
  const slots = layoutSlots(club.formation, side)
  const squad = new Map(club.squad.map((p) => [p.player_id, p]))
  const presetKey = Object.keys(CLUB_PRESET).find((k) => club.agent_id.toLowerCase().includes(k))
  const preset = TEAM_PRESETS[presetKey ?? 'boardman'] ?? TEAM_PRESETS.boardman
  const xi: PlayerOnPitch[] = club.starters.map((p, i) => {
    const [slot, x, z] = slots[i] ?? slots[0]
    return {
      id: p.player_id,
      slot,
      x,
      z,
      name: p.name,
      rating: p.base_rating ?? 0,
      nation: p.nation,
      number: i + 1,
    }
  })
  return {
    name: club.club_name,
    kit: preset.kit,
    kitDark: preset.kitDark,
    accent: preset.accent,
    formation: club.formation,
    xi,
    bench: club.bench.length ? club.bench : [...squad.values()].slice(0, 5),
    clubAgentId: club.agent_id,
    tags: club.tactical_tags?.length ? [...club.tactical_tags] : ['balanced'],
  }
}

function defaultTeams(cat: CatalogFile): { h: TeamXI; a: TeamXI } {
  const homePreset = TEAM_PRESETS.bluelock
  const awayPreset = TEAM_PRESETS.aoashi
  const homeXi = pickXI(cat.players, '4-3-3', new Set(), 1)
  const awayXi0 = pickXI(cat.players, '4-3-3', new Set(homeXi.map((p) => p.id)), 12)
  const awayXi = awayXi0.map((p) => ({ ...p, x: -p.x, z: -p.z }))
  const used = new Set([...homeXi, ...awayXi].map((p) => p.id))
  const h: TeamXI = {
    name: homePreset.name,
    kit: homePreset.kit,
    kitDark: homePreset.kitDark,
    accent: homePreset.accent,
    formation: '4-3-3',
    xi: homeXi,
    bench: pickBench(cat.players, used, 5),
  }
  const a: TeamXI = {
    name: awayPreset.name,
    kit: awayPreset.kit,
    kitDark: awayPreset.kitDark,
    accent: awayPreset.accent,
    formation: '4-3-3',
    xi: awayXi,
    bench: pickBench(cat.players, used, 5),
  }
  return { h, a }
}

function emptyTeam(presetKey: string): TeamXI {
  const p = TEAM_PRESETS[presetKey] ?? TEAM_PRESETS.bluelock
  return { name: p.name, kit: p.kit, kitDark: p.kitDark, accent: p.accent, formation: '4-3-3', xi: [], bench: [] }
}

function toViewTeam(t: TeamXI): ViewTeamSpec {
  return {
    name: t.name,
    color: t.kit,
    colorDark: t.kitDark,
    accent: t.accent,
    tokens: t.xi.map((p) => ({
      id: p.id,
      name: p.name,
      number: p.number,
      x: p.x,
      z: p.z,
      color: p.slot === 'GK' ? t.kitDark : t.kit,
      colorDark: p.slot === 'GK' ? t.kit : t.kitDark,
    })),
  }
}
