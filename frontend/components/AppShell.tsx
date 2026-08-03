'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'

const NAV = [
  { href: '/rematch/app', label: 'Home', ico: '🏠' },
  { href: '/rematch/app/challenge', label: 'Challenge', ico: '⚔️' },
  { href: '/rematch/app/wallet', label: 'Wallet', ico: '💰' },
  { href: '/rematch/app/match', label: 'Match', ico: '🎮' },
]

export function AppShell({
  children,
  title,
}: {
  children: React.ReactNode
  title?: string
}) {
  const path = usePathname() || ''
  return (
    <div className="rm-page">
      <header
        style={{
          borderBottom: '1px solid #1f2937',
          padding: '0.75rem 1rem',
        }}
      >
        <div
          style={{
            maxWidth: '28rem',
            margin: '0 auto',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
          }}
        >
          <Link href="/rematch" style={{ fontSize: '0.8rem', color: '#6b7280' }}>
            ← Rematch
          </Link>
          <span style={{ fontWeight: 800, letterSpacing: '-0.02em' }}>
            <span style={{ color: '#34d399' }}>Re</span>match
          </span>
          <a
            href="https://t.me/ClawStationOfficialBot"
            target="_blank"
            rel="noreferrer"
            style={{ fontSize: '0.75rem', color: '#34d399', fontWeight: 600 }}
          >
            Bot
          </a>
        </div>
        {title ? (
          <div style={{ maxWidth: '28rem', margin: '0.5rem auto 0', fontSize: '0.85rem', color: '#9ca3af' }}>
            {title}
          </div>
        ) : null}
      </header>
      <div className="rm-wrap">{children}</div>
      <nav className="rm-nav">
        <div className="rm-nav-inner">
          {NAV.map((n) => {
            const active =
              n.href === '/rematch/app'
                ? path === '/rematch/app'
                : path.startsWith(n.href)
            return (
              <Link key={n.href} href={n.href} className={active ? 'active' : ''}>
                <span className="ico">{n.ico}</span>
                {n.label}
              </Link>
            )
          })}
        </div>
      </nav>
    </div>
  )
}
