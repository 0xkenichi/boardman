import { NextResponse } from 'next/server'
import type { NextRequest } from 'next/server'

/**
 * Security headers for Rematch web surfaces.
 */
export function middleware(req: NextRequest) {
  const res = NextResponse.next()
  const path = req.nextUrl.pathname

  if (!path.startsWith('/rematch') && !path.startsWith('/api/rematch')) {
    return res
  }

  res.headers.set('X-Content-Type-Options', 'nosniff')
  res.headers.set('X-Frame-Options', 'SAMEORIGIN')
  res.headers.set('Referrer-Policy', 'strict-origin-when-cross-origin')
  res.headers.set('Permissions-Policy', 'camera=(self), microphone=()')
  res.headers.set(
    'Content-Security-Policy',
    [
      "default-src 'self'",
      "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://telegram.org",
      "style-src 'self' 'unsafe-inline'",
      "img-src 'self' data: blob: https:",
      "connect-src 'self' https://api.telegram.org",
      "frame-src https://oauth.telegram.org https://telegram.org",
      "base-uri 'self'",
      "form-action 'self'",
    ].join('; ')
  )
  if (process.env.NODE_ENV === 'production') {
    res.headers.set('Strict-Transport-Security', 'max-age=63072000; includeSubDomains; preload')
  }
  return res
}

export const config = {
  matcher: ['/rematch/:path*', '/api/rematch/:path*'],
}
