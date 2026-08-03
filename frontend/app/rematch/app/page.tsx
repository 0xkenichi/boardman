'use client'

import { useCallback, useEffect, useState } from 'react'
import Link from 'next/link'
import { AppShell } from '@/components/AppShell'
import { TelegramLogin } from '@/components/TelegramLogin'
import { api, type Me } from '@/lib/appClient'

const BOT = process.env.NEXT_PUBLIC_TELEGRAM_BOT_URL || 'https://t.me/ClawStationOfficialBot'
const BOT_USERNAME =
  process.env.NEXT_PUBLIC_TELEGRAM_BOT_USERNAME ||
  process.env.NEXT_PUBLIC_TELEGRAM_BOT_NAME ||
  ''

export default function RematchAppHome() {
  const [me, setMe] = useState<Me | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [tgMissing, setTgMissing] = useState(() => !BOT_USERNAME)

  const load = useCallback(async () => {
    setLoading(true)
    setErr(null)
    try {
      const sess = await api('/api/rematch/app/session')
      if (!sess.ok) {
        setMe(null)
        return
      }
      const m = await api<Me>('/api/rematch/app/me')
      if (m.ok) setMe(m.data)
      else setErr((m.data as { error?: string } | null)?.error || 'Could not load profile')
    } catch (e: any) {
      setErr(e?.message || 'Network error')
      setMe(null)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      await load()
      if (cancelled) return
      try {
        const w = window as any
        const tg = w.Telegram?.WebApp
        if (tg?.initData) {
          tg.ready?.()
          const res = await api('/api/rematch/app/session', {
            method: 'POST',
            body: JSON.stringify({ mode: 'webapp', initData: tg.initData }),
          })
          if (!cancelled && res.ok) await load()
        }
      } catch {
        /* not in WebApp */
      }
    })()
    return () => {
      cancelled = true
    }
  }, [load])

  const onTelegramAuth = useCallback(
    async (user: Record<string, string | number>) => {
      setErr(null)
      try {
        const res = await api('/api/rematch/app/session', {
          method: 'POST',
          body: JSON.stringify({ mode: 'telegram', ...user }),
        })
        if (!res.ok) {
          if (res.data?.error === 'open_bot_first') {
            setErr(res.data.message || 'Open the Rematch bot once, then sign in again.')
            return
          }
          setErr(res.data?.error || 'Telegram login failed')
          return
        }
        await load()
      } catch (e: any) {
        setErr(e?.message || 'Login failed')
      }
    },
    [load]
  )

  const onTgMissing = useCallback(() => setTgMissing(true), [])

  async function demoLogin() {
    setErr(null)
    try {
      const res = await api('/api/rematch/app/session', {
        method: 'POST',
        body: JSON.stringify({ mode: 'demo' }),
      })
      if (!res.ok) {
        setErr(res.data?.error || 'Demo login disabled in production')
        return
      }
      await load()
    } catch (e: any) {
      setErr(e?.message || 'Demo login failed')
    }
  }

  async function logout() {
    try {
      await api('/api/rematch/app/session', {
        method: 'POST',
        body: JSON.stringify({ mode: 'logout' }),
      })
    } catch {
      /* ignore */
    }
    setMe(null)
  }

  if (loading) {
    return (
      <AppShell>
        <div className="rm-stack">
          <div className="rm-skeleton" style={{ height: 120, borderRadius: 16 }} />
          <div className="rm-skeleton" style={{ height: 56, borderRadius: 14 }} />
          <div className="rm-skeleton" style={{ height: 56, borderRadius: 14 }} />
        </div>
      </AppShell>
    )
  }

  if (!me) {
    const showDemo =
      process.env.NODE_ENV !== 'production' ||
      process.env.NEXT_PUBLIC_ALLOW_DEMO_LOGIN === '1'

    return (
      <AppShell>
        <div className="rm-stack-lg">
          <div className="rm-card rm-card-hero">
            <p className="rm-section-title">Sign in</p>
            <h1 className="rm-h1" style={{ marginBottom: '0.5rem' }}>
              Play Rematch
            </h1>
            <p className="rm-muted rm-mb-0">
              Same account as Telegram. Same balance. Challenge, lock, play, send the final photo —
              no seed phrases.
            </p>
          </div>

          <div className="rm-card">
            <p className="rm-label">Continue with Telegram</p>
            <TelegramLogin
              botUsername={BOT_USERNAME}
              onAuth={onTelegramAuth}
              onMissing={onTgMissing}
            />
            {tgMissing ? (
              <p className="rm-muted" style={{ fontSize: '0.75rem', marginTop: '0.75rem', marginBottom: 0 }}>
                BotFather <code>/setdomain</code> must include <strong>playingsidequest.fun</strong>.
              </p>
            ) : null}
          </div>

          {showDemo ? (
            <button type="button" className="rm-btn rm-btn-ghost" onClick={demoLogin}>
              Continue with demo login
            </button>
          ) : null}

          <a href={BOT} target="_blank" rel="noreferrer" className="rm-btn rm-btn-primary">
            Open Telegram bot
          </a>

          <p className="rm-muted" style={{ fontSize: '0.75rem', textAlign: 'center', margin: 0 }}>
            First time? Open the bot once so we can create your wallet, then sign in here.
          </p>

          {err ? <p className="rm-err">{err}</p> : null}
        </div>
      </AppShell>
    )
  }

  return (
    <AppShell>
      <div className="rm-stack-lg">
        <div>
          <p className="rm-muted" style={{ margin: '0 0 0.15rem', fontSize: '0.8rem' }}>
            Welcome back
          </p>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap' }}>
            <h1 className="rm-h1">@{me.tag}</h1>
            {me.demo ? <span className="rm-chip-dim rm-chip">Demo</span> : (
              <span className="rm-chip">Live</span>
            )}
          </div>
        </div>

        <div className="rm-card rm-card-hero">
          <span className="rm-label">Stakeable balance</span>
          <div className="rm-balance">
            <span>$</span>
            {Number(me.balance || 0).toFixed(2)}
          </div>
          <p className="rm-muted" style={{ margin: '0.5rem 0 0', fontSize: '0.8rem' }}>
            Ready to challenge right now
          </p>
          {me.playPoints != null ? (
            <p style={{ margin: '0.65rem 0 0', fontSize: '0.85rem', color: '#d1d5db' }}>
              PLAY score{' '}
              <strong style={{ color: '#34d399' }}>{me.playPoints}</strong>
              <span className="rm-muted"> · not cash</span>
            </p>
          ) : null}
          {me.otherBalance && me.otherBalance > 0.009 ? (
            <p className="rm-warn-text">
              ⚠️ ${me.otherBalance.toFixed(2)} on another address — move to play wallet to stake
            </p>
          ) : null}
          {(me as any).paused ? (
            <p className="rm-err" style={{ marginTop: '0.65rem' }}>
              Matching is paused. Check Telegram for updates.
            </p>
          ) : null}
        </div>

        <div className="rm-stack">
          <Link href="/rematch/app/challenge" className="rm-action">
            <span className="rm-action-ico">⚔️</span>
            <span className="rm-action-body">
              <span className="rm-action-title">Challenge a friend</span>
              <span className="rm-action-sub">Pick stake, game, send challenge</span>
            </span>
            <span className="rm-action-chev">›</span>
          </Link>
          <Link href="/rematch/app/match" className="rm-action">
            <span className="rm-action-ico">🎮</span>
            <span className="rm-action-body">
              <span className="rm-action-title">My matches</span>
              <span className="rm-action-sub">Open codes, lock, submit results</span>
            </span>
            <span className="rm-action-chev">›</span>
          </Link>
          <Link href="/rematch/app/wallet" className="rm-action">
            <span className="rm-action-ico">💰</span>
            <span className="rm-action-body">
              <span className="rm-action-title">Wallet & fund</span>
              <span className="rm-action-sub">Copy address, faucet, refresh</span>
            </span>
            <span className="rm-action-chev">›</span>
          </Link>
        </div>

        <div className="rm-card">
          <p className="rm-label">How it works</p>
          <ol className="rm-muted" style={{ margin: 0, paddingLeft: '1.1rem', lineHeight: 1.65 }}>
            <li>Get money into your play wallet</li>
            <li>Challenge a friend</li>
            <li>Both lock</li>
            <li>Play → upload final photo → winner paid</li>
          </ol>
        </div>

        <button
          type="button"
          onClick={logout}
          className="rm-btn rm-btn-ghost"
          style={{ fontSize: '0.8rem', fontWeight: 600 }}
        >
          Log out
        </button>
        {err ? <p className="rm-err">{err}</p> : null}
      </div>
    </AppShell>
  )
}
