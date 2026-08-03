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
      setErr(
        typeof res.data?.error === 'string'
          ? res.data.error
          : res.data?.detail || 'Action failed'
      )
      return
    }
    if (res.data.match) setMatch(res.data.match)
    else await load()
  }

  if (!match) {
    return (
      <AppShell title={`Match ${code}`}>
        <div className="rm-stack">
          <div className="rm-skeleton" style={{ height: 140, borderRadius: 16 }} />
          <p className="rm-muted" style={{ textAlign: 'center' }}>
            {err || 'Loading match…'}
          </p>
          {err ? (
            <Link href="/rematch/app/match" className="rm-btn rm-btn-ghost">
              Back to matches
            </Link>
          ) : null}
        </div>
      </AppShell>
    )
  }

  const status = String(match.status || '—')
  const canAccept = status === 'open'
  const canLock = ['open', 'accepted', 'creator_locked'].includes(status)
  const statusClass =
    status === 'open' || status === 'accepted' ? 'rm-status-live' : 'rm-status'

  return (
    <AppShell title={`Match ${match.public_code || code}`}>
      <div className="rm-stack-lg">
        <div className="rm-card rm-card-hero">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12 }}>
            <div>
              <span className="rm-label">Stake</span>
              <div className="rm-balance">
                <span>$</span>
                {Number(match.amount_usdc || 0).toFixed(2)}
              </div>
            </div>
            <span className={`rm-status ${statusClass}`}>{status}</span>
          </div>
          <p className="rm-muted" style={{ margin: '0.75rem 0 0', fontSize: '0.9rem' }}>
            <strong style={{ color: '#e5e7eb' }}>{match.game_label || match.game_id || 'Game'}</strong>
          </p>
          {match.creator_tag ? (
            <p className="rm-muted" style={{ margin: '0.35rem 0 0', fontSize: '0.8rem' }}>
              @{match.creator_tag}
              {match.opponent_tag ? ` · vs @${match.opponent_tag}` : ''}
            </p>
          ) : null}
        </div>

        <div className="rm-card">
          <p className="rm-label">What to do</p>
          <p className="rm-muted" style={{ margin: 0, whiteSpace: 'pre-wrap' }}>
            {match.proof_hint
              ? String(match.proof_hint).replace(/<[^>]+>/g, '')
              : 'After both lock: play your game, then upload the final screen photo.'}
          </p>
        </div>

        <div className="rm-stack">
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

        {err ? <p className="rm-err">{err}</p> : null}
        {match.demo || status === 'unknown' ? (
          <p className="rm-muted" style={{ fontSize: '0.75rem', textAlign: 'center', margin: 0 }}>
            Demo / offline match state may apply.
          </p>
        ) : null}
      </div>
    </AppShell>
  )
}
