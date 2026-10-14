'use client'

/**
 * What the house chess table is doing right now, in one honest word:
 * live, next (a seat time on the clock), quiet, or offline.
 *
 * Reads the same two public endpoints the arena reads —
 * /api/agentic/house-play (GET) and /api/agentic/house-schedule — and never
 * calls a table LIVE unless the floor says a game is actually on.
 */

import { useCallback, useState } from 'react'
import { fetchJson, usePolling } from './live'

export function agentName(id: string | undefined, fallback: string): string {
  const s = String(id || '')
  if (s.includes('raja')) return 'Raja'
  if (s.includes('nero')) return 'Nero'
  if (s.includes('sheila')) return 'Sheila'
  return fallback
}

export type HouseScheduleInfo = {
  ok: boolean
  enabled?: boolean
  cadence_sec?: number
  every_minutes?: number
  games_per_day?: number
  last_settled_at?: string | null
  cadence_mode?: string
  next_game_at?: string | null
  next_in_sec?: number | null
}

type HousePlay = {
  ok?: boolean
  match_id?: string
  status?: string
  last_settled?: boolean
  error?: string
  match?: {
    status?: string
    result?: string
    agent_a_id?: string
    agent_b_id?: string
    white_agent_id?: string
    winner_agent_id?: string
    stake_usdc?: number
    pot_usdc?: number
    moves?: unknown[]
    spectator_book?: { totals?: { a?: string | number; b?: string | number; draw?: string | number } }
  } | null
}

const LIVE_STATUSES = new Set(['playing', 'locking', 'locked', 'open'])

export type LastResult = { a: string; b: string; head: string }

export type HouseTable =
  | { kind: 'checking' }
  | {
      kind: 'live'
      a: string
      b: string
      move: number
      pot: number
      backed: { a: number; b: number; draw: number } | null
    }
  | { kind: 'next'; at: number; onTheHour: boolean; last: LastResult | null }
  | { kind: 'quiet'; paused: boolean; last: LastResult | null }
  | { kind: 'offline' }

function nextSeatAt(s: HouseScheduleInfo | null, fetchedAt: number): number | null {
  if (!s?.ok || !s.enabled) return null
  const parsed = Date.parse(String(s.next_game_at || ''))
  if (Number.isFinite(parsed)) return parsed
  if (typeof s.next_in_sec === 'number') return fetchedAt + s.next_in_sec * 1000
  return null
}

function lastResult(p: HousePlay): LastResult | null {
  const m = p.match
  if (!p.last_settled || !m) return null
  const a = agentName(m.agent_a_id, 'Side A')
  const b = agentName(m.agent_b_id, 'Side B')
  const head =
    m.result === 'draw'
      ? 'drawn'
      : m.winner_agent_id
        ? `${agentName(m.winner_agent_id, 'the house agent')} won`
        : 'settled'
  return { a, b, head }
}

/** Polls gently (default 30s), pauses in hidden tabs, backs off when offline. */
export function useHouseTable(intervalMs = 30_000): HouseTable {
  const [table, setTable] = useState<HouseTable>({ kind: 'checking' })

  const pull = useCallback(async () => {
    const [play, sched] = await Promise.all([
      fetchJson<HousePlay>('/api/agentic/house-play', 6000),
      fetchJson<HouseScheduleInfo>('/api/agentic/house-schedule', 6000),
    ])
    const fetchedAt = Date.now()
    const p = play.data

    if (play.offline || !play.ok || !p || p.ok !== true) {
      setTable({ kind: 'offline' })
      return false
    }

    const status = String(p.status || p.match?.status || '')
    if (p.match_id && p.match && !p.last_settled && !p.match.result && LIVE_STATUSES.has(status)) {
      const m = p.match
      const t = m.spectator_book?.totals
      setTable({
        kind: 'live',
        a: agentName(m.agent_a_id, 'Side A'),
        b: agentName(m.agent_b_id, 'Side B'),
        move: Array.isArray(m.moves) ? m.moves.length : 0,
        pot: Number(m.pot_usdc ?? 0) || Number(m.stake_usdc ?? 0) * 2 || 0,
        backed: t
          ? { a: Number(t.a ?? 0) || 0, b: Number(t.b ?? 0) || 0, draw: Number(t.draw ?? 0) || 0 }
          : null,
      })
      return true
    }

    const s = sched.ok ? sched.data : null
    const last = lastResult(p)
    const at = nextSeatAt(s, fetchedAt)
    if (at != null) {
      setTable({ kind: 'next', at, onTheHour: s?.cadence_mode === 'on_the_hour', last })
    } else {
      setTable({ kind: 'quiet', paused: Boolean(s?.ok && !s.enabled), last })
    }
    return true
  }, [])

  usePolling(pull, { intervalMs, maxMs: 5 * 60_000 })
  return table
}
