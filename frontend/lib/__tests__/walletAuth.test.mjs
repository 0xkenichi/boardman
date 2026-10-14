// Wallet sign-in (EIP-4361) + session secret checks.
// Run: cd frontend && node --test lib/__tests__/   (Node >= 23.6 strips TS types natively)
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { secp256k1 } from '@noble/curves/secp256k1.js'
import { keccak_256 } from '@noble/hashes/sha3.js'

process.env.NODE_ENV = 'test'
process.env.REMATCH_SESSION_SECRET = 's'.repeat(40)

const wm = await import('../walletMessage.ts')
const { recoverPersonalSignAddress } = await import('../walletVerify.ts')
const session = await import('../session.ts')

const HOST = 'boardman.example.com'
const PROD = { NODE_ENV: 'production', BOARDMAN_SITE_HOSTS: `${HOST}, other.example.com` }
const NOW = Date.parse('2026-10-14T12:00:00.000Z')

const priv = secp256k1.utils.randomSecretKey()
const pub = secp256k1.getPublicKey(priv, false)
const ADDRESS = '0x' + Buffer.from(keccak_256(pub.slice(1))).toString('hex').slice(24)

function personalSign(message) {
  const msg = Buffer.from(message, 'utf8')
  const digest = keccak_256(Buffer.concat([Buffer.from(`\x19Ethereum Signed Message:\n${msg.length}`), msg]))
  const rec = secp256k1.sign(digest, priv, { prehash: false, format: 'recovered' })
  // noble recid||r||s → wallet r||s||v
  return '0x' + Buffer.concat([rec.subarray(1), Buffer.from([rec[0] + 27])]).toString('hex')
}

function msg(over = {}) {
  return wm.buildWalletSignMessage({
    domain: HOST,
    address: ADDRESS,
    action: 'login',
    chainId: 5042002,
    nonce: 'abcdef0123456789',
    issuedAt: new Date(NOW).toISOString(),
    ...over,
  })
}

const want = (over = {}) => ({ action: 'login', host: HOST, nonce: 'abcdef0123456789', ...over })
const problem = (raw, w = want(), now = NOW, env = PROD) =>
  wm.walletMessageProblem(wm.parseWalletMessage(raw), w, now, env)

test('round trip: build → sign → parse → recover → accepted', () => {
  const m = msg()
  const parsed = wm.parseWalletMessage(m)
  assert.ok(parsed)
  assert.equal(parsed.address, ADDRESS)
  assert.equal(parsed.chainId, 5042002)
  assert.match(m.split('\n')[1], /[A-F]/) // EIP-55 checksummed
  assert.equal(recoverPersonalSignAddress(m, personalSign(m)), ADDRESS)
  assert.equal(problem(m), null)
})

test('rejects tampered or malformed messages', () => {
  const m = msg()
  assert.equal(wm.parseWalletMessage(m + '\nExtra: 1'), null)
  assert.equal(wm.parseWalletMessage(m.replace('Version: 1', 'Version: 2')), null)
  assert.equal(wm.parseWalletMessage(m.replace(`URI: https://${HOST}`, 'URI: https://evil.example')), null)
  assert.equal(wm.parseWalletMessage(m.replace('\n', '\r\n')), null)
  const badSum = m.replace(m.split('\n')[1], m.split('\n')[1].replace(/[a-f]/, (c) => c.toUpperCase()))
  assert.equal(wm.parseWalletMessage(badSum), null)
  // signature over a different message recovers a different address
  assert.notEqual(recoverPersonalSignAddress(m, personalSign(msg({ nonce: 'zzzzzzzzzzzz' }))), ADDRESS)
})

test('domain must equal Host and be on the exact allowlist (no *.vercel.app)', () => {
  const phish = msg({ domain: 'boardman-evil.vercel.app' })
  assert.equal(problem(phish), 'domain_mismatch')
  assert.equal(problem(phish, want({ host: 'boardman-evil.vercel.app' })), 'domain_not_allowed')
  assert.equal(problem(msg(), want({ host: 'other.example.com' })), 'domain_mismatch')
  const wild = { NODE_ENV: 'production', BOARDMAN_SITE_HOSTS: '*.vercel.app' }
  assert.equal(problem(phish, want({ host: 'boardman-evil.vercel.app' }), NOW, wild), 'domain_not_allowed')
})

