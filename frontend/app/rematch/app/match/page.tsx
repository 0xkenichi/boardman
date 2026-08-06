'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import { AppShell } from '@/components/AppShell'
import { api } from '@/lib/appClient'

type MatchRow = {
  id?: string
  public_code?: string
  status?: string
  amount_usdc?: number
  game_label?: string
  game_id?: string
  result?: string
  settlement_chain?: string
  created_at?: string
}

export default function MatchListPage() {
  const router = useRouter()
  const [matches, setMatches] = useState<MatchRow[]>([])
  const [code, setCode] = useState('')
  const [loading, setLoading] = useState(true)
  const [demo, setDemo] = useState(false)

  useEffect(() => {
    ;(async () => {
      const s = await api('/api/rematch/app/session')
      if (!s.ok) {
        router.replace('/rematch/app')
        return
      }
      const m = await api('/api/rematch/app/matches')
      if (m.ok) {
        setMatches(m.data.matches || [])
        setDemo(Boolean(m.data.demo))
      }
      setLoading(false)
    })()
  }, [router])

  const active = matches.filter((m) =>
    ['open', 'accepted', 'locked', 'playing', 'submitted', 'creator_locked', 'opponent_locked'].includes(
      String(m.status || '')
    )
  )
  const history = matches.filter((m) => !active.includes(m))

  return (
    <AppShell title="My matches">
      <div className="rm-stack-lg">
        <div className="rm-card">
          <label className="rm-label" htmlFor="rm-code">
            Open match by code
          </label>
          <input
            id="rm-code"
            className="rm-input"
            placeholder="AB12CD"
            value={code}
            onChange={(e) => setCode(e.target.value.toUpperCase())}
            autoCapitalize="characters"
          />
          <button
            type="button"
            className="rm-btn rm-btn-primary rm-mt-1"
            disabled={!code.trim()}
            onClick={() => router.push(`/rematch/app/match/${encodeURIComponent(code.trim())}`)}
          >
            Open match
          </button>
        </div>

        {loading ? (
          <div className="rm-stack">
            <div className="rm-skeleton" style={{ height: 72, borderRadius: 16 }} />
            <div className="rm-skeleton" style={{ height: 72, borderRadius: 16 }} />
          </div>
        ) : (
          <>
            <div className="rm-stack">
              <p className="rm-label">Active</p>
              {active.length === 0 ? (
                <div className="rm-card">
                  <p className="rm-muted" style={{ margin: '0 0 0.75rem' }}>
                    No open matches. Challenge a friend or open a code.
                  </p>
                  <Link href="/app/challenge" className="rm-btn rm-btn-primary">
                    ⚔️ New challenge
                  </Link>
                </div>
              ) : (
                active.map((m) => (
                  <Link
                    key={m.public_code || m.id}
                    href={`/rematch/app/match/${encodeURIComponent(m.public_code || m.id || '')}`}
                    className="rm-match-row"
                  >
                    <div
                      style={{
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'center',
                        gap: 8,
                      }}
                    >
                      <span className="rm-match-code">{m.public_code || m.id}</span>
                      <span className="rm-status rm-status-live">{m.status}</span>
                    </div>
                    <div className="rm-muted" style={{ marginTop: '0.4rem', fontSize: '0.8rem' }}>
                      ${m.amount_usdc} · {m.game_label || m.game_id}
                    </div>
                  </Link>
                ))
              )}
            </div>

            <div className="rm-stack">
              <p className="rm-label">Recent (same as Telegram)</p>
              {history.length === 0 ? (
                <p className="rm-muted" style={{ margin: 0 }}>
                  No past matches yet.
                </p>
              ) : (
                history.map((m) => (
                  <Link
                    key={(m.public_code || m.id) + String(m.created_at)}
                    href={`/rematch/app/match/${encodeURIComponent(m.public_code || m.id || '')}`}
                    className="rm-match-row"
                  >
                    <div
                      style={{
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'center',
                        gap: 8,
                      }}
                    >
                      <span className="rm-match-code">{m.public_code || m.id}</span>
                      <span
                        className={`rm-status ${
                          m.result === 'W'
                            ? 'rm-status-live'
                            : m.result === 'L'
                              ? 'rm-status-warn'
                              : ''
                        }`}
                      >
                        {m.result && m.result !== '—' ? m.result : m.status}
                      </span>
                    </div>
                    <div className="rm-muted" style={{ marginTop: '0.4rem', fontSize: '0.8rem' }}>
                      ${m.amount_usdc} · {m.game_label || m.game_id}
                      {m.settlement_chain ? ` · ${m.settlement_chain}` : ''}
                      {m.created_at
                        ? ` · ${new Date(m.created_at).toLocaleDateString()}`
                        : ''}
                    </div>
                  </Link>
                ))
              )}
              {demo ? (
                <p className="rm-muted" style={{ fontSize: '0.75rem', margin: 0 }}>
                  Demo mode — live history needs Stack API.
                </p>
              ) : null}
            </div>
          </>
        )}
      </div>
    </AppShell>
  )
}
