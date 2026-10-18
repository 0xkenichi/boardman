/**
 * BFF for the one-time naira top-up page (/app/naira/[token]).
 *
 * The link token from the chat is the bearer. The page collects the
 * customer KYC Paycrest requires on every naira on-ramp (full name, date of
 * birth, BVN or NIN) and the player's own refund bank account; this route
 * forwards them once to the backend, which passes them to Paycrest and keeps
 * none of the KYC. Nothing is logged here. The POST is a geo-fenced money
 * route, so the visitor's country goes along with the master key.
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

function str(v: unknown, max: number): string {
  return typeof v === 'string' ? v.trim().slice(0, max) : ''
}

export async function GET(req: Request, { params }: { params: Promise<{ token: string }> }) {
  const limited = rateLimitRequest(req, 'naira-view', 30)
  if (limited) return limited
  const token = await tokenFrom(params)
  if (!token) return NextResponse.json({ ok: false, error: 'not_found' }, { status: 404, headers: NO_STORE })
  const out = await stackCall(`/api/channels/naira/${encodeURIComponent(token)}`, {
    method: 'GET',
    headers: callerHeaders(req),
    clientReq: req,
  })
  return reply(out)
}

export async function POST(req: Request, { params }: { params: Promise<{ token: string }> }) {
  const limited = rateLimitRequest(req, 'naira-submit', 10)
  if (limited) return limited
  const token = await tokenFrom(params)
  if (!token) return NextResponse.json({ ok: false, error: 'not_found' }, { status: 404, headers: NO_STORE })
  const body = await readJsonObject(req)
  const kyc = (body.kyc && typeof body.kyc === 'object' ? body.kyc : {}) as Record<string, unknown>
  const refund = (body.refund && typeof body.refund === 'object' ? body.refund : {}) as Record<string, unknown>
  const forward = {
    kyc: {
      full_name: str(kyc.full_name, 120),
      birth_date: str(kyc.birth_date, 10),
      id_type: str(kyc.id_type, 16),
      id_number: str(kyc.id_number, 16),
      email: str(kyc.email, 120) || null,
      phone: str(kyc.phone, 20) || null,
    },
    refund: {
      institution: str(refund.institution, 16),
      account_identifier: str(refund.account_identifier, 12),
    },
  }
  const out = await stackCall(`/api/channels/naira/${encodeURIComponent(token)}`, {
    method: 'POST',
    headers: callerHeaders(req),
    body: JSON.stringify(forward),
    clientReq: req,
    timeoutMs: 30_000,
  })
  return reply(out)
}
