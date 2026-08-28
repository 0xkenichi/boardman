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
  { href: '/app/how-to-play', label: 'How to play' },
  { href: '/contact', label: 'Contact' },
  { href: '/minipay', label: 'MiniPay' },
] as const

const FOOTER_LINK_STYLE: React.CSSProperties = {
  fontSize: '0.8rem',
  color: '#6b7280',
  textDecoration: 'none',
  padding: '0.35rem 0.5rem',
  borderRadius: '0.5rem',
  minHeight: 36,
  display: 'inline-flex',
  alignItems: 'center',
}

export function RematchFooter() {
  const path = usePathname() || ''
  const isApp = path === '/app' || path.startsWith('/app/')

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
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(90px, 1fr))',
            gap: '0.25rem',
            alignItems: 'center',
            justifyItems: 'center',
            width: '100%',
          }}
        >
          {FOOTER_LINKS.map((l) =>
            'external' in l && l.external ? (
              <a
                key={l.href}
                href={l.href}
                style={FOOTER_LINK_STYLE}
              >
                {l.label}
              </a>
            ) : (
              <Link
                key={l.href}
                href={l.href}
                style={FOOTER_LINK_STYLE}
              >
                {l.label}
              </Link>
            )
          )}
          <a
            href={`mailto:${BRAND.email}`}
            style={{ ...FOOTER_LINK_STYLE, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: '100%' }}
          >
            {BRAND.email}
          </a>
          <a
            href={BOT}
            target="_blank"
            rel="noreferrer"
            style={{ ...FOOTER_LINK_STYLE, color: '#a78bfa', fontWeight: 700 }}
          >
            Bot
          </a>
          <a
            href="https://playingsidequest.fun"
            style={{
              ...FOOTER_LINK_STYLE,
              fontWeight: 700,
              color: '#d1d5db',
              border: '1px solid rgba(255,255,255,0.1)',
              borderRadius: 999,
              padding: '0.35rem 0.7rem',
              minHeight: 36,
            }}
          >
            sideQuest
          </a>
        </div>
      </div>
    </footer>
  )
}
