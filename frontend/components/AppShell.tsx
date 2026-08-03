'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'

const NAV = [
  { href: '/rematch/app', label: 'Home', ico: '🏠' },
  { href: '/rematch/app/challenge', label: 'Challenge', ico: '⚔️' },
  { href: '/rematch/app/wallet', label: 'Wallet', ico: '💰' },
  { href: '/rematch/app/match', label: 'Match', ico: '🎮' },
]

/**
 * Mini-app shell under /rematch/app/*
 * Top product nav lives in rematch/layout (RematchNav) — no second brand bar here.
 * Bottom tab bar is the app navigation.
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
      {title ? (
        <div
          style={{
            maxWidth: '28rem',
            margin: '0 auto',
            padding: '0.75rem 1rem 0',
            fontSize: '0.85rem',
            color: '#9ca3af',
          }}
        >
          {title}
        </div>
      ) : null}
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
