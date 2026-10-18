'use client'

/**
 * One-time passkey approval, opened from a chat link (Telegram or WhatsApp).
 *
 * Shows exactly what will be signed (the action in words, then every call:
 * contract, purpose, raw calldata), asks the player's passkey to sign it as
 * one UserOperation from their own smart account, waits for it to land, then
 * tells Boardman the transaction hash. Boardman only advances the match after
 * reading the escrow's own event on chain; this page's word is not enough.
 */

import { useParams } from 'next/navigation'
import { useEffect, useState } from 'react'
import { BookShell } from '@/components/rematch/BookShell'
import { PasskeyGate } from '@/components/rematch/PasskeyGate'
import { passkeySupport, type PasskeySupport } from '@/lib/selfCustody/env'
import {
  approveCalls,
  walletsConfigured,
  WalletError,
  type ChainInfo,
  type PreparedCall,
} from '@/lib/selfCustody/wallet'

type View = {
  ok: boolean
  action?: 'lock_create' | 'lock_join' | 'withdraw'
  headline?: string
  amount?: string
  account?: string
  to?: string
  challenge_id?: string | null
  match?: { code?: string; game?: string; opponent?: string }
  calls?: PreparedCall[]
  sponsor_gas?: boolean
  chain?: ChainInfo
  expires_in_sec?: number
  error?: string
  message?: string
}

type Result = { ok: boolean; status?: string; message?: string; tx_hash?: string; error?: string }

const DEAD = ['used', 'expired', 'amount_mismatch', 'not_found', 'wrong_profile']

function short(a?: string | null) {
  return a && a.length > 14 ? `${a.slice(0, 8)}…${a.slice(-6)}` : a || ''
}

