'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { BRAND } from '@/lib/brand'
import { telegramBotUrl } from '@/lib/telegramBot'

const BOT = telegramBotUrl()

const FOOTER_LINKS = [
  { href: '/', label: 'Home' },
  { href: '/app', label: 'Play' },
  { href: '/agentic/arena.html', label: 'Arena', external: true },
  { href: '/agentic/hub.html', label: 'Hub', external: true },
  { href: '/agentic/docs.html', label: 'Docs', external: true },
  { href: '/leaderboard', label: 'Board' },
  { href: '/get-usdc', label: 'Fund' },
  { href: '/minipay', label: 'MiniPay' },
] as const

export function RematchFooter() {
  const path = usePathname() || ''
  const isApp = path === '/app' || path.startsWith('/app/')
  const isHome = path === '/' || path === '/rematch' || path === '/rematch/'
  if (isHome) return null

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
          maxWidth: isApp ? '28rem' : '44rem',
          margin: '0 auto',
          padding: '1.1rem 1rem',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: '0.65rem',
        }}
      >
        <p style={{ margin: 0, fontSize: '0.8rem', color: '#6b7280', textAlign: 'center' }}>
          <span style={{ fontWeight: 800, color: '#9ca3af' }}>
            <span style={{ color: '#34d399' }}>Board</span>man
          </span>{' '}
          by sideQuest
        </p>
        <p
          style={{
            margin: 0,
            fontSize: '0.68rem',
            color: '#4b5563',
            textAlign: 'center',
            lineHeight: 1.4,
            maxWidth: '22rem',
          }}
        >
          {BRAND.formerlyNote}
        </p>
        <div
          style={{
            display: 'flex',
            flexWrap: 'wrap',
            alignItems: 'center',
            justifyContent: 'center',
            gap: '0.55rem',
          }}
        >
          {FOOTER_LINKS.map((l) =>
            'external' in l && l.external ? (
              <a
                key={l.href}
                href={l.href}
                style={{ fontSize: '0.75rem', color: '#6b7280', textDecoration: 'none' }}
              >
                {l.label}
              </a>
            ) : (
              <Link
                key={l.href}
                href={l.href}
                style={{ fontSize: '0.75rem', color: '#6b7280', textDecoration: 'none' }}
              >
                {l.label}
              </Link>
            )
          )}
          <a
            href={BOT}
            target="_blank"
            rel="noreferrer"
            style={{ fontSize: '0.75rem', color: '#a78bfa', textDecoration: 'none', fontWeight: 700 }}
          >
            Bot
          </a>
          <a
            href="https://playingsidequest.fun"
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
            sideQuest
          </a>
        </div>
      </div>
    </footer>
  )
}
