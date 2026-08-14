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

export async function rematchApiFetch(
  path: string,
  init: RequestInit = {}
): Promise<{ ok: boolean; status: number; data: any }> {
  const base = REMATCH_API_URL
  const key = REMATCH_API_KEY
  if (!base || !key) {
    return { ok: false, status: 503, data: { error: 'rematch_api_not_configured', demo: true } }
  }
  const url = path.startsWith('http') ? path : `${base}${path.startsWith('/') ? '' : '/'}${path}`
  const headers = new Headers(init.headers || {})
  // On-brand header + legacy alias for older API processes
  headers.set('X-Rematch-Key', key)
  headers.set('X-Stack-Key', key)
  if (!headers.has('Content-Type') && init.body && !(init.body instanceof FormData)) {
    headers.set('Content-Type', 'application/json')
  }
  try {
    const res = await fetch(url, { ...init, headers, cache: 'no-store' })
    const text = await res.text()
    let data: any = null
    try {
      data = text ? JSON.parse(text) : null
    } catch {
      data = { raw: text }
    }
    return { ok: res.ok, status: res.status, data }
  } catch (e: any) {
    const raw = String(e?.message || e || '')
    const offline =
      /fetch failed|ECONNREFUSED|ENOTFOUND|EAI_AGAIN|network|certificate/i.test(raw)
    return {
      ok: false,
      status: 502,
      data: {
        error: offline
          ? 'House API is offline. Play match needs the Stack running (not just Vercel).'
          : raw || 'house_unreachable',
      },
    }
  }
}

/** @deprecated use rematchApiFetch */
export async function stackFetch(
  path: string,
  init: RequestInit = {}
): Promise<{ ok: boolean; status: number; data: any }> {
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
