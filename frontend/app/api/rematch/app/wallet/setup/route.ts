/**
 * BFF for the passkey wallet setup page (/app/wallet/setup).
 *
 * Opened from a chat link (?t=<one-time token>) or by a signed-in web session
 * (see lib/selfCustody/setupBff.ts for the caller headers). The page posts
 * the new smart-account address, the public passkey credential id and the
 * account's signature over the backend's one-time challenge (./challenge);
 * the backend verifies it on chain (ERC-1271 / ERC-6492) and then asks the
 * player to confirm in their chat. No key material ever reaches us. The
 * backend answers 404 while self-custody is off.
 */
import { rateLimitRequest } from '@/lib/bff'
import { readJsonObject } from '@/lib/proxyAuthed'
import { ADDRESS_RE, badRequest, callerHeaders, notFound, reply, tokenQuery } from '@/lib/selfCustody/setupBff'
import { stackCall } from '@/lib/stackServer'

export const dynamic = 'force-dynamic'

const CRED_RE = /^[A-Za-z0-9_\-+/=]{8,512}$/
const CHALLENGE_RE = /^scw_[0-9a-f]{24}$/
// 65 bytes (plain ECDSA) up to 8 KB (ERC-6492 wrapper + WebAuthn assertion).
const SIG_RE = /^0x(?:[0-9a-fA-F]{2}){65,8192}$/

export async function GET(req: Request) {
  const limited = rateLimitRequest(req, 'sc-setup-view', 30)
  if (limited) return limited
  const q = tokenQuery(req)
  if (q === null) return notFound()
  return reply(await stackCall(`/api/self-custody/setup${q}`, { method: 'GET', headers: callerHeaders(req), clientReq: req }))
}

export async function POST(req: Request) {
  const limited = rateLimitRequest(req, 'sc-setup', 10)
  if (limited) return limited
  const q = tokenQuery(req)
  if (q === null) return notFound()
  const body = await readJsonObject(req)
  const str = (k: string) => (typeof body[k] === 'string' ? (body[k] as string) : '')
  const address = str('address')
  const credential_id = str('credential_id')
  const challenge_id = str('challenge_id')
  const signature = str('signature')
  if (!ADDRESS_RE.test(address) || !CRED_RE.test(credential_id) || !CHALLENGE_RE.test(challenge_id) || !SIG_RE.test(signature)) {
    return badRequest()
  }
  return reply(
    await stackCall(`/api/self-custody/setup${q}`, {
      method: 'POST',
      headers: callerHeaders(req),
      body: JSON.stringify({ address, credential_id, challenge_id, signature }),
      clientReq: req,
    }),
  )
}
