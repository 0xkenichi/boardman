'use client'

/**
 * Create a self-custody passkey wallet and link it to the Boardman profile.
 * Opened from a chat link (?t=…) or while signed in on the web.
 *
 * The passkey is made by the phone (Face ID / fingerprint) and stays there;
 * the smart-account address is computed from it. We send Boardman only the
 * address and the public credential id.
 */

import { Suspense, useEffect, useState } from 'react'
import { useSearchParams } from 'next/navigation'
import { BookShell } from '@/components/rematch/BookShell'
import { PasskeyGate } from '@/components/rematch/PasskeyGate'
import { passkeySupport, type PasskeySupport } from '@/lib/selfCustody/env'
import { createWallet, walletsConfigured, WalletError, type ChainInfo } from '@/lib/selfCustody/wallet'

type View = {
  ok: boolean
  username?: string
  wallet?: { address: string; credential_id: string } | null
  chain?: ChainInfo
  error?: string
  message?: string
}

function SetupInner() {
  const t = useSearchParams().get('t') || ''
  const q = t ? `?t=${encodeURIComponent(t)}` : ''
  const [view, setView] = useState<View | null>(null)
  const [support, setSupport] = useState<PasskeySupport>('ok')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [linked, setLinked] = useState<string | null>(null)

  useEffect(() => {
    setSupport(passkeySupport(navigator.userAgent))
    ;(async () => {
      const res = await fetch(`/api/rematch/app/wallet/setup${q}`, { credentials: 'same-origin', cache: 'no-store' })
      const data = (await res.json().catch(() => ({ ok: false }))) as View
      setView(res.ok ? data : { ok: false, message: data.message || 'This link is not valid.' })
    })()
  }, [q])

  async function create() {
    if (!view?.chain) return
    setErr(null)
    setBusy(true)
    try {
      const w = await createWallet(view.chain, view.username || 'Boardman')
      const res = await fetch(`/api/rematch/app/wallet/setup${q}`, {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ address: w.address, credential_id: w.credentialId }),
      })
      const data = (await res.json().catch(() => ({ ok: false }))) as { ok: boolean; address?: string; message?: string }
      if (res.ok && data.ok) setLinked(data.address || w.address)
      else setErr(data.message || 'Could not link the wallet. Start again in the chat.')
    } catch (e) {
      setErr(e instanceof WalletError ? e.message : 'Something went wrong. Nothing was created.')
    } finally {
      setBusy(false)
    }
  }

  const address = linked || view?.wallet?.address

  return (
    <BookShell title="Your wallet">
      {!view ? (
        <div className="rm-card">
          <div className="rm-skeleton" style={{ height: 40, width: '60%' }} />
        </div>
      ) : !view.ok ? (
        <div className="rm-card rm-card-warn">
          <p className="rm-warn-text" style={{ marginTop: 0 }}>{view.message || 'This link is not valid.'}</p>
          <p className="rm-muted" style={{ marginBottom: 0, fontSize: '0.8rem' }}>
            Setup links work once and expire after ten minutes. Ask the chat for a new one.
          </p>
        </div>
      ) : address ? (
        <div className="rm-card rm-stack">
          <p className="rm-ok" style={{ marginTop: 0 }}>{linked ? 'Your wallet is ready.' : 'You already have a wallet.'}</p>
          <span className="rm-label">Your address on {view.chain?.label}</span>
          <code className="rm-code" style={{ wordBreak: 'break-all' }}>{address}</code>
          <p className="rm-muted" style={{ margin: 0, fontSize: '0.85rem' }}>
            Send USDC on {view.chain?.label} to this address to play. Stakes and withdrawals are approved with your
            passkey, one at a time.
          </p>
          <p className="rm-muted" style={{ margin: 0, fontSize: '0.75rem' }}>
            You can close this page. The chat will confirm too.
          </p>
        </div>
      ) : support !== 'ok' ? (
        <PasskeyGate support={support} />
      ) : !walletsConfigured() ? (
        <div className="rm-card rm-card-warn">
          <p className="rm-warn-text" style={{ margin: 0 }}>Passkey wallets are not switched on yet.</p>
        </div>
      ) : (
        <div className="rm-card rm-stack-lg">
          <div className="rm-stack">
            <span className="rm-label">A wallet only you control</span>
            <p style={{ margin: 0 }}>
              You hold the keys; Boardman can&apos;t move your money. Your phone keeps a passkey (Face ID, fingerprint
              or screen lock) and you approve every stake and withdrawal with it.
            </p>
            <ul className="rm-muted" style={{ margin: 0, paddingLeft: '1.1rem', fontSize: '0.85rem' }}>
              <li>Your passkey syncs with your Apple or Google account, so a new phone keeps working.</li>
              <li>If you lose every device with the passkey, Boardman cannot recover the wallet for you.</li>
              <li>Winnings are paid by the escrow contract straight to this wallet.</li>
            </ul>
          </div>
          <button type="button" className="rm-btn rm-btn-primary" disabled={busy} onClick={create}>
            {busy ? 'Waiting for your passkey…' : 'Create my wallet with a passkey'}
          </button>
          <p className="rm-muted" style={{ margin: 0, fontSize: '0.75rem' }}>
            Wallet by Circle (Modular Wallets) on {view.chain?.label}. If you did not start this, close the page.
          </p>
        </div>
      )}
      {err ? <p className="rm-err">{err}</p> : null}
    </BookShell>
  )
}

export default function WalletSetupPage() {
  return (
    <Suspense fallback={null}>
      <SetupInner />
    </Suspense>
  )
}
