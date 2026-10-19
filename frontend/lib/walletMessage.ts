/**
 * EIP-4361 (Sign-In with Ethereum) message — built by the client before
 * `personal_sign`, re-parsed and validated by the server after recovery.
 * No external SIWE dep; pure functions so they can be unit-tested.
 *
 * Format (strict — every line is checked, unknown lines are rejected):
 *   <domain> wants you to sign in with your Ethereum account:
 *   <EIP-55 address>
 *
 *   <statement>
 *
 *   URI: <origin>
 *   Version: 1
 *   Chain ID: <int>
 *   Nonce: <server-issued, single-use>
 *   Issued At: <ISO-8601>
 *   Resources:
 *   - urn:boardman:action:<login|link>
 *   - urn:boardman:profile:<uuid>     (link only)
 */
import { keccak_256 } from '@noble/hashes/sha3.js'

export type WalletSignAction = 'login' | 'link'

export type WalletSignMessageFields = {
  domain: string
  address: string
  action: WalletSignAction
  chainId: number
  nonce: string
  uri?: string
  profileId?: string
  issuedAt?: string
}

export type ParsedWalletMessage = {
  domain: string
  /** lowercase 0x address */
  address: string
  action: WalletSignAction
  profileId?: string
  uri: string
  chainId: number
  nonce: string
  issuedAtMs: number
}

type Env = Record<string, string | undefined>

const HEADER_SUFFIX = ' wants you to sign in with your Ethereum account:'
const ACTION_URN = 'urn:boardman:action:'
const PROFILE_URN = 'urn:boardman:profile:'
export const MAX_AGE_MS = 10 * 60 * 1000 // signatures older than 10 min are rejected
export const MAX_FUTURE_SKEW_MS = 60 * 1000 // clock skew tolerance for Issued At
const STATEMENTS: Record<WalletSignAction, string> = {
  login: 'Sign in to Boardman. This signature is free and creates no transaction.',
  link: 'Link this wallet to your Boardman profile.',
}
/** Arc testnet, Celo, Celo Alfajores, Ethereum, Base — override with BOARDMAN_SIWE_CHAIN_IDS. */
const DEFAULT_CHAIN_IDS = [5042002, 42220, 44787, 1, 8453]

function hex(bytes: Uint8Array): string {
  let s = ''
  for (const b of bytes) s += b.toString(16).padStart(2, '0')
  return s
}

/** EIP-55 mixed-case checksum encoding. */
export function toChecksumAddress(address: string): string {
  const a = address.toLowerCase().replace(/^0x/, '')
  const h = hex(keccak_256(new TextEncoder().encode(a)))
  let out = '0x'
  for (let i = 0; i < a.length; i++) {
    out += parseInt(h[i], 16) >= 8 ? a[i].toUpperCase() : a[i]
  }
  return out
}

export function buildWalletSignMessage(m: WalletSignMessageFields): string {
  const lines = [
    `${m.domain}${HEADER_SUFFIX}`,
    toChecksumAddress(m.address),
    '',
    STATEMENTS[m.action],
    '',
    `URI: ${m.uri || `https://${m.domain}`}`,
    'Version: 1',
    `Chain ID: ${m.chainId}`,
    `Nonce: ${m.nonce}`,
    `Issued At: ${m.issuedAt || new Date().toISOString()}`,
    'Resources:',
    `- ${ACTION_URN}${m.action}`,
  ]
  if (m.profileId) lines.push(`- ${PROFILE_URN}${m.profileId}`)
  return lines.join('\n')
}

/**
 * Parse a message produced by buildWalletSignMessage.
 * Returns null on any structural problem — never throws.
 */
export function parseWalletMessage(raw: unknown): ParsedWalletMessage | null {
  if (typeof raw !== 'string' || raw.length > 4096 || raw.includes('\r')) return null
  const lines = raw.split('\n')
  if (lines.length < 12 || lines.length > 13) return null

  const header = lines[0]
  if (!header.endsWith(HEADER_SUFFIX)) return null
  const domain = header.slice(0, -HEADER_SUFFIX.length)
  if (!/^[a-z0-9.-]+(:\d{1,5})?$/.test(domain)) return null

  const addrRaw = lines[1]
  if (!/^0x[0-9a-fA-F]{40}$/.test(addrRaw)) return null
  // Mixed case must be a valid EIP-55 checksum; all-lowercase is tolerated.
  if (addrRaw !== addrRaw.toLowerCase() && addrRaw !== toChecksumAddress(addrRaw)) return null
  const address = addrRaw.toLowerCase()

  if (lines[2] !== '' || lines[4] !== '') return null
  const statement = lines[3]

  const field = (i: number, key: string): string | null =>
    lines[i].startsWith(`${key}: `) ? lines[i].slice(key.length + 2) : null
  const uri = field(5, 'URI')
  const version = field(6, 'Version')
  const chainRaw = field(7, 'Chain ID')
  const nonce = field(8, 'Nonce')
  const issuedRaw = field(9, 'Issued At')
  if (!uri || version !== '1' || !chainRaw || !nonce || !issuedRaw) return null
  if (lines[10] !== 'Resources:') return null

  let uriHost = ''
  try {
    const u = new URL(uri)
    if (u.protocol !== 'https:' && u.protocol !== 'http:') return null
    uriHost = u.host
  } catch {
    return null
  }
  if (uriHost !== domain) return null

  if (!/^[1-9]\d{0,15}$/.test(chainRaw)) return null
  const chainId = Number(chainRaw)
  if (!/^[A-Za-z0-9]{8,128}$/.test(nonce)) return null
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})$/.test(issuedRaw)) return null
  const issuedAtMs = Date.parse(issuedRaw)
  if (!Number.isFinite(issuedAtMs)) return null

  const actionLine = lines[11]
  if (!actionLine.startsWith(`- ${ACTION_URN}`)) return null
  const action = actionLine.slice(ACTION_URN.length + 2)
  if (action !== 'login' && action !== 'link') return null
  if (statement !== STATEMENTS[action]) return null

  let profileId: string | undefined
  if (lines.length === 13) {
    if (!lines[12].startsWith(`- ${PROFILE_URN}`)) return null
    profileId = lines[12].slice(PROFILE_URN.length + 2)
    if (!/^[A-Za-z0-9-]{1,64}$/.test(profileId)) return null
  }

  return { domain, address, action, profileId, uri, chainId, nonce, issuedAtMs }
}

