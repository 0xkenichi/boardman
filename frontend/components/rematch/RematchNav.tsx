'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'

import { telegramBotUrl } from '@/lib/telegramBot'

const BOT = telegramBotUrl()

/** Full Boardman product nav — keep in sync with public/boardman-nav.js */
const LINKS = [
  { href: '/', label: 'Home', match: (p: string) => p === '/' || p === '/rematch' || p === '/rematch/' },
  { href: '/app', label: 'Play', match: (p: string) => p === '/app' || p.startsWith('/app/') },
  {
    href: '/agentic/arena.html',
    label: 'Arena',
    match: (p: string) => p.includes('/agentic/arena'),
    external: true,
  },
  {
    href: '/agentic/football-managers.html',
    label: 'AFM',
    match: (p: string) => p.includes('/agentic/football-managers'),
    external: true,
  },
  {
    href: '/agentic/hub.html',
    label: 'Hub',
    match: (p: string) => p.includes('/agentic/hub'),
    external: true,
  },
  {
    href: '/agentic/docs.html',
    label: 'Docs',
    match: (p: string) => p.includes('/agentic/docs'),
    external: true,
  },
  {
    href: '/leaderboard',
    label: 'Board',
    match: (p: string) => p === '/leaderboard' || p.startsWith('/leaderboard'),
  },
  {
    href: '/get-usdc',
    label: 'Fund',
    match: (p: string) => p === '/get-usdc' || p.startsWith('/get-usdc'),
  },
] as const

function NavLink({
  href,
  label,
  active,
  external,
}: {
  href: string
  label: string
  active: boolean
  external?: boolean
}) {
  const style: React.CSSProperties = {
    borderRadius: '0.55rem',
    padding: '0.4rem 0.65rem',
    fontSize: '0.75rem',
    fontWeight: 700,
    textDecoration: 'none',
    color: active ? '#34d399' : '#9ca3af',
    background: active ? 'rgba(16,185,129,0.12)' : 'transparent',
    whiteSpace: 'nowrap',
  }
  if (external) {
    return (
      <a href={href} style={style}>
        {label}
      </a>
    )
  }
  return (
    <Link href={href} style={style}>
      {label}
    </Link>
  )
}

export function RematchNav() {
  const path = usePathname() || ''

  return (
    <header
      style={{
        position: 'fixed',
        top: 0,
        left: 0,
        right: 0,
        zIndex: 200,
        borderBottom: '1px solid rgba(255,255,255,0.1)',
        background: 'rgba(7,8,12,0.94)',
        backdropFilter: 'blur(18px)',
        WebkitBackdropFilter: 'blur(18px)',
        boxShadow: '0 8px 24px rgba(0,0,0,0.35)',
      }}
    >
      <div
        className="rm-nav-bar rm-nav-bar--site"
        style={{
          margin: '0 auto',
          padding: '0.65rem 1rem',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: '0.75rem',
          flexWrap: 'wrap',
          maxWidth: 1100,
        }}
      >
        <Link
          href="/"
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '0.45rem',
            fontWeight: 900,
            letterSpacing: '-0.03em',
            fontSize: '1.05rem',
            textDecoration: 'none',
            color: '#fff',
            whiteSpace: 'nowrap',
          }}
        >
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src="/boardman-logo.jpg"
            alt=""
            width={28}
            height={28}
            style={{ borderRadius: 8, objectFit: 'cover' }}
          />
          <span>
            <span style={{ color: '#34d399' }}>Board</span>
            <span>man</span>
          </span>
        </Link>

        <nav
          aria-label="Boardman"
          className="rm-desktop-nav"
          style={{
            display: 'flex',
            flexWrap: 'wrap',
            alignItems: 'center',
            gap: '0.2rem',
            flex: 1,
            justifyContent: 'center',
            minWidth: 0,
          }}
        >
          {LINKS.map((l) => (
            <NavLink
              key={l.href}
              href={l.href}
              label={l.label}
              active={l.match(path)}
              external={'external' in l && l.external}
            />
          ))}
        </nav>

        <div style={{ display: 'flex', alignItems: 'center', gap: '0.45rem', flexWrap: 'wrap' }}>
          <a
            href={BOT}
            target="_blank"
            rel="noreferrer"
            className="rm-nav-bot"
            style={{
              borderRadius: 999,
              background: '#7c3aed',
              color: '#fff',
              padding: '0.4rem 0.75rem',
              fontSize: '0.72rem',
              fontWeight: 700,
              textDecoration: 'none',
            }}
          >
            Bot
          </a>
          <a
            href="https://playingsidequest.fun"
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
            sideQuest
          </a>
        </div>
      </div>
    </header>
  )
}
