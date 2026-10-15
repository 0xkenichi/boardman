'use client'
/**
 * BettingPots — the spectator pot panel.
 *
 * Reads the parimutuel boards for the current matchday and renders, per
 * fixture: the pot total, the crowd's split (home/draw/away) and the implied
 * odds per USDC staked. Read-only for now — placing a bet attaches to the
 * spectator seat's wallet flow, this panel is the price-of-entry view.
 */
import { useEffect, useState } from 'react'

/** One parimutuel odds board (mirrors betting.current_odds). */
interface Board {
  season_no: number
  matchday: number
  home: string
  away: string
  pot_total: string
  pot: { home: string; draw: string; away: string }
  odds: { home: string; draw: string; away: string }
  betters: number
  status: string
}

interface BoardWithNames extends Board {
  home_club?: string
  away_club?: string
}

function Odd({ label, odds, pot }: { label: string; odds: string; pot: string }) {
  const backed = Number(pot) > 0
  return (
    <div className="fd-bet-side">
      <span className="fd-bet-label">{label}</span>
      <span className="fd-bet-odds">{backed ? odds : '—'}</span>
      <span className="fd-bet-pot">{backed ? `${pot} in` : 'no bets'}</span>
    </div>
  )
}

export default function BettingPots({ fixtures }: { fixtures?: { matchday: number; home_club: string; away_club: string }[] }) {
  const [boards, setBoards] = useState<BoardWithNames[]>([])
  const [loaded, setLoaded] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    fetch('/api/agentic/football/betting/odds')
      .then((res) => (res.ok ? res.json() : Promise.reject(new Error(`odds fetch failed (${res.status})`))))
      .then((data: { boards?: BoardWithNames[] }) => {
        if (cancelled) return
        setBoards(data.boards ?? [])
        setLoaded(true)
      })
      .catch((e: Error) => {
        if (!cancelled) setErr(e.message)
      })
    return () => {
      cancelled = true
    }
  }, [])

  // merge the spectator-facing club names from the fixtures list if provided
  const nameFor = (agentId: string, fallback?: string) =>
    fallback ?? agentId.replace('agent_', '').replace('_demo', '')
  const named = boards.map((b) => {
    const fx = fixtures?.find((f) => f.home_club === b.home || f.away_club === b.away)
    return fx ? { ...b, home_club: fx.home_club, away_club: fx.away_club } : b
  })

  if (err) return <p className="fd-note">Odds boards unavailable right now — {err}.</p>
  if (!loaded) return <p className="fd-note">Loading the pots…</p>
  if (named.length === 0) {
    return (
      <p className="fd-note">
        No bets pooled yet. When spectators back a fixture, its pot and the crowd&apos;s odds appear
        here — the crowd prices the match, the house never does.
      </p>
    )
  }

  return (
    <div className="fd-bet-grid">
      {named.map((b) => (
        <div key={`${b.season_no}-${b.matchday}-${b.home}-${b.away}`} className="fd-bet-card">
          <div className="fd-bet-head">
            <b>
              {b.home_club ?? nameFor(b.home)} vs {b.away_club ?? nameFor(b.away)}
            </b>
            <span className="fd-bet-total">
              pot {b.pot_total} test USDC · {b.betters} better{b.betters === 1 ? '' : 's'}
            </span>
          </div>
          <Odd label="Home" odds={b.odds.home} pot={b.pot.home} />
          <Odd label="Draw" odds={b.odds.draw} pot={b.pot.draw} />
          <Odd label="Away" odds={b.odds.away} pot={b.pot.away} />
          <p className="fd-bet-foot">
            Parimutuel: winners split the pot (after the 7% platform fee), losing stakes fund it.
            Odds move as the crowd bets.
          </p>
        </div>
      ))}
    </div>
  )
}
