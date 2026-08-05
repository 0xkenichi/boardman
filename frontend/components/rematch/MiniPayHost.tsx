'use client'

import { useCallback, useEffect, useState } from 'react'
import {
  chainLabel,
  isMiniPayEnvironment,
  MINIPAY_ENTRY_URL,
  readMiniPayState,
  type MiniPayState,
} from '@/lib/minipay'

/**
 * MiniPay shell for Celo Proof-of-Ship / Research Tech Build.
 * Detects MiniPay, connects wallet address (display), keeps Rematch stakes on our rails.
 */
export function MiniPayHost() {
  const [state, setState] = useState<MiniPayState | null>(null)
  const [busy, setBusy] = useState(false)
  const [force, setForce] = useState(false)
  const [mounted, setMounted] = useState(false)

  const refresh = useCallback(async () => {
    setBusy(true)
    try {
      const s = await readMiniPayState()
      setState(s)
    } finally {
      setBusy(false)
    }
  }, [])

  useEffect(() => {
    setMounted(true)
    try {
      setForce(new URLSearchParams(window.location.search).get('host') === 'minipay')
    } catch {
      setForce(false)
    }
    refresh()
  }, [refresh])

  if (!mounted) return null

  const show = force || state?.isMiniPay || isMiniPayEnvironment()
  if (!show) {
    return null
  }

  const connected = Boolean(state?.address)

  return (
    <div
      className="rm-card"
      style={{
        marginBottom: '0.85rem',
        borderColor: 'rgba(53, 208, 127, 0.45)',
        background:
          'linear-gradient(135deg, rgba(53,208,127,0.12) 0%, rgba(7,8,12,0.95) 60%)',
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, alignItems: 'flex-start' }}>
        <div>
          <p className="rm-section-title" style={{ color: '#35d07f' }}>
            MiniPay · Celo
          </p>
          <h2 className="rm-h2" style={{ marginBottom: 4 }}>
            {state?.isMiniPay || force ? 'Running in MiniPay' : 'MiniPay ready'}
          </h2>
          <p className="rm-muted" style={{ margin: 0, fontSize: '0.8rem' }}>
            Same Boardman app — challenge, lock, screenshot settle. MiniPay is the host for Africa
            distribution (Proof-of-Ship).
          </p>
        </div>
        <span className="rm-chip" style={{ background: 'rgba(53,208,127,0.15)', color: '#35d07f' }}>
          Celo
        </span>
      </div>

      <div className="rm-stack" style={{ marginTop: '0.75rem', gap: '0.45rem' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.85rem' }}>
          <span className="rm-muted">Host</span>
          <strong>{state?.host || '…'}</strong>
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.85rem' }}>
          <span className="rm-muted">Network</span>
          <strong>{chainLabel(state?.chainId ?? null)}</strong>
        </div>
        <div>
          <span className="rm-label">MiniPay address</span>
          <code className="rm-code" style={{ marginBottom: 0, fontSize: '0.72rem' }}>
            {state?.address || (busy ? 'Connecting…' : 'Not connected')}
          </code>
        </div>
      </div>

      <div className="rm-btn-row" style={{ marginTop: '0.75rem' }}>
        <button type="button" className="rm-btn rm-btn-primary" disabled={busy} onClick={refresh}>
          {connected ? 'Refresh MiniPay' : 'Connect MiniPay'}
        </button>
      </div>

      {state?.error ? <p className="rm-err">{state.error}</p> : null}

      <p className="rm-muted" style={{ margin: '0.65rem 0 0', fontSize: '0.72rem' }}>
        Stakes still use your Boardman play wallet (Balance $). MiniPay address is for host identity /
        future Celo USDC rails.{' '}
        <a href={MINIPAY_ENTRY_URL} style={{ color: '#35d07f' }}>
          Deep link
        </a>
      </p>
    </div>
  )
}

/** Always-visible entry for non-MiniPay browsers (proof-of-ship demos). */
export function MiniPayPromo() {
  if (typeof window !== 'undefined' && window.ethereum?.isMiniPay) return null
  return (
    <a
      href={MINIPAY_ENTRY_URL}
      className="rm-action"
      style={{ textDecoration: 'none' }}
    >
      <span className="rm-action-ico" style={{ background: 'rgba(53,208,127,0.15)' }}>
        📱
      </span>
      <span className="rm-action-body">
        <span className="rm-action-title">Open in MiniPay</span>
        <span className="rm-action-sub">Celo wallet mini-app · Africa distribution</span>
      </span>
      <span className="rm-action-chev">›</span>
    </a>
  )
}
