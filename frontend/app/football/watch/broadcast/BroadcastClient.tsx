'use client'
/**
 * BroadcastClient — resolves a real fixture for the 2D broadcast board.
 *
 * ?md=N&home=<agent_id>&away=<agent_id> deep-links a specific recorded
 * fixture; with no params it falls back to the season's most recent
 * finished result. While loading (or when the season API is unavailable)
 * the scripted demo board plays, so the page is never empty.
 */
import { useEffect, useState } from 'react'
import { useSearchParams } from 'next/navigation'
import {
  fetchAfmSeason,
  fetchSeasonReplay,
  type MatchdayReplay,
} from '@/lib/afm'
import MatchBroadcast from '@/components/football/MatchBroadcast'

/** Richer result shape as returned by the season API (recent results). */
interface Result {
  matchday: number
  home_agent_id: string
  away_agent_id: string
}

export default function BroadcastClient() {
  const params = useSearchParams()
  const [replay, setReplay] = useState<MatchdayReplay | null>(null)
  const [label, setLabel] = useState<string | null>(null)
  const [err, setErr] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setErr(null)

    const md = params.get('md')
    const home = params.get('home')
    const away = params.get('away')
    const load = (p: Promise<MatchdayReplay>, l: string) => {
      setLabel(l)
      p.then((r) => {
        if (!cancelled) setReplay(r)
      }).catch((e: Error) => {
        if (!cancelled) setErr(e.message)
      })
    }

    if (md && home && away) {
      load(fetchSeasonReplay(Number(md), home, away), `Matchday ${md}`)
    } else {
      // No deep link — fall back to the season's most recent result.
      load(
        fetchAfmSeason().then((season) => {
          const seasonAny = season as unknown as { recent?: Result[] }
          const latest = seasonAny.recent?.[0]
          if (!latest) throw new Error('no finished fixtures yet this season')
          setLabel(`Matchday ${latest.matchday}`)
          return fetchSeasonReplay(latest.matchday, latest.home_agent_id, latest.away_agent_id)
        }),
        'Latest fixture',
      )
    }
    return () => {
      cancelled = true
    }
  }, [params])

  return (
    <div>
      {err && (
        <p className="bc-note" role="status">
          {err} — showing the demo board.
        </p>
      )}
      {!err && label && replay && <p className="bc-note">{label}</p>}
      <MatchBroadcast
        replay={replay}
        homeLabel={replay?.home.club_name ?? 'Trafford FC'}
        awayLabel={replay?.away.club_name ?? 'Ashbury Town'}
      />
    </div>
  )
}
