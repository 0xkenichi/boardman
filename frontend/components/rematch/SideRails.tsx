'use client'

/**
 * Wide-screen side atmosphere: game tiles, glow, and depth so the
 * center column doesn't float in empty dark space.
 * Hidden on narrow viewports and mini-app routes so the product stays clean.
 */

import { usePathname } from 'next/navigation'

const LEFT_GAMES = [
  { emoji: '⚽', name: 'EA FC', tag: 'Console · Mobile' },
  { emoji: '🏀', name: 'NBA 2K', tag: 'Console' },
  { emoji: '🔥', name: 'Free Fire', tag: 'Mobile 1v1' },
  { emoji: '🎯', name: 'COD DM', tag: 'Mobile' },
  { emoji: '♟️', name: 'Chess', tag: 'iMessage · App' },
  { emoji: '🎲', name: 'Ludo', tag: 'Casual' },
]

const RIGHT_GAMES = [
  { emoji: '📱', name: 'iMessage', tag: 'GamePigeon' },
  { emoji: '🥊', name: 'Fighting', tag: 'BO sets' },
  { emoji: '🏟️', name: 'eFootball', tag: 'Console' },
  { emoji: '🔫', name: 'Shooters', tag: '1v1 only' },
  { emoji: '🏆', name: 'Public board', tag: 'Open stakes' },
  { emoji: '💎', name: 'USDC lock', tag: 'Fair settle' },
]

const FLOAT_CHIPS_L = ['Lock in', '1v1', 'Arc', 'Screenshot', 'PLAY']
const FLOAT_CHIPS_R = ['Settle', 'Boardman', 'Telegram', 'Stake', 'Win']

function GameCard({
  emoji,
  name,
  tag,
  delay,
}: {
  emoji: string
  name: string
  tag: string
  delay: number
}) {
  return (
    <div className="rm-rail-card" style={{ animationDelay: `${delay}s` }}>
      <span className="rm-rail-emoji" aria-hidden>
        {emoji}
      </span>
      <div className="rm-rail-card-body">
        <div className="rm-rail-card-name">{name}</div>
        <div className="rm-rail-card-tag">{tag}</div>
      </div>
    </div>
  )
}

function RailColumn({
  side,
  games,
  chips,
}: {
  side: 'left' | 'right'
  games: typeof LEFT_GAMES
  chips: string[]
}) {
  return (
    <aside className={`rm-side-rail rm-side-rail--${side}`} aria-hidden>
      <div className="rm-side-rail-glow" />
      <div className="rm-side-rail-inner">
        <div className="rm-side-rail-brand">
          <span className="rm-side-rail-dot" />
          {side === 'left' ? 'Live skill games' : 'Lock · play · settle'}
        </div>
        <div className="rm-side-rail-stack">
          {games.map((g, i) => (
            <GameCard key={g.name} {...g} delay={0.08 * i + (side === 'right' ? 0.2 : 0)} />
          ))}
        </div>
        <div className="rm-side-rail-chips">
          {chips.map((c) => (
            <span key={c} className="rm-side-chip">
              {c}
            </span>
          ))}
        </div>
      </div>
    </aside>
  )
}

export function SideRails() {
  const path = usePathname() || ''
  // Keep mini-app focused; atmosphere is for marketing pages
  if (path === '/app' || path.startsWith('/app/')) return null

  return (
    <div className="rm-side-rails" aria-hidden>
      <RailColumn side="left" games={LEFT_GAMES} chips={FLOAT_CHIPS_L} />
      <RailColumn side="right" games={RIGHT_GAMES} chips={FLOAT_CHIPS_R} />
    </div>
  )
}
