/**
 * Public Boardman paths (no /rematch prefix).
 * App files still live under app/rematch/*; middleware rewrites clean → internal.
 */

export const routes = {
  home: '/',
  app: '/app',
  challenge: '/app/challenge',
  match: '/app/match',
  matchCode: (code: string) => `/app/match/${encodeURIComponent(code)}`,
  matchUpload: (code: string) => `/app/match/${encodeURIComponent(code)}/upload`,
  wallet: '/app/wallet',
  leaderboard: '/leaderboard',
  getUsdc: '/get-usdc',
  minipay: '/minipay',
  /** Agentic surfaces (static under public/) */
  arena: '/agentic/arena.html',
  hub: '/agentic/hub.html',
  docs: '/agentic/docs.html',
  /** Static assets still under /rematch/ for now */
  atmosphere: (file: string) => `/rematch/atmosphere/${file}`,
  logo: '/boardman-logo.jpg',
  icon192: '/rematch/icon-192.png',
  icon512: '/brand/icon-512.png',
  manifest: '/manifest.webmanifest',
  sw: '/sw.js',
} as const

/** True when pathname is the mini-app shell */
export function isAppPath(pathname: string): boolean {
  return pathname === '/app' || pathname.startsWith('/app/')
}
