'use client'

/**
 * Full-bleed cinematic marketing atmosphere:
 * - rotating game scene backgrounds (Ken Burns)
 * - infinite marquees: Play EA FC · Free Fire · Valorant · platforms
 * - floating game cards on the sides
 * Hidden only on the mini-app routes.
 */

import { useEffect, useState } from 'react'
import { usePathname } from 'next/navigation'

const SCENES = [
  {
    src: '/rematch/atmosphere/football.jpg',
    label: 'Play EA FC',
    sub: 'Console · Mobile',
  },
  {
    src: '/rematch/atmosphere/battle.jpg',
    label: 'Play Free Fire',
    sub: 'Mobile 1v1',
  },
  {
    src: '/rematch/atmosphere/fps.jpg',
    label: 'Play tactical FPS',
    sub: 'PC · Console',
  },
  {
    src: '/rematch/atmosphere/fight.jpg',
    label: 'Fighting BO sets',
    sub: 'Mortal-style settle',
  },
  {
    src: '/rematch/atmosphere/console.jpg',
    label: 'Earn on your console',
    sub: 'PlayStation · Xbox · PC',
  },
  {
    src: '/rematch/atmosphere/mobile.jpg',
    label: 'Play on Mobile',
    sub: 'iMessage · Free Fire · FC',
  },
]

const MARQUEE_A = [
  'BOARDMAN',
  'PLAY EA FC',
  'PLAY FREE FIRE',
  'PLAY VALORANT',
  'PLAY ON iMESSAGE',
  'PLAYSTATION',
  'XBOX',
  'PC',
  'MOBILE',
  'EARN WITH YOUR CONSOLE',
  'DIGITAL BOARDMAN',
  '1v1 LOCK · PLAY · SETTLE',
  'RUN IT BACK',
]

const MARQUEE_B = [
  '⚽ EA FC',
  '🔥 FREE FIRE',
  '🎯 VALORANT',
  '📱 iMESSAGE',
  '🎮 PLAYSTATION',
  '🟩 XBOX',
  '💻 PC',
  '📲 MOBILE',
  '🥊 FIGHTING',
  '🏀 NBA 2K',
  '♟️ CHESS',
  '💎 USDC STAKES',
]

const SIDE_CARDS = [
  {
    src: '/rematch/atmosphere/football.jpg',
    title: 'EA FC',
    tag: 'Play on console or mobile',
  },
  {
    src: '/rematch/atmosphere/battle.jpg',
    title: 'Free Fire',
    tag: 'Mobile 1v1 rooms',
  },
  {
    src: '/rematch/atmosphere/fps.jpg',
    title: 'Valorant & shooters',
    tag: 'PC · deathmatch 1v1',
  },
  {
    src: '/rematch/atmosphere/fight.jpg',
    title: 'Fighting games',
    tag: 'BO sets · final screen',
  },
  {
    src: '/rematch/atmosphere/console.jpg',
    title: 'PlayStation · Xbox · PC',
    tag: 'Earn with your console',
  },
  {
    src: '/rematch/atmosphere/mobile.jpg',
    title: 'iMessage · Mobile',
    tag: 'GamePigeon & more',
  },
]

function Marquee({
  items,
  reverse,
  className,
}: {
  items: string[]
  reverse?: boolean
  className?: string
}) {
  const doubled = [...items, ...items]
  return (
    <div className={`rm-marquee ${className || ''} ${reverse ? 'rm-marquee--rev' : ''}`}>
      <div className="rm-marquee-track">
        {doubled.map((t, i) => (
          <span key={`${t}-${i}`} className="rm-marquee-item">
            {t}
            <span className="rm-marquee-dot" aria-hidden>
              ◆
            </span>
          </span>
        ))}
      </div>
    </div>
  )
}

