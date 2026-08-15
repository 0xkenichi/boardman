'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { AppShell } from '@/components/AppShell'
import { api, type Me } from '@/lib/appClient'

const FAUCET = 'https://faucet.circle.com/'
const GET_USDC = '/get-usdc'

export default function WalletPage() {
  const router = useRouter()
  const [me, setMe] = useState<Me | null>(null)
  const [copied, setCopied] = useState(false)
  const [loading, setLoading] = useState(true)

  async function load() {
    setLoading(true)
    try {
      const s = await api('/api/rematch/app/session')
      if (!s.ok) {
        router.replace('/app')
        return
      }
      const m = await api<Me>('/api/rematch/app/me')
      if (m.ok) setMe(m.data)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
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
      <div className="rm-stack-lg">
        <div className="rm-card rm-card-hero">
          <span className="rm-label">Balance (Arc · play wallet)</span>
          {loading && !me ? (
            <div className="rm-skeleton" style={{ height: 40, width: '50%', marginTop: 8 }} />
          ) : (
            <div className="rm-balance">
              <span>$</span>
              {Number(me?.balance ?? 0).toFixed(2)}
            </div>
          )}
          <p className="rm-muted" style={{ margin: '0.45rem 0 0', fontSize: '0.8rem' }}>
            Same play wallet as the Telegram bot · Arc USDC
          </p>
        </div>

        <div className="rm-card">
          <span className="rm-label">Fund / deposit address</span>
          <code className="rm-code">{me?.address || '—'}</code>
          <button
            type="button"
            className="rm-btn rm-btn-primary"
            onClick={copy}
            disabled={!me?.address}
          >
            {copied ? '✓ Copied' : 'Copy address'}
          </button>
          <p className="rm-muted" style={{ marginTop: '0.75rem', marginBottom: 0, fontSize: '0.8rem' }}>
            Send Arc testnet USDC here only. This is the address Boardman stakes from.
          </p>
        </div>

        {me?.otherBalance && me.otherBalance > 0.009 ? (
          <div className="rm-card rm-card-warn">
            <p className="rm-warn-text" style={{ marginTop: 0 }}>
              ⚠️ ${me.otherBalance.toFixed(2)} still sitting on an older address
            </p>
            {me.otherAddress ? <code className="rm-code">{me.otherAddress}</code> : null}
            <p className="rm-muted" style={{ marginBottom: 0, fontSize: '0.8rem' }}>
              Not used for new stakes. Send those funds to the play address above (or ask support
              to consolidate).
            </p>
          </div>
        ) : null}

        <div className="rm-stack">
          <a href={FAUCET} target="_blank" rel="noreferrer" className="rm-btn rm-btn-ghost">
            Open Circle faucet (testnet)
          </a>
          <a href={GET_USDC} className="rm-btn rm-btn-ghost">
            Fund helper page
          </a>
          <button type="button" className="rm-btn rm-btn-ghost" onClick={load}>
            Refresh balance
          </button>
        </div>
      </div>
    </AppShell>
  )
}
