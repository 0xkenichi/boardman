'use client'

import { useCallback, useEffect, useState } from 'react'
import Link from 'next/link'
import { AppShell } from '@/components/AppShell'
import { api, type Me } from '@/lib/appClient'

const BOT = 'https://t.me/ClawStationOfficialBot'

export default function RematchAppHome() {
  const [me, setMe] = useState<Me | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  const load = useCallback(async () => {
    setLoading(true)
    setErr(null)
    const sess = await api('/api/rematch/app/session')
    if (!sess.ok) {
      setMe(null)
      setLoading(false)
      return
    }
    const m = await api<Me>('/api/rematch/app/me')
    if (m.ok) setMe(m.data)
    else setErr((m.data as { error?: string } | null)?.error || 'Could not load profile')
    setLoading(false)
  }, [])

  useEffect(() => {
    load()
  }, [load])

  async function demoLogin() {
    setErr(null)
    const res = await api('/api/rematch/app/session', {
      method: 'POST',
      body: JSON.stringify({ mode: 'demo' }),
    })
    if (!res.ok) {
      setErr(res.data?.error || 'Login failed — set REMATCH_ALLOW_DEMO_LOGIN=1 for demo')
      return
    }
    await load()
  }

  async function logout() {
    await api('/api/rematch/app/session', {
      method: 'POST',
      body: JSON.stringify({ mode: 'logout' }),
    })
    setMe(null)
  }

  if (loading) {
    return (
      <AppShell>
        <p className="rm-muted">Loading…</p>
      </AppShell>
    )
  }

  if (!me) {
    return (
      <AppShell title="Sign in">
        <div className="rm-card" style={{ marginBottom: '1rem' }}>
          <h1 style={{ fontSize: '1.35rem', margin: '0 0 0.5rem' }}>Play Rematch</h1>
          <p className="rm-muted" style={{ marginBottom: '1rem' }}>
            Same account as Telegram. Same balance. No seed phrases — just challenge, lock,
            play, and send the final photo.
          </p>
          <button type="button" className="rm-btn rm-btn-primary" onClick={demoLogin}>
            Continue (demo login)
          </button>
          <p className="rm-muted" style={{ marginTop: '0.85rem', fontSize: '0.75rem' }}>
            Production uses <strong>Telegram Login</strong> (verified on our server). Demo mode
            needs <code>REMATCH_ALLOW_DEMO_LOGIN=1</code> locally.
          </p>
        </div>
        <a href={BOT} target="_blank" rel="noreferrer" className="rm-btn rm-btn-ghost">
          Open Telegram bot instead
        </a>
        {err ? (
          <p style={{ color: '#f87171', marginTop: '1rem', fontSize: '0.85rem' }}>{err}</p>
        ) : null}
      </AppShell>
    )
  }

  return (
    <AppShell>
      <div style={{ marginBottom: '1.25rem' }}>
        <p className="rm-muted" style={{ margin: 0 }}>
          Hi @{me.tag}
        </p>
        <div
          className="rm-card"
          style={{ marginTop: '0.75rem', background: 'rgba(5,150,105,0.08)', borderColor: '#065f46' }}
        >
          <span className="rm-label">Balance</span>
          <div style={{ fontSize: '2rem', fontWeight: 900, letterSpacing: '-0.03em' }}>
            ${Number(me.balance || 0).toFixed(2)}
          </div>
          <p className="rm-muted" style={{ margin: '0.35rem 0 0', fontSize: '0.8rem' }}>
            What you can stake right now
          </p>
          {me.otherBalance && me.otherBalance > 0.009 ? (
            <p style={{ color: '#fbbf24', fontSize: '0.8rem', marginTop: '0.5rem' }}>
              ⚠️ ${me.otherBalance.toFixed(2)} on another address — move to play wallet to stake
            </p>
          ) : null}
          {me.demo ? (
            <p className="rm-muted" style={{ marginTop: '0.5rem', fontSize: '0.7rem' }}>
              Demo mode — wire STACK_API_URL for live balances
            </p>
          ) : null}
        </div>
      </div>

      <div style={{ display: 'grid', gap: '0.65rem', marginBottom: '1.25rem' }}>
        <Link href="/rematch/app/challenge" className="rm-btn rm-btn-primary">
          ⚔️ Challenge a friend
        </Link>
        <Link href="/rematch/app/match" className="rm-btn rm-btn-ghost">
          🎮 My match
        </Link>
        <Link href="/rematch/app/wallet" className="rm-btn rm-btn-ghost">
          💧 Get money
        </Link>
      </div>

      <div className="rm-card">
        <p className="rm-muted" style={{ margin: 0 }}>
          <strong style={{ color: '#e5e7eb' }}>How it works</strong>
          <br />
          1. Get money → 2. Challenge → 3. Both lock → 4. Play (phone / iMessage / console) →
          5. Upload final photo → winner gets paid.
        </p>
        {me.playPoints != null ? (
          <p className="rm-muted" style={{ marginTop: '0.75rem', marginBottom: 0 }}>
            PLAY score: <strong style={{ color: '#34d399' }}>{me.playPoints}</strong> (not cash)
          </p>
        ) : null}
      </div>

      <button
        type="button"
        onClick={logout}
        className="rm-btn rm-btn-ghost"
        style={{ marginTop: '1rem', fontSize: '0.8rem', fontWeight: 500 }}
      >
        Log out
      </button>
      {err ? (
        <p style={{ color: '#f87171', marginTop: '0.75rem', fontSize: '0.85rem' }}>{err}</p>
      ) : null}
    </AppShell>
  )
}
