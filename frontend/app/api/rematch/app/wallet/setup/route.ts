/**
 * BFF for the passkey wallet setup page (/app/wallet/setup).
 *
 * Opened from a chat link (?t=<one-time token>) or by a signed-in web session
 * (its profile goes to the backend as X-Boardman-Caller). The page posts only
 * the new smart-account address and the public passkey credential id; no key
 * material ever reaches us. The backend answers 404 while self-custody is off.
 */
import { NextResponse } from 'next/server'
import { rateLimitRequest } from '@/lib/bff'
import { readJsonObject } from '@/lib/proxyAuthed'
import { readSessionFromRequest } from '@/lib/session'
import { stackCall } from '@/lib/stackServer'

export const dynamic = 'force-dynamic'

const NO_STORE = { 'Cache-Control': 'no-store', 'Referrer-Policy': 'no-referrer' }
const TOKEN_RE = /^[A-Za-z0-9_-]{20,128}$/
const ADDRESS_RE = /^0x[a-fA-F0-9]{40}$/
const CRED_RE = /^[A-Za-z0-9_\-+/=]{8,512}$/

function callerHeaders(req: Request): Record<string, string> {
  const session = readSessionFromRequest(req)
  return session?.profileId ? { 'X-Boardman-Caller': session.profileId } : {}
}

function query(req: Request): string | null {
  const t = new URL(req.url).searchParams.get('t')
  if (t === null) return ''
  return TOKEN_RE.test(t) ? `?t=${encodeURIComponent(t)}` : null
}

function reply(out: { ok: boolean; status: number; data: any }) {
  const body = out.data && typeof out.data === 'object' ? out.data : { ok: false, error: 'bad_gateway' }
  return NextResponse.json(body, { status: out.status || 502, headers: NO_STORE })
}

const notFound = () => NextResponse.json({ ok: false, error: 'not_found' }, { status: 404, headers: NO_STORE })

export async function GET(req: Request) {
  const limited = rateLimitRequest(req, 'sc-setup-view', 30)
  if (limited) return limited
  const q = query(req)
  if (q === null) return notFound()
  return reply(await stackCall(`/api/self-custody/setup${q}`, { method: 'GET', headers: callerHeaders(req), clientReq: req }))
}

export async function POST(req: Request) {
  const limited = rateLimitRequest(req, 'sc-setup', 10)
  if (limited) return limited
  const q = query(req)
  if (q === null) return notFound()
  const body = await readJsonObject(req)
  const address = typeof body.address === 'string' ? body.address : ''
  const credential_id = typeof body.credential_id === 'string' ? body.credential_id : ''
  if (!ADDRESS_RE.test(address) || !CRED_RE.test(credential_id)) {
    return NextResponse.json({ ok: false, error: 'bad_request' }, { status: 400, headers: NO_STORE })
  }
  return reply(
    await stackCall(`/api/self-custody/setup${q}`, {
      method: 'POST',
      headers: callerHeaders(req),
      body: JSON.stringify({ address, credential_id }),
      clientReq: req,
    }),
  )
}
