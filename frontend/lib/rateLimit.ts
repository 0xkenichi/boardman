/**
 * Simple in-memory rate limiter for BFF routes (per-process).
 * Production multi-instance should use Redis; this still stops abuse on a single node.
 */

type Bucket = { count: number; reset: number }

const buckets = new Map<string, Bucket>()

export function rateLimit(
  key: string,
  { limit = 30, windowMs = 60_000 }: { limit?: number; windowMs?: number } = {}
): { ok: true } | { ok: false; retryAfterSec: number } {
  const now = Date.now()
  let b = buckets.get(key)
  if (!b || now >= b.reset) {
    b = { count: 0, reset: now + windowMs }
    buckets.set(key, b)
  }
  b.count += 1
  if (b.count > limit) {
    return { ok: false, retryAfterSec: Math.max(1, Math.ceil((b.reset - now) / 1000)) }
  }
  return { ok: true }
}

/**
 * Rate-limit key for the caller's IP. Prefer headers the edge sets itself
 * (Vercel overwrites these); the first X-Forwarded-For entry is whatever the
 * client typed, so it is never trusted — at most the last hop, which the
 * nearest proxy appended.
 */
export function clientIp(req: Request): string {
  const first = (v: string | null) => v?.split(',')[0]?.trim() || ''
  const last = (v: string | null) => v?.split(',').pop()?.trim() || ''
  return (
    first(req.headers.get('x-vercel-forwarded-for')) ||
    first(req.headers.get('x-real-ip')) ||
    last(req.headers.get('x-forwarded-for')) ||
    'unknown'
  )
}