export function CinematicAtmosphere() {
  const path = usePathname() || ''
  const [scene, setScene] = useState(0)
  // Dimmer on mini-app so UI stays readable; full intensity on marketing pages
  const isApp = path.startsWith('/rematch/app')

  useEffect(() => {
    const id = window.setInterval(() => {
      setScene((s) => (s + 1) % SCENES.length)
    }, 5200)
    return () => window.clearInterval(id)
  }, [])

  const leftCards = SIDE_CARDS.filter((_, i) => i % 2 === 0)
  const rightCards = SIDE_CARDS.filter((_, i) => i % 2 === 1)

  const poster = (c: (typeof SIDE_CARDS)[0], i: number) => (
    <article key={c.title} className="rm-poster" style={{ animationDelay: `${i * 0.35}s` }}>
      <div className="rm-poster-media">
        {/* plain img = reliable local/static serving, no next/image layout quirks */}
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={c.src} alt="" className="rm-poster-img" />
        <div className="rm-poster-shade" />
      </div>
      <div className="rm-poster-meta">
        <div className="rm-poster-play">PLAY</div>
        <div className="rm-poster-title">{c.title}</div>
        <div className="rm-poster-tag">{c.tag}</div>
      </div>
    </article>
  )

  return (
    <div className={`rm-cinema ${isApp ? 'rm-cinema--app' : ''}`} aria-hidden>
      {/* Full-bleed rotating backgrounds — always mounted so first paint shows art */}
      <div className="rm-cinema-bg">
        {SCENES.map((s, i) => (
          <div
            key={s.src}
            className={`rm-cinema-slide ${i === scene ? 'rm-cinema-slide--on' : ''}`}
          >
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={s.src} alt="" className="rm-cinema-img" />
          </div>
        ))}
        <div className="rm-cinema-vignette" />
        <div className="rm-cinema-scan" />
      </div>

      {/* Top marquee */}
      <div className="rm-cinema-marquees">
        <Marquee items={MARQUEE_A} className="rm-marquee--top" />
        <Marquee items={MARQUEE_B} reverse className="rm-marquee--mid" />
      </div>

      {/* Active scene caption */}
      {!isApp && (
        <div className="rm-cinema-caption">
          <span className="rm-cinema-caption-live">LIVE</span>
          <span className="rm-cinema-caption-title">{SCENES[scene].label}</span>
          <span className="rm-cinema-caption-sub">{SCENES[scene].sub}</span>
        </div>
      )}

      {/* Side floating game posters — marketing pages only (space on app is tight) */}
      {!isApp && (
        <div className="rm-cinema-sides">
          <div className="rm-cinema-col rm-cinema-col--left">
            {leftCards.map((c, i) => poster(c, i))}
          </div>
          <div className="rm-cinema-col rm-cinema-col--right">
            {rightCards.map((c, i) => poster(c, i + 3))}
          </div>
          <div className="rm-cinema-mobile-strip">
            {[...SIDE_CARDS, ...SIDE_CARDS].map((c, i) => (
              <article key={`${c.title}-m-${i}`} className="rm-poster">
                <div className="rm-poster-media">
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img src={c.src} alt="" className="rm-poster-img" />
                  <div className="rm-poster-shade" />
                </div>
                <div className="rm-poster-meta">
                  <div className="rm-poster-title">{c.title}</div>
                  <div className="rm-poster-tag">{c.tag}</div>
                </div>
              </article>
            ))}
          </div>
        </div>
      )}

      {!isApp && (
        <div className="rm-platform-strip">
          {[
            { ico: '🎮', t: 'PlayStation' },
            { ico: '🟩', t: 'Xbox' },
            { ico: '💻', t: 'PC' },
            { ico: '📱', t: 'Mobile' },
            { ico: '💬', t: 'iMessage' },
            { ico: '🏆', t: 'Earn USDC' },
          ].map((p) => (
            <span key={p.t} className="rm-platform-pill">
              <span aria-hidden>{p.ico}</span> {p.t}
            </span>
          ))}
        </div>
      )}
    </div>
  )
}
