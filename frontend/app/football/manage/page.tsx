'use client'

/**
 * /football/manage — Manager Mode: the human game loop.
 *
 * Pick a club, name your XI, choose shape and tactics, save before the
 * matchday deadline — then watch your choices play out on the engine.
 * The House's agents decide at matchday open; a human save after open
 * (before lock) wins for that matchday. Same rules as the agents:
 * 11 starters, one GK, bench ≤ 5, no injured/suspended players.
 */

import { useCallback, useEffect, useMemo, useState } from 'react'
import Link from 'next/link'
import { PortalNav } from '@/components/football/PortalNav'
import '../portal.css'

type SquadPlayer = {
  player_id: string
  name: string
  slot: string
  primary_pos: string
  base_rating: number
  condition?: number
  injury?: unknown
  suspension_matches?: number
  wage_per_matchday_usdc?: string
  form?: number
  morale?: number
}

type Club = {
  agent_id: string
  club_name: string
  formation?: string
  tactical_tags?: string[]
  starters?: string[]
  bench?: string[]
}

type SeasonInfo = {
  season_no?: number
  status?: string
  current_matchday?: number
  matchdays_total?: number
  upcoming?: {
    matchday: number
    home_agent_id: string
    away_agent_id: string
    home_club: string
    away_club: string
    status: string
    deadline_at: string
  }[]
}

const FORMATIONS: Record<string, string[]> = {
  '4-3-3': ['GK', 'RB', 'CB', 'CB', 'LB', 'CDM', 'CM', 'CM', 'LW', 'RW', 'ST'],
  '4-2-3-1': ['GK', 'RB', 'CB', 'CB', 'LB', 'CDM', 'CDM', 'RW', 'CAM', 'LW', 'ST'],
  '4-4-2': ['GK', 'RB', 'CB', 'CB', 'LB', 'CM', 'CM', 'RW', 'LW', 'ST', 'ST'],
  '3-5-2': ['GK', 'CB', 'CB', 'CB', 'RB', 'LB', 'CDM', 'CM', 'CM', 'ST', 'ST'],
  '5-3-2': ['GK', 'RB', 'CB', 'CB', 'CB', 'LB', 'CDM', 'CM', 'CM', 'ST', 'ST'],
  '4-1-4-1': ['GK', 'RB', 'CB', 'CB', 'LB', 'CDM', 'RW', 'CM', 'CM', 'LW', 'ST'],
  '3-4-3': ['GK', 'CB', 'CB', 'CB', 'RB', 'LB', 'CDM', 'CM', 'CM', 'LW', 'RW'],
}

const TAGS = [
  'balanced',
  'high_press',
  'gegenpress',
  'low_block',
  'park_bus',
  'counter',
  'tiki_taka',
  'long_ball',
]

const BENCH_MAX = 5

function posGroup(slot: string): string {
  if (slot === 'GK') return 'GK'
  if (['RB', 'CB', 'LB'].includes(slot)) return 'DEF'
  if (['CDM', 'CM', 'CAM'].includes(slot)) return 'MID'
  return 'FWD'
}

function primaryGroup(pos: string): string {
  const p = String(pos || 'MID').toUpperCase()
  if (p === 'GK') return 'GK'
  if (p === 'DEF') return 'DEF'
  if (p === 'MID') return 'MID'
  return 'FWD'
}