test('localhost only outside production', () => {
  const m = msg({ domain: 'localhost:3000', uri: 'http://localhost:3000' })
  const w = want({ host: 'localhost:3000' })
  assert.equal(problem(m, w, NOW, { NODE_ENV: 'development' }), null)
  assert.equal(problem(m, w, NOW, { NODE_ENV: 'production', BOARDMAN_SITE_HOSTS: HOST }), 'domain_not_allowed')
  assert.equal(problem(m, w, NOW, { VERCEL_ENV: 'production' }), 'domain_not_allowed')
})

test('nonce must match the cookie nonce', () => {
  assert.equal(problem(msg(), want({ nonce: null })), 'nonce_mismatch')
  assert.equal(problem(msg(), want({ nonce: 'different0123456' })), 'nonce_mismatch')
})

test('issued-at window: <=60s future, <=10min old', () => {
  const at = (ms) => msg({ issuedAt: new Date(ms).toISOString() })
  assert.equal(problem(at(NOW + 59_000)), null)
  assert.equal(problem(at(NOW + 61_000)), 'issued_in_future')
  assert.equal(problem(at(NOW + 9 * 60_000)), 'issued_in_future')
  assert.equal(problem(at(NOW - 9 * 60_000)), null)
  assert.equal(problem(at(NOW - 11 * 60_000)), 'expired')
})

test('chain id must be allowed', () => {
  assert.equal(problem(msg({ chainId: 999 })), 'chain_not_allowed')
  assert.equal(problem(msg({ chainId: 999 }), want(), NOW, { ...PROD, BOARDMAN_SIWE_CHAIN_IDS: '999' }), null)
})

test('link messages are bound to the session profile', () => {
  const link = msg({ action: 'link', profileId: 'p-1' })
  assert.equal(problem(link, want({ action: 'link', profileId: 'p-1' })), null)
  assert.equal(problem(link, want({ action: 'link', profileId: 'p-2' })), 'profile_mismatch')
  assert.equal(problem(link), 'action_mismatch')
})

test('nonce token: signed, expiring, tamper-evident', () => {
  const now = 1_800_000_000
  const { nonce, token } = session.issueWalletNonce(now)
  assert.match(nonce, /^[0-9a-f]{32}$/)
  assert.equal(session.verifyWalletNonceToken(token, now + 599), nonce)
  assert.equal(session.verifyWalletNonceToken(token, now + 601), null)
  const [p, s] = token.split('.')
  const forged = Buffer.from(JSON.stringify({ n: 'attacker0000', exp: now + 600 })).toString('base64url')
  assert.equal(session.verifyWalletNonceToken(`${forged}.${s}`, now), null)
  // a session signature is not a nonce signature (domain-separated HMAC)
  const sess = session.encodeSession({ profileId: 'x', telegramId: '1', tag: 't', name: 'n' })
  assert.equal(session.verifyWalletNonceToken(sess, now), null)
  assert.equal(session.decodeSession(`${p}.${s}`), null)
  assert.match(session.walletNonceCookieHeader(token), /HttpOnly; SameSite=Strict/)
})

test('session secret: required in production, no API-key fallback', () => {
  const saved = { ...process.env }
  try {
    process.env.NODE_ENV = 'production'
    delete process.env.REMATCH_SESSION_SECRET
    process.env.REMATCH_API_KEY = 'k'.repeat(64)
    assert.throws(() => session.encodeSession({ profileId: 'x', telegramId: '1', tag: 't', name: 'n' }), /REMATCH_SESSION_SECRET/)
    process.env.REMATCH_SESSION_SECRET = 'short'
    assert.throws(() => session.issueWalletNonce(), /at least 32/)
    process.env.NODE_ENV = 'test'
    process.env.VERCEL_ENV = 'production'
    assert.throws(() => session.issueWalletNonce(), /REMATCH_SESSION_SECRET/)
  } finally {
    for (const k of ['NODE_ENV', 'VERCEL_ENV', 'REMATCH_SESSION_SECRET', 'REMATCH_API_KEY']) {
      if (saved[k] === undefined) delete process.env[k]
      else process.env[k] = saved[k]
    }
  }
})
