// 2026-10 web audit (docs/security/AUDIT_2026-10_web.md): BFF regression tests.
// Run: cd frontend && node --test lib/__tests__/
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { createHash, createHmac } from 'node:crypto'

const { crossSiteRefusal } = await import('../csrf.ts')
const { walletLoginQuery, WALLET_LOGIN_COLUMN } = await import('../walletMessage.ts')
const tg = await import('../telegramAuth.ts')
const { escapeTelegramHtml } = await import('../telegramBot.ts')

const HOST = 'boardman.playingsidequest.fun'
const h = (o) => ({ get: (k) => (k.toLowerCase() in o ? o[k.toLowerCase()] : null) })

// ── WEB-04 CSRF / login CSRF ─────────────────────────────────────────────────
test('same-origin browser POSTs pass', () => {
  const hdr = h({ 'sec-fetch-site': 'same-origin', origin: `https://${HOST}`, 'content-type': 'application/json' })
  assert.equal(crossSiteRefusal('POST', '/api/rematch/app/session', hdr, HOST), null)
})

test('a sibling subdomain (same site, other origin) is refused', () => {
  const hdr = h({ 'sec-fetch-site': 'same-site', origin: 'https://evil.playingsidequest.fun' })
  assert.equal(crossSiteRefusal('POST', '/api/agentic/football/wallet/withdraw', hdr, HOST), 'cross_site_request')
  // older browsers without Sec-Fetch-*: the Origin still decides
  const old = h({ origin: 'https://evil.playingsidequest.fun', 'content-type': 'application/json' })
  assert.equal(crossSiteRefusal('POST', '/api/agentic/football/wallet/withdraw', old, HOST), 'origin_mismatch')
})

test('login CSRF via a cross-site text/plain form is refused', () => {
  const hdr = h({ 'sec-fetch-site': 'cross-site', origin: 'https://attacker.example', 'content-type': 'text/plain' })
  assert.notEqual(crossSiteRefusal('POST', '/api/rematch/app/session', hdr, HOST), null)
  // even with the Origin stripped (no-referrer tricks), a form body type is refused
  const bare = h({ 'content-type': 'text/plain;charset=UTF-8' })
  assert.equal(crossSiteRefusal('POST', '/api/rematch/app/session', bare, HOST), 'form_content_type')
  const nullOrigin = h({ origin: 'null', 'content-type': 'application/json' })
  assert.equal(crossSiteRefusal('POST', '/api/rematch/app/session', nullOrigin, HOST), 'bad_origin')
})

test('reads, server-to-server calls and signed webhooks are not affected', () => {
  const cross = h({ 'sec-fetch-site': 'cross-site', origin: 'https://attacker.example' })
  assert.equal(crossSiteRefusal('GET', '/api/rematch/app/me', cross, HOST), null)
  assert.equal(crossSiteRefusal('POST', '/api/rematch/app/session', h({ 'content-type': 'application/json' }), HOST), null)
  assert.equal(crossSiteRefusal('POST', '/api/rematch/paystack/webhook', h({ 'content-type': 'text/plain' }), HOST), null)
  // multipart uploads from this origin keep working
  const up = h({ 'sec-fetch-site': 'same-origin', origin: `https://${HOST}`, 'content-type': 'multipart/form-data; boundary=x' })
  assert.equal(crossSiteRefusal('POST', '/api/rematch/app/matches/ABC/proof', up, HOST), null)
})

// ── WEB-03 wallet sign-in trusts only the proven link ────────────────────────
test('wallet sign-in looks up linked_wallet only, lower-cased, and asks for two rows', () => {
  assert.equal(WALLET_LOGIN_COLUMN, 'linked_wallet')
  const q = new URLSearchParams(walletLoginQuery('0xABCDEF0123456789abcdef0123456789ABCDEF01'))
  assert.equal(q.get('linked_wallet'), 'eq.0xabcdef0123456789abcdef0123456789abcdef01')
  assert.equal(q.get('wallet_address'), null)
  assert.equal(q.get('withdrawal_wallet'), null)
  assert.equal(q.get('limit'), '2')
  assert.throws(() => walletLoginQuery('0x123,or=(id.neq.0)'))
})

// ── WEB-09 Telegram login freshness ──────────────────────────────────────────
test('auth_date must be a fresh positive integer', () => {
  const now = 1_800_000_000
  assert.equal(tg.authDateFresh(String(now - 60), now), true)
  assert.equal(tg.authDateFresh(String(now - 86401), now), false)
  assert.equal(tg.authDateFresh(String(now + 3600), now), false) // future
  for (const bad of ['', 'abc', '1e9', '-5', '0', undefined, '12.5']) {
    assert.equal(tg.authDateFresh(bad, now), false, String(bad))
  }
})

test('a correctly signed widget payload with a stale or non-numeric auth_date is refused', () => {
  process.env.TELEGRAM_BOT_TOKEN_BOARDMAN = '123456:test-token-not-real'
  const sign = (data) => {
    const pairs = Object.keys(data).sort().map((k) => `${k}=${data[k]}`).join('\n')
    const secret = createHash('sha256').update(process.env.TELEGRAM_BOT_TOKEN_BOARDMAN).digest()
    return { ...data, hash: createHmac('sha256', secret).update(pairs).digest('hex') }
  }
  const now = Math.floor(Date.now() / 1000)
  assert.ok(tg.verifyTelegramLogin(sign({ id: '42', first_name: 'A', auth_date: String(now) })))
  assert.equal(tg.verifyTelegramLogin(sign({ id: '42', first_name: 'A', auth_date: 'soon' })), null)
  assert.equal(tg.verifyTelegramLogin(sign({ id: '42', first_name: 'A', auth_date: String(now - 90000) })), null)
  assert.equal(tg.verifyTelegramLogin(sign({ id: '6277067771x', auth_date: String(now) })), null)
  delete process.env.TELEGRAM_BOT_TOKEN_BOARDMAN
})

// ── WEB-08 admin chat HTML injection ─────────────────────────────────────────
test('Telegram HTML escaping neutralises tags and links', () => {
  const out = escapeTelegramHtml('<a href="https://evil.example">verify</a> & <b>x</b>')
  assert.doesNotMatch(out, /<a|<b>/)
  assert.match(out, /&lt;a href=&quot;/)
  assert.equal(escapeTelegramHtml(undefined), '')
})
