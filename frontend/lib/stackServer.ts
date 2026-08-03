/**
 * Server-only client for Rematch Stack API.
 * STACK_API_KEY never goes to the browser.
 */

const DEFAULT_STACK = process.env.STACK_API_URL || process.env.REMATCH_API_URL || ''

export function stackConfigured(): boolean {
  return Boolean(process.env.STACK_API_KEY && DEFAULT_STACK)
}

export async function stackFetch(
  path: string,
  init: RequestInit = {}
): Promise<{ ok: boolean; status: number; data: any }> {
  const base = DEFAULT_STACK.replace(/\/$/, '')
  const key = process.env.STACK_API_KEY || ''
  if (!base || !key) {
    return { ok: false, status: 503, data: { error: 'stack_not_configured', demo: true } }
  }
  const url = path.startsWith('http') ? path : `${base}${path.startsWith('/') ? '' : '/'}${path}`
  const headers = new Headers(init.headers || {})
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
    return { ok: false, status: 502, data: { error: String(e?.message || e) } }
  }
}

/** Fallback catalog when Stack is offline (keeps UI usable). */
export const DEMO_GAMES = {
  categories: [
    { id: 'imessage', label: '📱 iMessage' },
    { id: 'mobile', label: '📲 Mobile' },
    { id: 'console', label: '🎮 Console' },
  ],
  games: [
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
