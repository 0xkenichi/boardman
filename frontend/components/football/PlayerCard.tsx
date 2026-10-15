/**
 * PlayerCard — one AFM player as a card in the Boardman book.
 *
 * Paper card, ink type, a generated crest (no player photos: every original,
 * Nigerian and licence-pending star gets a stable crest from their id), and a
 * tier stamp. Icons carry a slow foil sheen; licence-pending players are
 * greyed with a "coming soon" stamp; real legends get a gold edge and the year
 * they passed. Motion lives in player-card.css and switches off under
 * prefers-reduced-motion.
 */
import type { CSSProperties } from 'react'
import type { AfmPlayer } from '@/lib/afm'
import { isSignable } from '@/lib/afm'
import './player-card.css'

/** Small, stable hash so a player's crest never changes between renders. */
function hash(s: string): number {
  let h = 2166136261
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i)
    h = Math.imul(h, 16777619)
  }
  return h >>> 0
}

// Crest inks: house green, stamp red, slate, ochre, plum, teal — all printed
// on the same cream, so cards read as one set.
const CREST_INKS = ['#256b48', '#b04a32', '#3d4a5c', '#a6782a', '#6b3f62', '#2c6e73']

export function callName(p: AfmPlayer): string {
  return p.persona?.known_as || p.name.split(' ').slice(-1)[0] || p.name
}

function initials(p: AfmPlayer): string {
  const call = callName(p).replace(/[^\p{L}\s-]/gu, '')
  const parts = call.split(/[\s-]+/).filter(Boolean)
  return (parts.length > 1 ? parts[0][0] + parts[1][0] : call.slice(0, 2)).toUpperCase()
}

type Tier = 'icon' | 'headliner' | 'legend' | 'nigeria' | 'star' | 'prospect'

export function tierOf(p: AfmPlayer): Tier {
  const t = p.persona?.tier
  if (t === 'legend' || p.origin === 'legend') return 'legend'
  if (p.origin === 'global_star') return 'star'
  if (t === 'icon') return 'icon'
  if (t === 'headliner') return 'headliner'
  if (p.origin === 'real_ng') return 'nigeria'
  return 'prospect'
}

const STAMP: Record<Tier, string | null> = {
  icon: 'Icon',
  headliner: 'Headliner',
  legend: 'Legend',
  nigeria: 'Nigeria',
  star: null,
  prospect: null,
}

export function PlayerCard({
  player: p,
  index = 0,
  size = 'md',
}: {
  player: AfmPlayer
  /** Position in the grid — staggers the deal-in animation. */
  index?: number
  size?: 'sm' | 'md' | 'lg'
}) {
  const tier = tierOf(p)
  const pending = !isSignable(p)
  const realLegend = p.origin === 'legend'
  const h = hash(p.player_id)
  const style = {
    '--pc-i': Math.min(index, 24),
    '--pc-crest': CREST_INKS[h % CREST_INKS.length],
    '--pc-crest-2': CREST_INKS[(h >> 3) % CREST_INKS.length],
    '--pc-angle': `${(h % 4) * 45 - 45}deg`,
  } as CSSProperties
  const stamp = STAMP[tier]
  const persona = p.persona
  const call = callName(p)
  const showFull = call !== p.name

  return (
    <article
      className={`pc pc-${size} pc-${tier}${pending ? ' pc-pending' : ''}${realLegend ? ' pc-real-legend' : ''}`}
      style={style}
      aria-label={`${p.name}, ${p.slot}, rated ${p.base_rating}${pending ? `, ${p.availability_label ?? 'coming soon'}` : ''}`}
    >
      <header className="pc-top">
        <div className="pc-rating">
          <strong>{p.base_rating}</strong>
          <span>{p.slot}</span>
        </div>
        <span className="pc-nation">{p.nation}</span>
      </header>

      <div className="pc-crest" aria-hidden>
        <span>{initials(p)}</span>
      </div>

      <div className="pc-names">
        <h3 className="pc-call">{call}</h3>
        {showFull ? <p className="pc-full">{persona?.full_name || p.name}</p> : null}
        {persona?.title ? <p className="pc-title">“{persona.title}”</p> : null}
      </div>

      <div className="pc-meta">
        {persona?.archetype ? <span>{persona.archetype}</span> : null}
        {persona?.weapon ? <span className="pc-weapon">{persona.weapon}</span> : null}
        {realLegend && persona?.passed ? <span>Remembered · {persona.passed}</span> : null}
        {persona?.era && !realLegend ? <span>{persona.era}</span> : null}
      </div>

      <footer className="pc-foot">
        {pending ? (
          <span className="pc-soon">{p.availability_label ?? 'Coming soon'}</span>
        ) : (
          <span className="pc-price">
            {Number(p.game_price_usdc).toFixed(2)} <small>USDC</small>
          </span>
        )}
        {stamp ? <span className={`pc-stamp pc-stamp-${tier}`}>{stamp}</span> : null}
      </footer>
    </article>
  )
}
