/**
 * BFF for the one-time passkey approve page (/app/approve/[token]).
 *
 * GET returns exactly what the player is asked to sign (the prepared calls).
 * POST reports the UserOperation the player's passkey already sent: the
 * backend claims the link once and then believes only the chain (the escrow's
 * own event, or the USDC transfer). No session is required; when one exists
 * the backend refuses a link that belongs to another account.
 */
import { NextResponse } from 'next/server'
import { rateLimitRequest } from '@/lib/bff'
import { readJsonObject } from '@/lib/proxyAuthed'
import { readSessionFromRequest } from '@/lib/session'
import { stackCall } from '@/lib/stackServer'

export const dynamic = 'force-dynamic'

const NO_STORE = { 'Cache-Control': 'no-store', 'Referrer-Policy': 'no-referrer' }
const TOKEN_RE = /^[A-Za-z0-9_-]{20,128}$/
const HASH_RE = /^0x[0-9a-fA-F]{64}$/

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

const notFound = () => NextResponse.json({ ok: false, error: 'not_found' }, { status: 404, headers: NO_STORE })

export async function GET(req: Request, { params }: { params: Promise<{ token: string }> }) {
  const limited = rateLimitRequest(req, 'sc-approve-view', 30)
  if (limited) return limited
  const token = await tokenFrom(params)
  if (!token) return notFound()
  return reply(
    await stackCall(`/api/self-custody/approve/${encodeURIComponent(token)}`, {
      method: 'GET',
      headers: callerHeaders(req),
      clientReq: req,
    }),
  )
}

export async function POST(req: Request, { params }: { params: Promise<{ token: string }> }) {
  const limited = rateLimitRequest(req, 'sc-approve', 10)
  if (limited) return limited
  const token = await tokenFrom(params)
  if (!token) return notFound()
  const body = await readJsonObject(req)
  const tx_hash = typeof body.tx_hash === 'string' ? body.tx_hash : ''
  const user_op_hash = typeof body.user_op_hash === 'string' && HASH_RE.test(body.user_op_hash) ? body.user_op_hash : null
  if (!HASH_RE.test(tx_hash)) {
    return NextResponse.json({ ok: false, error: 'bad_request' }, { status: 400, headers: NO_STORE })
  }
  const forward = {
    tx_hash,
    user_op_hash,
    amount: typeof body.amount === 'string' ? body.amount.slice(0, 32) : '',
    challenge_id: typeof body.challenge_id === 'string' ? body.challenge_id.slice(0, 64) : null,
  }
  return reply(
    await stackCall(`/api/self-custody/approve/${encodeURIComponent(token)}`, {
      method: 'POST',
      headers: callerHeaders(req),
      body: JSON.stringify(forward),
      clientReq: req,
      timeoutMs: 20_000,
    }),
  )
}
