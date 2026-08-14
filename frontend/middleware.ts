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

function securityHeaders(res: NextResponse, opts?: { agentic?: boolean }) {
  const agentic = Boolean(opts?.agentic)
  res.headers.set('X-Content-Type-Options', 'nosniff')
  res.headers.set('X-Frame-Options', 'SAMEORIGIN')
  res.headers.set('Referrer-Policy', 'strict-origin-when-cross-origin')
  res.headers.set('Permissions-Policy', 'camera=(self), microphone=()')
  // Agentic arena needs chess.js CDN + remote Stockfish APIs for the recordable demo
  const scriptSrc = agentic
    ? "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://telegram.org https://cdnjs.cloudflare.com https://cdn.jsdelivr.net"
    : "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://telegram.org"
  const connectSrc = agentic
    ? "connect-src 'self' https://api.telegram.org https://chess-api.com https://stockfish.online https://cdnjs.cloudflare.com https://cdn.jsdelivr.net"
    : "connect-src 'self' https://api.telegram.org"
  res.headers.set(
    'Content-Security-Policy',
    [
      "default-src 'self'",
      scriptSrc,
      "style-src 'self' 'unsafe-inline'",
      "img-src 'self' data: blob: https:",
      connectSrc,
      "worker-src 'self' blob:",
      "child-src 'self' blob:",
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

  // Domain verification & ACME — plain files, no rewrites
  if (path.startsWith('/.well-known/')) {
    return NextResponse.next()
  }

  if (path === '/agentic/admin-dashboard.html' || path === '/agentic/admin-dashboard') {
    return redirectTo(req, '/admin')
  }
  if (path === '/agentic/aggregated_metrics.json') {
    const url = req.nextUrl.clone()
    url.pathname = '/api/agentic/admin/summary'
    return securityHeaders(NextResponse.rewrite(url))
  }

  // Agent arena demo (Stockfish CDN + remote engine APIs)
  if (path.startsWith('/agentic/')) {
    return securityHeaders(NextResponse.next(), { agentic: true })
  }

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

  // Clean builder / arena shortcuts
  if (path === '/builders' || path === '/stack' || path === '/docs/stack') {
    return redirectTo(req, '/agentic/docs.html')
  }
  if (path === '/arena') {
    return redirectTo(req, '/agentic/arena.html')
  }
  if (path === '/metrics' || path === '/agentic/metrics') {
    return redirectTo(req, '/agentic/metrics.html')
  }
  if (path === '/catalog' || path === '/agentic/catalog') {
    return redirectTo(req, '/agentic/football-catalog.html')
  }
  if (path === '/hub') {
    return redirectTo(req, '/agentic/hub.html')
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