export default function ApprovePage() {
  const params = useParams()
  const token = String(params?.token || '')
  const [view, setView] = useState<View | null>(null)
  const [support, setSupport] = useState<PasskeySupport>('ok')
  const [busy, setBusy] = useState<string | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [done, setDone] = useState<Result | null>(null)
  const [showRaw, setShowRaw] = useState(false)

  useEffect(() => {
    setSupport(passkeySupport(navigator.userAgent))
    ;(async () => {
      const res = await fetch(`/api/rematch/app/approve/${encodeURIComponent(token)}`, {
        credentials: 'same-origin',
        cache: 'no-store',
      })
      const data = (await res.json().catch(() => ({ ok: false }))) as View
      setView(res.ok ? data : { ok: false, message: data.message || 'This link is not valid.' })
    })()
  }, [token])

  async function approve() {
    if (!view?.chain || !view.calls || !view.account) return
    setErr(null)
    setBusy('Waiting for your passkey…')
    let sent: { userOpHash: string; txHash: string; success: boolean }
    try {
      sent = await approveCalls(view.chain, view.account, view.calls, Boolean(view.sponsor_gas), 'Boardman')
    } catch (e) {
      setBusy(null)
      setErr(e instanceof WalletError ? e.message : 'Something went wrong. Nothing was sent.')
      return
    }
    if (!sent.success) {
      // The bundle landed but our calls reverted inside it: nothing moved, and
      // the link stays open so the player can try again.
      setBusy(null)
      setErr("That didn't go through on the network. Nothing moved. Check your balance and try again.")
      return
    }
    setBusy('Confirming on the network…')
    const res = await fetch(`/api/rematch/app/approve/${encodeURIComponent(token)}`, {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        tx_hash: sent.txHash,
        user_op_hash: sent.userOpHash,
        amount: view.amount,
        challenge_id: view.challenge_id ?? null,
      }),
    })
    const data = (await res.json().catch(() => ({ ok: false }))) as Result
    setBusy(null)
    if (res.ok && data.ok) {
      setDone(data)
      return
    }
    if (DEAD.includes(String(data.error))) {
      setView({ ok: false, message: data.message })
      return
    }
    setErr(data.message || 'The network did not accept this. Nothing moved; start again in the chat.')
  }

  const explorer = (h?: string) => (h && view?.chain?.explorer_tx ? `${view.chain.explorer_tx}${h}` : null)
  const isLock = view?.action === 'lock_create' || view?.action === 'lock_join'

  return (
    <BookShell title={isLock ? 'Lock your stake' : 'Approve withdrawal'}>
      {!view ? (
        <div className="rm-card">
          <div className="rm-skeleton" style={{ height: 40, width: '60%' }} />
        </div>
      ) : !view.ok ? (
        <div className="rm-card rm-card-warn">
          <p className="rm-warn-text" style={{ marginTop: 0 }}>{view.message || 'This link is not valid.'}</p>
          <p className="rm-muted" style={{ marginBottom: 0, fontSize: '0.8rem' }}>
            Links work once and expire after ten minutes. Go back to the chat and start again.
          </p>
        </div>
      ) : done ? (
        <div className="rm-card rm-stack">
          <p className="rm-ok" style={{ marginTop: 0 }}>{done.message || 'Done.'}</p>
          {done.tx_hash ? (
            explorer(done.tx_hash) ? (
              <a className="rm-code" href={explorer(done.tx_hash)!} target="_blank" rel="noreferrer noopener">
                {short(done.tx_hash)} ↗
              </a>
            ) : (
              <code className="rm-code">{done.tx_hash}</code>
            )
          ) : null}
          <p className="rm-muted" style={{ marginBottom: 0, fontSize: '0.8rem' }}>
            You can close this page. The chat will confirm too.
          </p>
        </div>
      ) : (
        <div className="rm-card rm-stack-lg">
          <div className="rm-card-hero" style={{ padding: 0 }}>
            <span className="rm-label">{isLock ? 'You are locking' : 'You are sending'}</span>
            <div className="rm-balance">
              <span>$</span>
              {Number(view.amount || 0).toFixed(2)}
            </div>
            <span className="rm-label">USDC</span>
            <p style={{ margin: '0.5rem 0 0' }}>{view.headline}</p>
            {isLock && view.match ? (
              <span className="rm-muted" style={{ fontSize: '0.85rem' }}>
                {[view.match.game, view.match.opponent ? `vs ${view.match.opponent}` : ''].filter(Boolean).join(' · ')}
              </span>
            ) : null}
          </div>

          <dl className="rm-stack" style={{ margin: 0, fontSize: '0.85rem' }}>
            <div>
              <dt className="rm-label">From your wallet</dt>
              <dd style={{ margin: 0 }}>
                <code className="rm-code" style={{ wordBreak: 'break-all' }}>{view.account}</code>
              </dd>
            </div>
            <div>
              <dt className="rm-label">{isLock ? 'Into the escrow contract' : 'To'}</dt>
              <dd style={{ margin: 0 }}>
                <code className="rm-code" style={{ wordBreak: 'break-all' }}>{view.to}</code>
              </dd>
            </div>
            <div>
              <dt className="rm-label">Network</dt>
              <dd style={{ margin: 0 }}>
                {view.chain?.label} · gas {view.sponsor_gas ? 'paid by Boardman' : 'paid from your USDC (about $0.01)'}
              </dd>
            </div>
          </dl>

          <div className="rm-stack">
            <span className="rm-label">Your passkey signs these steps, all or nothing</span>
            <ol style={{ margin: 0, paddingLeft: '1.1rem', fontSize: '0.85rem' }}>
              {(view.calls || []).map((c, i) => (
                <li key={i}>
                  {c.label || 'Contract call'} <span className="rm-muted">({short(c.to)})</span>
                </li>
              ))}
            </ol>
            <button type="button" className="rm-btn rm-btn-ghost" onClick={() => setShowRaw(!showRaw)}>
              {showRaw ? 'Hide raw data' : 'Show raw data'}
            </button>
            {showRaw
              ? (view.calls || []).map((c, i) => (
                  <code key={i} className="rm-code" style={{ wordBreak: 'break-all', fontSize: '0.7rem' }}>
                    to {c.to} · value {c.value} · data {c.data}
                  </code>
                ))
              : null}
          </div>

          {isLock ? (
            <p className="rm-muted" style={{ margin: 0, fontSize: '0.8rem' }}>
              The escrow contract holds the stake until the result is in, then pays the winner&apos;s wallet. If the
              match never finishes, the contract lets anyone refund both stakes after the timeout.
            </p>
          ) : null}

          {support !== 'ok' ? (
            <PasskeyGate support={support} />
          ) : !walletsConfigured() ? (
            <p className="rm-warn-text" style={{ margin: 0 }}>Passkey wallets are not switched on yet.</p>
          ) : (
            <button type="button" className="rm-btn rm-btn-primary" disabled={Boolean(busy)} onClick={approve}>
              {busy || `Approve with passkey`}
            </button>
          )}
          <p className="rm-muted" style={{ margin: 0, fontSize: '0.75rem' }}>
            You hold the keys; Boardman can&apos;t move your money. Boardman never asks you to approve anything in a
            chat. If you did not start this, close the page.
          </p>
        </div>
      )}
      {err ? <p className="rm-err">{err}</p> : null}
    </BookShell>
  )
}
