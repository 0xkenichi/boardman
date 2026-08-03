'use client'

import { useEffect, useMemo, useState } from 'react'
import { useRouter } from 'next/navigation'
import { AppShell } from '@/components/AppShell'
import { api, type Game } from '@/lib/appClient'

const STAKES = [1, 5, 10, 25]

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
  const [auth, setAuth] = useState(false)

  useEffect(() => {
    ;(async () => {
      const s = await api('/api/rematch/app/session')
      if (!s.ok) {
        router.replace('/rematch/app')
        return
      }
      setAuth(true)
      const g = await api('/api/rematch/app/games')
      if (g.ok) {
        setCategories(g.data.categories || [])
        setGames(g.data.games || [])
      }
    })()
  }, [router])

  const filtered = useMemo(
    () => (category ? games.filter((g) => g.category === category) : games),
    [games, category]
  )

  async function submit() {
    setBusy(true)
    setErr(null)
    const res = await api('/api/rematch/app/matches', {
      method: 'POST',
      body: JSON.stringify({
        opponent_tag: tag.replace(/^@/, ''),
        amount_usdc: amount,
        game_id: gameId,
      }),
    })
    setBusy(false)
    if (!res.ok) {
      setErr(res.data?.error || res.data?.detail || 'Could not create challenge')
      return
    }
    const code = res.data.public_code || res.data.match_id
    router.push(`/rematch/app/match/${encodeURIComponent(code)}`)
  }

  if (!auth) {
    return (
      <AppShell>
        <p className="rm-muted">Checking session…</p>
      </AppShell>
    )
  }

  return (
    <AppShell title="New challenge">
      {step === 0 && (
        <div className="rm-card">
          <label className="rm-label">Friend&apos;s tag</label>
          <input
            className="rm-input"
            placeholder="@stillkenichi"
            value={tag}
            onChange={(e) => setTag(e.target.value)}
            autoCapitalize="none"
          />
          <p className="rm-muted" style={{ marginTop: '0.5rem' }}>
            They must have opened Rematch (bot or app) once.
          </p>
          <button
            type="button"
            className="rm-btn rm-btn-primary"
            style={{ marginTop: '1rem' }}
            disabled={!tag.trim()}
            onClick={() => setStep(1)}
          >
            Next
          </button>
        </div>
      )}

      {step === 1 && (
        <div className="rm-card">
          <label className="rm-label">Stake</label>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.5rem' }}>
            {STAKES.map((a) => (
              <button
                key={a}
                type="button"
                className="rm-btn"
                style={{
                  background: amount === a ? '#059669' : '#111827',
                  border: '1px solid #1f2937',
                  color: '#fff',
                }}
                onClick={() => setAmount(a)}
              >
                ${a}
              </button>
            ))}
          </div>
          <div style={{ display: 'flex', gap: '0.5rem', marginTop: '1rem' }}>
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
          <div style={{ display: 'grid', gap: '0.5rem' }}>
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
                className="rm-btn rm-btn-ghost"
                style={{
                  borderColor: category === c.id ? '#059669' : '#1f2937',
                  color: category === c.id ? '#34d399' : '#e5e7eb',
                }}
                onClick={() => {
                  setCategory(c.id)
                  setGameId('')
                }}
              >
                {c.label}
              </button>
            ))}
          </div>
          <div style={{ display: 'flex', gap: '0.5rem', marginTop: '1rem' }}>
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
          <div style={{ display: 'grid', gap: '0.45rem', maxHeight: '50vh', overflowY: 'auto' }}>
            {filtered.map((g) => (
              <button
                key={g.game_id}
                type="button"
                className="rm-btn rm-btn-ghost"
                style={{
                  justifyContent: 'flex-start',
                  borderColor: gameId === g.game_id ? '#059669' : '#1f2937',
                  color: gameId === g.game_id ? '#34d399' : '#e5e7eb',
                }}
                onClick={() => setGameId(g.game_id)}
              >
                {g.emoji || ''} {g.display_name}
              </button>
            ))}
          </div>
          <div style={{ display: 'flex', gap: '0.5rem', marginTop: '1rem' }}>
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
        <div className="rm-card">
          <h2 style={{ margin: '0 0 0.75rem', fontSize: '1.1rem' }}>Confirm</h2>
          <p className="rm-muted">
            To: <strong style={{ color: '#fff' }}>@{tag.replace(/^@/, '')}</strong>
            <br />
            Stake: <strong style={{ color: '#34d399' }}>${amount}</strong>
            <br />
            Game: <strong style={{ color: '#fff' }}>{gameId}</strong>
          </p>
          <p className="rm-muted" style={{ fontSize: '0.8rem' }}>
            After both lock: play, then upload the final screen photo here or in the bot.
          </p>
          <div style={{ display: 'flex', gap: '0.5rem', marginTop: '1rem' }}>
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

      {err ? (
        <p style={{ color: '#f87171', marginTop: '1rem', fontSize: '0.85rem' }}>{err}</p>
      ) : null}
    </AppShell>
  )
}
