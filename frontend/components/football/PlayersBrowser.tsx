'use client'
/**
 * The players page body: every AFM player as a card, with the cast grouped
 * the way a fan meets it — Icons, each nation's headliner, Nigeria, Legends —
 * then the whole signable pool, filterable by position, nation and name.
 * Reads the static catalog snapshot (works with the backend down).
 */
import { useEffect, useMemo, useState } from 'react'
import { loadCatalog, isSignable, type AfmPlayer } from '@/lib/afm'
import { PlayerCard, callName, tierOf } from './PlayerCard'

type View = 'all' | 'icons' | 'headliners' | 'nigeria' | 'legends' | 'soon'

const VIEWS: { id: View; label: string }[] = [
  { id: 'all', label: 'Everyone' },
  { id: 'icons', label: 'Icons' },
  { id: 'headliners', label: 'Headliners' },
  { id: 'nigeria', label: 'Nigeria' },
  { id: 'legends', label: 'Legends' },
  { id: 'soon', label: 'Coming soon' },
]
const SLOTS = ['GK', 'RB', 'CB', 'LB', 'CDM', 'CM', 'CAM', 'RW', 'LW', 'ST'] as const
const PAGE = 48

const byRating = (a: AfmPlayer, b: AfmPlayer) =>
  (b.base_rating ?? 0) - (a.base_rating ?? 0) || callName(a).localeCompare(callName(b))

function inView(p: AfmPlayer, view: View): boolean {
  const tier = tierOf(p)
  switch (view) {
    case 'icons':
      return tier === 'icon'
    case 'headliners':
      return tier === 'headliner'
    case 'nigeria':
      return p.nation === 'NG' && tier !== 'legend'
    case 'legends':
      return tier === 'legend'
    case 'soon':
      return !isSignable(p)
    default:
      return true
  }
}

function Row({ title, note, players }: { title: string; note: string; players: AfmPlayer[] }) {
  if (!players.length) return null
  return (
    <section className="pl-row" aria-label={title}>
      <header className="pl-row-head">
        <h2>{title}</h2>
        <p>{note}</p>
      </header>
      <div className="pl-rail">
        {players.map((p, i) => (
          <div className="pl-rail-item" key={p.player_id}>
            <PlayerCard player={p} index={i} size="sm" />
          </div>
        ))}
      </div>
    </section>
  )
}

export function PlayersBrowser() {
  const [players, setPlayers] = useState<AfmPlayer[] | null>(null)
  const [error, setError] = useState(false)
  const [view, setView] = useState<View>('all')
  const [slot, setSlot] = useState<string>('')
  const [nation, setNation] = useState<string>('')
  const [q, setQ] = useState('')
  const [shown, setShown] = useState(PAGE)

  useEffect(() => {
    loadCatalog()
      .then((c) => setPlayers(c.players))
      .catch(() => setError(true))
  }, [])

  useEffect(() => setShown(PAGE), [view, slot, nation, q])

  const all = useMemo(() => (players ?? []).slice().sort(byRating), [players])
  const nations = useMemo(() => Array.from(new Set(all.map((p) => p.nation))).sort(), [all])
  const counts = useMemo(
    () => ({ signable: all.filter(isSignable).length, soon: all.filter((p) => !isSignable(p)).length }),
    [all],
  )

  const filtered = useMemo(() => {
    const needle = q.trim().toLowerCase()
    return all.filter((p) => {
      if (!inView(p, view)) return false
      // "Everyone" shows the signable pool below the curated rows
      if (view === 'all' && !isSignable(p)) return false
      if (slot && p.slot !== slot) return false
      if (nation && p.nation !== nation) return false
      if (needle) {
        const hay = `${p.name} ${callName(p)} ${p.persona?.title ?? ''} ${p.persona?.full_name ?? ''}`.toLowerCase()
        if (!hay.includes(needle)) return false
      }
      return true
    })
  }, [all, view, slot, nation, q])

  const browsing = view === 'all' && !slot && !nation && !q.trim()

  return (
    <div className="pl">
      <header className="pl-hero">
        <p className="pl-eyebrow">The players · season one</p>
        <h1>
          A world of players. <em>Pick your squad.</em>
        </h1>
        <p className="pl-lede">
          Boardman&apos;s own cast from 58 nations — every one with a name the crowd can chant, a
          weapon and a rival — plus Nigeria&apos;s stars. Real legends and global stars wait for
          their licence.
        </p>
        {players ? (
          <p className="pl-counts">
            <strong>{counts.signable}</strong> to sign · <strong>{counts.soon}</strong> coming soon
          </p>
        ) : null}
      </header>

      <div className="pl-bar" role="toolbar" aria-label="Filter players">
        <div className="pl-tabs" role="tablist">
          {VIEWS.map((v) => (
            <button
              key={v.id}
              role="tab"
              aria-selected={view === v.id}
              className={`pl-tab${view === v.id ? ' on' : ''}`}
              onClick={() => setView(v.id)}
            >
              {v.label}
            </button>
          ))}
        </div>
        <div className="pl-filters">
          <div className="pl-slots" aria-label="Position">
            {SLOTS.map((s) => (
              <button
                key={s}
                className={`pl-chip${slot === s ? ' on' : ''}`}
                aria-pressed={slot === s}
                onClick={() => setSlot(slot === s ? '' : s)}
              >
                {s}
              </button>
            ))}
          </div>
          <select className="pl-select" value={nation} onChange={(e) => setNation(e.target.value)} aria-label="Nation">
            <option value="">All nations</option>
            {nations.map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </select>
          <input
            className="pl-search"
            type="search"
            placeholder="Search a name or title"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            aria-label="Search players"
          />
        </div>
      </div>

      {error ? <p className="pl-empty">The player book is unavailable right now. Try again shortly.</p> : null}
      {!players && !error ? (
        <div className="pl-grid" aria-busy>
          {Array.from({ length: 8 }, (_, i) => (
            <div className="pl-skel" key={i} />
          ))}
        </div>
      ) : null}

      {players && browsing ? (
        <>
          <Row title="Icons" note="Sixteen leads. Each one has a rival." players={all.filter((p) => tierOf(p) === 'icon')} />
          <Row
            title="Headliners"
            note="The face of every nation's cast."
            players={all.filter((p) => tierOf(p) === 'headliner')}
          />
          <Row
            title="Nigeria"
            note="Super Eagles and the originals they inspired."
            players={all.filter((p) => p.nation === 'NG' && tierOf(p) !== 'legend')}
          />
          <Row
            title="Legends · coming soon"
            note="Remembered greats, waiting on a licence or their family's blessing."
            players={all.filter((p) => tierOf(p) === 'legend')}
          />
        </>
      ) : null}

      {players ? (
        <section aria-label="Players">
          {browsing ? (
            <header className="pl-row-head">
              <h2>Everyone you can sign</h2>
              <p>Best first. {filtered.length} players.</p>
            </header>
          ) : (
            <p className="pl-result">{filtered.length} players</p>
          )}
          {filtered.length ? (
            <div className="pl-grid">
              {filtered.slice(0, shown).map((p, i) => (
                <PlayerCard key={p.player_id} player={p} index={i % PAGE} />
              ))}
            </div>
          ) : (
            <p className="pl-empty">Nobody matches that. Try another position or nation.</p>
          )}
          {shown < filtered.length ? (
            <button className="pl-more" onClick={() => setShown(shown + PAGE)}>
              Show {Math.min(PAGE, filtered.length - shown)} more
            </button>
          ) : null}
        </section>
      ) : null}
    </div>
  )
}
