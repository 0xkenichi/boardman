'use client'

/**
 * Public Boardman marketing — playingsidequest.fun/rematch
 */
import { useState } from 'react'
import Image from 'next/image'
import Link from 'next/link'
import { LiveRoomsCard } from '@/components/rematch/LiveRoomsCard'
import { BRAND } from '@/lib/brand'
import { REMATCH_BOT_URL, REMATCH_GROUP_URL } from '@/lib/rematchLinks'

const BOT = REMATCH_BOT_URL
const FAUCET = 'https://faucet.circle.com/'

const STEPS = [
  {
    n: '01',
    t: 'Fund your wallet',
    d: 'Get USDC (Kobox, bank top-up, or crypto) into your Boardman play wallet.',
    ico: '💧',
  },
  {
    n: '02',
    t: 'Challenge someone',
    d: 'Tag a friend or post public. Pick stake, game, and lock in.',
    ico: '⚔️',
  },
  {
    n: '03',
    t: 'Both lock stake',
    d: 'Escrow holds both sides. No one can ghost with the money.',
    ico: '🔐',
  },
  {
    n: '04',
    t: 'Play & settle',
    d: 'Finish the match. Send the final screen. Winner gets paid.',
    ico: '🏆',
  },
]

const GAMES = [
  { emoji: '⚽', name: 'EA FC', where: 'Console · Mobile' },
  { emoji: '🏀', name: 'NBA 2K', where: 'Console' },
  { emoji: '🔥', name: 'Free Fire', where: 'Mobile 1v1' },
  { emoji: '🎯', name: 'COD', where: 'Deathmatch' },
  { emoji: '♟️', name: 'Chess', where: 'App · iMessage' },
  { emoji: '🎲', name: 'Ludo & more', where: 'Casual' },
  { emoji: '📱', name: 'iMessage', where: 'GamePigeon' },
  { emoji: '🥊', name: 'Fighting', where: 'BO sets' },
]

const FEATURES = [
  { t: 'Dual-lock escrow', d: 'Both players lock before play starts.' },
  { t: 'Screenshot settle', d: 'Final screen is enough for many games.' },
  { t: 'Balance in $', d: 'You see dollars — not chain homework.' },
  { t: 'Telegram + web', d: 'Bot for DMs, site for open board.' },
]

