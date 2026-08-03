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
  const [err, setErr] = useState<string | null>(null)

  useEffect(() => {
    ;(async () => {
      const s = await api('/api/rematch/app/session')
      if (!s.ok) {
        router.replace('/rematch/app')
        return
      }
      const m = await api('/api/rematch/app/matches')
      if (m.ok) setMatches(m.data.matches || [])
    })()
  }, [router])

  return (
    <AppShell title="My match">
      <div className="rm-card" style={{ marginBottom: '1rem' }}>
        <label className="rm-label">Open match by code</label>
        <input
          className="rm-input"
          placeholder="AB12CD"
          value={code}
          onChange={(e) => setCode(e.target.value.toUpperCase())}
        />
        <button
          type="button"
          className="rm-btn rm-btn-primary"
          style={{ marginTop: '0.75rem' }}
          disabled={!code.trim()}
          onClick={() => router.push(`/rematch/app/match/${encodeURIComponent(code.trim())}`)}
        >
          Open
        </button>
      </div>

      {matches.length === 0 ? (
        <div className="rm-card">
          <p className="rm-muted" style={{ margin: 0 }}>
            No active matches in this session. Create a challenge or open a code from Telegram.
          </p>
          <Link
            href="/rematch/app/challenge"
            className="rm-btn rm-btn-ghost"
            style={{ marginTop: '0.75rem' }}
          >
            New challenge
          </Link>
        </div>
      ) : (
        <div style={{ display: 'grid', gap: '0.55rem' }}>
          {matches.map((m) => (
            <Link
              key={m.public_code || m.id}
              href={`/rematch/app/match/${encodeURIComponent(m.public_code || m.id)}`}
              className="rm-card"
              style={{ display: 'block' }}
            >
              <strong style={{ color: '#34d399' }}>{m.public_code || m.id}</strong>
              <div className="rm-muted" style={{ marginTop: '0.25rem' }}>
                ${m.amount_usdc} · {m.game_label || m.game_id} · {m.status}
              </div>
            </Link>
          ))}
        </div>
      )}
      {err ? (
        <p style={{ color: '#f87171', marginTop: '0.75rem', fontSize: '0.85rem' }}>{err}</p>
      ) : null}
    </AppShell>
  )
}
