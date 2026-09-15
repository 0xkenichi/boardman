'use client'

/**
 * The first FM tool: a club's squad screen.
 *
 * Football Manager layout, adapted to what the engine actually knows:
 * a sortable squad table (status, name, ability, form, condition, morale,
 * injury, wage, value, contract) with position filters, and a player detail
 * panel grouping attributes into Physical / Technical / Mental — the FM
 * profile structure. Read-only V1: transfers and in-match tools are their
 * own roadmap rows.
 */
import { useEffect, useMemo, useState } from 'react'
import { useParams } from 'next/navigation'
import Link from 'next/link'
import { PortalNav } from '@/components/football/PortalNav'
import { PlayerProfileTabs } from '@/components/football/PlayerProfileTabs'
import { fetchClubSquad, type ClubSquad, type SquadPlayer } from '@/lib/afm'
import '../../portal.css'
import '../squad.css'

type SortKey =
  | 'status'
  | 'name'
  | 'slot'
  | 'ability'
  | 'form'
  | 'fitness'
  | 'morale'
  | 'wage'
  | 'value'
  | 'contract'
type Group = 'All' | 'GK' | 'DEF' | 'MID' | 'FWD'

const GROUP_OF: Record<string, Group> = {
  GK: 'GK', RB: 'DEF', CB: 'DEF', LB: 'DEF',
  CDM: 'MID', CM: 'MID', CAM: 'MID',
  RW: 'FWD', ST: 'FWD', LW: 'FWD',
}
const STATUS_RANK: Record<string, number> = { starter: 0, bench: 1, squad: 2 }
const STATUS_LABEL: Record<string, string> = { starter: 'ST', bench: 'BENCH', squad: 'SQUAD' }

const COLUMNS: { key: SortKey; label: string; sortable: boolean }[] = [
  { key: 'status', label: 'Status', sortable: true },
  { key: 'name', label: 'Player', sortable: true },
  { key: 'slot', label: 'Pos', sortable: true },
  { key: 'ability', label: 'Ability', sortable: true },
  { key: 'form', label: 'Form', sortable: true },
  { key: 'fitness', label: 'Cond', sortable: true },
  { key: 'morale', label: 'Moral', sortable: true },
  { key: 'wage', label: 'Wage/md', sortable: true },
  { key: 'value', label: 'Value', sortable: true },
  { key: 'contract', label: 'Contract', sortable: true },
]

const GROUPS: Group[] = ['All', 'GK', 'DEF', 'MID', 'FWD']

