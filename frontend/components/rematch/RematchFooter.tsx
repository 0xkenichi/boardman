'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'

export function RematchFooter() {
  const path = usePathname() || ''
  const isApp = path.startsWith('/rematch/app')

  return (
    <footer
      style={{
        borderTop: '1px solid rgba(255,255,255,0.06)',
        background: 'rgba(7,8,12,0.95)',
        paddingBottom: isApp ? '5.5rem' : 0,
      }}
    >
      <div
        style={{
          maxWidth: isApp ? '28rem' : '42rem',
          margin: '0 auto',
          padding: '1.1rem 1rem',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: '0.65rem',
        }}
      >
        <p style={{ margin: 0, fontSize: '0.8rem', color: '#6b7280' }}>
          <span style={{ fontWeight: 800, color: '#9ca3af' }}>
            <span style={{ color: '#34d399' }}>Re</span>match
          </span>{' '}
          by sideQuest
        </p>
        <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', justifyContent: 'center', gap: '0.65rem' }}>
          <Link href="/rematch" style={{ fontSize: '0.75rem', color: '#6b7280', textDecoration: 'none' }}>
            Home
          </Link>
          <Link
            href="/rematch/leaderboard"
            style={{ fontSize: '0.75rem', color: '#6b7280', textDecoration: 'none' }}
          >
            Board
          </Link>
          <Link
            href="/"
            style={{
              fontSize: '0.75rem',
              fontWeight: 700,
              color: '#d1d5db',
              textDecoration: 'none',
              border: '1px solid rgba(255,255,255,0.1)',
              borderRadius: 999,
              padding: '0.35rem 0.7rem',
            }}
          >
            Go back to sideQuest
          </Link>
        </div>
      </div>
    </footer>
  )
}
