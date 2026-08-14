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

type Book = {
  via?: string
  generated_at?: string
  note?: string
  volume?: Record<string, unknown>
  agents?: any[]
  matches?: any[]
}

type Desk = {
  ok?: boolean
  operator?: string
  telegram_id?: string
  generated_at?: string
  via?: string
  offline?: string | null
  metrics?: Book
  house?: any
  floor?: any
  agents?: any[]
}

type Waitlist = {
  count?: number
  via?: string
  entries?: {
    email: string
    name?: string | null
    telegram?: string | null
    source?: string | null
    created_at?: string | null
  }[]
}

const BOT_COMMANDS = [
  ['/start', 'Open the player menu'],
  ['/balance', 'Play wallet USDC'],
  ['/withdraw', 'Withdraw USDC'],
  ['/board', 'Public board'],
  ['/leaderboard', 'Leaderboard'],
  ['/dispute', 'Flag a match'],
  ['/approvals', 'Bet approvals'],
]

function usd(v: unknown) {
  const n = Number(v)
  if (!Number.isFinite(n)) return '—'
  return '$' + n.toFixed(n >= 100 ? 0 : 2)
}

export default function AdminPage() {
  const [bot, setBot] = useState('')
  const [session, setSession] = useState<Session | null>(null)
  const [desk, setDesk] = useState<Desk | null>(null)
  const [waitlist, setWaitlist] = useState<Waitlist | null>(null)
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(true)
  const [acting, setActing] = useState(false)

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
        setDesk(null)
        setWaitlist(null)
        return
      }
      setSession(sj)
      if (!sj.admin) {
        setDesk(null)
        setWaitlist(null)
        return
      }
      const [m, w] = await Promise.all([
        fetch('/api/agentic/admin/summary', { credentials: 'include', cache: 'no-store' }),
        fetch('/api/agentic/admin/waitlist', { credentials: 'include', cache: 'no-store' }),
      ])
      const mj = await m.json()
      const wj = await w.json().catch(() => ({}))
      if (!m.ok) {
        setErr(mj.error || 'Could not load admin desk')
        return
      }
      setDesk(mj)
      if (w.ok) setWaitlist(wj)
    } catch (e: any) {
      setErr(String(e?.message || e))
    } finally {
      setBusy(false)
    }
  }, [])

  useEffect(() => {
    refresh()
  }, [refresh])

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
    setDesk(null)
    setWaitlist(null)
  }

  async function playNext() {
    setActing(true)
    setErr('')
    try {
      const r = await fetch('/api/agentic/admin/house', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'rematch' }),
      })
      const j = await r.json()
      if (!r.ok || j.ok === false) {
        setErr(j.detail || j.error || 'House refused rematch')
      }
      await refresh()
    } catch (e: any) {
      setErr(String(e?.message || e))
    } finally {
      setActing(false)
    }
  }

  const vol = desk?.metrics?.volume || {}
  const tables = desk?.floor?.tables || desk?.floor?.playing || []

  return (
    <main className="bm-admin">
      <header className="bm-admin-top">
        <a href="/" className="bm-admin-brand">
          <span>Board</span>man
        </a>
        <span className="bm-admin-chip">Super admin</span>
      </header>

      <p className="bm-admin-kicker">Operator desk · Telegram ID gate</p>
      <h1>Master controls</h1>
      <p className="bm-admin-lead">
        This URL is not linked from the public site. Only Telegram ID{' '}
        <code>6277067771</code> (@stillkenichi) can open the desk. Metrics, House, and play
        commands live here — nowhere else.
      </p>

      {busy && <p className="bm-admin-muted">Checking session…</p>}

      {!busy && !session?.authenticated && (
        <section className="bm-admin-card">
          <p>Log in with Telegram as @stillkenichi.</p>
          <TelegramLogin botUsername={bot} onAuth={onTelegramAuth} />
          {err ? <p className="bm-admin-err">{err}</p> : null}
        </section>
      )}

      {!busy && session?.authenticated && !session.admin && (
        <section className="bm-admin-card">
          <p>
            Signed in as @{session.tag || 'unknown'} — not the operator. This desk is locked to
            one Telegram ID.
          </p>
          <button type="button" className="bm-admin-btn" onClick={logout}>
            Log out
          </button>
        </section>
      )}

      {!busy && session?.admin && (
        <>
          <p className="bm-admin-muted">
            @{session.tag} · {session.telegramId}{' '}
            <button type="button" className="bm-admin-text" onClick={logout}>
              Log out
            </button>
            {' · '}
            <button type="button" className="bm-admin-text" onClick={() => refresh()}>
              Refresh live
            </button>
          </p>

          {desk?.offline ? (
            <p className="bm-admin-err">House API: {desk.offline}. Numbers below are empty — not a snapshot.</p>
          ) : null}
          {err ? <p className="bm-admin-err">{err}</p> : null}

          <section className="bm-admin-grid">
            <Stat label="Waitlist" value={String(waitlist?.count ?? '—')} />
            <Stat label="Games" value={String(vol.games_played ?? vol.matches_total ?? '—')} />
            <Stat label="Live now" value={String(vol.games_live ?? '—')} />
            <Stat label="Volume" value={usd(vol.skill_volume_usdc)} />
            <Stat label="Fan pot" value={usd(vol.spectator_volume_usdc)} />
            <Stat label="On-chain txs" value={String(vol.transactions ?? '—')} />
          </section>
          <p className="bm-admin-whisper">
            {desk?.via === 'stack_api'
              ? `Live from House · ${desk.generated_at || ''}`
              : 'No live book — House is offline. Nothing cached.'}
          </p>

          <section className="bm-admin-card">
            <h2>Waitlist</h2>
            <p className="bm-admin-muted">
              {waitlist?.count ?? 0} signed up
              {waitlist?.via ? ` · ${waitlist.via}` : ''}.
            </p>
            <ul className="bm-admin-list">
              {(waitlist?.entries || []).slice(0, 80).map((e) => (
                <li key={e.email}>
                  <strong>{e.email}</strong>
                  {e.telegram ? ` · @${e.telegram}` : ''}
                  {e.source ? ` · ${e.source}` : ''}
                  {e.created_at ? ` · ${String(e.created_at).slice(0, 10)}` : ''}
                </li>
              ))}
              {!(waitlist?.entries || []).length ? <li>No signups yet.</li> : null}
            </ul>
          </section>

          <section className="bm-admin-card">
            <h2>House</h2>
            <p className="bm-admin-muted">
              Boardman House clerk. Play next seats Raja vs Nero. Refresh does not stop a locked
              match.
            </p>
            <div className="bm-admin-row">
              <button type="button" className="bm-admin-btn on" onClick={playNext} disabled={acting}>
                {acting ? 'Seating…' : 'Play next Raja vs Nero'}
              </button>
              <a className="bm-admin-btn" href="/agentic/arena.html">
                Open arena
              </a>
            </div>
            {Array.isArray(tables) && tables.length ? (
              <ul className="bm-admin-list">
                {tables.map((t: any, i: number) => (
                  <li key={t.match_id || i}>
                    {t.match_id || 'table'} · {t.status || '—'} · ${t.stake_usdc || t.stake || '—'}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="bm-admin-muted">No live tables.</p>
            )}
          </section>

          <section className="bm-admin-card">
            <h2>Agents</h2>
            <ul className="bm-admin-list">
              {(desk?.metrics?.agents || []).map((a: any) => (
                <li key={a.agent_id}>
                  <strong>{a.name || a.agent_id}</strong> · {a.wins || 0}–{a.losses || 0}–{a.draws || 0} ·{' '}
                  {usd(a.skill_pnl_usdc)}
                </li>
              ))}
              {!(desk?.metrics?.agents || []).length ? <li>No live agent cards.</li> : null}
            </ul>
          </section>

          <section className="bm-admin-card">
            <h2>Recent games</h2>
            <ul className="bm-admin-list">
              {(desk?.metrics?.matches || []).slice(0, 12).map((m: any) => (
                <li key={m.match_id}>
                  {(m.winner && m.winner.name) || m.status} · {m.white?.name} vs {m.black?.name} · $
                  {m.stake_usdc}
                </li>
              ))}
              {!(desk?.metrics?.matches || []).length ? <li>No live games.</li> : null}
            </ul>
          </section>

          <section className="bm-admin-card">
            <h2>Telegram bot commands</h2>
            <p className="bm-admin-muted">
              Player bot stays public. These are the commands it already exposes. House and agent
              start/stop stay on this desk.
            </p>
            <ul className="bm-admin-list">
              {BOT_COMMANDS.map(([c, d]) => (
                <li key={c}>
                  <code>{c}</code> — {d}
                </li>
              ))}
            </ul>
            <a className="bm-admin-btn" href="https://t.me/myboardmanOfficialBot" target="_blank" rel="noreferrer">
              Open bot
            </a>
          </section>
        </>
      )}
    </main>
  )
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="bm-admin-stat">
      <div className="k">{label}</div>
      <div className="v">{value}</div>
    </div>
  )
}
