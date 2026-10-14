/**
 * Server-only client for the Boardman gaming API (never ship keys to the browser).
 *
 * Preferred env (Boardman brand):
 *   BOARDMAN_API_URL
 *   BOARDMAN_API_KEY
 *
 * Still accepted (rename later when convenient):
 *   REMATCH_API_URL / REMATCH_API_KEY
 *   STACK_API_URL / STACK_API_KEY
 *   REMATCH_API_BASE
 */

const REMATCH_API_URL = (
  process.env.BOARDMAN_API_URL ||
  process.env.REMATCH_API_URL ||
  process.env.STACK_API_URL ||
  process.env.REMATCH_API_BASE ||
  ''
).replace(/\/$/, '')

const REMATCH_API_KEY =
  process.env.BOARDMAN_API_KEY ||
  process.env.REMATCH_API_KEY ||
  process.env.STACK_API_KEY ||
  ''

export function rematchApiConfigured(): boolean {
  return Boolean(REMATCH_API_URL && REMATCH_API_KEY)
}

/** Alias — same as rematchApiConfigured */
export function boardmanApiConfigured(): boolean {
  return rematchApiConfigured()
}

/** @deprecated use rematchApiConfigured */
export function stackConfigured(): boolean {
  return rematchApiConfigured()
}

/** Default ceiling on any backend call. Production hangs past 30s otherwise. */
export const DEFAULT_STACK_TIMEOUT_MS = 8000

/** Header the backend geo-fence trusts (only alongside the master key). */
export const CLIENT_COUNTRY_HEADER = 'x-boardman-client-country'

export type StackResult = { ok: boolean; status: number; data: any }

export type StackInit = RequestInit & {
  /** Abort the backend call after this many ms (default 8000). */
  timeoutMs?: number
  /** The incoming end-user request — its Vercel country is forwarded. */
  clientReq?: Request | null
  /** Or the end user's ISO country directly. */
  clientCountry?: string | null
}

/** End user's ISO-3166 alpha-2 country from Vercel's edge header ('' if absent/odd). */
export function clientCountry(req?: Request | null): string {
  const raw = (req?.headers.get('x-vercel-ip-country') || '').trim().toUpperCase()
  return /^[A-Z]{2}$/.test(raw) ? raw : ''
}

function localStackBase(): string {
  return (REMATCH_API_URL || 'http://127.0.0.1:8000').replace(/\/$/, '')
}

async function backendFetch(url: string, key: string, init: StackInit): Promise<StackResult> {
  const { timeoutMs, clientReq, clientCountry: country, signal: outer, ...rest } = init
  const headers = new Headers(rest.headers || {})
  if (key) {
    // On-brand header + legacy alias for older API processes
    headers.set('X-Rematch-Key', key)
    headers.set('X-Stack-Key', key)
  }
  if (!headers.has('Content-Type') && rest.body && !(rest.body instanceof FormData)) {
    headers.set('Content-Type', 'application/json')
  }
  // only ever the edge-derived country, never a value a caller smuggled in
  headers.delete(CLIENT_COUNTRY_HEADER)
  const cc = (country || '').trim().toUpperCase() || clientCountry(clientReq)
  if (/^[A-Z]{2}$/.test(cc)) headers.set(CLIENT_COUNTRY_HEADER, cc)

  const ms = Math.max(1, timeoutMs ?? DEFAULT_STACK_TIMEOUT_MS)
  const ctl = new AbortController()
  let timedOut = false
  const timer = setTimeout(() => {
    timedOut = true
    ctl.abort()
  }, ms)
  const onOuter = () => ctl.abort()
  if (outer) {
    if (outer.aborted) ctl.abort()
    else outer.addEventListener('abort', onOuter, { once: true })
  }
  try {
    const res = await fetch(url, { ...rest, headers, cache: 'no-store', signal: ctl.signal })
    const text = await res.text()
    let data: any = null
    try {
      data = text ? JSON.parse(text) : null
    } catch {
      data = { raw: text }
    }
    return { ok: res.ok, status: res.status, data }
  } catch (e: any) {
    if (timedOut || e?.name === 'AbortError' || e?.name === 'TimeoutError') {
      return {
        ok: false,
        status: 504,
        data: {
          ok: false,
          success: false,
          offline: true,
          error: `House API did not answer within ${Math.round(ms / 1000)}s — the Boardman backend looks offline.`,
        },
      }
    }
    const raw = String(e?.message || e || '')
    const cause = String(e?.cause?.code || e?.cause?.message || '')
    const offline =
      /fetch failed|ECONNREFUSED|ENOTFOUND|EAI_AGAIN|network|certificate/i.test(raw + ' ' + cause)
    return {
      ok: false,
      status: 502,
      data: {
        ok: false,
        success: false,
        offline: true,
        error: offline
          ? 'House API is offline. Play match needs the Boardman API running (not just Vercel).'
          : raw || 'house_unreachable',
        // ops: underlying socket/DNS reason (e.g. ECONNREFUSED, ENOTFOUND, CERT errors)
        detail: [raw, cause].filter(Boolean).join(' | ') || undefined,
      },
    }
  } finally {
    clearTimeout(timer)
    outer?.removeEventListener('abort', onOuter)
  }
}

