'use client'

import { LIVE_ROOMS, REMATCH_GROUP_URL } from '@/lib/rematchLinks'

type Props = {
  /** compact = tighter card for mini-app home */
  variant?: 'full' | 'compact'
}

/**
 * Inform players: join Telegram group for per-platform live rooms
 * and public stakes vs random opponents.
 */
export function LiveRoomsCard({ variant = 'full' }: Props) {
  const compact = variant === 'compact'

  return (
    <div
      className="rm-card"
      style={{
        borderColor: 'rgba(52,211,153,0.28)',
        background:
          'linear-gradient(145deg, rgba(16,185,129,0.1) 0%, rgba(16,20,28,0.9) 55%, rgba(7,8,12,0.95) 100%)',
      }}
    >
      <p className="rm-section-title" style={{ marginBottom: '0.35rem' }}>
        Live rooms · public games
      </p>
      <h2 className="rm-h2" style={{ marginBottom: '0.45rem' }}>
        Join the Telegram group
      </h2>
      <p className="rm-muted" style={{ margin: '0 0 0.85rem' }}>
        Want random opponents or a live lobby? Jump into the group — there&apos;s a{' '}
        <strong style={{ color: '#e5e7eb' }}>room per platform</strong> so you can browse open
        games, post a public stake, and play whoever&apos;s ready.
      </p>

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: compact ? '1fr 1fr' : '1fr 1fr',
          gap: '0.5rem',
          marginBottom: '0.9rem',
        }}
      >
        {LIVE_ROOMS.map((r) => (
          <div
            key={r.id}
            style={{
              borderRadius: 14,
              border: '1px solid rgba(255,255,255,0.08)',
              background: 'rgba(0,0,0,0.32)',
              padding: '0.65rem 0.7rem',
              transition: 'border-color 0.15s, background 0.15s',
            }}
          >
            <div style={{ fontWeight: 800, fontSize: '0.88rem' }}>
              {r.emoji} {r.label}
            </div>
            {!compact ? (
              <div className="rm-muted" style={{ fontSize: '0.7rem', marginTop: 3, marginBottom: 0 }}>
                {r.hint}
              </div>
            ) : null}
          </div>
        ))}
      </div>

      <ul
        className="rm-muted"
        style={{
          margin: '0 0 0.9rem',
          paddingLeft: '1.1rem',
          fontSize: '0.8rem',
          lineHeight: 1.55,
        }}
      >
        <li>See who&apos;s live in Mobile / Console / PC / iMessage</li>
        <li>Post a public challenge — random players can accept &amp; lock</li>
        <li>Or pick an open game and stake vs whoever posted it</li>
      </ul>

      <a
        href={REMATCH_GROUP_URL}
        target="_blank"
        rel="noreferrer"
        className="rm-btn rm-btn-primary"
      >
        💬 Join Telegram live rooms
      </a>
      <p
        className="rm-muted"
        style={{ margin: '0.55rem 0 0', fontSize: '0.72rem', textAlign: 'center' }}
      >
        Friends only? Challenge them here in the app. Randoms → group rooms.
      </p>
    </div>
  )
}
