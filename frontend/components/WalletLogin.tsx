'use client'

/**
 * Wallet sign-in (EIP-1193 `personal_sign`, no viem/ethers).
 *
 * Link-first model: `intent: 'login'` resolves the profile the wallet is
 * already linked to; `intent: 'link'` binds the wallet to the current
 * Telegram session (POST needs the session cookie).
 *
 * Flow (EIP-4361): GET /wallet-nonce → sign a message carrying that nonce,
 * this host and the wallet's chain id → POST /session, which checks all three.
 */
import { useCallback, useState } from 'react'
import { api } from '@/lib/appClient'
import { buildWalletSignMessage, type WalletSignAction } from '@/lib/walletMessage'

type Props = {
  intent?: WalletSignAction
  onAuth?: () => void
  label?: string
  className?: string
}

type AuthResult = {
  ok?: boolean
  error?: string
  message?: string
  wallet?: string
}

async function requestAccounts(): Promise<string | null> {
  const eth = window.ethereum
  if (!eth) return null
  try {
    const accounts = (await eth.request({ method: 'eth_requestAccounts' })) as string[]
    return accounts?.[0] || null
  } catch {
    return null
  }
}

export function WalletLogin({ intent = 'login', onAuth, label, className }: Props) {
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [info, setInfo] = useState<string | null>(null)

  const run = useCallback(async () => {
    setBusy(true)
    setErr(null)
    setInfo(null)
    try {
      if (!window.ethereum) {
        setErr(
          'No wallet found. Open this page in a wallet browser (MiniPay, MetaMask, etc.).'
        )
        return
      }
      const address = await requestAccounts()
      if (!address) {
        setErr('Wallet connection was rejected.')
        return
      }

      let profileId: string | undefined
      if (intent === 'link') {
        const sess = await api<{ profileId?: string }>('/api/rematch/app/session')
        if (!sess.ok || !sess.data?.profileId) {
          setErr('Sign in with Telegram first, then link your wallet.')
          return
        }
        profileId = sess.data.profileId
      }

      // Single-use server nonce (also set as an HttpOnly cookie the POST checks).
      const nonceRes = await api<{ nonce?: string }>('/api/rematch/app/wallet-nonce')
      const nonce = nonceRes.ok ? nonceRes.data?.nonce : undefined
      if (!nonce) {
        setErr('Could not start wallet sign-in. Try again.')
        return
      }
      const chainHex = (await window.ethereum.request({ method: 'eth_chainId' })) as string
      const chainId = parseInt(String(chainHex || ''), 16)
      if (!Number.isSafeInteger(chainId) || chainId <= 0) {
        setErr('Could not read the wallet network.')
        return
      }

      const message = buildWalletSignMessage({
        domain: window.location.host,
        uri: window.location.origin,
        address,
        action: intent,
        chainId,
        nonce,
        profileId,
      })
      const signature = (await window.ethereum.request({
        method: 'personal_sign',
        params: [message, address],
      })) as string

      const res = await api<AuthResult>('/api/rematch/app/session', {
        method: 'POST',
        body: JSON.stringify({ mode: 'wallet', intent, message, signature }),
      })
      if (!res.ok) {
        const d = res.data || {}
        setErr(d.message || d.error || 'Wallet sign-in failed.')
        return
      }
      if (intent === 'link') {
        setInfo(`Wallet ${(res.data?.wallet || address).slice(0, 10)}… linked.`)
      }
      onAuth?.()
    } catch (e: any) {
      const msg = String(e?.message || e || '')
      setErr(/reject|denied|4001/i.test(msg) ? 'Signature was rejected.' : msg || 'Wallet sign-in failed.')
    } finally {
      setBusy(false)
    }
  }, [intent, onAuth])

  return (
    <div className={className} style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
      <button
        type="button"
        className="rm-btn rm-btn-ghost"
        disabled={busy}
        onClick={run}
        style={{ width: '100%' }}
      >
        {busy
          ? 'Check your wallet…'
          : label || (intent === 'link' ? 'Link this wallet' : 'Sign in with wallet')}
      </button>
      {err ? <p className="rm-err" style={{ margin: 0 }}>{err}</p> : null}
      {info ? <p className="rm-ok" style={{ margin: 0 }}>{info}</p> : null}
    </div>
  )
}
