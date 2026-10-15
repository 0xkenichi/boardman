/**
 * BFF for the one-time withdraw page (/app/withdraw/[token]).
 *
 * The link token from the chat is the bearer; the PIN typed on the page is the
 * second factor. No session is required (WhatsApp players may never have
 * signed in on the web), but when one exists its profile is forwarded as
 * X-Boardman-Caller and the backend refuses a link that belongs to another
 * account. The backend call carries the master key and the visitor's country
 * (the confirm POST is a geo-fenced money route).
 */
import { NextResponse } from 'next/server'
import { rateLimitRequest } from '@/lib/bff'
import { readJsonObject } from '@/lib/proxyAuthed'
import { readSessionFromRequest } from '@/lib/session'
import { stackCall } from '@/lib/stackServer'

export const dynamic = 'force-dynamic'

const NO_STORE = { 'Cache-Control': 'no-store', 'Referrer-Policy': 'no-referrer' }
const TOKEN_RE = /^[A-Za-z0-9_-]{20,128}$/

function callerHeaders(req: Request): Record<string, string> {
  const session = readSessionFromRequest(req)
  return session?.profileId ? { 'X-Boardman-Caller': session.profileId } : {}
}

async function tokenFrom(params: Promise<{ token: string }>): Promise<string | null> {
  const { token } = await params
  const t = decodeURIComponent(token || '')
  return TOKEN_RE.test(t) ? t : null
}

function reply(out: { ok: boolean; status: number; data: any }) {
  const body = out.data && typeof out.data === 'object' ? out.data : { ok: false, error: 'bad_gateway' }
  return NextResponse.json(body, { status: out.status || 502, headers: NO_STORE })
}

export async function GET(req: Request, { params }: { params: Promise<{ token: string }> }) {
  const limited = rateLimitRequest(req, 'wd-view', 30)
  if (limited) return limited
  const token = await tokenFrom(params)
  if (!token) return NextResponse.json({ ok: false, error: 'not_found' }, { status: 404, headers: NO_STORE })
  const out = await stackCall(`/api/channels/withdraw/${encodeURIComponent(token)}`, {
    method: 'GET',
    headers: callerHeaders(req),
    clientReq: req,
  })
  return reply(out)
}

export async function POST(req: Request, { params }: { params: Promise<{ token: string }> }) {
  const limited = rateLimitRequest(req, 'wd-confirm', 10)
  if (limited) return limited
  const token = await tokenFrom(params)
  if (!token) return NextResponse.json({ ok: false, error: 'not_found' }, { status: 404, headers: NO_STORE })
  const body = await readJsonObject(req)
  const pin = typeof body.pin === 'string' ? body.pin.slice(0, 64) : ''
  if (!pin) return NextResponse.json({ ok: false, error: 'bad_request' }, { status: 400, headers: NO_STORE })
  const forward = {
    pin,
    pin_confirm: typeof body.pin_confirm === 'string' ? body.pin_confirm.slice(0, 64) : null,
    amount: typeof body.amount === 'string' ? body.amount.slice(0, 32) : null,
  }
  const out = await stackCall(`/api/channels/withdraw/${encodeURIComponent(token)}`, {
    method: 'POST',
    headers: callerHeaders(req),
    body: JSON.stringify(forward),
    clientReq: req,
    timeoutMs: 20_000,
  })
  return reply(out)
}
