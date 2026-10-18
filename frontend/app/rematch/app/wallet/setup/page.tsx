'use client'

/**
 * Create a self-custody passkey wallet and link it to the Boardman profile.
 * Opened from a chat link (?t=…) or while signed in on the web.
 *
 * 1. The phone makes a passkey (Face ID / fingerprint); the smart-account
 *    address is computed from it.
 * 2. The backend issues a one-time challenge for that address; the passkey
 *    signs it (a second prompt) and the backend verifies it on chain.
 * 3. The player confirms the address in their chat ("Yes, it's mine"). Only
 *    then is it linked. Changing an existing wallet also needs a recent web
 *    sign-in and waits 24 hours.
 *
 * We send Boardman only the address, the public credential id and the
 * signature over the challenge.
 */

import { Suspense, useEffect, useState } from 'react'
import { useSearchParams } from 'next/navigation'
import { BookShell } from '@/components/rematch/BookShell'
import { PasskeyGate } from '@/components/rematch/PasskeyGate'
import { passkeySupport, type PasskeySupport } from '@/lib/selfCustody/env'
import { challengeProblem, type SetupChallenge } from '@/lib/selfCustody/proof'
import { createWallet, walletsConfigured, WalletError, type ChainInfo } from '@/lib/selfCustody/wallet'

type Pending = { address: string; kind: 'setup' | 'change'; status: 'pending_confirm' | 'cooling'; active_at_ms?: number | null }

type View = {
  ok: boolean
  username?: string
  wallet?: { address: string; credential_id: string } | null
  pending?: Pending | null
  can_change?: boolean
  change_needs_signin?: boolean
  chain?: ChainInfo
  error?: string
  message?: string
}

type Proved = { address: string; kind: 'setup' | 'change'; confirmSent: boolean }

async function postJson(url: string, body: unknown): Promise<{ ok: boolean; data: any }> {
  const res = await fetch(url, {
    method: 'POST',
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  const data = await res.json().catch(() => ({ ok: false }))
  return { ok: res.ok && Boolean(data?.ok), data }
}

function when(ms?: number | null): string {
  return ms ? new Date(ms).toLocaleString() : 'in 24 hours'
}

function SetupInner() {
  const t = useSearchParams().get('t') || ''
  const q = t ? `?t=${encodeURIComponent(t)}` : ''
  const [view, setView] = useState<View | null>(null)
  const [support, setSupport] = useState<PasskeySupport>('ok')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [proved, setProved] = useState<Proved | null>(null)

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
    const chain = view.chain
    setErr(null)
    setBusy(true)
    try {
      const w = await createWallet(chain, view.username || 'Boardman')
      const ch = await postJson(`/api/rematch/app/wallet/setup/challenge${q}`, { address: w.address })
      if (!ch.ok) {
        setErr(ch.data?.message || 'Could not start the wallet check. Start again in the chat.')
        return
      }
      const c = ch.data as SetupChallenge
      if (challengeProblem(c, w.address, chain.evm_chain_id)) {
        setErr('The wallet check did not match this wallet. Nothing was linked.')
        return
      }
      const signature = await w.signProof(c.message)
      const reg = await postJson(`/api/rematch/app/wallet/setup${q}`, {
        address: w.address,
        credential_id: w.credentialId,
        challenge_id: c.challenge_id,
        signature,
      })
      if (reg.ok) setProved({ address: reg.data.address || w.address, kind: c.kind, confirmSent: Boolean(reg.data.confirm_sent) })
      else setErr(reg.data?.message || 'Could not link the wallet. Start again in the chat.')
    } catch (e) {
      setErr(e instanceof WalletError ? e.message : 'Something went wrong. Nothing was linked.')
    } finally {
      setBusy(false)
    }
  }

  const pending = proved ? null : view?.pending
  const wallet = view?.wallet

  const createButton = (label: string) =>
    support !== 'ok' ? (
      <PasskeyGate support={support} />
    ) : !walletsConfigured() ? (
      <p className="rm-warn-text" style={{ margin: 0 }}>Passkey wallets are not switched on yet.</p>
    ) : (
      <button type="button" className="rm-btn rm-btn-primary" disabled={busy} onClick={create}>
        {busy ? 'Waiting for your passkey…' : label}
      </button>
    )

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
      ) : proved ? (
        <div className="rm-card rm-stack">
          <p className="rm-ok" style={{ marginTop: 0 }}>One last step: confirm it in your chat.</p>
          <span className="rm-label">Your new address on {view.chain?.label}</span>
          <code className="rm-code" style={{ wordBreak: 'break-all' }}>{proved.address}</code>
          <p className="rm-muted" style={{ margin: 0, fontSize: '0.85rem' }}>
            {proved.confirmSent
              ? 'We sent "Is this your new wallet?" to your Boardman chat. Check the address matches this one and tap Yes.'
              : 'Open your Boardman chat and send "wallet" to confirm this address.'}{' '}
            Nothing is linked until you confirm.
            {proved.kind === 'change' ? ' A changed wallet starts working 24 hours after you confirm.' : ''}
          </p>
        </div>
      ) : pending ? (
        <div className="rm-card rm-stack">
          <span className="rm-label">{pending.status === 'cooling' ? 'Wallet change scheduled' : 'Waiting for your confirmation'}</span>
          <code className="rm-code" style={{ wordBreak: 'break-all' }}>{pending.address}</code>
          <p className="rm-muted" style={{ margin: 0, fontSize: '0.85rem' }}>
            {pending.status === 'cooling'
              ? `This becomes your wallet on ${when(pending.active_at_ms)}. You can cancel it from your chat.`
              : 'Confirm this address in your Boardman chat (send "wallet" if you cannot find the message). If it is not yours, tap No there.'}
          </p>
        </div>
      ) : wallet ? (
        <div className="rm-card rm-stack">
          <p className="rm-ok" style={{ marginTop: 0 }}>You already have a wallet.</p>
          <span className="rm-label">Your address on {view.chain?.label}</span>
          <code className="rm-code" style={{ wordBreak: 'break-all' }}>{wallet.address}</code>
          <p className="rm-muted" style={{ margin: 0, fontSize: '0.85rem' }}>
            Send USDC on {view.chain?.label} to this address to play. Stakes and withdrawals are approved with your
            passkey, one at a time.
          </p>
          {view.can_change ? (
            <>
              <p className="rm-muted" style={{ margin: 0, fontSize: '0.8rem' }}>
                Lost this passkey? You can link a new wallet. You confirm it in your chat, and it starts working 24 hours
                later.
              </p>
              {createButton('Change to a new passkey wallet')}
            </>
          ) : view.change_needs_signin ? (
            <p className="rm-muted" style={{ margin: 0, fontSize: '0.75rem' }}>
              To change your wallet, sign in again on the website, then come back to this page.
            </p>
          ) : null}
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
              <li>Your phone asks for the passkey twice: once to create it, once to prove the wallet is yours.</li>
              <li>Then you confirm the new address in your Boardman chat.</li>
              <li>Your passkey syncs with your Apple or Google account, so a new phone keeps working.</li>
              <li>If you lose every device with the passkey, Boardman cannot recover the wallet for you.</li>
              <li>Winnings are paid by the escrow contract straight to this wallet.</li>
            </ul>
          </div>
          {createButton('Create my wallet with a passkey')}
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
