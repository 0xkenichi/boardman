/**
 * Shared helpers for the wallet setup BFF routes (server only).
 *
 * The signed-in web session goes to the backend as X-Boardman-Caller and its
 * sign-in time (`iat`, kept across sliding renewals) as X-Boardman-Auth-Iat:
 * changing an existing wallet needs a recent sign-in.
 */
import { NextResponse } from 'next/server'
import { readSessionFromRequest } from '@/lib/session'

export const NO_STORE = { 'Cache-Control': 'no-store', 'Referrer-Policy': 'no-referrer' }
const TOKEN_RE = /^[A-Za-z0-9_-]{20,128}$/
export const ADDRESS_RE = /^0x[a-fA-F0-9]{40}$/

export function callerHeaders(req: Request): Record<string, string> {
  const session = readSessionFromRequest(req)
  if (!session?.profileId) return {}
  const out: Record<string, string> = { 'X-Boardman-Caller': session.profileId }
  if (session.iat) out['X-Boardman-Auth-Iat'] = String(session.iat)
  return out
}

/** '' (no token), '?t=…' (well-formed token) or null (malformed: 404). */
export function tokenQuery(req: Request): string | null {
  const t = new URL(req.url).searchParams.get('t')
  if (t === null) return ''
  return TOKEN_RE.test(t) ? `?t=${encodeURIComponent(t)}` : null
}

export function reply(out: { ok: boolean; status: number; data: any }) {
  const body = out.data && typeof out.data === 'object' ? out.data : { ok: false, error: 'bad_gateway' }
  return NextResponse.json(body, { status: out.status || 502, headers: NO_STORE })
}

export const notFound = () => NextResponse.json({ ok: false, error: 'not_found' }, { status: 404, headers: NO_STORE })

export const badRequest = () => NextResponse.json({ ok: false, error: 'bad_request' }, { status: 400, headers: NO_STORE })
