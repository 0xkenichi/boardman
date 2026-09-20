'use client'
/**
 * PrematchClient — resolves the fixture for the pre-match board.
 *
 * ?md=N&home=<agent_id>&away=<agent_id> selects the fixture; with no params
 * it picks the soonest open/played matchday's first fixture from the season
 * snapshot. When the fixture hasn't resolved yet (or the API is down) the
 * board renders its demo plans so the page is never empty.
 */
import { useEffect, useState } from 'react'
import { useSearchParams } from 'next/navigation'
import Link from 'next/link'
import { broadcastHref, fetchPrematch, prematchHref, type PrematchView } from '@/lib/afm'
import PreMatchBoard from '@/components/football/PreMatchBoard'

/** The season snapshot slice this resolver needs. */
interface UpcomingFixture {
  matchday: number
  home_agent_id: string
  away_agent_id: string
  status: string
}

export default function PrematchClient() {
  const params = useSearchParams()
  const [view, setView] = useState<PrematchView | null>(null)
  const [label, setLabel] = useState<string | null>(null)
  const [err, setErr] = useState<string | null>(null)
  /** broadcast link for the same fixture once we know which one is on */
  const [watch, setWatch] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setErr(null)

    const md = params.get('md')
    const home = params.get('home')
    const away = params.get('away')

    const load = async () => {
      try {
        if (md && home && away) {
          const v = await fetchPrematch(Number(md), home, away)
          if (cancelled) return
          setView(v)
          setLabel(`Matchday ${md}`)
          setWatch(broadcastHref(v.matchday, v.home.agent_id, v.away.agent_id))
          return
        }
        // No deep link — pick the soonest decided fixture: the first
        // upcoming matchday with lineups in, else the latest played one.
        const res = await fetch('/api/agentic/football/season')
        if (!res.ok) throw new Error(`season fetch failed (${res.status})`)
        const data = (await res.json()) as {
          season?: { upcoming?: UpcomingFixture[]; recent?: { matchday: number; home_agent_id: string; away_agent_id: string }[]; current_matchday: number } | null
        }
        const season = data?.season
        if (!season) throw new Error('no season running right now')

        const upcoming = (season.upcoming ?? []).filter(
          (fx, i, arr) =>
            arr.findIndex(
              (o) => o.matchday === fx.matchday && o.home_agent_id === fx.home_agent_id && o.away_agent_id === fx.away_agent_id,
            ) === i,
        )
        const ready = upcoming.find((fx) => fx.status === 'open' || fx.status === 'played')
        if (ready) {
          const v = await fetchPrematch(ready.matchday, ready.home_agent_id, ready.away_agent_id)
          if (cancelled) return
          setView(v)
          setLabel(`Matchday ${ready.matchday}`)
          setWatch(broadcastHref(v.matchday, v.home.agent_id, v.away.agent_id))
          return
        }
        const last = season.recent?.[0]
        if (last) {
          const v = await fetchPrematch(last.matchday, last.home_agent_id, last.away_agent_id)
          if (cancelled) return
          setView(v)
          setLabel(`Matchday ${last.matchday}`)
          setWatch(broadcastHref(v.matchday, v.home.agent_id, v.away.agent_id))
          return
        }
        throw new Error('no fixtures on the slate yet')
      } catch (e) {
        if (!cancelled) setErr((e as Error).message)
      }
    }
    load()
    return () => {
      cancelled = true
    }
  }, [params])

  return (
    <div>
      <div className="bc-note bc-note-row">
        {err ? <span role="status">{err} — showing demo plans.</span> : label ? <span>{label}</span> : <span>Loading…</span>}
        {watch ? (
          <Link className="bc-watch-link" href={watch}>
            Watch the match →
          </Link>
        ) : null}
      </div>
      <PreMatchBoard view={view} />
    </div>
  )
}
