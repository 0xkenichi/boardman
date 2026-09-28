'use client'

import { FormEvent, useState } from 'react'
import { BookShell } from '@/components/rematch/BookShell'
import { BRAND } from '@/lib/brand'
import { REMATCH_BOT_URL, REMATCH_GROUP_URL } from '@/lib/rematchLinks'

export default function ContactPage() {
  const [email, setEmail] = useState('')
  const [note, setNote] = useState('')
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
        body: JSON.stringify({ email, note, source: 'contact-page' }),
      })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) {
        setStatus('err')
        setMessage(data.error || 'Try again.')
        return
      }
      setStatus('ok')
      setMessage(data.title || 'We got you.')
      setEmail('')
      setNote('')
    } catch {
      setStatus('err')
      setMessage('Network error.')
    }
  }

  return (
    <BookShell title="The desk">
      <main className="bm-contact" style={{ maxWidth: '40rem' }}>
        <p className="bm-kicker">TALK TO THE HOUSE</p>
        <p className="bm-contact-lead">
          No ticket queue, no hold music. Pick the door that fits and it lands on
          the boardman&apos;s desk — <em>we read everything that comes in.</em>
        </p>

        <div className="bm-contact-doors">
          <a className="bm-contact-door" href={REMATCH_BOT_URL} target="_blank" rel="noreferrer">
            <span>Play · wallet · bets</span>
            <strong>Telegram bot</strong>
            <em>@myboardmanOfficialBot — start there for anything with money on it.</em>
          </a>
          <a className="bm-contact-door" href={REMATCH_GROUP_URL} target="_blank" rel="noreferrer">
            <span>The regulars</span>
            <strong>Community</strong>
            <em>Live rooms, the crowd, the noise. Come hang — no pitch required.</em>
          </a>
          <a className="bm-contact-door" href="/agentic/docs.html">
            <span>Builders</span>
            <strong>Agents &amp; games</strong>
            <em>You host the brain, the house clerks the money. Docs first, then write us.</em>
          </a>
          <a className="bm-contact-door" href={`mailto:${BRAND.email}`}>
            <span>Everything else</span>
            <strong>{BRAND.email}</strong>
            <em>Support, press, partnership, builder keys. One inbox. We read it.</em>
          </a>
        </div>

        <section className="bm-contact-note">
          <h2>Leave a note</h2>
          <p>
            Want a builder key, a press chat, or a game on the slate? Write{' '}
            <a href={`mailto:${BRAND.email}`}>{BRAND.email}</a> or leave a note below.
            We&apos;ll write back.
          </p>
          {status === 'ok' ? (
            <p className="bm-msg">{message} — it&apos;s in the book.</p>
          ) : (
            <form onSubmit={onSubmit}>
              <input
                type="email"
                required
                autoComplete="email"
                placeholder="you@email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                disabled={status === 'loading'}
              />
              <textarea
                rows={3}
                placeholder="I want to ship an agent / a game / just saying hi"
                value={note}
                onChange={(e) => setNote(e.target.value)}
                disabled={status === 'loading'}
                maxLength={400}
              />
              <button type="submit" disabled={status === 'loading'}>
                {status === 'loading' ? 'Sending…' : 'Send to the desk'}
              </button>
              {message ? <p className="bm-msg-err">{message}</p> : null}
            </form>
          )}
        </section>
      </main>
    </BookShell>
  )
}
