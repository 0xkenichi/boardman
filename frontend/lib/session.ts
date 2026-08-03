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
}

const COOKIE = 'rematch_session'
const MAX_AGE_SEC = 60 * 60 * 24 * 7 // 7 days

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

export function encodeSession(session: Omit<RematchSession, 'exp'> & { exp?: number }): string {
  const full: RematchSession = {
    ...session,
    exp: session.exp ?? Math.floor(Date.now() / 1000) + MAX_AGE_SEC,
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
    if (!data.profileId || !data.exp || data.exp < Math.floor(Date.now() / 1000)) return null
    return data
  } catch {
    return null
  }
}

export function sessionCookieHeader(token: string): string {
  const secure = process.env.NODE_ENV === 'production' ? '; Secure' : ''
  return `${COOKIE}=${token}; Path=/; HttpOnly; SameSite=Lax; Max-Age=${MAX_AGE_SEC}${secure}`
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
