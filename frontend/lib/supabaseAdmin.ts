/**
 * Server-only Supabase REST helpers (service role or anon).
 * Used when REMATCH_API_URL does not expose Boardman rematch routes.
 */

export function supabaseConfig(): { url: string; key: string } | null {
  const url = (
    process.env.NEXT_PUBLIC_SUPABASE_URL ||
    process.env.SUPABASE_URL ||
    ''
  )
    .trim()
    .replace(/\/$/, '')
  const key = (
    process.env.SUPABASE_SERVICE_ROLE_KEY ||
    process.env.SUPABASE_SERVICE_KEY ||
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY ||
    ''
  ).trim()
  if (!url || !key) return null
  return { url, key }
}

export async function supabaseRest<T = unknown>(
  pathAndQuery: string,
  init: RequestInit = {}
): Promise<{ ok: boolean; status: number; data: T | null; error?: string }> {
  const cfg = supabaseConfig()
  if (!cfg) return { ok: false, status: 503, data: null, error: 'supabase_not_configured' }
  const url = pathAndQuery.startsWith('http')
    ? pathAndQuery
    : `${cfg.url}/rest/v1/${pathAndQuery.replace(/^\//, '')}`
  try {
    const headers = new Headers(init.headers || {})
    headers.set('apikey', cfg.key)
    headers.set('Authorization', `Bearer ${cfg.key}`)
    if (!headers.has('Accept')) headers.set('Accept', 'application/json')
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
    return { ok: false, status: 502, data: null, error: String(e?.message || e) }
  }
}

export type ProfileWalletRow = {
  id: string
  gaming_tag?: string | null
  display_name?: string | null
  telegram_id?: number | string | null
  wallet_balance_usdc?: number | string | null
  play_points?: number | string | null
  gaming_deposit_address?: string | null
  circle_wallet_id?: string | null
  wallet_address?: string | null
  linked_wallet?: string | null
}

/** Load Boardman profile + ledger balance by profile UUID. */
export async function fetchProfileWallet(
  profileId: string
): Promise<ProfileWalletRow | null> {
  if (!profileId) return null
  const q = new URLSearchParams()
  q.set(
    'select',
    [
      'id',
      'gaming_tag',
      'display_name',
      'telegram_id',
      'wallet_balance_usdc',
      'play_points',
      'gaming_deposit_address',
      'circle_wallet_id',
      'wallet_address',
      'linked_wallet',
    ].join(',')
  )
  q.set('id', `eq.${profileId}`)
  q.set('limit', '1')
  const res = await supabaseRest<ProfileWalletRow[]>(`profiles?${q.toString()}`)
  if (!res.ok || !Array.isArray(res.data) || !res.data[0]) return null
  return res.data[0]
}
