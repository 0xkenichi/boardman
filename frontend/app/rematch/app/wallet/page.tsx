'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { AppShell } from '@/components/AppShell'
import { api, type Me } from '@/lib/appClient'

const FAUCET = 'https://faucet.circle.com/'
const GET_USDC = '/rematch/get-usdc'

export default function WalletPage() {
  const router = useRouter()
  const [me, setMe] = useState<Me | null>(null)
  const [copied, setCopied] = useState(false)

  async function load() {
    const s = await api('/api/rematch/app/session')
    if (!s.ok) {
      router.replace('/rematch/app')
      return
    }
    const m = await api<Me>('/api/rematch/app/me')
    if (m.ok) setMe(m.data)
  }

  useEffect(() => {
    load()
  }, [router])

  async function copy() {
    if (!me?.address) return
    try {
      await navigator.clipboard.writeText(me.address)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      /* ignore */
    }
  }

  return (
    <AppShell title="Wallet">
      <div
        className="rm-card"
        style={{ marginBottom: '1rem', background: 'rgba(5,150,105,0.08)', borderColor: '#065f46' }}
      >
        <span className="rm-label">Balance</span>
        <div style={{ fontSize: '2rem', fontWeight: 900 }}>
          ${Number(me?.balance ?? 0).toFixed(2)}
        </div>
        <p className="rm-muted" style={{ margin: '0.25rem 0 0', fontSize: '0.8rem' }}>
          What you can stake
        </p>
      </div>

      <div className="rm-card" style={{ marginBottom: '1rem' }}>
        <span className="rm-label">Your fund address</span>
        <code
          style={{
            display: 'block',
            wordBreak: 'break-all',
            fontSize: '0.8rem',
            color: '#d1d5db',
            marginBottom: '0.75rem',
          }}
        >
          {me?.address || '—'}
        </code>
        <button type="button" className="rm-btn rm-btn-primary" onClick={copy} disabled={!me?.address}>
          {copied ? 'Copied' : 'Copy address'}
        </button>
        <p className="rm-muted" style={{ marginTop: '0.75rem', marginBottom: 0, fontSize: '0.8rem' }}>
          Send USDC here (crypto users). Fiat bank top-up is coming — same Balance $.
        </p>
      </div>

      {me?.otherBalance && me.otherBalance > 0.009 ? (
        <div className="rm-card" style={{ marginBottom: '1rem', borderColor: '#92400e' }}>
          <p style={{ color: '#fbbf24', margin: 0, fontSize: '0.9rem' }}>
            ⚠️ ${me.otherBalance.toFixed(2)} on another address
          </p>
          {me.otherAddress ? (
            <code style={{ fontSize: '0.75rem', color: '#9ca3af', wordBreak: 'break-all' }}>
              {me.otherAddress}
            </code>
          ) : null}
          <p className="rm-muted" style={{ marginBottom: 0, fontSize: '0.8rem' }}>
            Move funds to your play address above to stake.
          </p>
        </div>
      ) : null}

      <div style={{ display: 'grid', gap: '0.55rem' }}>
        <a href={FAUCET} target="_blank" rel="noreferrer" className="rm-btn rm-btn-ghost">
          Open Circle faucet (testnet)
        </a>
        <a href={GET_USDC} className="rm-btn rm-btn-ghost">
          Fund helper page
        </a>
        <button type="button" className="rm-btn rm-btn-ghost" onClick={load}>
          Refresh
        </button>
      </div>
    </AppShell>
  )
}
