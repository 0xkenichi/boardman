/**
 * Where is this page running, and can it use a passkey here?
 *
 * Telegram and WhatsApp open links in their own in-app browsers. Android
 * WebViews only do WebAuthn when the host app opts in, and we have no
 * evidence either app does (docs/payments/SELF_CUSTODY_WALLETS.md §1), so in
 * an in-app browser we ask the player to open the page in their real browser
 * instead of letting the passkey prompt fail.
 *
 * Pure functions (no DOM at import time) so node --test can load this file.
 */

export type InApp = 'Telegram' | 'WhatsApp' | 'Instagram' | 'Facebook' | 'an in-app browser'

export function inAppBrowser(ua: string): InApp | null {
  const s = ua || ''
  if (/Telegram/i.test(s)) return 'Telegram'
  if (/WhatsApp/i.test(s)) return 'WhatsApp'
  if (/Instagram/i.test(s)) return 'Instagram'
  if (/FBAN|FBAV|FB_IAB/i.test(s)) return 'Facebook'
  // Android System WebView marks itself with "; wv)"
  if (/Android/i.test(s) && /; wv\)/.test(s)) return 'an in-app browser'
  return null
}

export function isAndroid(ua: string): boolean {
  return /Android/i.test(ua || '')
}

/** An intent:// link that asks Android to open this https URL in Chrome. */
export function androidBrowserIntent(href: string): string | null {
  let u: URL
  try {
    u = new URL(href)
  } catch {
    return null
  }
  if (u.protocol !== 'https:') return null
  return `intent://${u.host}${u.pathname}${u.search}#Intent;scheme=https;package=com.android.chrome;S.browser_fallback_url=${encodeURIComponent(href)};end`
}

export type PasskeySupport = 'ok' | 'in_app' | 'unsupported'

/**
 * In-app browsers are refused up front; elsewhere WebAuthn must exist in a
 * secure context. A missing platform authenticator is not fatal: a phone via
 * QR code or a security key still works, so we do not gate on it.
 */
export function passkeySupport(ua: string, win?: any): PasskeySupport {
  if (inAppBrowser(ua)) return 'in_app'
  const w = win ?? (typeof window !== 'undefined' ? window : undefined)
  if (!w?.PublicKeyCredential || !w?.isSecureContext) return 'unsupported'
  return 'ok'
}