/** NODE_ENV or VERCEL_ENV says production. */
export function isProductionEnv(env: Env = process.env): boolean {
  return env.NODE_ENV === 'production' || env.VERCEL_ENV === 'production'
}

/** Exact hosts (host[:port]) allowed as the sign-in domain, from BOARDMAN_SITE_HOSTS. */
export function siteHostAllowlist(env: Env = process.env): string[] {
  return (env.BOARDMAN_SITE_HOSTS || '')
    .split(/[,\s]+/)
    .map((s) => s.trim().toLowerCase())
    .filter((s) => s && !s.includes('*'))
}

function isLocalDevHost(host: string): boolean {
  return /^(localhost|127\.0\.0\.1|\[::1\])(:\d{1,5})?$/.test(host)
}

/** Exact allowlist match. No wildcards; localhost only outside production. */
export function isAllowedSiteHost(host: string, env: Env = process.env): boolean {
  const h = (host || '').trim().toLowerCase()
  if (!h) return false
  if (siteHostAllowlist(env).includes(h)) return true
  return !isProductionEnv(env) && isLocalDevHost(h)
}

export function allowedChainIds(env: Env = process.env): number[] {
  const raw = (env.BOARDMAN_SIWE_CHAIN_IDS || '').trim()
  if (!raw) return DEFAULT_CHAIN_IDS
  return raw
    .split(/[,\s]+/)
    .map((s) => Number(s))
    .filter((n) => Number.isSafeInteger(n) && n > 0)
}

export type WalletMessageExpectation = {
  action: WalletSignAction
  profileId?: string
  /** The request Host header — the message domain must equal it. */
  host: string
  /** The nonce from the server's signed, single-use nonce cookie. */
  nonce: string | null
}

/**
 * Validate a parsed message against the request. Returns null when usable,
 * otherwise a short reason code.
 */
export function walletMessageProblem(
  parsed: ParsedWalletMessage,
  want: WalletMessageExpectation,
  nowMs = Date.now(),
  env: Env = process.env
): string | null {
  if (parsed.action !== want.action) return 'action_mismatch'
  const host = (want.host || '').trim().toLowerCase()
  if (!host || parsed.domain !== host) return 'domain_mismatch'
  if (!isAllowedSiteHost(host, env)) return 'domain_not_allowed'
  if (isProductionEnv(env) && !parsed.uri.startsWith('https://')) return 'insecure_uri'
  if (!allowedChainIds(env).includes(parsed.chainId)) return 'chain_not_allowed'
  if (!want.nonce || parsed.nonce !== want.nonce) return 'nonce_mismatch'
  if (parsed.issuedAtMs - nowMs > MAX_FUTURE_SKEW_MS) return 'issued_in_future'
  if (nowMs - parsed.issuedAtMs > MAX_AGE_MS) return 'expired'
  if (want.action === 'link') {
    if (!parsed.profileId || parsed.profileId !== want.profileId) return 'profile_mismatch'
  } else if (parsed.profileId) {
    return 'profile_mismatch'
  }
  return null
}

/** The only profile column wallet sign-in trusts (written after a signed link). */
export const WALLET_LOGIN_COLUMN = 'linked_wallet'

/**
 * PostgREST query for the profile(s) a proven wallet signs in to. limit=2 so
 * the caller can refuse a wallet that two profiles claim.
 */
export function walletLoginQuery(address: string): string {
  const addr = (address || '').trim().toLowerCase()
  if (!/^0x[0-9a-f]{40}$/.test(addr)) throw new Error('bad wallet address')
  const q = new URLSearchParams()
  q.set('select', 'id,telegram_id,gaming_tag,display_name')
  q.set(WALLET_LOGIN_COLUMN, `eq.${addr}`)
  q.set('limit', '2')
  return q.toString()
}
