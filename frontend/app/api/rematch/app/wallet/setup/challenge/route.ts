/**
 * BFF: the one-time challenge the new passkey account signs (setup proof).
 * Bound by the backend to the profile, this link or session, the address,
 * the chain id and a ten-minute window; usable once.
 */
import { rateLimitRequest } from '@/lib/bff'
import { readJsonObject } from '@/lib/proxyAuthed'
import { ADDRESS_RE, badRequest, callerHeaders, notFound, reply, tokenQuery } from '@/lib/selfCustody/setupBff'
import { stackCall } from '@/lib/stackServer'

export const dynamic = 'force-dynamic'

export async function POST(req: Request) {
  const limited = rateLimitRequest(req, 'sc-setup-challenge', 10)
  if (limited) return limited
  const q = tokenQuery(req)
  if (q === null) return notFound()
  const body = await readJsonObject(req)
  const address = typeof body.address === 'string' ? body.address : ''
  if (!ADDRESS_RE.test(address)) return badRequest()
  return reply(
    await stackCall(`/api/self-custody/setup/challenge${q}`, {
      method: 'POST',
      headers: callerHeaders(req),
      body: JSON.stringify({ address }),
      clientReq: req,
    }),
  )
}
