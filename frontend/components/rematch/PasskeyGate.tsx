'use client'

/**
 * Shown instead of the passkey button when this page can't use a passkey:
 * inside Telegram / WhatsApp / Instagram in-app browsers (their webviews
 * usually block WebAuthn) or a browser without WebAuthn. Offers "Open in
 * browser" (Chrome intent on Android) and a copy-link fallback. The link is
 * one-time and secret: we never put it anywhere but the clipboard.
 */

import { useState } from 'react'
import { androidBrowserIntent, inAppBrowser, isAndroid, type PasskeySupport } from '@/lib/selfCustody/env'

export function PasskeyGate({ support }: { support: PasskeySupport }) {
  const [copied, setCopied] = useState(false)
  const ua = typeof navigator !== 'undefined' ? navigator.userAgent : ''
  const href = typeof window !== 'undefined' ? window.location.href : ''
  const app = inAppBrowser(ua)
  const intent = isAndroid(ua) ? androidBrowserIntent(href) : null

  async function copy() {
    try {
      await navigator.clipboard.writeText(href)
      setCopied(true)
    } catch {
      setCopied(false)
    }
  }

  return (
    <div className="rm-card rm-card-warn rm-stack">
      <p className="rm-warn-text" style={{ marginTop: 0 }}>
        {support === 'in_app'
          ? `Passkeys don't work inside ${app || 'this app'}. Open this page in your phone's browser (Safari or Chrome) to continue.`
          : "This browser can't use passkeys. Open this page in Safari or Chrome on your phone."}
      </p>
      {intent ? (
        <a className="rm-btn rm-btn-primary" href={intent}>
          Open in browser
        </a>
      ) : (
        <p className="rm-muted" style={{ margin: 0, fontSize: '0.8rem' }}>
          On iPhone: tap the ••• or share menu and choose <b>Open in Safari</b>
          {app === 'Telegram' ? ' (or long-press the link in the chat and pick Open in Safari)' : ''}.
        </p>
      )}
      <button type="button" className="rm-btn rm-btn-ghost" onClick={copy}>
        {copied ? 'Link copied. Paste it in your browser.' : 'Copy link'}
      </button>
      <p className="rm-muted" style={{ margin: 0, fontSize: '0.75rem' }}>
        The link works once and only for you. Don't share it.
      </p>
    </div>
  )
}
