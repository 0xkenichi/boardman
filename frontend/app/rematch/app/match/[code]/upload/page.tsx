'use client'

import { useParams, useRouter } from 'next/navigation'
import { useEffect, useState } from 'react'
import { AppShell } from '@/components/AppShell'
import { api } from '@/lib/appClient'

export default function UploadProofPage() {
  const params = useParams()
  const router = useRouter()
  const code = String(params?.code || '')
  const [file, setFile] = useState<File | null>(null)
  const [score, setScore] = useState('')
  const [err, setErr] = useState<string | null>(null)
  const [msg, setMsg] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    ;(async () => {
      const s = await api('/api/rematch/app/session')
      if (!s.ok) router.replace('/rematch/app')
    })()
  }, [router])

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    if (!file) {
      setErr('Choose a photo of the final screen')
      return
    }
    setBusy(true)
    setErr(null)
    setMsg(null)
    const fd = new FormData()
    fd.set('file', file)
    fd.set('score', score)
    const res = await fetch(`/api/rematch/app/matches/${encodeURIComponent(code)}/proof`, {
      method: 'POST',
      body: fd,
      credentials: 'same-origin',
    })
    const data = await res.json().catch(() => ({}))
    setBusy(false)
    if (!res.ok) {
      setErr(data.error || data.detail || 'Upload failed')
      return
    }
    setMsg(data.message || 'Proof received. We’ll settle when rules match.')
    if (data.ai?.score_string) {
      setMsg((m) => `${m || ''} AI read: ${data.ai.score_string}`)
    }
  }

  return (
    <AppShell title="Submit result">
      <form className="rm-card rm-stack-lg" onSubmit={submit}>
        <div>
          <p className="rm-section-title">Match {code}</p>
          <p className="rm-muted" style={{ margin: 0 }}>
            Send the <strong style={{ color: '#fff' }}>final screen</strong> only — not lobby or
            mid-game.
          </p>
        </div>

        <div>
          <label className="rm-label" htmlFor="rm-photo">
            Photo
          </label>
          <input
            id="rm-photo"
            type="file"
            accept="image/*"
            capture="environment"
            className="rm-input"
            style={{ padding: '0.65rem' }}
            onChange={(e) => setFile(e.target.files?.[0] || null)}
          />
          {file ? (
            <p className="rm-muted" style={{ fontSize: '0.75rem', margin: '0.4rem 0 0' }}>
              Selected: {file.name}
            </p>
          ) : null}
        </div>

        <div>
          <label className="rm-label" htmlFor="rm-score">
            Score caption
          </label>
          <input
            id="rm-score"
            className="rm-input"
            placeholder="2-1 or W / L"
            value={score}
            onChange={(e) => setScore(e.target.value)}
          />
          <p className="rm-muted" style={{ fontSize: '0.75rem', margin: '0.4rem 0 0' }}>
            Sports: <code>2-1</code>. Binary games: <code>W</code> or <code>L</code>.
          </p>
        </div>

        <button type="submit" className="rm-btn rm-btn-primary" disabled={busy}>
          {busy ? 'Uploading…' : 'Submit result'}
        </button>
      </form>

      {err ? <p className="rm-err">{err}</p> : null}
      {msg ? <p className="rm-ok">{msg}</p> : null}

      <button
        type="button"
        className="rm-btn rm-btn-ghost rm-mt-2"
        onClick={() => router.push(`/rematch/app/match/${encodeURIComponent(code)}`)}
      >
        Back to match
      </button>
    </AppShell>
  )
}