export default function RematchPage() {
  const [activeTab, setActiveTab] = useState<'flow' | 'play' | 'wallet' | 'legal'>('flow')

  const tabs: Record<string, React.ReactNode> = {
    flow: (
      <div className="rm-stack" style={{ gap: '0.35rem' }}>
        <h2 className="rm-h2" style={{ color: 'var(--rm-green-bright)', marginBottom: '0.75rem' }}>
          How it works
        </h2>
        <div className="rm-how-grid">
          {STEPS.map((s) => (
            <div key={s.n} className="rm-how-step">
              <div className="rm-how-step-top">
                <span className="rm-how-ico" aria-hidden>
                  {s.ico}
                </span>
                <span className="rm-how-n">{s.n}</span>
              </div>
              <div className="rm-how-title">{s.t}</div>
              <p className="rm-muted rm-how-desc">{s.d}</p>
            </div>
          ))}
        </div>
      </div>
    ),
    play: (
      <div className="rm-stack" style={{ gap: '0.85rem' }}>
        <h2 className="rm-h2" style={{ color: 'var(--rm-green-bright)' }}>
          PLAY score
        </h2>
        <p className="rm-muted" style={{ margin: 0 }}>
          Points for competing. <strong style={{ color: '#fff' }}>Not cash.</strong> Climb tiers
          and show up on the board.
        </p>
        <div className="rm-score-grid">
          {[
            ['Win', '+100', 'green'],
            ['Loss', '+40', 'muted'],
            ['Draw', '+50', 'muted'],
            ['No-show', '−50', 'red'],
          ].map(([k, v, tone]) => (
            <div key={k} className={`rm-score-cell rm-score-${tone}`}>
              <span className="rm-score-k">{k}</span>
              <span className="rm-score-v">{v}</span>
            </div>
          ))}
        </div>
        <p className="rm-muted" style={{ margin: 0, fontSize: '0.8rem' }}>
          Tiers: Bronze → Silver → Gold → Platinum → Diamond
        </p>
      </div>
    ),
    wallet: (
      <div className="rm-stack" style={{ gap: '0.85rem' }}>
        <h2 className="rm-h2" style={{ color: 'var(--rm-green-bright)' }}>
          Wallet & funding
        </h2>
        <p className="rm-muted" style={{ margin: 0 }}>
          Play with a simple <strong style={{ color: '#fff' }}>Balance $</strong>. Fund however
          you like — partner app, bank top-up, or crypto.
        </p>
        <div className="rm-fund-list">
          <div className="rm-fund-row">
            <span className="rm-fund-ico">⭐</span>
            <div>
              <strong>Kobox</strong>
              <p className="rm-muted" style={{ margin: '0.15rem 0 0', fontSize: '0.8rem' }}>
                Swap Naira ↔ USDC yourself, then send to your play address.
              </p>
            </div>
          </div>
          <div className="rm-fund-row">
            <span className="rm-fund-ico">🏦</span>
            <div>
              <strong>Bank top-up</strong>
              <p className="rm-muted" style={{ margin: '0.15rem 0 0', fontSize: '0.8rem' }}>
                Pay our account in the bot — we credit USDC after confirmation.
              </p>
            </div>
          </div>
          <div className="rm-fund-row">
            <span className="rm-fund-ico">🪙</span>
            <div>
              <strong>Crypto</strong>
              <p className="rm-muted" style={{ margin: '0.15rem 0 0', fontSize: '0.8rem' }}>
                Send USDC to your deposit address.{' '}
                <a href={FAUCET} className="rm-inline-link" target="_blank" rel="noreferrer">
                  Testnet faucet
                </a>
              </p>
            </div>
          </div>
        </div>
        <Link href="/rematch/get-usdc" className="rm-btn rm-btn-ghost rm-btn-sm" style={{ width: 'auto' }}>
          Open fund helper →
        </Link>
      </div>
    ),
    legal: (
      <div className="rm-stack" style={{ gap: '0.75rem' }}>
        <h2 className="rm-h2" style={{ color: 'var(--rm-amber)' }}>
          Before you play
        </h2>
        <ul className="rm-rules-list">
          <li>Skill matches with proof — play fair.</li>
          <li>Only stake what you can afford to lose.</li>
          <li>PLAY is a score, not money.</li>
          <li>You must be allowed to use this product where you live.</li>
        </ul>
      </div>
    ),
  }

  return (
    <div className="rm-marketing">
      {/* Hero */}
      <section className="rm-hero-card">
        <div className="rm-hero-top">
          <Image
            src="/rematch-logo.jpg"
            alt={BRAND.name}
            width={88}
            height={88}
            className="rm-hero-logo"
            priority
          />
          <div>
            <p className="rm-section-title">{BRAND.role} · by {BRAND.parent}</p>
            <h1 className="rm-hero-title">
              <span className="rm-hero-re">Board</span>
              <span>man</span>
            </h1>
          </div>
        </div>

        <p className="rm-hero-tagline">{BRAND.tagline}</p>
        <p className="rm-hero-sub">
          The digital boardman holds both stakes. Play console, mobile, or iMessage 1v1s. Send the
          final photo — winner gets paid. Telegram bot or web.
        </p>

        <div className="rm-hero-cta">
          <Link href="/rematch/app" className="rm-btn rm-btn-primary rm-btn-cta">
            Open web app
          </Link>
          <a
            href={REMATCH_GROUP_URL}
            target="_blank"
            rel="noreferrer"
            className="rm-btn rm-btn-ghost rm-btn-cta"
          >
            Live rooms
          </a>
          <a href={BOT} target="_blank" rel="noreferrer" className="rm-btn rm-btn-ghost rm-btn-cta">
            Telegram bot
          </a>
        </div>

        <div className="rm-hero-stats">
          <div className="rm-stat">
            <span className="rm-stat-v">1v1</span>
            <span className="rm-stat-l">Only skill games</span>
          </div>
          <div className="rm-stat">
            <span className="rm-stat-v">2×</span>
            <span className="rm-stat-l">Lock escrow</span>
          </div>
          <div className="rm-stat">
            <span className="rm-stat-v">$</span>
            <span className="rm-stat-l">Simple balance</span>
          </div>
        </div>
      </section>

      {/* In-page game posters — always visible even if background fails */}
      <section className="rm-section">
        <div className="rm-section-head">
          <p className="rm-section-title">What you can play</p>
          <h2 className="rm-h2">Play on console · mobile · iMessage · PC</h2>
          <p className="rm-muted" style={{ margin: '0.35rem 0 0', maxWidth: '36rem' }}>
            Earn with your PlayStation, Xbox, PC, or phone. Lock stakes. Settle on the final
            screen.
          </p>
        </div>
        <div className="rm-play-gallery">
          {[
            {
              src: '/rematch/atmosphere/football.jpg',
              title: 'Play EA FC',
              tag: 'Console · Mobile',
            },
            {
              src: '/rematch/atmosphere/battle.jpg',
              title: 'Play Free Fire',
              tag: 'Mobile 1v1',
            },
            {
              src: '/rematch/atmosphere/fps.jpg',
              title: 'Play Valorant',
              tag: 'PC · shooters',
            },
            {
              src: '/rematch/atmosphere/fight.jpg',
              title: 'Fighting games',
              tag: 'BO · final screen',
            },
            {
              src: '/rematch/atmosphere/console.jpg',
              title: 'PS · Xbox · PC',
              tag: 'Earn on console',
            },
            {
              src: '/rematch/atmosphere/mobile.jpg',
              title: 'iMessage · Mobile',
              tag: 'GamePigeon & more',
            },
          ].map((g) => (
            <article key={g.title} className="rm-play-card">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={g.src} alt={g.title} className="rm-play-card-img" />
              <div className="rm-play-card-body">
                <span className="rm-play-card-badge">PLAY</span>
                <div className="rm-play-card-title">{g.title}</div>
                <div className="rm-play-card-tag">{g.tag}</div>
              </div>
            </article>
          ))}
        </div>
        <div className="rm-games-grid" style={{ marginTop: '0.85rem' }}>
          {GAMES.map((g) => (
            <div key={g.name} className="rm-game-tile">
              <span className="rm-game-emoji" aria-hidden>
                {g.emoji}
              </span>
              <div>
                <div className="rm-game-name">{g.name}</div>
                <div className="rm-game-where">{g.where}</div>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* Features */}
      <section className="rm-section">
        <div className="rm-feature-grid">
          {FEATURES.map((f) => (
            <div key={f.t} className="rm-feature-card">
              <div className="rm-feature-t">{f.t}</div>
              <p className="rm-muted" style={{ margin: 0, fontSize: '0.82rem' }}>
                {f.d}
              </p>
            </div>
          ))}
        </div>
      </section>

      <section className="rm-section">
        <LiveRoomsCard variant="full" />
      </section>

      {/* Tabs */}
      <section className="rm-section">
        <div className="rm-section-head">
          <p className="rm-section-title">Learn more</p>
          <h2 className="rm-h2">Flow, scores & funding</h2>
        </div>
        <div className="rm-tab-bar" role="tablist">
          {(
            [
              ['flow', 'How it works'],
              ['play', 'PLAY score'],
              ['wallet', 'Wallet'],
              ['legal', 'Rules'],
            ] as const
          ).map(([tab, label]) => (
            <button
              key={tab}
              type="button"
              role="tab"
              aria-selected={activeTab === tab}
              onClick={() => setActiveTab(tab)}
              className={`rm-tab ${activeTab === tab ? 'rm-tab-on' : ''}`}
            >
              {label}
            </button>
          ))}
        </div>
        <div className="rm-card rm-tab-panel" role="tabpanel">
          {tabs[activeTab]}
        </div>
      </section>

      {/* Bottom CTA */}
      <section className="rm-bottom-cta">
        <div>
          <h2 className="rm-h2" style={{ marginBottom: '0.35rem' }}>
            Ready to run it back?
          </h2>
          <p className="rm-muted" style={{ margin: 0 }}>
            Open the app or hop into Telegram — same matches either way.
          </p>
        </div>
        <div className="rm-hero-cta" style={{ marginTop: 0 }}>
          <Link href="/rematch/app" className="rm-btn rm-btn-primary rm-btn-cta">
            Play now
          </Link>
          <a href={BOT} target="_blank" rel="noreferrer" className="rm-btn rm-btn-ghost rm-btn-cta">
            Open bot
          </a>
        </div>
      </section>
    </div>
  )
}
