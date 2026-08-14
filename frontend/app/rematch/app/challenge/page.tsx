'use client'

import { useEffect, useMemo, useState } from 'react'
import { useRouter } from 'next/navigation'
import { AppShell } from '@/components/AppShell'
import { LiveRoomsCard } from '@/components/rematch/LiveRoomsCard'
import { api, type Game } from '@/lib/appClient'

const STAKES = [1, 5, 10, 25]
const STEP_LABELS = ['Friend', 'Stake', 'Platform', 'Game', 'Confirm']

export default function ChallengePage() {
  const router = useRouter()
  const [step, setStep] = useState(0)
  const [tag, setTag] = useState('')
  const [amount, setAmount] = useState(1)
  const [category, setCategory] = useState('')
  const [gameId, setGameId] = useState('')
  const [categories, setCategories] = useState<{ id: string; label: string }[]>([])
  const [games, setGames] = useState<Game[]>([])
  const [err, setErr] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [auth, setAuth] = useState<'checking' | 'yes' | 'no'>('checking')

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const s = await api('/api/rematch/app/session')
        if (cancelled) return
        if (!s.ok) {
          setAuth('no')
          router.replace('/app')
          return
        }
        setAuth('yes')
        const g = await api('/api/rematch/app/games')
        if (cancelled) return
        if (g.ok) {
          setCategories(g.data.categories || [])
          setGames(g.data.games || [])
        }
      } catch {
        if (!cancelled) {
          setAuth('no')
          setErr('Could not load session')
        }
      }
    })()
    return () => {
      cancelled = true
    }
  }, [router])

  const filtered = useMemo(
    () => (category ? games.filter((g) => g.category === category) : games),
    [games, category]
  )

  const selectedGame = games.find((g) => g.game_id === gameId)

  async function submit() {
    setBusy(true)
    setErr(null)
    try {
      const res = await api('/api/rematch/app/matches', {
        method: 'POST',
        body: JSON.stringify({
          opponent_tag: tag.replace(/^@/, ''),
          amount_usdc: amount,
          game_id: gameId,
        }),
      })
      if (!res.ok) {
        setErr(
          typeof res.data?.error === 'string'
            ? res.data.error
            : res.data?.detail || 'Could not create challenge'
        )
        setBusy(false)
        return
      }
      const code = res.data.public_code || res.data.match_id
      router.push(`/app/match/${encodeURIComponent(code)}`)
    } catch (e: any) {
      setErr(e?.message || 'Network error')
      setBusy(false)
    }
  }

  if (auth === 'checking' || auth === 'no') {
    return (
      <AppShell title="New challenge">
        <div className="rm-stack">
          <div className="rm-skeleton" style={{ height: 8, borderRadius: 4 }} />
          <div className="rm-skeleton" style={{ height: 160, borderRadius: 16 }} />
          <p className="rm-muted" style={{ textAlign: 'center' }}>
            {auth === 'no' ? 'Redirecting to sign in…' : 'Loading…'}
          </p>
        </div>
      </AppShell>
    )
  }

  return (
    <AppShell title="New challenge">
      <div className="rm-steps" aria-hidden>
        {STEP_LABELS.map((_, i) => (
          <div key={i} className={`rm-step-dot ${i <= step ? 'rm-step-dot-on' : ''}`} />
        ))}
      </div>
      <p className="rm-step-label">
        Step {step + 1} of {STEP_LABELS.length} · {STEP_LABELS[step]}
      </p>

      {step === 0 && (
        <div className="rm-stack-lg">
          <div className="rm-card">
            <label className="rm-label" htmlFor="rm-tag">
              Friend&apos;s tag
            </label>
            <input
              id="rm-tag"
              className="rm-input"
              placeholder="@stillkenichi"
              value={tag}
              onChange={(e) => setTag(e.target.value)}
              autoCapitalize="none"
              autoCorrect="off"
            />
            <p className="rm-muted" style={{ marginTop: '0.65rem', marginBottom: 0 }}>
              They must have opened Rematch (bot or app) once.
            </p>
            <button
              type="button"
              className="rm-btn rm-btn-primary rm-mt-2"
              disabled={!tag.trim()}
              onClick={() => setStep(1)}
            >
              Next
            </button>
          </div>
          <LiveRoomsCard variant="compact" />
        </div>
      )}

      {step === 1 && (
        <div className="rm-card">
          <label className="rm-label">Stake (USDC)</label>
          <div className="rm-grid-2">
            {STAKES.map((a) => (
              <button
                key={a}
                type="button"
                className={`rm-tile ${amount === a ? 'rm-tile-active' : ''}`}
                onClick={() => setAmount(a)}
              >
                ${a}
              </button>
            ))}
          </div>
          <div className="rm-btn-row rm-mt-2">
            <button type="button" className="rm-btn rm-btn-ghost" onClick={() => setStep(0)}>
              Back
            </button>
            <button type="button" className="rm-btn rm-btn-primary" onClick={() => setStep(2)}>
              Next
            </button>
          </div>
        </div>
      )}

      {step === 2 && (
        <div className="rm-card">
          <label className="rm-label">Where do you play?</label>
          <div className="rm-stack">
            {(categories.length
              ? categories
              : [
                  { id: 'mobile', label: '📲 Mobile' },
                  { id: 'imessage', label: '📱 iMessage' },
                  { id: 'console', label: '🎮 Console' },
                ]
            ).map((c) => (
              <button
                key={c.id}
                type="button"
                className={`rm-tile rm-tile-left ${category === c.id ? 'rm-tile-active' : ''}`}
                onClick={() => {
                  setCategory(c.id)
                  setGameId('')
                }}
              >
                {c.label}
              </button>
            ))}
          </div>
          <div className="rm-btn-row rm-mt-2">
            <button type="button" className="rm-btn rm-btn-ghost" onClick={() => setStep(1)}>
              Back
            </button>
            <button
              type="button"
              className="rm-btn rm-btn-primary"
              disabled={!category}
              onClick={() => setStep(3)}
            >
              Next
            </button>
          </div>
        </div>
      )}

      {step === 3 && (
        <div className="rm-card">
          <label className="rm-label">Game</label>
          <div
            className="rm-stack"
            style={{ maxHeight: '46vh', overflowY: 'auto', paddingRight: 2 }}
          >
            {filtered.length === 0 ? (
              <p className="rm-muted">No games in this category yet.</p>
            ) : (
              filtered.map((g) => (
                <button
                  key={g.game_id}
                  type="button"
                  className={`rm-tile rm-tile-left ${gameId === g.game_id ? 'rm-tile-active' : ''}`}
                  onClick={() => setGameId(g.game_id)}
                >
                  <span style={{ marginRight: 6 }}>{g.emoji || '🎮'}</span>
                  {g.display_name}
                </button>
              ))
            )}
          </div>
          <div className="rm-btn-row rm-mt-2">
            <button type="button" className="rm-btn rm-btn-ghost" onClick={() => setStep(2)}>
              Back
            </button>
            <button
              type="button"
              className="rm-btn rm-btn-primary"
              disabled={!gameId}
              onClick={() => setStep(4)}
            >
              Next
            </button>
          </div>
        </div>
      )}

      {step === 4 && (
        <div className="rm-card rm-card-hero">
          <p className="rm-section-title">Confirm</p>
          <h2 className="rm-h2" style={{ marginBottom: '0.85rem' }}>
            Ready to send?
          </h2>
          <div className="rm-stack" style={{ gap: '0.5rem' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.9rem' }}>
              <span className="rm-muted">To</span>
              <strong>@{tag.replace(/^@/, '')}</strong>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.9rem' }}>
              <span className="rm-muted">Stake</span>
              <strong style={{ color: '#34d399' }}>${amount}</strong>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.9rem' }}>
              <span className="rm-muted">Game</span>
              <strong>
                {selectedGame?.emoji || ''} {selectedGame?.display_name || gameId}
              </strong>
            </div>
          </div>
          <p className="rm-muted" style={{ fontSize: '0.8rem', marginTop: '0.9rem', marginBottom: 0 }}>
            After both lock: play, then upload the final screen photo here or in the bot.
          </p>
          <div className="rm-btn-row rm-mt-2">
            <button type="button" className="rm-btn rm-btn-ghost" onClick={() => setStep(3)}>
              Back
            </button>
            <button
              type="button"
              className="rm-btn rm-btn-primary"
              disabled={busy}
              onClick={submit}
            >
              {busy ? 'Sending…' : 'Send challenge'}
            </button>
          </div>
        </div>
      )}

      {err ? <p className="rm-err">{err}</p> : null}
    </AppShell>
  )
}