export default function ManagePage() {
  const [clubs, setClubs] = useState<Club[]>([])
  const [clubId, setClubId] = useState('')
  const [squad, setSquad] = useState<SquadPlayer[]>([])
  const [club, setClub] = useState<Club | null>(null)
  const [season, setSeason] = useState<SeasonInfo | null>(null)
  const [formation, setFormation] = useState('4-3-3')
  const [starters, setStarters] = useState<string[]>([])
  const [bench, setBench] = useState<string[]>([])
  const [tags, setTags] = useState<string[]>(['balanced'])
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const loadClubs = useCallback(async () => {
    const r = await fetch('/api/agentic/football/clubs', { cache: 'no-store' })
    const d = await r.json().catch(() => ({}))
    const list: Club[] = d.clubs || d.items || []
    setClubs(list)
    if (list.length && !clubId) setClubId(list[0].agent_id)
  }, [clubId])

  const loadClub = useCallback(async (id: string) => {
    if (!id) return
    setError(null)
    const r = await fetch(`/api/agentic/football/clubs/${id}`, { cache: 'no-store' })
    const d = await r.json().catch(() => ({}))
    if (!r.ok || !d.club) {
      setError('Could not load the club. Is the House API running?')
      return
    }
    setClub(d.club)
    setSquad(d.squad || [])
    setFormation(d.club.formation || '4-3-3')
    setStarters((d.club.starters || []).map((p: unknown) => (typeof p === 'string' ? p : (p as SquadPlayer).player_id)))
    setBench((d.club.bench || []).map((p: unknown) => (typeof p === 'string' ? p : (p as SquadPlayer).player_id)))
    setTags(d.club.tactical_tags || ['balanced'])
  }, [])

  useEffect(() => {
    loadClubs()
    fetch('/api/agentic/football/season', { cache: 'no-store' })
      .then((r) => r.json())
      .then((d) => setSeason(d.season || null))
      .catch(() => {})
  }, [loadClubs])

  useEffect(() => {
    loadClub(clubId)
  }, [clubId, loadClub])

  const byId = useMemo(() => new Map(squad.map((p) => [p.player_id, p])), [squad])

  const available = useMemo(
    () =>
      squad.filter(
        (p) => !p.injury && !(Number(p.suspension_matches) > 0)
      ),
    [squad]
  )

  const slots = FORMATIONS[formation] || FORMATIONS['4-3-3']

  const problems = useMemo(() => {
    const out: string[] = []
    if (starters.length !== 11) out.push(`XI needs exactly 11 starters (has ${starters.length})`)
    if (!starters.some((p) => byId.get(p)?.slot === 'GK'))
      out.push('the XI must include a goalkeeper')
    if (bench.length > BENCH_MAX) out.push(`bench is limited to ${BENCH_MAX}`)
    const dup = starters.length !== new Set(starters).size || bench.length !== new Set(bench).size
    if (dup) out.push('a player cannot appear twice')
    if (starters.some((p) => bench.includes(p))) out.push('a starter cannot also be on the bench')
    return out
  }, [starters, bench, byId])

  const nextFixture = useMemo(() => {
    if (!season?.upcoming || !clubId) return null
    return season.upcoming.find((u) => u.home_agent_id === clubId || u.away_agent_id === clubId) || null
  }, [season, clubId])

  const deadline = nextFixture?.deadline_at ? new Date(nextFixture.deadline_at) : null
  const msLeft = deadline ? deadline.getTime() - Date.now() : null
  const timeLeft =
    msLeft == null
      ? null
      : msLeft <= 0
        ? 'deadline passed'
        : `${Math.floor(msLeft / 3_600_000)}h ${Math.floor((msLeft % 3_600_000) / 60_000)}m left`

  function toggleStarter(pid: string) {
    setSaved(null)
    setStarters((cur) => {
      if (cur.includes(pid)) return cur.filter((x) => x !== pid)
      if (cur.length >= 11) return cur
      return [...cur, pid]
    })
  }

  function toggleBench(pid: string) {
    setSaved(null)
    setBench((cur) => {
      if (cur.includes(pid)) return cur.filter((x) => x !== pid)
      if (cur.length >= BENCH_MAX) return cur
      if (starters.includes(pid)) return cur
      return [...cur, pid]
    })
  }

  function autoFill() {
    setSaved(null)
    const gk = available.find((p) => p.slot === 'GK')
    const rest = available
      .filter((p) => p.player_id !== gk?.player_id)
      .sort((a, b) => {
        const effA = a.base_rating * (a.condition == null ? 1 : Math.max(0.35, a.condition))
        const effB = b.base_rating * (b.condition == null ? 1 : Math.max(0.35, b.condition))
        return effB - effA
      })
    const xi = [gk, ...rest]
      .slice(0, 11)
      .map((p) => p?.player_id)
      .filter((x): x is string => Boolean(x))
    setStarters(xi)
    const bn = rest
      .filter((p) => !xi.includes(p.player_id))
      .slice(0, BENCH_MAX)
      .map((p) => p.player_id)
    setBench(bn)
  }

  async function save() {
    if (!clubId || problems.length) return
    setSaving(true)
    setSaved(null)
    setError(null)
    try {
      const r = await fetch(`/api/agentic/football/clubs/${clubId}/lineup`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          formation,
          starters,
          bench,
          tactical_tags: tags.length ? tags : ['balanced'],
        }),
      })
      const d = await r.json().catch(() => ({}))
      if (!r.ok || !d.success) {
        setError(String(d.detail || d.error || 'The save was rejected — fix the team sheet and try again.'))
        return
      }
      setSaved('Team sheet locked in — the engine plays this shape at the next kick-off.')
    } finally {
      setSaving(false)
    }
  }

  const playerRow = (p: SquadPlayer) => {
    const isStarter = starters.includes(p.player_id)
    const isBench = bench.includes(p.player_id)
    const cond = p.condition == null ? 1 : p.condition
    const condTag = cond < 0.62 ? ' · tired' : ''
    return (
      <li key={p.player_id} className="fd-squad-row" style={{ opacity: p.injury || Number(p.suspension_matches) > 0 ? 0.45 : 1 }}>
        <span className="fd-squad-slot">{p.slot}</span>
        <span className="fd-squad-name">
          {p.name} <small>({p.base_rating}{condTag})</small>
        </span>
        <span className="fd-squad-actions">
          <button
            type="button"
            className={isStarter ? 'fd-btn fd-btn-sm fd-btn-on' : 'fd-btn fd-btn-sm'}
            disabled={!!p.injury || Number(p.suspension_matches) > 0}
            onClick={() => toggleStarter(p.player_id)}
          >
            {isStarter ? 'In XI' : 'XI'}
          </button>
          <button
            type="button"
            className={isBench ? 'fd-btn fd-btn-sm fd-btn-on' : 'fd-btn fd-btn-sm'}
            disabled={!!p.injury || Number(p.suspension_matches) > 0 || isStarter}
            onClick={() => toggleBench(p.player_id)}
          >
            {isBench ? 'On bench' : 'Bench'}
          </button>
        </span>
      </li>
    )
  }

  return (
    <div className="fd-wrap">
      <PortalNav active="/football/manage" />
      <div className="fd-hero">
        <h1 style={{ fontSize: 30 }}>Manager mode</h1>
        <p className="fd-lede">
          You are the manager. Name the XI, pick the shape, set the tone — save before the
          deadline and the engine plays your team sheet. The House agents manage their own
          clubs; your squad is yours.
        </p>
      </div>

      <div className="fd-panel">
        <label className="fd-label" htmlFor="manage-club">
          Your club
        </label>
        <select
          id="manage-club"
          className="fd-input"
          value={clubId}
          onChange={(e) => setClubId(e.target.value)}
        >
          {clubs.map((c) => (
            <option key={c.agent_id} value={c.agent_id}>
              {c.club_name}
            </option>
          ))}
        </select>
        {season?.status === 'open' ? (
          <p className="fd-note">
            Season {season.season_no} · matchday {season.current_matchday} of {season.matchdays_total}
            {nextFixture ? (
              <>
                {' '}· next: {nextFixture.home_club} vs {nextFixture.away_club} (MD {nextFixture.matchday})
                {timeLeft ? `, ${timeLeft}` : ''}
              </>
            ) : null}
          </p>
        ) : (
          <p className="fd-note">No season is open right now — you can still set the team sheet.</p>
        )}
      </div>

      {error ? <p className="fd-error">{error}</p> : null}

      {club ? (
        <>
          <div className="fd-panel">
            <div className="fd-row" style={{ gap: '1rem', flexWrap: 'wrap' }}>
              <div>
                <label className="fd-label" htmlFor="manage-formation">
                  Formation
                </label>
                <select
                  id="manage-formation"
                  className="fd-input"
                  value={formation}
                  onChange={(e) => {
                    setFormation(e.target.value)
                    setSaved(null)
                  }}
                >
                  {Object.keys(FORMATIONS).map((f) => (
                    <option key={f} value={f}>
                      {f}
                    </option>
                  ))}
                </select>
              </div>
              <div style={{ flex: 1, minWidth: 220 }}>
                <span className="fd-label">Tactical tone</span>
                <div className="fd-chip-row">
                  {TAGS.map((t) => (
                    <button
                      key={t}
                      type="button"
                      className={`fd-chip ${tags.includes(t) ? 'fd-chip-on' : ''}`}
                      onClick={() =>
                        setTags((cur) =>
                          cur.includes(t) ? cur.filter((x) => x !== t) : [...cur, t]
                        )
                      }
                    >
                      {t.replace('_', ' ')}
                    </button>
                  ))}
                </div>
              </div>
              <div>
                <button type="button" className="fd-btn" onClick={autoFill}>
                  Auto-pick the strongest XI
                </button>
              </div>
            </div>
          </div>

          <div className="fd-grid-2">
            <div className="fd-panel">
              <h2 style={{ fontSize: 18 }}>The squad</h2>
              <ul className="fd-squad-list">{squad.map(playerRow)}</ul>
            </div>
            <div className="fd-panel">
              <h2 style={{ fontSize: 18 }}>
                Team sheet — {formation}
              </h2>
              <ol className="fd-sheet">
                {slots.map((slot, i) => {
                  const pid = starters[i]
                  const p = pid ? byId.get(pid) : null
                  const fits =
                    !p || p.slot === slot || posGroup(p.slot) === posGroup(slot)
                  return (
                    <li key={`${slot}-${i}`} className={!fits ? 'fd-sheet-misfit' : ''}>
                      <span className="fd-sheet-slot">{slot}</span>
                      <span>{p ? p.name : <em>empty</em>}</span>
                      {p && !fits ? <small> — out of position</small> : null}
                    </li>
                  )
                })}
              </ol>
              <p className="fd-note">
                Bench ({bench.length}/{BENCH_MAX}):{' '}
                {bench.length ? bench.map((b) => byId.get(b)?.name || b).join(', ') : 'nobody'}
              </p>
              {problems.length ? (
                <ul className="fd-error">
                  {problems.map((p) => (
                    <li key={p}>{p}</li>
                  ))}
                </ul>
              ) : null}
              <button
                type="button"
                className="fd-btn fd-btn-primary"
                disabled={saving || problems.length > 0}
                onClick={save}
              >
                {saving ? 'Saving…' : 'Save the team sheet'}
              </button>
              {saved ? <p className="fd-ok">{saved}</p> : null}
            </div>
          </div>

          <p className="fd-note" style={{ marginTop: '1.5rem' }}>
            Watch how the last matchday played out on the{' '}
            <Link href="/football/league">league page</Link>, or read the managers&apos;
            press conferences in the news feed.
          </p>
        </>
      ) : (
        <p className="fd-note">Loading the club…</p>
      )}
    </div>
  )
}
