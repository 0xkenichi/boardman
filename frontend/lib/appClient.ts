/** Browser-side fetch to Rematch BFF only (never Stack key). */

export async function api<T = any>(
  path: string,
  init: RequestInit = {}
): Promise<{ ok: boolean; status: number; data: T }> {
  const headers = new Headers(init.headers || {})
  if (init.body && !(init.body instanceof FormData) && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }
  const res = await fetch(path, { ...init, headers, credentials: 'same-origin', cache: 'no-store' })
  let data: any = null
  try {
    data = await res.json()
  } catch {
    data = null
  }
  return { ok: res.ok, status: res.status, data }
}

export type Me = {
  profileId: string
  tag: string
  name: string
  balance: number
  otherBalance?: number
  otherAddress?: string
  address?: string
  playPoints?: number
  demo?: boolean
}

export type Game = {
  game_id: string
  display_name: string
  category: string
  emoji?: string
}
