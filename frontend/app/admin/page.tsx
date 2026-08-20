'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
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
  transactions?: any[]
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

type Schedule = {
  ok?: boolean
  presets?: Record<string, number>
  schedule?: {
    enabled?: boolean
    cadence_sec?: number
    burst_games?: number
    set_by?: string
    updated_at?: string | null
    last_settled_at?: string | null
    last_match_id?: string | null
  }
}

type Status = {
  ok?: boolean
  generated_at?: string
  api?: { ok?: boolean; host?: string }
  bot?: { running?: boolean; pid?: string | null }
  schedule?: any
  presets?: Record<string, number>
  agents?: {
    agent_id: string
    name: string
    wallet: string
    bankroll_usdc: number
    webhook_up?: boolean
    webhook_port?: number | null
  }[]
  games_24h?: number
  games_live?: number
  last_settled?: {
    match_id?: string
    result?: string
    winner?: string
    stake_usdc?: string
    settled_at?: string
  } | null
  next_game_at?: string | null
  next_in_sec?: number | null
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

const SECTIONS = [
  ['overview', 'Overview'],
  ['platform', 'Platform'],
  ['match', 'Match control'],
  ['status', 'System status'],
  ['waitlist', 'Waitlist'],
  ['agents', 'Agents'],
  ['tx', 'Transaction log'],
  ['games', 'Recent games'],
] as const

type SectionId = (typeof SECTIONS)[number][0]

function usd(v: unknown) {
  const n = Number(v)
  if (!Number.isFinite(n)) return '—'
  return '$' + n.toFixed(n >= 100 ? 0 : 2)
}

function fmtAgo(iso?: string | null) {
  if (!iso) return '—'
  const t = Date.parse(iso)
  if (!Number.isFinite(t)) return '—'
  const s = Math.max(0, Math.floor((Date.now() - t) / 1000))
  if (s < 60) return `${s}s ago`
  if (s < 3600) return `${Math.floor(s / 60)}m ago`
  return `${Math.floor(s / 3600)}h ago`
}

function Dot({ ok, label }: { ok: boolean; label: string }) {
  return (
    <span className="bm-admin-dot">
      <span className={`bm-admin-led ${ok ? 'ok' : 'bad'}`} />
      {label}
    </span>
  )
}

export default function AdminPage() {
  const [bot, setBot] = useState('')
  const [session, setSession] = useState<Session | null>(null)
  const [desk, setDesk] = useState<Desk | null>(null)
  const [waitlist, setWaitlist] = useState<Waitlist | null>(null)
  const [schedule, setSchedule] = useState<Schedule | null>(null)
  const [status, setStatus] = useState<Status | null>(null)
  const [section, setSection] = useState<SectionId>('overview')
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(true)
  const [acting, setActing] = useState(false)
  const [burstN, setBurstN] = useState(5)
  const [, setTick] = useState(0)
  const [platformMetrics, setPlatformMetrics] = useState<any>(null)

  const refresh = useCallback(async (opts?: { quiet?: boolean }) => {
    if (!opts?.quiet) setBusy(true)
    if (opts?.quiet) setErr('')
    try {
      const cfg = await fetch('/api/agentic/auth-config', { cache: 'no-store' }).then((r) => r.json())
      if (cfg?.bot_username) setBot(cfg.bot_username)
      const s = await fetch('/api/rematch/app/session', { credentials: 'include', cache: 'no-store' })
      const sj = await s.json()
      if (!sj?.authenticated) {
        setSession({ authenticated: false })
        setDesk(null)
        setWaitlist(null)
        setSchedule(null)
        setStatus(null)
        return
      }
      setSession(sj)
      if (!sj.admin) {
        setDesk(null)
        setWaitlist(null)
        setSchedule(null)
        setStatus(null)
        return
      }
      const [m, w, sc, st, pm] = await Promise.all([
        fetch('/api/agentic/admin/summary', { credentials: 'include', cache: 'no-store' }),
        fetch('/api/agentic/admin/waitlist', { credentials: 'include', cache: 'no-store' }),
        fetch('/api/agentic/admin/schedule', { credentials: 'include', cache: 'no-store' }),
        fetch('/api/agentic/admin/status', { credentials: 'include', cache: 'no-store' }),
        fetch('/api/agentic/admin/metrics-detail', { credentials: 'include', cache: 'no-store' }).catch(() => null),
      ])
      const mj = await m.json()
      const wj = await w.json().catch(() => ({}))
      const scj = await sc.json().catch(() => ({}))
      const stj = await st.json().catch(() => ({}))
      const pmj = pm ? await pm.json().catch(() => null) : null
      if (!m.ok) {
        setErr(mj.error || 'Could not load admin desk')
        return
      }
      setDesk(mj)
      if (w.ok) setWaitlist(wj)
      if (sc.ok) setSchedule(scj)
      if (st.ok) setStatus(stj)
      if (pmj?.success) setPlatformMetrics(pmj)
    } catch (e: any) {
      if (!opts?.quiet) setErr(String(e?.message || e))
    } finally {
      setBusy(false)
    }
  }, [])

  useEffect(() => {
    refresh()
  }, [refresh])

  // Live desk: re-poll every 25s so status/metrics stay fresh.
  useEffect(() => {
    const id = setInterval(() => refresh({ quiet: true }), 25000)
    return () => clearInterval(id)
  }, [refresh])

  // Countdown tick for "next game in".
  useEffect(() => {
    const id = setInterval(() => setTick((t) => t + 1), 1000)
    return () => clearInterval(id)
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
    setDesk(null)
    setWaitlist(null)
    setSchedule(null)
    setStatus(null)
  }

  async function applySchedule(payload: { cadence_sec?: number; burst_games?: number; enabled?: boolean }, label: string) {
    setActing(true)
    setErr('')
    try {
      const r = await fetch('/api/agentic/admin/schedule', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      const j = await r.json()
      if (!r.ok || j.ok === false) {
        setErr(j.error || j.detail || `${label} failed`)
      } else {
        setSchedule(j)
      }
      await refresh({ quiet: true })
    } catch (e: any) {
      setErr(String(e?.message || e))
    } finally {
      setActing(false)
    }
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
  const sc = schedule?.schedule || {}
  const cadenceMin = Math.round(Number(sc.cadence_sec || 0) / 60)
  const nextIn = status?.next_in_sec ?? null
  const txByStep: Record<string, number> = (vol.tx_by_step as Record<string, number>) || {}

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
        <code>6277067771</code> (@stillkenichi) can open the desk. Live metrics, House match
        scheduling, and system status live here — nowhere else.
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
        <div className="bm-admin-shell">
          <nav className="bm-admin-side">
            <p className="bm-admin-side-ops">
              @{session.tag}
              <br />
              <button type="button" className="bm-admin-text" onClick={logout}>
                Log out
              </button>
              {' · '}
              <button type="button" className="bm-admin-text" onClick={() => refresh()}>
                Refresh
              </button>
            </p>
            {SECTIONS.map(([id, label]) => (
              <button
                key={id}
                type="button"
                className={`bm-admin-nav ${section === id ? 'on' : ''}`}
                onClick={() => setSection(id)}
              >
                {label}
              </button>
            ))}
          </nav>

          <div className="bm-admin-main">
            {desk?.offline ? (
              <p className="bm-admin-err">House API: {desk.offline}. Numbers below are empty — not a snapshot.</p>
            ) : null}
            {err ? <p className="bm-admin-err">{err}</p> : null}
            <p className="bm-admin-whisper">
              {desk?.via === 'stack_api' ? `Live from House · ${desk.generated_at || ''}` : 'No live book — House is offline.'}
            </p>

            {section === 'overview' && (
              <>
                <section className="bm-admin-grid">
                  <Stat label="Waitlist" value={String(waitlist?.count ?? '—')} />
                  <Stat label="Games settled" value={String(vol.matches_settled ?? vol.games_played ?? '—')} />
                  <Stat label="Live now" value={String(vol.games_live ?? '—')} />
                  <Stat label="Skill volume" value={usd(vol.skill_volume_usdc)} />
                  <Stat label="Fan pot" value={usd(vol.spectator_volume_usdc)} />
                  <Stat label="Total volume" value={usd(Number(vol.skill_volume_usdc || 0) + Number(vol.spectator_volume_usdc || 0))} />
                  <Stat label="On-chain volume" value={usd(vol.total_onchain_volume_usdc ?? vol.onchain_volume_30d_usdc)} />
                  <Stat label="Volume 30d" value={usd(vol.volume_30d_usdc)} />
                  <Stat label="On-chain matches" value={String(vol.matches_onchain ?? '—')} />
                  <Stat label="Txs (unique)" value={String(vol.transactions ?? '—')} />
                </section>
                <section className="bm-admin-card">
                  <h2>Match schedule</h2>
                  <p className="bm-admin-muted">
                    {sc.enabled === false
                      ? 'Paused — bots are idle. Resume from Match control.'
                      : `Active: one session game every ${cadenceMin} min${sc.burst_games ? ` · burst: ${sc.burst_games} left` : ''}${status?.next_in_sec != null ? ` · next game in ${Math.ceil(status.next_in_sec / 60)}m` : ''}`}
                  </p>
                  <p className="bm-admin-muted">
                    Games in last 24h: <strong>{status?.games_24h ?? '—'}</strong> · last settled:{' '}
                    {status?.last_settled?.match_id
                      ? `${status.last_settled.match_id} (${status.last_settled.result}) ${fmtAgo(status.last_settled.settled_at)}`
                      : '—'}
                  </p>
                </section>
              </>
            )}

            {section === 'platform' && (
              <>
                {platformMetrics ? (
                  <>
                    <section className="bm-admin-card">
                      <h2>Platform Summary</h2>
                      <p className="bm-admin-muted">All-time totals since first transaction</p>
                      <div className="bm-admin-grid">
                        <Stat label="Total matches" value={String(platformMetrics.summary?.total_matches ?? 0)} />
                        <Stat label="Settled" value={String(platformMetrics.summary?.total_settled ?? 0)} />
                        <Stat label="Live now" value={String(platformMetrics.summary?.total_live ?? 0)} />
                        <Stat label="Total transactions" value={String(platformMetrics.summary?.total_transactions ?? 0)} />
                        <Stat label="Total volume" value={usd(platformMetrics.summary?.total_volume_usdc)} />
                        <Stat label="Skill volume" value={usd(platformMetrics.summary?.total_skill_volume_usdc)} />
                        <Stat label="Spectator volume" value={usd(platformMetrics.summary?.total_spectator_volume_usdc)} />
                        <Stat label="On-chain volume" value={usd(platformMetrics.summary?.total_onchain_volume_usdc)} />
                        <Stat label="Unique bettors" value={String(platformMetrics.summary?.unique_bettors ?? 0)} />
                        <Stat label="First match" value={platformMetrics.summary?.first_match_at?.slice(0, 10) ?? '—'} />
                        <Stat label="Last match" value={platformMetrics.summary?.last_match_at?.slice(0, 10) ?? '—'} />
                      </div>
                    </section>

                    <section className="bm-admin-card">
                      <h2>Human vs Agent</h2>
                      <div className="bm-admin-grid">
                        <Stat label="Human matches" value={String(platformMetrics.human_vs_agent?.human?.matches ?? 0)} />
                        <Stat label="Human skill volume" value={usd(platformMetrics.human_vs_agent?.human?.skill_volume_usdc)} />
                        <Stat label="Human bet volume" value={usd(platformMetrics.human_vs_agent?.human?.bet_volume_usdc)} />
                        <Stat label="Agent matches" value={String(platformMetrics.human_vs_agent?.agent?.matches ?? 0)} />
                        <Stat label="Agent skill volume" value={usd(platformMetrics.human_vs_agent?.agent?.skill_volume_usdc)} />
                        <Stat label="Agent bet volume" value={usd(platformMetrics.human_vs_agent?.agent?.bet_volume_usdc)} />
                      </div>
                    </section>

                    <section className="bm-admin-card">
                      <h2>Wallet Balances</h2>
                      <div className="bm-admin-grid">
                        {Object.entries(platformMetrics.wallet_balances || {}).map(([aid, w]: [string, any]) => (
                          <Stat key={aid} label={`${w.name} (${w.wallet?.slice(0, 8)}…)`} value={usd(w.balance_usdc)} />
                        ))}
                      </div>
                    </section>

                    <section className="bm-admin-card">
                      <h2>Liquidity Pools</h2>
                      <div className="bm-admin-grid">
                        <Stat label="Total LP deposited" value={usd(platformMetrics.total_lp_deposited_usdc)} />
                        {Object.entries(platformMetrics.lp_pools || {}).map(([aid, pool]: [string, any]) => (
                          <Stat key={aid} label={`${aid.slice(6, 20)}…`} value={`${usd(pool.total_deposited)} deposited · ${pool.positions} LPs`} />
                        ))}
                      </div>
                    </section>

                    <section className="bm-admin-card">
                      <h2>Spectator Pools</h2>
                      <div className="bm-admin-grid">
                        <Stat label="Total spectator pool" value={usd(platformMetrics.spectator_pool_total_usdc)} />
                      </div>
                    </section>
                  </>
                ) : (
                  <p className="bm-admin-muted">Loading platform metrics…</p>
                )}
              </>
            )}

            {section === 'match' && (
              <>
                <section className="bm-admin-card">
                  <h2>Cadence presets</h2>
                  <p className="bm-admin-muted">
                    The bots challenge each other on a schedule. Each game still opens a 2-minute
                    bet window, so cadence is minutes between game starts.
                  </p>
                  <div className="bm-admin-row">
                    {(Object.entries(schedule?.presets || {
                      '48/day (every 30m)': 1800,
                      '96/day (every 15m)': 900,
                      '144/day (every 10m)': 600,
                      continuous: 0,
                    }) as [string, number][]).map(([label, sec]) => (
                      <button
                        key={label}
                        type="button"
                        className={`bm-admin-btn ${sc.cadence_sec === sec ? 'on' : ''}`}
                        disabled={acting}
                        onClick={() => applySchedule({ cadence_sec: sec }, 'cadence')}
                      >
                        {label}
                      </button>
                    ))}
                  </div>
                  <p className="bm-admin-muted">
                    Current: {cadenceMin > 0 ? `every ${cadenceMin} min (${Math.round(86400 / Number(sc.cadence_sec || 86400))}/day)` : 'continuous'} · set by {sc.set_by}{' '}
                    {sc.updated_at ? `· ${fmtAgo(sc.updated_at)}` : ''}
                  </p>
                </section>

                <section className="bm-admin-card">
                  <h2>Play now / burst</h2>
                  <p className="bm-admin-muted">
                    Play now seats Raja vs Nero immediately (also available to anyone on the arena
                    page). Burst plays N games back-to-back regardless of cadence, then resumes.
                  </p>
                  <div className="bm-admin-row">
                    <button type="button" className="bm-admin-btn on" onClick={playNext} disabled={acting}>
                      {acting ? 'Seating…' : '▶ Play next now'}
                    </button>
                    <button
                      type="button"
                      className="bm-admin-btn"
                      disabled={acting}
                      onClick={() => applySchedule({ burst_games: 1 }, 'burst')}
                    >
                      +1 game now
                    </button>
                    <input
                      className="bm-admin-input"
                      type="number"
                      min={1}
                      max={1000}
                      value={burstN}
                      onChange={(e) => setBurstN(Number(e.target.value) || 1)}
                    />
                    <button
                      type="button"
                      className="bm-admin-btn on"
                      disabled={acting}
                      onClick={() => applySchedule({ burst_games: burstN }, 'burst')}
                    >
                      ⚡ Burst {burstN} games in a row
                    </button>
                  </div>
                  <p className="bm-admin-muted">
                    {sc.burst_games ? (
                      <>
                        Burst active: <strong>{sc.burst_games} game(s)</strong> left, then cadence
                        resumes. <button type="button" className="bm-admin-text"                        onClick={() => applySchedule({ burst_games: 0 }, 'cancel burst')}>cancel</button>
                      </>
                    ) : (
                      'No burst queued.'
                    )}
                  </p>
                </section>

                <section className="bm-admin-card">
                  <h2>Pause / resume</h2>
                  <div className="bm-admin-row">
                    {sc.enabled === false ? (
                      <button type="button" className="bm-admin-btn on" disabled={acting} onClick={() => applySchedule({ enabled: true }, 'resume')}>
                        ▶ Resume schedule
                      </button>
                    ) : (
                      <button type="button" className="bm-admin-btn" disabled={acting} onClick={() => applySchedule({ enabled: false }, 'pause')}>
                        ⏸ Pause schedule (Play now still works)
                      </button>
                    )}
                  </div>
                </section>

                <section className="bm-admin-card">
                  <h2>Live tables</h2>
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
              </>
            )}

            {section === 'status' && (
              <>
                <section className="bm-admin-card">
                  <h2>System health</h2>
                  <div className="bm-admin-status-row">
                    <Dot ok={!!status?.api?.ok} label="Boardman API" />
                    <Dot ok={!!status?.bot?.running} label={`Telegram bot${status?.bot?.pid ? ` (pid ${status.bot.pid})` : ''}`} />
                    {(status?.agents || []).map((a) => (
                      <Dot
                        key={a.agent_id}
                        ok={a.agent_id === 'agent_boardman_house' ? true : !!a.webhook_up}
                        label={`${a.name}${a.webhook_port ? ` webhook :${a.webhook_port}` : ''}`}
                      />
                    ))}
                  </div>
                  <p className="bm-admin-muted">
                    {status?.generated_at ? `Last probe ${fmtAgo(status.generated_at)} · auto-refreshes every 25s` : 'Probe unavailable — House API unreachable.'}
                  </p>
                </section>

                <section className="bm-admin-card">
                  <h2>Agents & wallets</h2>
                  <ul className="bm-admin-list">
                    {(status?.agents || []).map((a) => (
                      <li key={a.agent_id}>
                        <strong>{a.name}</strong> · {usd(a.bankroll_usdc)} bankroll · {a.wallet ? a.wallet.slice(0, 12) + '…' : 'no wallet'}
                        {a.agent_id !== 'agent_boardman_house' ? ` · webhook ${a.webhook_up ? 'up' : 'down'}` : ''}
                      </li>
                    ))}
                    {!(status?.agents || []).length ? <li>No agent data.</li> : null}
                  </ul>
                </section>

                <section className="bm-admin-card">
                  <h2>Last settlement</h2>
                  {status?.last_settled?.match_id ? (
                    <p className="bm-admin-muted">
                      {status.last_settled.match_id} · {status.last_settled.result} · winner{' '}
                      {status.last_settled.winner || '—'} · stake ${status.last_settled.stake_usdc} ·{' '}
                      {fmtAgo(status.last_settled.settled_at)}
                    </p>
                  ) : (
                    <p className="bm-admin-muted">No settled match yet.</p>
                  )}
                  {nextIn != null ? (
                    <p className="bm-admin-muted">
                      Next scheduled game in <strong>{Math.floor(nextIn / 60)}m {nextIn % 60}s</strong>
                    </p>
                  ) : null}
                </section>
              </>
            )}

            {section === 'waitlist' && (
              <section className="bm-admin-card">
                <h2>Waitlist</h2>
                <p className="bm-admin-muted">
                  {waitlist?.count ?? 0} signed up{waitlist?.via ? ` · ${waitlist.via}` : ''}. You get a
                  Telegram ping on every new signup.
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
            )}

            {section === 'agents' && (
              <section className="bm-admin-card">
                <h2>Agents</h2>
                <ul className="bm-admin-list">
                  {(desk?.metrics?.agents || []).map((a: any) => (
                    <li key={a.agent_id}>
                      <strong>{a.name || a.agent_id}</strong> · {a.wins || 0}–{a.losses || 0}–{a.draws || 0} ·{' '}
                      {usd(a.skill_pnl_usdc)} PnL · {usd(a.stake_volume_usdc)} staked
                      <br />
                      <span className="bm-admin-muted">
                        30d on-chain vol {usd(a.onchain_volume_30d_usdc)} · fees earned{' '}
                        {usd(a.fees_earned_usdc)}
                        {a.bankroll_usdc != null ? ` · bankroll ${usd(a.bankroll_usdc)}` : ''}
                      </span>
                    </li>
                  ))}
                  {!(desk?.metrics?.agents || []).length ? <li>No live agent cards.</li> : null}
                </ul>
              </section>
            )}

            {section === 'tx' && (
              <>
                <section className="bm-admin-card">
                  <h2>Transactions by step</h2>
                  {Object.keys(txByStep).length ? (
                    <ul className="bm-admin-list">
                      {Object.entries(txByStep)
                        .sort((a, b) => b[1] - a[1])
                        .map(([step, n]) => (
                          <li key={step}>
                            <code>{step}</code> — {n}
                          </li>
                        ))}
                    </ul>
                  ) : (
                    <p className="bm-admin-muted">No on-chain hashes recorded yet.</p>
                  )}
                </section>
                <section className="bm-admin-card">
                  <h2>Recent transactions</h2>
                  <ul className="bm-admin-list">
                    {(desk?.metrics?.transactions || []).slice(0, 30).map((t: any, i: number) => (
                      <li key={t.tx_hash || i}>
                        <code>{t.step || 'tx'}</code> · {(t.tx_hash || '').slice(0, 16)}… · {t.match_id || ''}
                      </li>
                    ))}
                    {!(desk?.metrics?.transactions || []).length ? <li>No transactions yet.</li> : null}
                  </ul>
                </section>
              </>
            )}

            {section === 'games' && (
              <>
                <section className="bm-admin-card">
                  <h2>Recent games</h2>
                  <ul className="bm-admin-list">
                    {(desk?.metrics?.matches || []).slice(0, 20).map((m: any) => (
                      <li key={m.match_id}>
                        {(m.winner && m.winner.name) || m.result || m.status} · {m.white?.name} vs {m.black?.name} · $
                        {m.stake_usdc}
                      </li>
                    ))}
                    {!(desk?.metrics?.matches || []).length ? <li>No live games.</li> : null}
                  </ul>
                </section>
                <section className="bm-admin-card">
                  <h2>Telegram bot commands</h2>
                  <p className="bm-admin-muted">
                    Player bot stays public. These are the commands it already exposes.
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
          </div>
        </div>
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