export async function rematchApiFetch(path: string, init: StackInit = {}): Promise<StackResult> {
  const base = REMATCH_API_URL
  const key = REMATCH_API_KEY
  if (!base || !key) {
    return { ok: false, status: 503, data: { error: 'rematch_api_not_configured', demo: true } }
  }
  const url = path.startsWith('http') ? path : `${base}${path.startsWith('/') ? '' : '/'}${path}`
  return backendFetch(url, key, init)
}

/**
 * The configured Boardman API or — local dev without a URL+key pair — the
 * stack on 127.0.0.1:8000 (key sent when one is set). Same timeout + offline
 * mapping either way. Replaces the per-route localStackBase()/stackCall copies.
 */
export async function stackCall(path: string, init: StackInit = {}): Promise<StackResult> {
  if (rematchApiConfigured()) return rematchApiFetch(path, init)
  return backendFetch(`${localStackBase()}${path.startsWith('/') ? '' : '/'}${path}`, REMATCH_API_KEY, init)
}

/** @deprecated use rematchApiFetch */
export async function stackFetch(path: string, init: StackInit = {}): Promise<StackResult> {
  return rematchApiFetch(path, init)
}

/** Fallback catalog when Rematch API is offline (keeps UI usable). */
export const DEMO_GAMES = {
  categories: [
    { id: 'physical', label: '🎲 Physical / Table' },
    { id: 'imessage', label: '📱 iMessage' },
    { id: 'mobile', label: '📲 Mobile' },
    { id: 'console', label: '🎮 Console' },
  ],
  games: [
    { game_id: 'physical.chess', display_name: 'Chess', category: 'physical', emoji: '♟️' },
    { game_id: 'physical.ludo', display_name: 'Ludo', category: 'physical', emoji: '🎲' },
    { game_id: 'physical.monopoly', display_name: 'Monopoly', category: 'physical', emoji: '🏠' },
    { game_id: 'physical.checkers', display_name: 'Checkers', category: 'physical', emoji: '🟥' },
    { game_id: 'mobile.fc_mobile', display_name: 'FC Mobile', category: 'mobile', emoji: '⚽' },
    { game_id: 'mobile.free_fire_1v1', display_name: 'Free Fire 1v1', category: 'mobile', emoji: '🔥' },
    { game_id: 'mobile.cod_mobile_1v1', display_name: 'COD Mobile 1v1', category: 'mobile', emoji: '🔫' },
    { game_id: 'mobile.valorant_1v1', display_name: 'Valorant 1v1', category: 'mobile', emoji: '🗡️' },
    { game_id: 'mobile.pubg_tdm', display_name: 'PUBG TDM', category: 'mobile', emoji: '🎯' },
    { game_id: 'imessage.8_ball', display_name: '8 Ball', category: 'imessage', emoji: '🎱' },
    { game_id: 'imessage.chess', display_name: 'Chess', category: 'imessage', emoji: '♟️' },
    { game_id: 'EAFC', display_name: 'EA FC', category: 'console', emoji: '⚽' },
    { game_id: 'NBA2K', display_name: 'NBA 2K', category: 'console', emoji: '🏀' },
  ],
}
