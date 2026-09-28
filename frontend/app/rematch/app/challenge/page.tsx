'use client'

import { useEffect, useMemo, useState } from 'react'
import { useRouter } from 'next/navigation'
import { BookShell } from '@/components/rematch/BookShell'
import { LiveRoomsCard } from '@/components/rematch/LiveRoomsCard'
import { api, type Game } from '@/lib/appClient'

const STAKES = [1, 5, 10, 25]
const STEP_LABELS = ['Friend', 'Stake', 'Platform', 'Game', 'Ticket']

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
      <BookShell title="New challenge">
        <div className="rm-stack">
          <div className="rm-skeleton" style={{ height: 8, borderRadius: 2 }} />
          <div className="rm-skeleton" style={{ height: 160, borderRadius: 3 }} />
          <p className="rm-muted" style={{ textAlign: 'center' }}>
            {auth === 'no' ? 'Redirecting to sign in…' : 'Loading…'}
          </p>
        </div>
      </BookShell>
    )
  }

  return (
    <BookShell title="New challenge">
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
              Who are you calling out?
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
              They must have opened the book once — bot or app.
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
          <label className="rm-label">The stake (USDC each)</label>
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
          <label className="rm-label">Where does the game happen?</label>
          <div className="rm-stack">
            {(categories.length
              ? categories
              : [
                  { id: 'mobile', label: 'Mobile' },
                  { id: 'imessage', label: 'iMessage' },
                  { id: 'console', label: 'Console' },
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
          <label className="rm-label">The game</label>
          <div
            className="rm-stack"
            style={{ maxHeight: '46vh', overflowY: 'auto', paddingRight: 2 }}
          >
            {filtered.length === 0 ? (
              <p className="rm-muted">Nothing on the slate in this category yet.</p>
            ) : (
              filtered.map((g) => (
                <button
                  key={g.game_id}
                  type="button"
                  className={`rm-tile rm-tile-left ${gameId === g.game_id ? 'rm-tile-active' : ''}`}
                  onClick={() => setGameId(g.game_id)}
                >
                  {g.emoji ? <span style={{ marginRight: 6 }}>{g.emoji}</span> : null}
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
          <div className="bk-slip">
            <div className="bk-slip-head">
              <span>THE TICKET</span>
              <span>UNSENT</span>
            </div>
            <div className="bk-slip-row">
              <span>TO</span>
              <strong>@{tag.replace(/^@/, '')}</strong>
            </div>
            <div className="bk-slip-row">
              <span>STAKE EACH</span>
              <strong className="bk-ink">${amount} USDC</strong>
            </div>
            <div className="bk-slip-row">
              <span>GAME</span>
              <strong>{selectedGame?.display_name || gameId}</strong>
            </div>
          </div>
          <p className="rm-muted" style={{ marginTop: '0.9rem', marginBottom: 0 }}>
            After both lock: play the game, then upload the final screen photo here
            or in the bot. The boardman pays the winner.
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
              {busy ? 'Writing it in…' : 'Send challenge'}
            </button>
          </div>
        </div>
      )}

      {err ? <p className="rm-err">{err}</p> : null}
    </BookShell>
  )
}
