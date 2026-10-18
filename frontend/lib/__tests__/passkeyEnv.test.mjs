// In-app browser detection for the passkey pages: Telegram / WhatsApp
// webviews get "Open in browser" instead of a passkey prompt that fails.
// Run: cd frontend && node --test lib/__tests__/
import { test } from 'node:test'
import assert from 'node:assert/strict'

const { inAppBrowser, androidBrowserIntent, passkeySupport } = await import('../selfCustody/env.ts')

const TG_ANDROID =
  'Mozilla/5.0 (Linux; Android 14; Pixel 8; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/129.0 Mobile Safari/537.36 Telegram-Android/11.2.0'
const WA_IOS =
  'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 WhatsApp/24.20'
const GENERIC_WV = 'Mozilla/5.0 (Linux; Android 13; SM-A515F; wv) AppleWebKit/537.36 Chrome/128.0 Mobile Safari/537.36'
const SAFARI =
  'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1'
const CHROME = 'Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0 Mobile Safari/537.36'

test('in-app browsers are recognised', () => {
  assert.equal(inAppBrowser(TG_ANDROID), 'Telegram')
  assert.equal(inAppBrowser(WA_IOS), 'WhatsApp')
  assert.equal(inAppBrowser(GENERIC_WV), 'an in-app browser')
  assert.equal(inAppBrowser(SAFARI), null)
  assert.equal(inAppBrowser(CHROME), null)
})

test('android intent keeps the one-time path and only for https', () => {
  const url = 'https://boardman.example/app/approve/abc_DEF-123456789012345'
  const intent = androidBrowserIntent(url)
  assert.ok(intent.startsWith('intent://boardman.example/app/approve/abc_DEF-123456789012345#Intent;scheme=https;'))
  assert.ok(intent.includes('package=com.android.chrome'))
  assert.equal(androidBrowserIntent('http://x.test/a'), null)
  assert.equal(androidBrowserIntent('not a url'), null)
})

test('passkey support: webviews refused, real browsers need WebAuthn in a secure context', () => {
  assert.equal(passkeySupport(TG_ANDROID, { PublicKeyCredential: {}, isSecureContext: true }), 'in_app')
  assert.equal(passkeySupport(SAFARI, { PublicKeyCredential: {}, isSecureContext: true }), 'ok')
  assert.equal(passkeySupport(SAFARI, { isSecureContext: true }), 'unsupported')
  assert.equal(passkeySupport(CHROME, { PublicKeyCredential: {}, isSecureContext: false }), 'unsupported')
})
