import { NextResponse, type NextRequest } from 'next/server'
import { crossSiteRefusal } from './lib/csrf'

/**
 * Per-request logic only. Clean URLs, legacy redirects and the security
 * headers are static rules in next.config.js, so public pages (/, /v2, …)
 * are served straight from the CDN without invoking this function.
 *
 * /admin stays here: it is a static page, and Next overwrites a
 * Cache-Control set from next.config.js headers() on static pages, so the
 * no-store + noindex for the desk has to be applied at request time.
 *
 * /api: unsafe methods must come from this origin (lib/csrf.ts) — the BFF
 * authenticates with a SameSite=Lax cookie, which neither sibling
 * subdomains nor login CSRF respect.
 */
export function proxy(req: NextRequest) {
  const { pathname } = req.nextUrl
  if (pathname.startsWith('/api/')) {
    const host = req.headers.get('host') || req.nextUrl.host
    const refused = crossSiteRefusal(req.method, pathname, req.headers, host)
    if (refused) {
      return NextResponse.json(
        { ok: false, error: 'forbidden', reason: refused },
        { status: 403, headers: { 'Cache-Control': 'no-store' } }
      )
    }
    return NextResponse.next()
  }
  const res = NextResponse.next()
  res.headers.set('X-Robots-Tag', 'noindex, nofollow, noarchive')
  res.headers.set('Cache-Control', 'no-store')
  return res
}

export const config = {
  matcher: ['/admin', '/admin/:path*', '/api/:path*'],
}
