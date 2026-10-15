'use client'

import { useEffect, useState } from 'react'
import { loadSessionProfileId } from '@/lib/sessionProfile'

/** The signed-in profile id: undefined while loading, null when signed out. */
export function useSessionProfileId(): string | null | undefined {
  const [id, setId] = useState<string | null | undefined>(undefined)
  useEffect(() => {
    let alive = true
    loadSessionProfileId().then((v) => {
      if (alive) setId(v)
    })
    return () => {
      alive = false
    }
  }, [])
  return id
}
