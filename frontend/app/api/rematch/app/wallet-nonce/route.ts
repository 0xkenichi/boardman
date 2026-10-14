import { NextResponse } from 'next/server'
import { issueWalletNonce, walletNonceCookieHeader } from '@/lib/session'
import { rateLimitRequest } from '@/lib/bff'

export const dynamic = 'force-dynamic'

/**
 * GET — issue a single-use EIP-4361 nonce for wallet sign-in.
 * The nonce travels back in an HMAC-signed HttpOnly cookie (no server store),
 * and POST /api/rematch/app/session clears it on every wallet attempt.
 */
export async function GET(req: Request) {
  const limited = rateLimitRequest(req, 'wallet-nonce', 20)
  if (limited) return limited
  const { nonce, token, expiresAt } = issueWalletNonce()
  const res = NextResponse.json(
    { ok: true, nonce, expiresAt },
    { headers: { 'Cache-Control': 'no-store' } }
  )
  res.headers.set('Set-Cookie', walletNonceCookieHeader(token))
  return res
}
