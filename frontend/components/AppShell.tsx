'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'

const NAV = [
  { href: '/rematch/app', label: 'Home', ico: '🏠' },
  { href: '/rematch/app/challenge', label: 'Challenge', ico: '⚔️' },
  { href: '/rematch/app/match', label: 'Match', ico: '🎮' },
  { href: '/rematch/app/wallet', label: 'Wallet', ico: '💰' },
]

/**
 * Mini-app shell under /rematch/app/*
 * Product top nav is in rematch/layout; this is content + bottom tabs.
 */
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
      <div className="rm-wrap">
        {title ? (
          <div style={{ marginBottom: '0.85rem' }}>
            <h1
              style={{
                margin: 0,
                fontSize: '1.15rem',
                fontWeight: 800,
                letterSpacing: '-0.02em',
                color: '#f3f4f6',
              }}
            >
              {title}
            </h1>
          </div>
        ) : null}
        {children}
      </div>
      <nav className="rm-nav" aria-label="Rematch app">
        <div className="rm-nav-inner">
          {NAV.map((n) => {
            const active =
              n.href === '/rematch/app'
                ? path === '/rematch/app'
                : path.startsWith(n.href)
            return (
              <Link key={n.href} href={n.href} className={active ? 'active' : ''}>
                <span className="ico" aria-hidden>
                  {n.ico}
                </span>
                {n.label}
              </Link>
            )
          })}
        </div>
      </nav>
    </div>
  )
}
