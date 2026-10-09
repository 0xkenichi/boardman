/**
 * Server-side session helpers for Rematch web app.
 * Cookie is HttpOnly; payload is HMAC-signed. Never put REMATCH_API_KEY here.
 */
import { createHmac, timingSafeEqual } from 'crypto'

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
}

const COOKIE = 'rematch_session'
const MAX_AGE_SEC = 60 * 60 * 24 * 7 // 7 days (slides forward while active)
const ABSOLUTE_MAX_SEC = 60 * 60 * 24 * 30 // hard cap: re-login after 30 days

function secret(): string {
  return (
    process.env.REMATCH_SESSION_SECRET ||
    process.env.REMATCH_API_KEY ||
    process.env.STACK_API_KEY ||
    'dev-only-change-me-rematch-session'
  )
}

function b64url(buf: Buffer | string): string {
  const b = typeof buf === 'string' ? Buffer.from(buf, 'utf8') : buf
  return b.toString('base64url')
}

function sign(payloadB64: string): string {
  return createHmac('sha256', secret()).update(payloadB64).digest('base64url')
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
  const expected = sign(payloadB64)
  try {
    const a = Buffer.from(sig)
    const b = Buffer.from(expected)
    if (a.length !== b.length || !timingSafeEqual(a, b)) return null
  } catch {
    return null
  }
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

export function sessionCookieHeader(token: string): string {
  const secure = process.env.NODE_ENV === 'production' ? '; Secure' : ''
  return `${COOKIE}=${token}; Path=/; HttpOnly; SameSite=Lax; Max-Age=${MAX_AGE_SEC}${secure}`
}

/** Re-issue a session with a fresh 7-day expiry, preserving iat (sliding renewal). */
export function renewSession(session: RematchSession): string {
  const { exp: _exp, ...rest } = session
  return encodeSession(rest)
}

export function clearSessionCookieHeader(): string {
  const secure = process.env.NODE_ENV === 'production' ? '; Secure' : ''
  return `${COOKIE}=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0${secure}`
}

export function readSessionFromRequest(req: Request): RematchSession | null {
  const cookie = req.headers.get('cookie') || ''
  const match = cookie.match(new RegExp(`(?:^|;\\s*)${COOKIE}=([^;]+)`))
  return decodeSession(match?.[1] ? decodeURIComponent(match[1]) : null)
}

export { COOKIE as SESSION_COOKIE_NAME, MAX_AGE_SEC }
