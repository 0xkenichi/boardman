'use client'

/**
 * Fund helper — shows the player's Arc address + Circle faucet.
 * Bot deep-links here with ?address=0x… so users don't hunt for their wallet.
 * Circle's public faucet requires human reCAPTCHA; we cannot auto-submit for them.
 *
 * Book paper — the old Three.js vault scene is gone; paper needs no fireworks.
 */
import { Suspense, useMemo, useState } from 'react'
import Link from 'next/link'
import { useSearchParams } from 'next/navigation'
import { BookShell } from '@/components/rematch/BookShell'

import { telegramBotUrl } from '@/lib/telegramBot'

const BOT = telegramBotUrl()
const FAUCET = 'https://faucet.circle.com/'

function FundInner() {
  const params = useSearchParams()
  const address = (params.get('address') || '').trim()
  const [copied, setCopied] = useState(false)

  const isAddr = useMemo(() => /^0x[a-fA-F0-9]{40}$/.test(address), [address])

  async function copy() {
    if (!isAddr) return
    try {
      await navigator.clipboard.writeText(address)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      /* ignore */
    }
  }

  return (
    <BookShell title="Fund the wallet">
      <div style={{ maxWidth: '34rem', margin: '0 auto', padding: '0 1rem 3.5rem' }}>
        <div className="rm-stack-lg">
          <p className="bk-lede" style={{ margin: 0 }}>
            The stake has to come from somewhere. <em>Testnet USDC only</em> —
            Circle&apos;s faucet pours it free; don&apos;t send real money here.
          </p>

          {isAddr ? (
            <div className="rm-card rm-card-hero">
              <div className="bk-slip">
                <div className="bk-slip-head">
                  <span>YOUR ARC ADDRESS</span>
                  <span>DEPOSIT</span>
                </div>
                <div className="bk-slip-row">
                  <strong style={{ wordBreak: 'break-all' }}>{address}</strong>
                </div>
              </div>
              <button
                type="button"
                onClick={copy}
                className="rm-btn rm-btn-primary"
                style={{ marginTop: '0.85rem' }}
              >
                {copied ? 'Copied ✓' : 'Copy address'}
              </button>
            </div>
          ) : (
            <div className="rm-card">
              <p className="rm-muted" style={{ margin: 0, fontSize: '0.95rem', lineHeight: 1.6 }}>
                Open <strong>Get USDC</strong> in the Telegram bot and your address loads
                here automatically.
              </p>
            </div>
          )}

          <div className="rm-card">
            <p className="rm-section-title">Fund in four steps</p>
            <ol className="rm-muted bk-rules" style={{ margin: 0, paddingLeft: '1.2rem', lineHeight: 1.85 }}>
              <li>Copy your address above</li>
              <li>
                Open the faucet → choose <strong>Arc Testnet</strong> →{' '}
                <strong>USDC</strong>
              </li>
              <li>Paste address → request tokens</li>
              <li>Back in Telegram → Wallet → Refresh</li>
            </ol>
          </div>

          <a
            href={FAUCET}
            target="_blank"
            rel="noreferrer"
            className="rm-btn rm-btn-primary"
            style={{ fontSize: '0.95rem' }}
          >
            Open Circle faucet →
          </a>

          <p className="rm-muted" style={{ fontSize: '0.78rem', textAlign: 'center', margin: 0 }}>
            Limit is set by Circle (often once per address every few hours). Testnet USDC
            only — don&apos;t send real money.
          </p>

          <div className="rm-btn-row">
            <Link href="/app/wallet" className="rm-btn rm-btn-ghost">
              My wallet
            </Link>
            <a href={BOT} target="_blank" rel="noreferrer" className="rm-btn rm-btn-ghost">
              Telegram bot
            </a>
          </div>
        </div>
      </div>
    </BookShell>
  )
}

export default function GetUsdcPage() {
  return (
    <Suspense
      fallback={
        <div className="min-h-screen flex items-center justify-center text-sm" style={{ background: '#f2eee2', color: '#8a8478' }}>
          Loading…
        </div>
      }
    >
      <FundInner />
    </Suspense>
  )
}
