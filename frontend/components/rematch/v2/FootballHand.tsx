'use client'
/**
 * The homepage's football pieces: a fanned hand of Icon cards for the hero,
 * and a ticker that runs real results when a season is on and the cast's
 * headliners when it isn't — never an "offline" banner.
 */
import { useEffect, useState } from 'react'
import { loadCatalog, type AfmPlayer } from '@/lib/afm'
import { PlayerCard, callName } from '@/components/football/PlayerCard'
import './football-hero.css'

// The three Icons on the cover: the Akanbi–Kurosawa rivalry and Danjuma.
const HAND = ['afm_og_001', 'afm_og_002', 'afm_og_006']

export function HeroHand() {
  const [cards, setCards] = useState<AfmPlayer[] | null>(null)
  useEffect(() => {
    loadCatalog()
      .then((c) => {
        const byId = new Map(c.players.map((p) => [p.player_id, p]))
        setCards(HAND.map((id) => byId.get(id)).filter(Boolean) as AfmPlayer[])
      })
      .catch(() => setCards([]))
  }, [])
  return (
    <div className="fh-hand" aria-label="Icons of the league">
      {(cards ?? []).map((p, i) => (
        <div className={`fh-card fh-card-${i}`} key={p.player_id}>
          <PlayerCard player={p} index={i * 3} />
        </div>
      ))}
      {cards === null ? <div className="fh-card fh-card-1 fh-ghost" aria-hidden /> : null}
    </div>
  )
}

interface TickerSeason {
  division?: { agent_id: string; name: string }[]
  recent?: { matchday: number; home_agent_id: string; away_agent_id: string; home_goals: number; away_goals: number }[]
}

export function FootballTicker() {
  const [items, setItems] = useState<string[]>([])
  useEffect(() => {
    let cancelled = false
    const castLines = () =>
      loadCatalog().then((c) =>
        c.players
          .filter((p) => p.persona?.tier === 'headliner' && p.persona.title)
          .sort((a, b) => (b.base_rating ?? 0) - (a.base_rating ?? 0))
          .slice(0, 18)
          .map((p) => `${callName(p)} · ${p.persona!.title} · ${p.nation}`),
      )
    fetch('/api/agentic/football/season')
      .then((r) => (r.ok ? r.json() : null))
      .then(async (d: { season?: TickerSeason | null } | null) => {
        const s = d?.season
        const names = new Map((s?.division ?? []).map((c) => [c.agent_id, c.name]))
        const results = (s?.recent ?? []).slice(0, 12).map(
          (r) =>
            `MD${r.matchday} · ${names.get(r.home_agent_id) ?? r.home_agent_id} ${r.home_goals}–${r.away_goals} ${names.get(r.away_agent_id) ?? r.away_agent_id}`,
        )
        return results.length ? results.map((x) => `FT · ${x}`) : castLines()
      })
      .catch(castLines)
      .then((lines) => {
        if (!cancelled && lines) setItems(lines)
      })
      .catch(() => undefined)
    return () => {
      cancelled = true
    }
  }, [])
  if (!items.length) return null
  // two copies back to back so the loop never shows a gap
  const run = [...items, ...items]
  return (
    <div className="fh-ticker" aria-label="Around the league">
      <div className="fh-ticker-track">
        {run.map((t, i) => (
          <span key={i} aria-hidden={i >= items.length}>
            {t}
          </span>
        ))}
      </div>
    </div>
  )
}
