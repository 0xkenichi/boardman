'use client'

import { useCallback, useEffect, useState } from 'react'
import { useParams, useRouter } from 'next/navigation'
import Link from 'next/link'
import { AppShell } from '@/components/AppShell'
import { api } from '@/lib/appClient'

export default function MatchDetailPage() {
  const params = useParams()
  const router = useRouter()
  const code = String(params?.code || '')
  const [match, setMatch] = useState<any>(null)
  const [err, setErr] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const load = useCallback(async () => {
    const s = await api('/api/rematch/app/session')
    if (!s.ok) {
      router.replace('/rematch/app')
      return
    }
    const res = await api(`/api/rematch/app/matches/${encodeURIComponent(code)}`)
    if (res.ok) setMatch(res.data.match)
    else setErr(res.data?.error || 'Not found')
  }, [code, router])

  useEffect(() => {
    load()
  }, [load])

  async function act(action: string) {
    setBusy(true)
    setErr(null)
    const res = await api(`/api/rematch/app/matches/${encodeURIComponent(code)}`, {
      method: 'POST',
      body: JSON.stringify({ action }),
    })
    setBusy(false)
    if (!res.ok) {
      setErr(res.data?.error || res.data?.detail || 'Action failed')
      return
    }
    if (res.data.match) setMatch(res.data.match)
    else await load()
  }

  if (!match) {
    return (
      <AppShell>
        <p className="rm-muted">{err || 'Loading match…'}</p>
      </AppShell>
    )
  }

  const status = String(match.status || '—')
  const canAccept = status === 'open'
  const canLock = ['open', 'accepted', 'creator_locked'].includes(status)

  return (
    <AppShell title={`Match ${match.public_code || code}`}>
      <div className="rm-card" style={{ marginBottom: '1rem' }}>
        <div style={{ fontSize: '1.5rem', fontWeight: 900, color: '#34d399' }}>
          ${Number(match.amount_usdc || 0).toFixed(2)}
        </div>
        <p className="rm-muted" style={{ margin: '0.35rem 0' }}>
          {match.game_label || match.game_id || 'Game'}
          <br />
          Status: <strong style={{ color: '#e5e7eb' }}>{status}</strong>
        </p>
        {match.creator_tag ? (
          <p className="rm-muted" style={{ margin: 0, fontSize: '0.8rem' }}>
            From @{match.creator_tag}
            {match.opponent_tag ? ` · vs @${match.opponent_tag}` : ''}
          </p>
        ) : null}
      </div>

      <div className="rm-card" style={{ marginBottom: '1rem' }}>
        <p className="rm-muted" style={{ margin: 0, whiteSpace: 'pre-wrap' }}>
          {match.proof_hint
            ? String(match.proof_hint).replace(/<[^>]+>/g, '')
            : 'After both lock: play your game, then upload the final screen photo.'}
        </p>
      </div>

      <div style={{ display: 'grid', gap: '0.55rem' }}>
        {canAccept ? (
          <button
            type="button"
            className="rm-btn rm-btn-primary"
            disabled={busy}
            onClick={() => act('accept')}
          >
            Accept challenge
          </button>
        ) : null}
        {canLock ? (
          <button
            type="button"
            className="rm-btn rm-btn-primary"
            disabled={busy}
            onClick={() => act('lock')}
          >
            Lock my stake
          </button>
        ) : null}
        <Link
          href={`/rematch/app/match/${encodeURIComponent(match.public_code || code)}/upload`}
          className="rm-btn rm-btn-ghost"
        >
          📸 Submit result photo
        </Link>
        <button type="button" className="rm-btn rm-btn-ghost" onClick={load}>
          Refresh
        </button>
      </div>

      {err ? (
        <p style={{ color: '#f87171', marginTop: '1rem', fontSize: '0.85rem' }}>{err}</p>
      ) : null}
      {match.demo || status === 'unknown' ? (
        <p className="rm-muted" style={{ marginTop: '1rem', fontSize: '0.75rem' }}>
          Demo / offline match state. Connect STACK_API_URL + STACK_API_KEY for live escrow.
        </p>
      ) : null}
    </AppShell>
  )
}
