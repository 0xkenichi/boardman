'use client'

/**
 * One-time withdraw confirmation, opened from a chat link (Telegram or WhatsApp).
 * The chat never sees the PIN: it is typed here, sent once to the BFF, and the
 * link stops working after one use or ten minutes.
 */

import { useParams } from 'next/navigation'
import { useEffect, useState } from 'react'
import { BookShell } from '@/components/rematch/BookShell'

type View = {
  ok: boolean
  purpose?: 'withdraw' | 'pin_reset'
  amount?: string
  destination?: { address?: string | null; tag?: string | null }
  needs_pin_setup?: boolean
  expires_in_sec?: number
  error?: string
  message?: string
}

type Result = { ok: boolean; status?: string; message?: string; error?: string; tx_hash?: string | null }

const PIN_RE = /^\d{6,12}$/

export default function WithdrawConfirmPage() {
  const params = useParams()
  const token = String(params?.token || '')
  const [view, setView] = useState<View | null>(null)
  const [pin, setPin] = useState('')
  const [pin2, setPin2] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [done, setDone] = useState<Result | null>(null)

  useEffect(() => {
    ;(async () => {
      const res = await fetch(`/api/rematch/app/withdraw/${encodeURIComponent(token)}`, {
        credentials: 'same-origin',
        cache: 'no-store',
      })
      const data = (await res.json().catch(() => ({ ok: false }))) as View
      setView(res.ok ? data : { ok: false, message: data.message || 'This link is not valid.' })
    })()
  }, [token])

  const setting = Boolean(view?.needs_pin_setup || view?.purpose === 'pin_reset')

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    setErr(null)
    if (setting) {
      if (!PIN_RE.test(pin)) return setErr('Use 6 to 12 digits.')
      if (pin !== pin2) return setErr("The two PINs don't match.")
    } else if (!pin) {
      return setErr('Enter your PIN.')
    }
    setBusy(true)
    const res = await fetch(`/api/rematch/app/withdraw/${encodeURIComponent(token)}`, {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ pin, pin_confirm: setting ? pin2 : null, amount: view?.amount ?? null }),
    })
    const data = (await res.json().catch(() => ({ ok: false }))) as Result
    setBusy(false)
    setPin('')
    setPin2('')
    if (res.ok && data.ok) {
      setDone(data)
      return
    }
    // A refused link (used, expired, locked, tampered) cannot be retried.
    if (['used', 'expired', 'locked', 'amount_mismatch', 'not_found'].includes(String(data.error))) {
      setView({ ok: false, message: data.message })
      return
    }
    setErr(data.message || data.error || 'That did not work. Try again.')
  }

  const dest = view?.destination?.tag ? `@${view.destination.tag}` : view?.destination?.address || ''
  const title = view?.purpose === 'pin_reset' ? 'New withdrawal PIN' : 'Confirm withdrawal'

  return (
    <BookShell title={title}>
      {!view ? (
        <div className="rm-card">
          <div className="rm-skeleton" style={{ height: 40, width: '60%' }} />
        </div>
      ) : !view.ok ? (
        <div className="rm-card rm-card-warn">
          <p className="rm-warn-text" style={{ marginTop: 0 }}>
            {view.message || 'This link is not valid.'}
          </p>
          <p className="rm-muted" style={{ marginBottom: 0, fontSize: '0.8rem' }}>
            Links work once and expire after ten minutes. Go back to the chat and start again.
          </p>
        </div>
      ) : done ? (
        <div className="rm-card rm-stack">
          <p className="rm-ok" style={{ marginTop: 0 }}>{done.message || 'Done.'}</p>
          {done.tx_hash ? <code className="rm-code">{done.tx_hash}</code> : null}
          <p className="rm-muted" style={{ marginBottom: 0, fontSize: '0.8rem' }}>
            You can close this page. The chat will confirm too.
          </p>
        </div>
      ) : (
        <form className="rm-card rm-stack-lg" onSubmit={submit} autoComplete="off">
          {view.purpose === 'withdraw' ? (
            <div className="rm-card-hero" style={{ padding: 0 }}>
              <span className="rm-label">You are sending</span>
              <div className="rm-balance">
                <span>$</span>
                {Number(view.amount || 0).toFixed(2)}
              </div>
              <span className="rm-label">USDC to</span>
              <code className="rm-code" style={{ wordBreak: 'break-all' }}>{dest}</code>
            </div>
          ) : null}

          <div>
            <label className="rm-label" htmlFor="bm-pin">
              {setting ? 'Choose a withdrawal PIN (6 to 12 digits)' : 'Withdrawal PIN'}
            </label>
            <input
              id="bm-pin"
              className="rm-input"
              type="password"
              inputMode="numeric"
              autoComplete={setting ? 'new-password' : 'current-password'}
              value={pin}
              onChange={(e) => setPin(e.target.value)}
            />
            {!setting ? (
              <p className="rm-muted" style={{ fontSize: '0.75rem', margin: '0.4rem 0 0' }}>
                Set a transaction password on Telegram before? It works here as your PIN.
              </p>
            ) : null}
          </div>

          {setting ? (
            <div>
              <label className="rm-label" htmlFor="bm-pin2">
                Same PIN again
              </label>
              <input
                id="bm-pin2"
                className="rm-input"
                type="password"
                inputMode="numeric"
                autoComplete="new-password"
                value={pin2}
                onChange={(e) => setPin2(e.target.value)}
              />
            </div>
          ) : null}

          <button type="submit" className="rm-btn rm-btn-primary" disabled={busy}>
            {busy
              ? 'Working…'
              : view.purpose === 'pin_reset'
                ? 'Save my PIN'
                : `Send $${Number(view.amount || 0).toFixed(2)}`}
          </button>
          <p className="rm-muted" style={{ margin: 0, fontSize: '0.75rem' }}>
            Boardman never asks for your PIN in a chat. If you did not start this, close the page.
          </p>
        </form>
      )}

      {err ? <p className="rm-err">{err}</p> : null}
    </BookShell>
  )
}
