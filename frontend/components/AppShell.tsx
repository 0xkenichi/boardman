'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'

const NAV = [
  { href: '/app', label: 'Home', ico: '🏠' },
  { href: '/app/challenge', label: 'Challenge', ico: '⚔️' },
  { href: '/app/match', label: 'Match', ico: '🎮' },
  { href: '/app/wallet', label: 'Wallet', ico: '💰' },
]

/**
 * Mini-app shell under /app/* (clean Boardman URLs).
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
            <p className="rm-label" style={{ marginBottom: '0.25rem' }}>
              Boardman · play
            </p>
            <h1 className="rm-h1">{title}</h1>
          </div>
        ) : null}
        {children}
      </div>
      <nav className="rm-nav" aria-label="Boardman app">
        <div className="rm-nav-inner">
          {NAV.map((n) => {
            const active =
              n.href === '/app' ? path === '/app' : path.startsWith(n.href)
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
