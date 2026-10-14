import { NextResponse } from 'next/server'

/**
 * Per-request logic only. Clean URLs, legacy redirects and the security
 * headers are static rules in next.config.js, so public pages (/, /v2, …)
 * are served straight from the CDN without invoking this function.
 *
 * /admin stays here: it is a static page, and Next overwrites a
 * Cache-Control set from next.config.js headers() on static pages, so the
 * no-store + noindex for the desk has to be applied at request time.
 */
export function proxy() {
  const res = NextResponse.next()
  res.headers.set('X-Robots-Tag', 'noindex, nofollow, noarchive')
  res.headers.set('Cache-Control', 'no-store')
  return res
}

export const config = {
  matcher: ['/admin', '/admin/:path*'],
}
