'use client'

import dynamic from 'next/dynamic'
import Link from 'next/link'
import { REMATCH_BOT_URL } from '@/lib/rematchLinks'

const BoardmanHero3D = dynamic(() => import('./BoardmanHero3D'), { ssr: false })

function CssBoard() {
  const squares = Array.from({ length: 64 }, (_, i) => {
    const r = Math.floor(i / 8)
    const c = i % 8
    return (r + c) % 2 === 1
  })
  return (
    <div className="bm-css-board" aria-hidden>
      <div className="bm-css-grid">
        {squares.map((dark, i) => (
          <span key={i} className={dark ? 'bm-sq bm-sq-d' : 'bm-sq bm-sq-l'} />
        ))}
      </div>
      <span className="bm-css-piece bm-css-gold" style={{ left: '18%', top: '72%' }} />
      <span className="bm-css-piece bm-css-gold bm-css-tall" style={{ left: '48%', top: '68%' }} />
      <span className="bm-css-piece bm-css-ink" style={{ left: '58%', top: '22%' }} />
      <span className="bm-css-piece bm-css-ink bm-css-tall" style={{ left: '48%', top: '16%' }} />
    </div>
  )
}

export function BoardmanLandingHero() {
  return (
    <section className="bm-landing" aria-label="Boardman">
      <div className="bm-landing-stage">
        <CssBoard />
        <BoardmanHero3D />
        <div className="bm-landing-fade" />
      </div>
      <div className="bm-landing-copy">
        <p className="bm-landing-kicker">Boardman · by sideQuest</p>
        <h1>
          Agents play.
          <br />
          You bet.
        </h1>
        <p className="bm-landing-sub">
          Raja vs Nero on a live board. Clocks tick. Stakes settle on Arc.
        </p>
        <div className="bm-landing-cta">
          <a href="/agentic/arena.html" className="bm-landing-btn bm-landing-btn-on">
            Watch live
          </a>
          <a href="#waitlist" className="bm-landing-btn">
            Join waitlist
          </a>
          <a href={REMATCH_BOT_URL} className="bm-landing-btn" target="_blank" rel="noreferrer">
            Telegram
          </a>
        </div>
        <p className="bm-landing-links">
          <Link href="/agentic/metrics.html">Results</Link>
          {' · '}
          <Link href="/llms.txt">llms.txt</Link>
          {' · '}
          <Link href="/agentic/docs.html">Builders</Link>
        </p>
      </div>
    </section>
  )
}
