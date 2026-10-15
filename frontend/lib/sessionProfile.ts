/**
 * Who is signed in, for client components that filter "mine".
 *
 * Every football write goes through the BFF, which stamps the session's
 * profileId as the owner/buyer/party (lib/proxyAuthed.ts). Reads that pick
 * out "my managers", "my club" or "my sales" must use the same id, or a
 * signed-in user never sees what they just created.
 */

type FetchLike = (input: string, init?: RequestInit) => Promise<{ ok: boolean; json: () => Promise<any> }>

/** The signed-in profile id, or null when signed out / unreachable. */
export async function loadSessionProfileId(fetchImpl: FetchLike = fetch): Promise<string | null> {
  try {
    const res = await fetchImpl('/api/rematch/app/session', { credentials: 'same-origin', cache: 'no-store' })
    if (!res.ok) return null
    const data = await res.json()
    const id = typeof data?.profileId === 'string' ? data.profileId.trim() : ''
    return id || null
  } catch {
    return null
  }
}

/** Items owned by `profileId` (never matches anything when signed out). */
export function ownedBy<T extends { owner_id?: string | null }>(items: T[], profileId: string | null | undefined): T[] {
  if (!profileId) return []
  return items.filter((a) => a.owner_id === profileId)
}
