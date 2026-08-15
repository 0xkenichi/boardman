'use client'

/**
 * Fund helper — shows the player's Arc address + Circle faucet.
 * Bot deep-links here with ?address=0x… so users don't hunt for their wallet.
 * Circle's public faucet requires human reCAPTCHA; we cannot auto-submit for them.
 *
 * Background: golden vault Three.js scene (BoardmanVaultScene) — money, not chess.
 */
import { Suspense, useMemo, useState } from 'react'
import dynamic from 'next/dynamic'
import Link from 'next/link'
import { useSearchParams } from 'next/navigation'

import { telegramBotUrl } from '@/lib/telegramBot'

const BoardmanVaultScene = dynamic(() => import('@/components/rematch/BoardmanVaultScene'), {
  ssr: false,
})

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
    <div className="bm-vault">
      <div className="bm-vault-stage" aria-hidden>
        <BoardmanVaultScene />
        <div className="bm-app-veil" />
      </div>

      <div className="bm-vault-body">
        <div className="rm-wrap" style={{ maxWidth: '34rem' }}>
          <div className="rm-stack-lg">
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src="/boardman-logo.jpg"
                alt=""
                width={44}
                height={44}
                style={{ borderRadius: 12, border: '1px solid rgba(52,211,153,0.25)' }}
              />
              <div>
                <p className="rm-label" style={{ margin: '0 0 0.15rem' }}>
                  Arc · Get USDC
                </p>
                <h1 className="rm-h1" style={{ margin: 0 }}>
                  Fund your wallet
                </h1>
              </div>
            </div>

            {isAddr ? (
              <div className="rm-card rm-card-hero">
                <span className="rm-label">Your Arc address</span>
                <code className="rm-code" style={{ fontSize: '0.82rem', wordBreak: 'break-all' }}>
                  {address}
                </code>
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
                <p className="rm-muted" style={{ margin: 0, fontSize: '0.9rem', lineHeight: 1.6 }}>
                  Open <strong style={{ color: '#fff' }}>Get USDC</strong> in the Telegram bot to
                  load your address here automatically.
                </p>
              </div>
            )}

            <div className="rm-card">
              <p className="rm-section-title">Fund in four steps</p>
              <ol className="rm-muted" style={{ margin: 0, paddingLeft: '1.1rem', lineHeight: 1.85 }}>
                <li>Copy your address above</li>
                <li>
                  Open the faucet → choose <strong style={{ color: '#fff' }}>Arc Testnet</strong> →{' '}
                  <strong style={{ color: '#fff' }}>USDC</strong>
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
              Limit is set by Circle (often once per address every few hours). Testnet USDC only —
              don&apos;t send real money.
            </p>

            <div className="rm-btn-row">
              <Link href="/app/wallet" className="rm-btn rm-btn-ghost">
                💰 My wallet
              </Link>
              <a href={BOT} target="_blank" rel="noreferrer" className="rm-btn rm-btn-ghost">
                Open Telegram bot
              </a>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

export default function GetUsdcPage() {
  return (
    <Suspense
      fallback={
        <div className="min-h-screen bg-[#07080c] text-gray-500 flex items-center justify-center text-sm">
          Loading…
        </div>
      }
    >
      <FundInner />
    </Suspense>
  )
}
