'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { BRAND } from '@/lib/brand'
import { telegramBotUrl } from '@/lib/telegramBot'

const BOT = telegramBotUrl()

const FOOTER_LINKS = [
  { href: '/', label: 'Home' },
  { href: '/app', label: 'Play' },
  { href: '/arena', label: 'Arena' },
  { href: '/games', label: 'Games' },
  { href: '/builders', label: 'Builders' },
  { href: '/how-it-works', label: 'How it works' },
  { href: '/questions', label: 'Questions' },
  { href: '/leaderboard', label: 'The board' },
  { href: '/get-usdc', label: 'Fund' },
  { href: '/about', label: 'About' },
  { href: '/contact', label: 'Contact' },
  { href: '/minipay', label: 'MiniPay' },
] as const

/**
 * The colophon at the back of the book: ruled top line, mono links,
 * paper ink. Styles live in rematch.css under .bm-colophon.
 */
export function RematchFooter() {
  const path = usePathname() || ''
  const inApp = path === '/app' || path.startsWith('/app/')

  return (
    <footer className="bm-colophon" style={inApp ? { paddingBottom: '6.5rem' } : undefined}>
      <div className="bm-colophon-in">
        <p className="bm-colophon-brand">
          Boardman <em>— the book</em>
        </p>
        <div className="bm-colophon-links">
          {FOOTER_LINKS.map((l) => (
            <Link key={l.href} href={l.href}>
              {l.label}
            </Link>
          ))}
          <a href={`mailto:${BRAND.email}`}>{BRAND.email}</a>
          <a href={BOT} target="_blank" rel="noreferrer">
            Bot ↗
          </a>
          <a href="https://playingsidequest.fun" target="_blank" rel="noreferrer">
            sideQuest ↗
          </a>
        </div>
        <p className="bm-colophon-fine">ARC TESTNET · DUAL-LOCK ESCROW · FAIR · FAST · YOURS TO KEEP</p>
      </div>
    </footer>
  )
}
