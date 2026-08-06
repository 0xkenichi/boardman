'use client'

/**
 * MiniPay listing / Proof-of-Ship landing.
 * Submit this URL to MiniPay discovery & Celo Research Tech Build demos.
 */
import Link from 'next/link'
import { MiniPayHost } from '@/components/rematch/MiniPayHost'
import { MINIPAY_ENTRY_URL } from '@/lib/minipay'
import { REMATCH_BOT_URL, REMATCH_GROUP_URL } from '@/lib/rematchLinks'

export default function MiniPayLandingPage() {
  return (
    <div style={{ maxWidth: '28rem', margin: '0 auto', padding: '1.5rem 1rem 3rem' }}>
      <p className="rm-section-title" style={{ color: '#35d07f' }}>
        Celo · MiniPay · Proof-of-Ship
      </p>
      <h1 className="rm-h1" style={{ marginBottom: '0.5rem' }}>
        Rematch on MiniPay
      </h1>
      <p className="rm-muted" style={{ marginBottom: '1.25rem' }}>
        1v1 skill matches with dual-lock USDC, screenshot settle, and a simple Balance $ UX —
        packaged as a MiniPay mini-app host for Africa.
      </p>

      <MiniPayHost />

      <div className="rm-stack" style={{ marginTop: '1rem' }}>
        <Link href="/app?host=minipay" className="rm-btn rm-btn-primary">
          Launch Rematch mini-app
        </Link>
        <a href={REMATCH_BOT_URL} target="_blank" rel="noreferrer" className="rm-btn rm-btn-ghost">
          Telegram bot (same accounts)
        </a>
        <a
          href={REMATCH_GROUP_URL}
          target="_blank"
          rel="noreferrer"
          className="rm-btn rm-btn-ghost"
        >
          Live rooms group
        </a>
      </div>

      <div className="rm-card" style={{ marginTop: '1.25rem' }}>
        <p className="rm-label">Proof-of-ship checklist</p>
        <ul className="rm-muted" style={{ margin: 0, paddingLeft: '1.1rem', lineHeight: 1.6 }}>
          <li>Live URL: playingsidequest.fun/rematch/app?host=minipay</li>
          <li>Detects <code>window.ethereum.isMiniPay</code></li>
          <li>Connects MiniPay address for host identity</li>
          <li>Same challenge / lock / proof flow as Telegram</li>
          <li>Custodial play wallet + optional Celo rail later</li>
        </ul>
        <p className="rm-muted" style={{ margin: '0.75rem 0 0', fontSize: '0.75rem' }}>
          Deep link for listings:{' '}
          <code style={{ color: '#35d07f', wordBreak: 'break-all' }}>{MINIPAY_ENTRY_URL}</code>
        </p>
      </div>
    </div>
  )
}