function money(v: string | number | undefined): string {
  const n = Number(v ?? 0)
  if (!Number.isFinite(n)) return '—'
  return n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function barClass(v: number, good: number, mid: number): string {
  if (v >= good) return 'good'
  if (v >= mid) return 'mid'
  return 'low'
}

export default function SquadPage() {
  const params = useParams<{ agent_id: string }>()
  const agentId = params?.agent_id ?? ''
  const [data, setData] = useState<ClubSquad | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [search, setSearch] = useState('')
  const [group, setGroup] = useState<Group>('All')
  const [sortKey, setSortKey] = useState<SortKey>('status')
  const [sortDir, setSortDir] = useState<1 | -1>(1)
  const [selectedId, setSelectedId] = useState<string | null>(null)

  useEffect(() => {
    let alive = true
    fetchClubSquad(agentId)
      .then((d) => {
        if (!alive) return
        setData(d)
        setSelectedId(d.squad[0]?.player_id ?? null)
      })
      .catch((e: unknown) => {
        if (alive) setError(e instanceof Error ? e.message : String(e))
      })
    return () => {
      alive = false
    }
  }, [agentId])

  const rows = useMemo(() => {
    if (!data) return []
    const q = search.trim().toLowerCase()
    let out = data.squad.filter((p) => {
      if (group !== 'All' && GROUP_OF[p.slot] !== group) return false
      if (q && !p.name.toLowerCase().includes(q) && !p.slot.toLowerCase().includes(q)) return false
      return true
    })
    const val = (p: SquadPlayer, k: SortKey): number | string => {
      switch (k) {
        case 'status': return STATUS_RANK[p.status] ?? 3
        case 'name': return p.name.toLowerCase()
        case 'slot': return p.slot
        case 'ability': return p.base_rating ?? 0
        case 'form': return p.form ?? 0
        case 'fitness': return p.fitness ?? 0
        case 'morale': return p.morale ?? 0
        case 'wage': return Number(p.wage_per_matchday_usdc ?? 0)
        case 'value': return Number(p.game_price_usdc ?? 0)
        case 'contract': return p.contract?.years_left ?? 0
      }
    }
    out = [...out].sort((a, b) => {
      const va = val(a, sortKey)
      const vb = val(b, sortKey)
      if (typeof va === 'string' && typeof vb === 'string') return va.localeCompare(vb) * sortDir
      return ((va as number) - (vb as number)) * sortDir
    })
    return out
  }, [data, search, group, sortKey, sortDir])

  const selected = data?.squad.find((p) => p.player_id === selectedId) ?? null

  const onSort = (key: SortKey) => {
    if (key === sortKey) setSortDir((d) => (d === 1 ? -1 : 1))
    else {
      setSortKey(key)
      setSortDir(1)
    }
  }

  if (error) {
    return (
      <div className="fd-wrap">
        <PortalNav active="/football/owner" />
        <div className="fd-hero">
          <h1 style={{ fontSize: 30 }}>Squad room</h1>
        </div>
        <div className="fd-err">
          Couldn’t reach the club store — the agent services may be offline in this environment.
          This screen shows the real FM-style squad once the backend is running.
        </div>
        <p>
          <Link href="/football/owner">← Back to the owner hub</Link>
        </p>
      </div>
    )
  }

  if (!data) {
    return (
      <div className="fd-wrap">
        <PortalNav active="/football/owner" />
        <div className="fd-hero">
          <h1 style={{ fontSize: 30 }}>Squad room</h1>
          <p className="fd-lede">Loading the dressing room…</p>
        </div>
      </div>
    )
  }

  const club = data.club

  return (
    <div className="fd-wrap">
      <PortalNav active="/football/owner" />

      <div className="fd-hero sq-head">
        <div>
          <h1 style={{ fontSize: 30 }}>{club.club_name}</h1>
          <p className="fd-lede">
            <span className="fd-clubmeta">{club.agent_id}</span> · {club.formation} ·{' '}
            {(club.tactical_tags ?? []).join(', ') || 'balanced'} · {club.roster_size} players ·{' '}
            spend {money(club.spend_usdc)} of {money(club.budget_usdc)} USDC
          </p>
        </div>
        <Link href="/football/owner" className="sq-back">
          ← Owner hub
        </Link>
      </div>

      <div className="sq-toolbar">
        <input
          className="sq-search"
          placeholder="Search name or position…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <div className="sq-groups">
          {GROUPS.map((g) => (
            <button
              key={g}
              className={g === group ? 'sq-chip on' : 'sq-chip'}
              onClick={() => setGroup(g)}
            >
              {g}
            </button>
          ))}
        </div>
      </div>

      <div className="sq-body">
        <div className="sq-table-wrap">
          <table className="sq-table">
            <thead>
              <tr>
                {COLUMNS.map((c) => (
                  <th key={c.key} onClick={() => c.sortable && onSort(c.key)} className={c.sortable ? 'sortable' : ''}>
                    {c.label}
                    {sortKey === c.key ? (sortDir === 1 ? ' ↑' : ' ↓') : ''}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((p) => (
                <tr
                  key={p.player_id}
                  className={selectedId === p.player_id ? 'on' : ''}
                  onClick={() => setSelectedId(p.player_id)}
                >
                  <td>
                    <span className={`sq-status ${p.status}`}>{STATUS_LABEL[p.status]}</span>
                  </td>
                  <td className="sq-name">{p.name}</td>
                  <td>
                    <span className="sq-slot">{p.slot}</span>
                  </td>
                  <td className="sq-ability">{p.base_rating ?? '—'}</td>
                  <td className="sq-form">{p.form != null ? p.form.toFixed(1) : '—'}</td>
                  <td>
                    <span className={`sq-bar ${barClass(p.fitness ?? 0, 0.9, 0.7)}`}>
                      <span style={{ width: `${Math.round((p.fitness ?? 0) * 100)}%` }} />
                    </span>
                  </td>
                  <td>
                    <span className={`sq-bar ${barClass(p.morale ?? 0, 0.8, 0.6)}`}>
                      <span style={{ width: `${Math.round((p.morale ?? 0) * 100)}%` }} />
                    </span>
                  </td>
                  <td className="sq-injury">{p.injury || '—'}</td>
                  <td>{money(p.wage_per_matchday_usdc)}</td>
                  <td>{money(p.game_price_usdc)}</td>
                  <td>{p.contract?.years_left ?? '—'}y</td>
                </tr>
              ))}
              {rows.length === 0 && (
                <tr>
                  <td colSpan={COLUMNS.length} className="sq-empty">
                    No players match — try another filter or search.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>        {selected && <PlayerProfileTabs player={selected} squad={data.squad} />}
      </div>
    </div>
  )
}

/** Full-width FM player profile: role suitability, attributes, contract + season. */

