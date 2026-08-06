import { NextResponse } from 'next/server'
import type { NextRequest } from 'next/server'

/**
 * Clean Boardman URLs:
 *   /              → marketing (internal /rematch)
 *   /app/*         → mini-app (internal /rematch/app/*)
 *   /leaderboard   → /rematch/leaderboard
 *   /get-usdc      → /rematch/get-usdc
 *   /minipay       → /rematch/minipay
 *
 * Legacy /rematch/* redirects to clean paths (except static /rematch/icon|atmosphere|sw|manifest).
 */

const STATIC_PREFIXES = [
  '/rematch/icon-',
  '/rematch/atmosphere/',
  '/rematch/manifest.webmanifest',
  '/rematch/sw.js',
]

function isRematchStatic(path: string): boolean {
  return STATIC_PREFIXES.some((p) => path.startsWith(p) || path === p.replace(/\/$/, ''))
}

function securityHeaders(res: NextResponse) {
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
    res.headers.set(
      'Strict-Transport-Security',
      'max-age=63072000; includeSubDomains; preload'
    )
  }
  return res
}

function rewriteTo(req: NextRequest, internalPath: string) {
  const url = req.nextUrl.clone()
  url.pathname = internalPath
  return securityHeaders(NextResponse.rewrite(url))
}

function redirectTo(req: NextRequest, cleanPath: string) {
  const url = req.nextUrl.clone()
  url.pathname = cleanPath
  return securityHeaders(NextResponse.redirect(url, 308))
}

export function middleware(req: NextRequest) {
  const path = req.nextUrl.pathname

  // API stays as-is
  if (path.startsWith('/api/')) {
    return securityHeaders(NextResponse.next())
  }

  // Static rematch assets (icons, atmosphere, old SW)
  if (isRematchStatic(path)) {
    return securityHeaders(NextResponse.next())
  }

  // Legacy /rematch → clean public URLs
  if (path === '/rematch' || path === '/rematch/') {
    return redirectTo(req, '/')
  }
  if (path.startsWith('/rematch/')) {
    const rest = path.slice('/rematch'.length) || '/'
    // e.g. /rematch/app → /app
    return redirectTo(req, rest.startsWith('/') ? rest : `/${rest}`)
  }

  // Clean → internal app/rematch/*
  if (path === '/' || path === '') {
    return rewriteTo(req, '/rematch')
  }
  if (path === '/app' || path.startsWith('/app/')) {
    return rewriteTo(req, `/rematch${path}`)
  }
  if (path === '/leaderboard' || path.startsWith('/leaderboard/')) {
    return rewriteTo(req, `/rematch${path}`)
  }
  if (path === '/get-usdc' || path.startsWith('/get-usdc/')) {
    return rewriteTo(req, `/rematch${path}`)
  }
  if (path === '/minipay' || path.startsWith('/minipay/')) {
    return rewriteTo(req, `/rematch${path}`)
  }

  // Public root assets: serve boardman SW/manifest at /
  if (path === '/sw.js') {
    return rewriteTo(req, '/rematch/sw.js')
  }
  if (path === '/manifest.webmanifest') {
    return rewriteTo(req, '/rematch/manifest.webmanifest')
  }

  return securityHeaders(NextResponse.next())
}

export const config = {
  matcher: [
    /*
     * Match all paths except Next internals and common static files in /_next
     */
    '/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp)$).*)',
  ],
}
