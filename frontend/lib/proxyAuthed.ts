/**
 * One BFF → Boardman API proxy for the football / marketplace routes.
 *
 * - proxyAuthed: signed-in users only. Every identity field in the body is
 *   overwritten with session.profileId and X-Boardman-Caller is set, so the
 *   backend (which honours that header only with the master key) acts for
 *   the session — never for an id the browser chose.
 * - proxyAdmin: Telegram-id admins only; sent without a caller header, i.e.
 *   as the platform itself (the only principal backend admin routes accept).
 * - proxyPublic: read-only GETs.
 *
 * All three share stackCall: master key, the end user's country, an 8s
 * timeout, and fast 502/504 JSON when the backend is down.
 */
import { NextResponse } from 'next/server'
import { requireAdmin } from '@/lib/adminAuth'
import { requireSession } from '@/lib/bff'
import { stackCall, type StackResult } from '@/lib/stackServer'

export const CALLER_HEADER = 'X-Boardman-Caller'

type Method = 'GET' | 'POST' | 'PUT' | 'DELETE'

export type ProxyOpts = {
  method?: Method
  /** JSON body to forward (already parsed). Identity fields are overwritten. */
  body?: Record<string, unknown> | null
  /** Body fields that name the acting party — always set to the session profile. */
  identityFields?: string[]
  timeoutMs?: number
  /** Extra fields merged into the error body when the backend is unreachable
   *  (keeps UI shapes like `{ agents: [] }` intact). */
  offlineBody?: Record<string, unknown>
  /** Session rate limit (per IP, per minute). */
  limit?: number
}

/** Parse a JSON object body; anything else (bad JSON, arrays) → {}. */
export async function readJsonObject(req: Request): Promise<Record<string, unknown>> {
  try {
    const v = await req.json()
    return v && typeof v === 'object' && !Array.isArray(v) ? (v as Record<string, unknown>) : {}
  } catch {
    return {}
  }
}

function respond(out: StackResult, opts: ProxyOpts): NextResponse {
  if (out.ok) return NextResponse.json(out.data, { status: 200, headers: { 'Cache-Control': 'no-store' } })
  const data =
    out.data && typeof out.data === 'object' && !Array.isArray(out.data) ? out.data : { error: out.data }
  const body = data.offline && opts.offlineBody ? { ...opts.offlineBody, ...data } : data
  return NextResponse.json(body, {
    status: out.status || 502,
    headers: { 'Cache-Control': 'no-store' },
  })
}

async function forward(
  req: Request,
  path: string,
  opts: ProxyOpts,
  caller: string | null
): Promise<NextResponse> {
  const method = opts.method ?? (opts.body ? 'POST' : 'GET')
  const headers: Record<string, string> = {}
  if (caller) headers[CALLER_HEADER] = caller
  const out = await stackCall(path, {
    method,
    headers,
    body: opts.body && method !== 'GET' ? JSON.stringify(opts.body) : undefined,
    timeoutMs: opts.timeoutMs,
    clientReq: req,
  })
  return respond(out, opts)
}

/** Signed-in write (or private read) acting as the session's profile.
 *  `path` may be built from the caller (e.g. `?party_id=<session profile>`),
 *  so a private read never takes the party from the browser. */
export async function proxyAuthed(
  req: Request,
  path: string | ((caller: string) => string),
  opts: ProxyOpts = {}
): Promise<NextResponse> {
  const auth = requireSession(req, { limit: opts.limit ?? 30 })
  if ('error' in auth) return auth.error
  const caller = auth.session.profileId
  if (typeof path === 'function') path = path(caller)
  let body = opts.body ? { ...opts.body } : opts.body
  if (body) {
    for (const f of opts.identityFields ?? []) body[f] = caller
  } else if (opts.identityFields?.length && (opts.method ?? 'POST') !== 'GET') {
    body = Object.fromEntries(opts.identityFields.map((f) => [f, caller]))
  }
  return forward(req, path, { ...opts, body }, caller)
}

/** Admin-only call, made as the platform itself (no caller header). */
export async function proxyAdmin(req: Request, path: string, opts: ProxyOpts = {}): Promise<NextResponse> {
  const auth = requireAdmin(req)
  if ('error' in auth) return auth.error
  return forward(req, path, opts, null)
}

/** Public read-only GET (still keyed server-side, still on the timeout). */
export async function proxyPublic(req: Request, path: string, opts: ProxyOpts = {}): Promise<NextResponse> {
  return forward(req, path, { ...opts, method: 'GET', body: null }, null)
}
