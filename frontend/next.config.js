/**
 * Clean Boardman URLs, legacy redirects and security headers live here as
 * static routing rules, not in proxy.ts. On Vercel these are served from the
 * edge routing table, so a static page (/ → /v2) is a CDN hit with no
 * function invocation and no iad1 cold start in front of it. proxy.ts only
 * runs for the routes that still need per-request logic (/admin).
 *
 *   /              → /v2 (front door)
 *   /app/*         → /rematch/app/* (mini-app)
 *   /leaderboard   → /rematch/leaderboard, likewise get-usdc, minipay, contact
 *   /rematch/*     → 308 to the clean path (except the static icon / atmosphere
 *                    / manifest / sw assets that still live under /rematch)
 */

const isProd = process.env.NODE_ENV === 'production'

function csp({ agentic, passkey = false }) {
  // Agentic arena needs chess.js CDN + remote Stockfish APIs for the recordable demo
  const scriptSrc = agentic
    ? "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://telegram.org https://cdnjs.cloudflare.com https://cdn.jsdelivr.net"
    : "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://telegram.org"
  // Passkey wallet pages talk to Circle's modular-wallet RPC (passkey RP,
  // bundler, chain reads) straight from the browser.
  const connectSrc = agentic
    ? "connect-src 'self' https://api.telegram.org https://chess-api.com https://stockfish.online https://cdnjs.cloudflare.com https://cdn.jsdelivr.net"
    : passkey
      ? "connect-src 'self' https://api.telegram.org https://modular-sdk.circle.com"
      : "connect-src 'self' https://api.telegram.org"
  return [
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
}

const securityHeaders = [
  { key: 'X-Content-Type-Options', value: 'nosniff' },
  { key: 'X-Frame-Options', value: 'SAMEORIGIN' },
  { key: 'Referrer-Policy', value: 'strict-origin-when-cross-origin' },
  { key: 'Permissions-Policy', value: 'camera=(self), microphone=()' },
  { key: 'Content-Security-Policy', value: csp({ agentic: false }) },
  ...(isProd
    ? [{ key: 'Strict-Transport-Security', value: 'max-age=63072000; includeSubDomains; preload' }]
    : []),
]

// Static assets that stay under /rematch (everything else there redirects).
// Mirrors the old proxy matcher, which also skipped image files entirely.
const REMATCH_KEEP =
  '(?!icon-|atmosphere/|atmosphere$|manifest\\.webmanifest|sw\\.js|.*\\.(?:svg|png|jpg|jpeg|gif|webp)$)'

const permanent = (source, destination) => ({ source, destination, permanent: true })

// Passkey wallet SDK: until `npm i @circle-fin/modular-wallets-core viem`
// has run, alias the imports to a stub that throws, so the build passes and
// the passkey pages say "not available yet". Installed → real packages.
const path = require('path')
function resolvable(name) {
  try {
    require.resolve(name)
    return true
  } catch {
    return false
  }
}
const PASSKEY_SDK = ['@circle-fin/modular-wallets-core', 'viem', 'viem/account-abstraction']
const passkeyStubs = PASSKEY_SDK.filter((m) => !resolvable(m))

/** @type {import('next').NextConfig} */
const nextConfig = {
  turbopack: {
    resolveAlias: Object.fromEntries(passkeyStubs.map((m) => [m, './lib/selfCustody/sdkMissing.ts'])),
  },
  webpack(config) {
    const stub = path.join(__dirname, 'lib/selfCustody/sdkMissing.ts')
    for (const m of passkeyStubs) config.resolve.alias[`${m}$`] = stub
    return config
  },
  reactStrictMode: true,
  // Allow both loopback hosts for local dev resources (HMR, fonts, chunks).
  allowedDevOrigins: ['localhost', '127.0.0.1'],
  images: {
    unoptimized: true,
  },
  async headers() {
    return [
      // Everything except Next's hashed build output (/.well-known is plain files).
      {
        source: '/:path((?!_next/static|_next/image|\\.well-known/).*)',
        headers: securityHeaders,
      },
      // Later entries win for the same key: the agentic demo pages get the wider CSP.
      {
        source: '/agentic/:path*',
        headers: [{ key: 'Content-Security-Policy', value: csp({ agentic: true }) }],
      },
      // BFF answers are per-session (or carry one-time tokens): never stored
      // by a browser or shared cache. Was `public, max-age=0` on /api/rematch.
      ...['/api/agentic/:path*', '/api/rematch/:path*'].map((source) => ({
        source,
        headers: [{ key: 'Cache-Control', value: 'no-store' }],
      })),
      // One-time withdraw / naira link pages: the token is in the path.
      ...['/app/withdraw/:path*', '/app/naira/:path*'].map((source) => ({
        source,
        headers: [
          { key: 'Cache-Control', value: 'no-store' },
          { key: 'Referrer-Policy', value: 'no-referrer' },
        ],
      })),
      // Self-custody passkey pages: Circle RPC allowed, nothing cached or leaked.
      ...['/app/wallet/setup', '/app/approve/:path*'].map((source) => ({
        source,
        headers: [
          { key: 'Content-Security-Policy', value: csp({ agentic: false, passkey: true }) },
          { key: 'Cache-Control', value: 'no-store' },
          { key: 'Referrer-Policy', value: 'no-referrer' },
        ],
      })),
    ]
  },
  async redirects() {
    return [
      // Retired static agentic pages → their React homes
      permanent('/agentic/admin-dashboard.html', '/admin'),
      permanent('/agentic/admin-dashboard', '/admin'),
      permanent('/agentic/aggregated_metrics.json', '/admin'),
      permanent('/agentic/match-proofs.json', '/admin'),
      permanent('/agentic/metrics.html', '/admin'),
      permanent('/agentic/metrics', '/admin'),
      permanent('/metrics', '/admin'),
      permanent('/agentic/football-managers.html', '/football'),
      permanent('/agentic/football-managers', '/football'),
      permanent('/agentic/hub.html', '/games'),
      permanent('/agentic/hub', '/games'),
      permanent('/agentic/docs.html', '/builders'),
      permanent('/agentic/docs', '/builders'),
      permanent('/agentic/arena.html', '/arena'),
      permanent('/agentic/arena', '/arena'),
      // Clean builder / arena shortcuts
      permanent('/stack', '/builders'),
      permanent('/docs/stack', '/builders'),
      permanent('/docs', '/builders'),
      permanent('/hub', '/games'),
      permanent('/catalog', '/agentic/football-catalog.html'),
      permanent('/agentic/catalog', '/agentic/football-catalog.html'),
      // Legacy /rematch → clean public URLs
      permanent('/rematch', '/'),
      permanent(`/rematch/:path(${REMATCH_KEEP}.+)`, '/:path'),
    ]
  },
  async rewrites() {
    // beforeFiles = same position the proxy rewrite had (ahead of pages/public).
    const toRematch = (source) => ({ source, destination: `/rematch${source}` })
    return {
      beforeFiles: [
        { source: '/', destination: '/v2' },
        { source: '/app', destination: '/rematch/app' },
        { source: '/app/:path*', destination: '/rematch/app/:path*' },
        toRematch('/how-it-works'),
        toRematch('/questions'),
        toRematch('/about'),
        toRematch('/games'),
        toRematch('/builders'),
        toRematch('/arena'),
        // Legal pages (Meta app review needs these exact public URLs)
        toRematch('/terms'),
        toRematch('/privacy'),
        toRematch('/data-deletion'),
        { source: '/leaderboard/:path*', destination: '/rematch/leaderboard/:path*' },
        { source: '/get-usdc/:path*', destination: '/rematch/get-usdc/:path*' },
        { source: '/minipay/:path*', destination: '/rematch/minipay/:path*' },
        { source: '/contact/:path*', destination: '/rematch/contact/:path*' },
        // Public root assets: serve boardman SW/manifest at /
        { source: '/sw.js', destination: '/rematch/sw.js' },
        { source: '/manifest.webmanifest', destination: '/rematch/manifest.webmanifest' },
      ],
    }
  },
}

module.exports = nextConfig
