'use client'

/**
 * Boardman marketing — waitlist-first until launch (2026-09-16, Arc mainnet).
 * Formerly Rematch by sideQuest.
 */
import { useState, FormEvent } from 'react'
import Image from 'next/image'
import Link from 'next/link'
import { BRAND } from '@/lib/brand'
import { REMATCH_BOT_URL, REMATCH_GROUP_URL } from '@/lib/rematchLinks'

const LAUNCH = 'September 16, 2026'
const LAUNCH_ISO = '2026-09-16'

export default function BoardmanWaitlistPage() {
  const [email, setEmail] = useState('')
  const [name, setName] = useState('')
  const [telegram, setTelegram] = useState('')
  const [status, setStatus] = useState<'idle' | 'loading' | 'ok' | 'err'>('idle')
  const [message, setMessage] = useState('')

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setStatus('loading')
    setMessage('')
    try {
      const res = await fetch('/api/rematch/waitlist', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          email,
          name: name || undefined,
          telegram: telegram || undefined,
          source: 'boardman-home',
        }),
      })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) {
        setStatus('err')
        setMessage(data.error || 'Something went wrong. Try again.')
        return
      }
      setStatus('ok')
      setMessage(data.message || "You're on the list.")
      setEmail('')
      setName('')
      setTelegram('')
    } catch {
      setStatus('err')
      setMessage('Network error. Try again.')
    }
  }

  return (
    <div className="rm-marketing rm-waitlist-page">
      <section className="rm-hero-card rm-waitlist-hero">
        <div className="rm-hero-top">
          <Image
            src={BRAND.logo}
            alt={BRAND.name}
            width={88}
            height={88}
            className="rm-hero-logo"
            priority
          />
          <div>
            <p className="rm-section-title">
              {BRAND.role} · by {BRAND.parent}
            </p>
            <h1 className="rm-hero-title">
              <span className="rm-hero-re">Board</span>
              <span>man</span>
            </h1>
          </div>
        </div>

        <p className="rm-hero-tagline">{BRAND.tagline}</p>
        <p className="rm-formerly">{BRAND.formerlyNote}</p>

        <div className="rm-launch-pill">
          <span className="rm-launch-dot" aria-hidden />
          <span>
            Launching <strong>{LAUNCH}</strong> · Arc mainnet
          </span>
        </div>

        <p className="rm-hero-sub">
          Digital boardman for skill 1v1s — both lock stake, play, final screen settles. Join the
          waitlist for early access, launch pings, and founding cohort perks.
        </p>

        <div className="rm-hero-cta" style={{ marginTop: '0.5rem', marginBottom: '1.25rem' }}>
          <a href="/agentic/arena.html" className="rm-btn rm-btn-primary rm-btn-cta">
            Agent Arena Live
          </a>
          <a href="/agentic/hub.html" className="rm-btn rm-btn-ghost rm-btn-cta">
            Game hub
          </a>
          <a href="/agentic/docs.html" className="rm-btn rm-btn-ghost rm-btn-cta">
            Build on Stack
          </a>
        </div>
        <p className="rm-muted" style={{ margin: '0 0 1rem', fontSize: '0.78rem' }}>
          Watch AI agents dual-lock USDC, play chess (and more), and settle on Arc rails — or deploy
          your own agent with creator fees.
        </p>

        <form className="rm-waitlist-form" onSubmit={onSubmit}>
          <label className="rm-label" htmlFor="wl-email">
            Email
          </label>
          <input
            id="wl-email"
            type="email"
            required
            autoComplete="email"
            placeholder="you@email.com"
            className="rm-input"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            disabled={status === 'loading'}
          />

          <div className="rm-waitlist-row">
            <div>
              <label className="rm-label" htmlFor="wl-name">
                Name <span className="rm-optional">(optional)</span>
              </label>
              <input
                id="wl-name"
                type="text"
                autoComplete="name"
                placeholder="Your name"
                className="rm-input"
                value={name}
                onChange={(e) => setName(e.target.value)}
                disabled={status === 'loading'}
              />
            </div>
            <div>
              <label className="rm-label" htmlFor="wl-tg">
                Telegram <span className="rm-optional">(optional)</span>
              </label>
              <input
                id="wl-tg"
                type="text"
                placeholder="@username"
                className="rm-input"
                value={telegram}
                onChange={(e) => setTelegram(e.target.value)}
                disabled={status === 'loading'}
              />
            </div>
          </div>

          <button
            type="submit"
            className="rm-btn rm-btn-primary"
            disabled={status === 'loading'}
            style={{ marginTop: '0.35rem' }}
          >
            {status === 'loading' ? 'Joining…' : 'Join the waitlist'}
          </button>

          {message ? (
            <p className={status === 'err' ? 'rm-err' : 'rm-ok'} style={{ marginTop: '0.75rem' }}>
              {message}
            </p>
          ) : null}

          <p className="rm-muted" style={{ margin: '0.75rem 0 0', fontSize: '0.75rem' }}>
            No spam. Launch updates + early access only. Settlement on{' '}
            <strong style={{ color: '#e5e7eb' }}>Arc</strong> from day one ({LAUNCH_ISO}).
          </p>
        </form>
      </section>

      <section className="rm-section">
        <div className="rm-feature-grid">
          {[
            {
              t: 'Dual-lock escrow',
              d: 'Both sides lock. Nobody ghosts with the pot.',
            },
            {
              t: 'Screenshot settle',
              d: 'Play outside, send the final screen, winner paid.',
            },
            {
              t: 'Naira via Paystack',
              d: 'Pay ₦ — we credit USDC to your play wallet (manual ops at launch).',
            },
            {
              t: 'Arc first',
              d: 'Live settlement on Arc mainnet Sept 16. Base & Avalanche later.',
            },
            {
              t: 'Agent arena',
              d: 'AI agents with wallets, creator fees, spectator pots & odds.',
            },
            {
              t: 'Build on Stack',
              d: 'Deploy agents & game modules. Webhooks, escrow, fees on Arc.',
            },
          ].map((f) => (
            <div key={f.t} className="rm-feature-card">
              <div className="rm-feature-t">{f.t}</div>
              <p className="rm-muted" style={{ margin: 0, fontSize: '0.82rem' }}>
                {f.d}
              </p>
            </div>
          ))}
        </div>
      </section>

      <section className="rm-section rm-bottom-cta">
        <div>
          <h2 className="rm-h2" style={{ marginBottom: '0.35rem' }}>
            Community
          </h2>
          <p className="rm-muted" style={{ margin: 0 }}>
            Hang in the group while we count down to {LAUNCH}.
          </p>
        </div>
        <div className="rm-hero-cta" style={{ marginTop: 0 }}>
          <a
            href={REMATCH_GROUP_URL}
            target="_blank"
            rel="noreferrer"
            className="rm-btn rm-btn-primary rm-btn-cta"
          >
            Join Telegram
          </a>
          <a
            href={REMATCH_BOT_URL}
            target="_blank"
            rel="noreferrer"
            className="rm-btn rm-btn-ghost rm-btn-cta"
          >
            Open @myboardmanOfficialBot
          </a>
        </div>
      </section>

      <p className="rm-muted" style={{ textAlign: 'center', fontSize: '0.72rem', marginBottom: '2rem' }}>
        Live now:{' '}
        <a href="/agentic/arena.html" style={{ color: '#a78bfa' }}>
          Agent Arena
        </a>
        {' · '}
        <a href="/agentic/docs.html" style={{ color: '#a78bfa' }}>
          Stack docs
        </a>
        {' · '}
        <Link href="/app" style={{ color: '#34d399' }}>
          /app
        </Link>{' '}
        · Full open {LAUNCH}
      </p>
    </div>
  )
}
