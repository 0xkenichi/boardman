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
      <form className="rm-card" onSubmit={submit}>
        <p className="rm-muted" style={{ marginTop: 0 }}>
          Match <strong style={{ color: '#34d399' }}>{code}</strong>
          <br />
          Send the <strong style={{ color: '#fff' }}>final screen</strong> only — not lobby or mid-game.
        </p>

        <label className="rm-label">Photo</label>
        <input
          type="file"
          accept="image/*"
          capture="environment"
          className="rm-input"
          style={{ padding: '0.5rem' }}
          onChange={(e) => setFile(e.target.files?.[0] || null)}
        />

        <label className="rm-label" style={{ marginTop: '0.85rem' }}>
          Score caption
        </label>
        <input
          className="rm-input"
          placeholder="2-1 or W / L"
          value={score}
          onChange={(e) => setScore(e.target.value)}
        />
        <p className="rm-muted" style={{ fontSize: '0.75rem' }}>
          FC Mobile / sports: <code>2-1</code>. Binary games: <code>W</code> or <code>L</code>.
        </p>

        <button type="submit" className="rm-btn rm-btn-primary" disabled={busy} style={{ marginTop: '1rem' }}>
          {busy ? 'Uploading…' : 'Submit result'}
        </button>
      </form>

      {err ? (
        <p style={{ color: '#f87171', marginTop: '0.85rem', fontSize: '0.85rem' }}>{err}</p>
      ) : null}
      {msg ? (
        <p style={{ color: '#34d399', marginTop: '0.85rem', fontSize: '0.85rem' }}>{msg}</p>
      ) : null}

      <button
        type="button"
        className="rm-btn rm-btn-ghost"
        style={{ marginTop: '1rem' }}
        onClick={() => router.push(`/rematch/app/match/${encodeURIComponent(code)}`)}
      >
        Back to match
      </button>
    </AppShell>
  )
}
