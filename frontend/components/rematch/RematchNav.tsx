'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { useState } from 'react'

import { telegramBotUrl } from '@/lib/telegramBot'

const BOT = telegramBotUrl()

type NavLinkDef = {
  href: string
  label: string
  match: (p: string) => boolean
  /** drawerOnly links live in the mobile drawer, not the desktop bar */
  drawerOnly?: boolean
}

const LINKS: NavLinkDef[] = [
  {
    href: '/',
    label: 'Home',
    match: (p: string) => p === '/' || p === '/rematch' || p === '/rematch/',
  },
  {
    href: '/how-it-works',
    label: 'How it works',
    match: (p: string) =>
      p.startsWith('/how-it-works') || p.startsWith('/app/how-to-play'),
  },
  {
    href: '/games',
    label: 'Games',
    match: (p: string) => p.startsWith('/games') || p.startsWith('/football'),
  },
  {
    href: '/arena',
    label: 'Arena',
    match: (p: string) => p.startsWith('/arena') || p.includes('/agentic/arena'),
  },
  {
    href: '/questions',
    label: 'Questions',
    match: (p: string) => p.startsWith('/questions'),
  },
  {
    href: '/builders',
    label: 'Builders',
    match: (p: string) => p.startsWith('/builders') || p.includes('/agentic/docs'),
  },
  // Counter pages: one tap away in the drawer and the chips
  {
    href: '/app',
    label: 'Play',
    match: (p: string) => p === '/app' || p.startsWith('/app/'),
    drawerOnly: true,
  },
  {
    href: '/leaderboard',
    label: 'The board',
    match: (p: string) => p === '/leaderboard' || p.startsWith('/leaderboard'),
    drawerOnly: true,
  },
  {
    href: '/get-usdc',
    label: 'Fund',
    match: (p: string) => p === '/get-usdc' || p.startsWith('/get-usdc'),
    drawerOnly: true,
  },
  {
    href: '/about',
    label: 'About',
    match: (p: string) => p.startsWith('/about'),
    drawerOnly: true,
  },
  {
    href: '/contact',
    label: 'Contact',
    match: (p: string) => p.startsWith('/contact'),
    drawerOnly: true,
  },
]

/**
 * The top bar of the book: paper background, mono links, inked chips.
 * Styles live in app/rematch/rematch.css under .bm-topbar so the bar is
 * themed everywhere it renders, independent of BookShell.
 */
export function RematchNav() {
  const path = usePathname() || ''
  const [open, setOpen] = useState(false)

  return (
    <header className="bm-topbar">
      <div className="bm-topbar-in rm-nav-bar--site">
        <Link href="/" className="bm-logo">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src="/boardman-logo.jpg" alt="" width={26} height={26} />
          <span className="bm-logo-word">Boardman</span>
          <span className="bm-logo-mark">— the book</span>
        </Link>

        {/* Desktop nav — hidden on mobile */}
        <nav aria-label="Boardman" className="bm-toplinks rm-desktop-nav">
          {LINKS.filter((l) => !l.drawerOnly).map((l) => (
            <Link key={l.href} href={l.href} className={l.match(path) ? 'on' : ''}>
              {l.label}
            </Link>
          ))}
        </nav>

        <div className="bm-topchips">
          <Link href="/app" className="bm-chip bm-chip--ink">
            Play
          </Link>
          <a href={BOT} target="_blank" rel="noreferrer" className="bm-chip">
            Bot
          </a>
          <a
            href="https://playingsidequest.fun"
            target="_blank"
            rel="noreferrer"
            className="bm-chip bm-chip--dim"
          >
            sideQuest
          </a>
          {/* Mobile hamburger — shown under 760px via .rm-nav-hamburger rules */}
          <button
            type="button"
            aria-label="Toggle menu"
            onClick={() => setOpen((v) => !v)}
            className="bm-burger rm-nav-hamburger"
          >
            {open ? '✕' : '☰'}
          </button>
        </div>
      </div>

      {/* Mobile drawer */}
      {open ? (
        <nav aria-label="Boardman mobile" className="bm-topdrawer rm-mobile-nav">
          {LINKS.map((l) => (
            <Link
              key={l.href}
              href={l.href}
              onClick={() => setOpen(false)}
              className={l.match(path) ? 'on' : ''}
            >
              {l.label}
            </Link>
          ))}
          <a href={BOT} target="_blank" rel="noreferrer" onClick={() => setOpen(false)}>
            Telegram bot ↗
          </a>
        </nav>
      ) : null}
    </header>
  )
}
