/**
 * SIWE-lite sign-in message — built by the client before `personal_sign`,
 * re-parsed and validated by the server after recovery. No external SIWE dep.
 *
 * Format:
 *   <domain> wants you to sign in with your Ethereum account:
 *   0x<address>
 *
 *   <statement>
 *
 *   URI: https://<domain>
 *   Action: login | link
 *   Profile: <uuid>        (link only)
 *   Issued At: <ISO>
 */

export type WalletSignAction = 'login' | 'link'

export type WalletSignMessageFields = {
  domain: string
  address: string
  action: WalletSignAction
  profileId?: string
  issuedAt?: string
}

export type ParsedWalletMessage = {
  domain: string
  address: string
  action: WalletSignAction
  profileId?: string
  issuedAtMs: number
}

const HEADER_SUFFIX = ' wants you to sign in with your Ethereum account:'
const MAX_AGE_MS = 10 * 60 * 1000 // signatures older than 10 min are rejected

export function buildWalletSignMessage(m: WalletSignMessageFields): string {
  const lines = [
    `${m.domain}${HEADER_SUFFIX}`,
    m.address.toLowerCase(),
    '',
    m.action === 'link'
      ? 'Link this wallet to your Boardman profile.'
      : 'Sign in to Boardman. This signature is free and creates no transaction.',
    '',
    `URI: https://${m.domain}`,
    `Action: ${m.action}`,
  ]
  if (m.profileId) lines.push(`Profile: ${m.profileId}`)
  lines.push(`Issued At: ${m.issuedAt || new Date().toISOString()}`)
  return lines.join('\n')
}

/** Addresses we accept as the message domain (prevents cross-site phish reuse). */
export function allowedWalletDomains(): string[] {
  const host = (process.env.NEXT_PUBLIC_SITE_HOST || '').trim().toLowerCase()
  return [
    'boardman.playingsidequest.fun',
    'boardman-six.vercel.app',
    'localhost:3000',
    '127.0.0.1:3000',
    ...(host ? [host] : []),
  ]
}

export function isAllowedWalletDomain(domain: string): boolean {
  const d = (domain || '').trim().toLowerCase()
  if (!d) return false
  if (allowedWalletDomains().includes(d)) return true
  // Vercel preview deployments: <project>-<hash>-<team>-<project>.vercel.app
  if (d.endsWith('.vercel.app')) return true
  return false
}

/**
 * Parse a message produced by buildWalletSignMessage.
 * Returns null on any structural problem — never throws.
 */
export function parseWalletMessage(raw: unknown): ParsedWalletMessage | null {
  if (typeof raw !== 'string' || raw.length > 4096) return null
  const lines = raw.split('\n')
  if (lines.length < 6) return null

  const header = lines[0] || ''
  const hi = header.indexOf(HEADER_SUFFIX)
  if (hi <= 0) return null
  const domain = header.slice(0, hi).trim().toLowerCase()

  const address = (lines[1] || '').trim().toLowerCase()
  if (!/^0x[0-9a-f]{40}$/.test(address)) return null

  let action: WalletSignAction | null = null
  let profileId: string | undefined
  let issuedAtMs = 0
  for (const line of lines) {
    if (line.startsWith('Action:')) {
      const v = line.slice(7).trim()
      if (v === 'login' || v === 'link') action = v
    } else if (line.startsWith('Profile:')) {
      profileId = line.slice(8).trim() || undefined
    } else if (line.startsWith('Issued At:')) {
      const t = Date.parse(line.slice(10).trim())
      if (Number.isFinite(t)) issuedAtMs = t
    }
  }
  if (!action || !issuedAtMs) return null

  return { domain, address, action, profileId, issuedAtMs }
}

/** True when the parsed message is fresh, on an allowed domain, and matches expectations. */
export function walletMessageUsable(
  parsed: ParsedWalletMessage,
  want: { action: WalletSignAction; profileId?: string },
  nowMs = Date.now()
): boolean {
  if (parsed.action !== want.action) return false
  if (!isAllowedWalletDomain(parsed.domain)) return false
  if (Math.abs(nowMs - parsed.issuedAtMs) > MAX_AGE_MS) return false
  if (want.action === 'link' && (!parsed.profileId || parsed.profileId !== want.profileId)) {
    return false
  }
  return true
}
