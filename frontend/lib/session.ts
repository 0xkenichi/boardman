/**
 * Server-side session helpers for Rematch web app.
 * Cookie is HttpOnly; payload is HMAC-signed with REMATCH_SESSION_SECRET only
 * (never REMATCH_API_KEY / STACK_API_KEY). Production refuses to run without it.
 *
 * Also issues the single-use wallet sign-in nonce (EIP-4361) as a signed,
 * short-lived HttpOnly cookie — stateless, so it works on serverless.
 */
import { createHmac, randomBytes, timingSafeEqual } from 'crypto'

export type RematchSession = {
  profileId: string
  telegramId: string
  tag: string
  name: string
  exp: number
  /** Issued-at (epoch sec) — absolute lifetime cap for sliding sessions. */
  iat?: number
  /** Linked wallet address (lowercase 0x…) proven via personal_sign. */
  wallet?: string
  /** Demo session (dev only). Never an admin, never a real profile. */
  demo?: boolean
}

const COOKIE = 'rematch_session'
const MAX_AGE_SEC = 60 * 60 * 24 * 7 // 7 days (slides forward while active)
const ABSOLUTE_MAX_SEC = 60 * 60 * 24 * 30 // hard cap: re-login after 30 days

const MIN_SECRET_LEN = 32
const DEV_ONLY_SECRET = 'dev-only-change-me-rematch-session'
let warnedDevSecret = false

/** NODE_ENV or VERCEL_ENV says production (kept local: this file is server-only). */
export function isProductionRuntime(): boolean {
  return process.env.NODE_ENV === 'production' || process.env.VERCEL_ENV === 'production'
}

function secret(): string {
  const configured = process.env.REMATCH_SESSION_SECRET || ''
  if (isProductionRuntime()) {
    if (configured.length < MIN_SECRET_LEN) {
      throw new Error(
        `REMATCH_SESSION_SECRET must be set to at least ${MIN_SECRET_LEN} characters in production`
      )
    }
    return configured
  }
  if (configured) return configured
  if (!warnedDevSecret) {
    warnedDevSecret = true
    console.warn(
      '[session] REMATCH_SESSION_SECRET is not set — using an insecure dev-only secret. ' +
        'This is refused in production.'
    )
  }
  return DEV_ONLY_SECRET
}

function b64url(buf: Buffer | string): string {
  const b = typeof buf === 'string' ? Buffer.from(buf, 'utf8') : buf
  return b.toString('base64url')
}

function sign(payloadB64: string): string {
  return createHmac('sha256', secret()).update(payloadB64).digest('base64url')
}

function sigEqual(sig: string, expected: string): boolean {
  try {
    const a = Buffer.from(sig)
    const b = Buffer.from(expected)
    return a.length === b.length && timingSafeEqual(a, b)
  } catch {
    return false
  }
}

export function encodeSession(session: Omit<RematchSession, 'exp' | 'iat'> & { exp?: number; iat?: number }): string {
  const now = Math.floor(Date.now() / 1000)
  const full: RematchSession = {
    ...session,
    iat: session.iat ?? now,
    exp: session.exp ?? now + MAX_AGE_SEC,
  }
  const payloadB64 = b64url(JSON.stringify(full))
  return `${payloadB64}.${sign(payloadB64)}`
}

export function decodeSession(token: string | undefined | null): RematchSession | null {
  if (!token || !token.includes('.')) return null
  const [payloadB64, sig] = token.split('.')
  if (!payloadB64 || !sig) return null
  if (!sigEqual(sig, sign(payloadB64))) return null
  try {
    const data = JSON.parse(Buffer.from(payloadB64, 'base64url').toString('utf8')) as RematchSession
    const now = Math.floor(Date.now() / 1000)
    if (!data.profileId || !data.exp || data.exp < now) return null
    // Absolute lifetime: sessions older than 30 days die even while sliding.
    if (data.iat && data.iat + ABSOLUTE_MAX_SEC < now) return null
    return data
  } catch {
    return null
  }
}

function secureAttr(): string {
  return isProductionRuntime() ? '; Secure' : ''
}

export function sessionCookieHeader(token: string): string {
  const secure = secureAttr()
  return `${COOKIE}=${token}; Path=/; HttpOnly; SameSite=Lax; Max-Age=${MAX_AGE_SEC}${secure}`
}

/** Re-issue a session with a fresh 7-day expiry, preserving iat (sliding renewal). */
export function renewSession(session: RematchSession): string {
  const { exp: _exp, ...rest } = session
  return encodeSession(rest)
}

export function clearSessionCookieHeader(): string {
  const secure = secureAttr()
  return `${COOKIE}=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0${secure}`
}

function readCookie(req: Request, name: string): string | null {
  const cookie = req.headers.get('cookie') || ''
  const match = cookie.match(new RegExp(`(?:^|;\\s*)${name}=([^;]+)`))
  if (!match?.[1]) return null
  try {
    return decodeURIComponent(match[1])
  } catch {
    return null
  }
}

export function readSessionFromRequest(req: Request): RematchSession | null {
  return decodeSession(readCookie(req, COOKIE))
}

// ── Wallet sign-in nonce (EIP-4361) ─────────────────────────────────────────
// Server-issued, single-use: GET /wallet-nonce sets it, POST /session (wallet)
// checks it equals the signed message's nonce and always clears it.

const NONCE_COOKIE = 'rematch_wallet_nonce'
const NONCE_TTL_SEC = 10 * 60
const NONCE_PATH = '/api/rematch/app'
const NONCE_PURPOSE = 'wallet-nonce.'

export function issueWalletNonce(nowSec = Math.floor(Date.now() / 1000)): {
  nonce: string
  token: string
  expiresAt: number
} {
  const nonce = randomBytes(16).toString('hex')
  const exp = nowSec + NONCE_TTL_SEC
  const payloadB64 = b64url(JSON.stringify({ n: nonce, exp }))
  return { nonce, token: `${payloadB64}.${sign(NONCE_PURPOSE + payloadB64)}`, expiresAt: exp }
}

/** The nonce inside a valid, unexpired nonce token — or null. */
export function verifyWalletNonceToken(
  token: string | null | undefined,
  nowSec = Math.floor(Date.now() / 1000)
): string | null {
  if (!token) return null
  const [payloadB64, sig, extra] = token.split('.')
  if (!payloadB64 || !sig || extra !== undefined) return null
  if (!sigEqual(sig, sign(NONCE_PURPOSE + payloadB64))) return null
  try {
    const data = JSON.parse(Buffer.from(payloadB64, 'base64url').toString('utf8'))
    if (typeof data?.n !== 'string' || typeof data?.exp !== 'number') return null
    if (data.exp < nowSec) return null
    return data.n
  } catch {
    return null
  }
}

export function readWalletNonceFromRequest(req: Request): string | null {
  return verifyWalletNonceToken(readCookie(req, NONCE_COOKIE))
}

export function walletNonceCookieHeader(token: string): string {
  return `${NONCE_COOKIE}=${token}; Path=${NONCE_PATH}; HttpOnly; SameSite=Strict; Max-Age=${NONCE_TTL_SEC}${secureAttr()}`
}

export function clearWalletNonceCookieHeader(): string {
  return `${NONCE_COOKIE}=; Path=${NONCE_PATH}; HttpOnly; SameSite=Strict; Max-Age=0${secureAttr()}`
}

export { COOKIE as SESSION_COOKIE_NAME, MAX_AGE_SEC }
