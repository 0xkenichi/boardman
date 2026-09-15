'use client'

/**
 * Season/status strip — sits directly under the portal nav on every page
 * (the reference clip's "2026/27 · MW1 · SUMMER WINDOW OPEN" bar).
 * Reads the live season: number, status, current matchday, total matchdays.
 * Boardman tokens: emerald accent, uppercase letter-spaced labels.
 */
import { useEffect, useState } from 'react'
import { fetchAfmSeason, type AfmSeason } from '@/lib/afm'

/** Transfer window: open during the first third of a season, reopen near the end. */
function windowOpen(season: AfmSeason | null): boolean {
  if (!season || season.status !== 'open') return false
  const md = season.current_matchday
  return md <= 6 || md >= season.matchdays_total - 3
}

export function SeasonStrip({ active }: { active?: string }) {
  const [season, setSeason] = useState<AfmSeason | null>(null)
  const [err, setErr] = useState(false)

  useEffect(() => {
    let alive = true
    fetchAfmSeason()
      .then((s) => alive && setSeason(s))
      .catch(() => alive && setErr(true))
    return () => {
      alive = false
    }
  }, [])

  const open = windowOpen(season)

  return (
    <div className="ss-bar" data-active={active}>
      <span className="ss-season">
        {season ? `Season ${season.season_no}` : 'Season —'}
      </span>
      <span className="ss-sep" aria-hidden>
        ·
      </span>
      <span className="ss-md">
        {season
          ? season.status === 'open'
            ? `MD ${season.current_matchday}/${season.matchdays_total}`
            : season.status === 'finished'
              ? 'complete'
              : season.status
          : err
            ? 'offline'
            : '…'}
      </span>
      {open && (
        <span className={`ss-pill${season && season.current_matchday <= 6 ? '' : ' late'}`}>
          {season && season.current_matchday > 6 ? 'TRANSFER WINDOW · FINAL DAYS' : 'TRANSFER WINDOW OPEN'}
        </span>
      )}
      {season?.status === 'finished' && (
        <span className="ss-pill done">SEASON COMPLETE</span>
      )}
    </div>
  )
}
