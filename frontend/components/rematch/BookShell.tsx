'use client'

/**
 * BookShell — the rm AppShell wearing the bookmaker's day-book.
 * Same NAV and layout contract as components/AppShell.tsx, but the
 * page renders on Boardman paper (book.css) with the /v2 type stack.
 * Used by how-to-play, challenge and contact; the rest of /app keeps
 * the glass rm-* system untouched.
 */

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import '@fontsource-variable/big-shoulders'
import '@fontsource/instrument-serif'
import '@fontsource/instrument-serif/400-italic.css'
import '@fontsource/space-mono'
import './book.css'

const NAV = [
  { href: '/app', label: 'Home', ico: '🏠' },
  { href: '/app/challenge', label: 'Challenge', ico: '⚔️' },
  { href: '/app/match', label: 'Match', ico: '🎮' },
  { href: '/app/wallet', label: 'Wallet', ico: '💰' },
]

export function BookShell({
  children,
  title,
}: {
  children: React.ReactNode
  title?: string
}) {
  const path = usePathname() || ''
  return (
    <div className="bm-book">
      <div className="rm-wrap">
        {title ? (
          <div className="bk-head">
            <p className="bk-eyebrow">BOARDMAN · THE BOOK</p>
            <h1>{title}</h1>
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
