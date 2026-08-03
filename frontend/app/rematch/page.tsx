'use client'

/**
 * Public Rematch marketing — playingsidequest.fun/rematch
 */
import { useState } from 'react'
import Image from 'next/image'
import Link from 'next/link'

const BOT = 'https://t.me/ClawStationOfficialBot'
const FAUCET = 'https://faucet.circle.com/'

const STEPS = [
  { n: '01', t: 'Fund', d: 'Get USDC into your Arc play wallet' },
  { n: '02', t: 'Challenge', d: 'Tag a friend, pick stake & game' },
  { n: '03', t: 'Lock', d: 'Both players lock — stake is held' },
  { n: '04', t: 'Play & settle', d: 'Upload the final screen. Winner paid.' },
]

export default function RematchPage() {
  const [activeTab, setActiveTab] = useState<'flow' | 'play' | 'wallet' | 'legal'>('flow')

  const tabs: Record<string, React.ReactNode> = {
    flow: (
      <div className="rm-stack" style={{ gap: '1rem' }}>
        <h2 className="rm-h2" style={{ color: '#34d399' }}>
          How it works
        </h2>
        <div className="rm-stack">
          {STEPS.map((s) => (
            <div
              key={s.n}
              style={{
                display: 'flex',
                gap: '0.85rem',
                alignItems: 'flex-start',
                padding: '0.75rem 0',
                borderBottom: '1px solid rgba(255,255,255,0.05)',
              }}
            >
              <span
                style={{
                  fontSize: '0.7rem',
                  fontWeight: 800,
                  color: '#34d399',
                  letterSpacing: '0.06em',
                  minWidth: '1.6rem',
                  paddingTop: 2,
                }}
              >
                {s.n}
              </span>
              <div>
                <div style={{ fontWeight: 800, marginBottom: 2 }}>{s.t}</div>
                <div className="rm-muted" style={{ margin: 0, fontSize: '0.85rem' }}>
                  {s.d}
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    ),
    play: (
      <div className="rm-stack" style={{ gap: '0.85rem' }}>
        <h2 className="rm-h2" style={{ color: '#34d399' }}>
          PLAY score
        </h2>
        <p className="rm-muted" style={{ margin: 0 }}>
          Points for competing. <strong style={{ color: '#fff' }}>Not cash.</strong>
        </p>
        <table style={{ width: '100%', fontSize: '0.9rem', borderCollapse: 'collapse' }}>
          <tbody>
            {[
              ['Win', '+100'],
              ['Loss', '+40'],
              ['Draw', '+50'],
              ['No-show', '−50'],
              ['Tiers', 'Bronze → Diamond'],
            ].map(([k, v]) => (
              <tr key={k} style={{ borderBottom: '1px solid rgba(255,255,255,0.06)' }}>
                <td style={{ padding: '0.65rem 0', color: '#9ca3af' }}>{k}</td>
                <td style={{ padding: '0.65rem 0', color: '#34d399', textAlign: 'right', fontWeight: 700 }}>
                  {v}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    ),
    wallet: (
      <div className="rm-stack" style={{ gap: '0.85rem' }}>
        <h2 className="rm-h2" style={{ color: '#34d399' }}>
          Wallet
        </h2>
        <p className="rm-muted" style={{ margin: 0 }}>
          Rematch runs on <strong style={{ color: '#fff' }}>Arc</strong>. Gas is USDC — you only
          need USDC.
        </p>
        <ul className="rm-muted" style={{ margin: 0, paddingLeft: '1.1rem', lineHeight: 1.7 }}>
          <li>
            <strong style={{ color: '#fff' }}>Get USDC</strong> —{' '}
            <a href={FAUCET} className="text-emerald-400 underline" target="_blank" rel="noreferrer">
              Circle faucet
            </a>{' '}
            → Arc → your address
          </li>
          <li>
            <strong style={{ color: '#fff' }}>Withdraw</strong> — Wallet in bot or app
          </li>
        </ul>
      </div>
    ),
    legal: (
      <div className="rm-stack" style={{ gap: '0.75rem' }}>
        <h2 className="rm-h2" style={{ color: '#fbbf24' }}>
          Before you play
        </h2>
        <ul className="rm-muted" style={{ margin: 0, paddingLeft: '1.1rem', lineHeight: 1.7 }}>
          <li>Skill matches with proof — play fair.</li>
          <li>Only stake what you can afford to lose.</li>
          <li>PLAY is a score, not money.</li>
          <li>You must be allowed to use this product where you live.</li>
        </ul>
      </div>
    ),
  }

  return (
    <div style={{ maxWidth: '42rem', margin: '0 auto', padding: '2rem 1rem 3rem' }}>
      {/* Hero */}
      <div
        style={{
          display: 'flex',
          flexDirection: 'column',
          gap: '1.5rem',
          marginBottom: '2rem',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
          <Image
            src="/rematch-logo.jpg"
            alt="Rematch"
            width={80}
            height={80}
            className="rm-hero-logo"
            priority
          />
          <div>
            <p className="rm-section-title">by sideQuest</p>
            <h1
              style={{
                margin: 0,
                fontSize: 'clamp(2.4rem, 8vw, 3.25rem)',
                fontWeight: 900,
                letterSpacing: '-0.04em',
                lineHeight: 1,
              }}
            >
              <span style={{ color: '#34d399' }}>Re</span>
              <span style={{ color: '#fff' }}>match</span>
            </h1>
          </div>
        </div>

        <div>
          <p
            style={{
              margin: '0 0 0.5rem',
              fontSize: '1.25rem',
              color: '#d1d5db',
              lineHeight: 1.4,
              maxWidth: '28rem',
            }}
          >
            Lock in. Play. Settle. Run it back.
          </p>
          <p className="rm-muted" style={{ margin: 0, maxWidth: '28rem' }}>
            1v1 skill matches — console, iMessage, or mobile. Stake, lock, send the final photo.
            Telegram or web.
          </p>
        </div>

        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.65rem' }}>
          <Link
            href="/rematch/app"
            className="rm-btn rm-btn-primary"
            style={{ width: 'auto', minWidth: 140, padding: '0.9rem 1.35rem' }}
          >
            Open web app
          </Link>
          <a
            href={BOT}
            target="_blank"
            rel="noreferrer"
            className="rm-btn rm-btn-ghost"
            style={{ width: 'auto', minWidth: 140, padding: '0.9rem 1.35rem' }}
          >
            Telegram bot
          </a>
          <a
            href={FAUCET}
            target="_blank"
            rel="noreferrer"
            className="rm-btn rm-btn-ghost"
            style={{ width: 'auto', minWidth: 140, padding: '0.9rem 1.35rem' }}
          >
            Get USDC
          </a>
        </div>
      </div>

      {/* Feature pills */}
      <div
        style={{
          display: 'flex',
          flexWrap: 'wrap',
          gap: '0.45rem',
          marginBottom: '1.5rem',
        }}
      >
        {['Dual-lock escrow', 'Screenshot settle', 'Arc USDC', 'Telegram + web'].map((t) => (
          <span key={t} className="rm-chip">
            {t}
          </span>
        ))}
      </div>

      {/* Tabs */}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.4rem', marginBottom: '1rem' }}>
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
            onClick={() => setActiveTab(tab)}
            className={`rm-tile ${activeTab === tab ? 'rm-tile-active' : ''}`}
            style={{ width: 'auto', padding: '0.55rem 0.9rem', fontSize: '0.8rem' }}
          >
            {label}
          </button>
        ))}
      </div>

      <div className="rm-card" style={{ padding: '1.35rem 1.4rem' }}>
        {tabs[activeTab]}
      </div>
    </div>
  )
}
