'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import { AppShell } from '@/components/AppShell'
import { api } from '@/lib/appClient'

export default function MatchListPage() {
  const router = useRouter()
  const [matches, setMatches] = useState<any[]>([])
  const [code, setCode] = useState('')
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    ;(async () => {
      const s = await api('/api/rematch/app/session')
      if (!s.ok) {
        router.replace('/rematch/app')
        return
      }
      const m = await api('/api/rematch/app/matches')
      if (m.ok) setMatches(m.data.matches || [])
      setLoading(false)
    })()
  }, [router])

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
        ) : matches.length === 0 ? (
          <div className="rm-card">
            <p className="rm-h2" style={{ marginBottom: '0.35rem' }}>
              No matches yet
            </p>
            <p className="rm-muted" style={{ margin: '0 0 0.85rem' }}>
              Create a challenge or open a code from Telegram.
            </p>
            <Link href="/rematch/app/challenge" className="rm-btn rm-btn-primary">
              ⚔️ New challenge
            </Link>
          </div>
        ) : (
          <div className="rm-stack">
            <p className="rm-label">Active</p>
            {matches.map((m) => (
              <Link
                key={m.public_code || m.id}
                href={`/rematch/app/match/${encodeURIComponent(m.public_code || m.id)}`}
                className="rm-match-row"
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
                  <span className="rm-match-code">{m.public_code || m.id}</span>
                  <span className="rm-status">{m.status || '—'}</span>
                </div>
                <div className="rm-muted" style={{ marginTop: '0.4rem', fontSize: '0.8rem' }}>
                  ${m.amount_usdc} · {m.game_label || m.game_id}
                </div>
              </Link>
            ))}
          </div>
        )}
      </div>
    </AppShell>
  )
}
