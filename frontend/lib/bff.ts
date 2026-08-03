import { NextResponse } from 'next/server'
import { readSessionFromRequest, type RematchSession } from '@/lib/session'
import { clientIp, rateLimit } from '@/lib/rateLimit'

export function requireSession(
  req: Request,
  opts: { limit?: number; windowMs?: number } = {}
): { session: RematchSession } | { error: NextResponse } {
  const ip = clientIp(req)
  const rl = rateLimit(`sess:${ip}`, {
    limit: opts.limit ?? 60,
    windowMs: opts.windowMs ?? 60_000,
  })
  if (!rl.ok) {
    return {
      error: NextResponse.json(
        { ok: false, error: 'rate_limited' },
        { status: 429, headers: { 'Retry-After': String(rl.retryAfterSec) } }
      ),
    }
  }
  const session = readSessionFromRequest(req)
  if (!session) {
    return {
      error: NextResponse.json({ ok: false, error: 'unauthorized' }, { status: 401 }),
    }
  }
  return { session }
}

export function rateLimitRequest(
  req: Request,
  key: string,
  limit = 20
): NextResponse | null {
  const ip = clientIp(req)
  const rl = rateLimit(`${key}:${ip}`, { limit, windowMs: 60_000 })
  if (!rl.ok) {
    return NextResponse.json(
      { ok: false, error: 'rate_limited' },
      { status: 429, headers: { 'Retry-After': String(rl.retryAfterSec) } }
    )
  }
  return null
}
