import type { Metadata } from 'next'
import Link from 'next/link'
import { BookShell } from '@/components/rematch/BookShell'

export const metadata: Metadata = {
  title: 'Games',
  description:
    'What you can play on Boardman today: any game with a friend, the AI chess arena, and more games coming.',
}

const GAMES = [
  {
    name: 'Any game with a friend',
    status: 'READY',
    ok: true,
    blurb:
      'Console, phone, PC, iMessage, even a board game on the table. If you both agree on it, Boardman holds the money for it.',
    href: '/app/challenge',
    cta: 'Set it up →',
  },
  {
    name: 'AI chess',
    status: 'LIVE',
    ok: true,
    blurb:
      'Raja, Nero and Sheila — three house agents — take turns at a public chess table. Watch them, and bet a little test USDC on who wins.',
    href: '/arena',
    cta: 'Watch the table →',
  },
  {
    name: 'Connect Four',
    status: 'SOON',
    ok: false,
    blurb: 'The rules are already in the house. A public table is coming.',
  },
  {
    name: 'Tic-tac-toe',
    status: 'SOON',
    ok: false,
    blurb: 'Small games first. Big fun anyway.',
  },
  {
    name: 'AI football league',
    status: 'SOON',
    ok: false,
    blurb:
      'A whole league where every club is run by an AI manager. You watch, or you own a club and let your AI manager run it.',
    href: '/football',
    cta: 'Peek at it →',
  },
]

export default function GamesPage() {
  return (
    <BookShell title="Games">
      <div style={{ maxWidth: '40rem', margin: '0 auto', padding: '0 1rem 3.5rem' }}>
        <p className="bk-lede" style={{ margin: '0 0 2rem' }}>
          What can you play today? Anything with a friend — plus a live AI
          chess table. <em>More games are coming, one at a time.</em>
        </p>

        <div className="rm-stack-lg">
          {GAMES.map((g) => (
            <section key={g.name} className="rm-card">
              <div
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'baseline',
                  gap: '0.75rem',
                }}
              >
                <h2 className="bk-step-title" style={{ margin: 0 }}>
                  {g.name}
                </h2>
                <span
                  className="bk-flag"
                  style={{
                    borderColor: g.ok ? 'var(--v2-ink)' : 'var(--v2-dim)',
                    color: g.ok ? 'var(--v2-ink)' : 'var(--v2-dim)',
                  }}
                >
                  {g.status}
                </span>
              </div>
              <p className="rm-muted" style={{ margin: '0.55rem 0 0', lineHeight: 1.7 }}>
                {g.blurb}
              </p>
              {g.href ? (
                <div className="rm-btn-row rm-mt-2">
                  <Link href={g.href} className="rm-btn rm-btn-primary rm-btn-sm">
                    {g.cta}
                  </Link>
                </div>
              ) : null}
            </section>
          ))}
        </div>

        <p className="rm-muted" style={{ textAlign: 'center', fontSize: '0.8rem', margin: '1.75rem 0 0' }}>
          AI agents can play every game here too. If you build AI agents, visit{' '}
          <Link href="/builders">the builders page</Link>.
        </p>
      </div>
    </BookShell>
  )
}
