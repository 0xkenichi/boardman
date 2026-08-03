'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'

const BOT = process.env.NEXT_PUBLIC_TELEGRAM_BOT_URL || 'https://t.me/ClawStationOfficialBot'

const LINKS = [
  { href: '/rematch', label: 'Home', exact: true },
  { href: '/rematch/app', label: 'Play' },
  { href: '/rematch/leaderboard', label: 'Board' },
  { href: '/rematch/minipay', label: 'MiniPay' },
  { href: '/rematch/get-usdc', label: 'Fund' },
]

export function RematchNav() {
  const path = usePathname() || ''
  const isApp = path.startsWith('/rematch/app')

  return (
    <header
      style={{
        position: 'sticky',
        top: 0,
        zIndex: 50,
        borderBottom: '1px solid rgba(255,255,255,0.06)',
        background: 'rgba(7,8,12,0.88)',
        backdropFilter: 'blur(16px)',
        WebkitBackdropFilter: 'blur(16px)',
      }}
    >
      <div
        style={{
          maxWidth: isApp ? '28rem' : '42rem',
          margin: '0 auto',
          padding: '0.7rem 1rem',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: '0.75rem',
        }}
      >
        <Link
          href="/rematch"
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '0.15rem',
            fontWeight: 900,
            letterSpacing: '-0.03em',
            fontSize: '1.05rem',
            textDecoration: 'none',
            color: '#fff',
          }}
        >
          <span style={{ color: '#34d399' }}>Re</span>
          <span>match</span>
        </Link>

        {!isApp && (
          <nav className="rm-desktop-nav">
            {LINKS.map((l) => {
              const active = l.exact
                ? path === l.href
                : path === l.href || path.startsWith(l.href + '/')
              return (
                <Link
                  key={l.href}
                  href={l.href}
                  style={{
                    borderRadius: '0.55rem',
                    padding: '0.4rem 0.65rem',
                    fontSize: '0.75rem',
                    fontWeight: 700,
                    textDecoration: 'none',
                    color: active ? '#34d399' : '#9ca3af',
                    background: active ? 'rgba(16,185,129,0.12)' : 'transparent',
                  }}
                >
                  {l.label}
                </Link>
              )
            })}
          </nav>
        )}

        <div style={{ display: 'flex', alignItems: 'center', gap: '0.45rem' }}>
          {!isApp && (
            <a href={BOT} target="_blank" rel="noreferrer" className="rm-nav-bot">
              Bot
            </a>
          )}
          <Link
            href="/"
            style={{
              borderRadius: 999,
              border: '1px solid rgba(255,255,255,0.1)',
              background: 'rgba(255,255,255,0.03)',
              color: '#d1d5db',
              padding: '0.4rem 0.7rem',
              fontSize: '0.7rem',
              fontWeight: 700,
              textDecoration: 'none',
              whiteSpace: 'nowrap',
            }}
          >
            ← sideQuest
          </Link>
        </div>
      </div>
    </header>
  )
}
