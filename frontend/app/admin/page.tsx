'use client'

import { useCallback, useEffect, useState } from 'react'
import { TelegramLogin } from '@/components/TelegramLogin'

type Session = {
  authenticated?: boolean
  tag?: string
  name?: string
  telegramId?: string
  admin?: boolean
}

type Metrics = {
  players_count?: number
  profiles_count?: number
  total_arc?: string
  profiles?: { id: string; arc: string }[]
}

export default function AdminPage() {
  const [bot, setBot] = useState('')
  const [session, setSession] = useState<Session | null>(null)
  const [metrics, setMetrics] = useState<Metrics | null>(null)
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(true)

  const refresh = useCallback(async () => {
    setBusy(true)
    setErr('')
    try {
      const cfg = await fetch('/api/agentic/auth-config', { cache: 'no-store' }).then((r) => r.json())
      if (cfg?.bot_username) setBot(cfg.bot_username)
      const s = await fetch('/api/rematch/app/session', { credentials: 'include', cache: 'no-store' })
      const sj = await s.json()
      if (!sj?.authenticated) {
        setSession({ authenticated: false })
        setMetrics(null)
        return
      }
      setSession(sj)
      if (!sj.admin) {
        setMetrics(null)
        return
      }
      const m = await fetch('/api/agentic/admin/summary', { credentials: 'include', cache: 'no-store' })
      const mj = await m.json()
      if (!m.ok) {
        setErr(mj.error || 'Could not load admin data')
        return
      }
      setMetrics(mj.metrics || {})
    } catch (e: any) {
      setErr(String(e?.message || e))
    } finally {
      setBusy(false)
    }
  }, [])

  useEffect(() => {
    refresh()
  }, [refresh])

  useEffect(() => {
    if (document.getElementById('bm-nav-js')) return
    const s = document.createElement('script')
    s.id = 'bm-nav-js'
    s.src = '/boardman-nav.js'
    document.body.appendChild(s)
  }, [])

  async function onTelegramAuth(user: Record<string, string | number>) {
    setErr('')
    const res = await fetch('/api/rematch/app/session', {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ mode: 'telegram', ...user }),
    })
    const data = await res.json()
    if (!data?.ok) {
      setErr(data?.message || data?.error || 'Telegram login failed')
      return
    }
    await refresh()
  }

  async function logout() {
    await fetch('/api/rematch/app/session', {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ mode: 'logout' }),
    })
    setSession({ authenticated: false })
    setMetrics(null)
  }

  return (
    <>
      <link rel="stylesheet" href="/boardman-nav.css" />
      <div id="bm-nav-root" />
      <main
        style={{
          maxWidth: 920,
          margin: '0 auto',
          padding: '88px 20px 80px',
        }}
      >
        <p
          style={{
            color: '#a78bfa',
            fontSize: 12,
            letterSpacing: '0.08em',
            textTransform: 'uppercase',
            margin: '0 0 8px',
          }}
        >
          Operator
        </p>
        <h1 style={{ margin: '0 0 8px', fontSize: '1.7rem' }}>Admin</h1>
        <p style={{ color: '#9ca3af', margin: '0 0 24px', maxWidth: 36 * 16 }}>
          This page is only for <strong style={{ color: '#e4e4e7' }}>@stillkenichi</strong> after
          Telegram login on this site. Everyone else is refused.
        </p>

        {busy && <p style={{ color: '#9ca3af' }}>Checking session…</p>}

        {!busy && !session?.authenticated && (
          <div
            style={{
              background: '#0e0e14',
              border: '1px solid #23232f',
              borderRadius: 14,
              padding: 20,
            }}
          >
            <p style={{ margin: '0 0 14px', color: '#d4d4d8' }}>
              Log in with Telegram as @stillkenichi.
            </p>
            <TelegramLogin botUsername={bot} onAuth={onTelegramAuth} />
            {err ? <p style={{ color: '#f87171', marginTop: 12 }}>{err}</p> : null}
          </div>
        )}

        {!busy && session?.authenticated && !session.admin && (
          <div
            style={{
              background: '#0e0e14',
              border: '1px solid #23232f',
              borderRadius: 14,
              padding: 20,
            }}
          >
            <p style={{ margin: 0, color: '#d4d4d8' }}>
              Signed in as @{session.tag || 'unknown'} — this account is not an operator.
            </p>
            <button
              type="button"
              onClick={logout}
              style={{
                marginTop: 14,
                background: '#1c1c24',
                color: '#e4e4e7',
                border: '1px solid #23232f',
                borderRadius: 10,
                padding: '8px 14px',
                cursor: 'pointer',
              }}
            >
              Log out
            </button>
          </div>
        )}

        {!busy && session?.admin && metrics && (
          <div>
            <p style={{ color: '#9ca3af', marginTop: 0 }}>
              Signed in as @{session.tag}{' '}
              <button
                type="button"
                onClick={logout}
                style={{
                  marginLeft: 8,
                  background: 'transparent',
                  color: '#a78bfa',
                  border: 0,
                  cursor: 'pointer',
                }}
              >
                Log out
              </button>
            </p>
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fit,minmax(180px,1fr))',
                gap: 12,
                marginBottom: 16,
              }}
            >
              <Stat label="Players" value={String(metrics.players_count ?? '—')} />
              <Stat label="Profiles" value={String(metrics.profiles_count ?? '—')} />
              <Stat label="Total ARC USDC" value={String(metrics.total_arc ?? '—')} />
            </div>
            <div
              style={{
                background: '#0e0e14',
                border: '1px solid #23232f',
                borderRadius: 14,
                padding: 16,
              }}
            >
              <h2 style={{ fontSize: '1rem', margin: '0 0 10px' }}>Profiles</h2>
              <ul style={{ margin: 0, paddingLeft: 18, color: '#d4d4d8', fontSize: 14 }}>
                {(metrics.profiles || []).map((p) => (
                  <li key={p.id} style={{ wordBreak: 'break-all' }}>
                    {p.id} — {p.arc} ARC
                  </li>
                ))}
              </ul>
            </div>
            {err ? <p style={{ color: '#f87171' }}>{err}</p> : null}
          </div>
        )}
      </main>
    </>
  )
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div
      style={{
        background: '#0e0e14',
        border: '1px solid #23232f',
        borderRadius: 14,
        padding: 16,
      }}
    >
      <div style={{ color: '#9ca3af', fontSize: 12, textTransform: 'uppercase' }}>{label}</div>
      <div style={{ fontSize: 22, fontWeight: 700, marginTop: 4 }}>{value}</div>
    </div>
  )
}
