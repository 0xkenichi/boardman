'use client'

/**
 * /arena — the live AI-agent chess table, rebuilt as a React page in the book.
 * Replaced the retired public/agentic/arena.html. Polls /api/agentic/house-play (which
 * proxies the Stack house floor) every ~10s while the tab is visible, backing
 * off when the house does not answer; renders moves via chess.js, and posts
 * spectator bets to /api/agentic/spectator-bet.
 *
 * The 1s heartbeat lives inside <ChessClock> and <NextTableLine> only, so the
 * page itself re-renders on data, not on every second.
 */

import { useCallback, useEffect, useMemo, useState } from 'react'
import { Chess } from 'chess.js'
import { BookShell } from '@/components/rematch/BookShell'
import { TelegramLogin } from '@/components/TelegramLogin'
import { WalletLogin } from '@/components/WalletLogin'
import { agentName, type HouseScheduleInfo } from '@/components/rematch/house'
import { fetchJson, useNow, usePolling } from '@/components/rematch/live'
import { api } from '@/lib/appClient'
// NEXT_PUBLIC_TELEGRAM_BOT_USERNAME (with the house default) — the old
// NEXT_PUBLIC_BOT_USERNAME read was never set anywhere.
import { REMATCH_BOT_URL, REMATCH_BOT_USERNAME } from '@/lib/rematchLinks'

const FILES = ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h'] as const

type MatchMove = { ply?: number; side?: string; san?: string; uci?: string; is_check?: boolean }
type ClockSide = { remaining_ms?: number; flag?: boolean }
type Match = {
  match_id?: string
  status?: string
  result?: string
  termination?: string
  winner_agent_id?: string
  agent_a_id?: string
  agent_b_id?: string
  white_agent_id?: string
  black_agent_id?: string
  created_at?: string
  settled_at?: string
  stake_usdc?: number
  pot_usdc?: number
  moves?: MatchMove[]
  fen?: string
  ply?: number
  board?: string[]
  clock?: {
    control_id?: string
    increment_ms?: number
    white?: ClockSide
    black?: ClockSide
    move_times?: unknown[]
  }
  spectator_book?: {
    totals?: { a?: string | number; b?: string | number; draw?: string | number }
    status?: string
  }
  [k: string]: unknown
}

type ScheduleInfo = HouseScheduleInfo

type HousePlayResponse = {
  ok?: boolean
  match_id?: string
  status?: string
  last_settled?: boolean
  match?: Match | null
  error?: string
}

type Ticket =
  | {
      state: 'pending'
      approval_id: string
      amount: number
      side: 'a' | 'b' | 'draw'
      match_id: string
      message?: string
    }
  | { state: 'printed'; amount: number; side: 'a' | 'b' | 'draw'; match_id: string; balance?: number }
  | {
      state: 'settled'
      amount: number
      side: 'a' | 'b' | 'draw'
      match_id: string
      outcome: 'win' | 'loss' | 'refund'
      payout?: number
      endedAt?: string
    }
  | { state: 'failed'; message: string }

const TICKET_KEY = 'boardman_ticket_v1'

function pieceGlyph(kind: string | undefined, side: string | undefined): string {
  const white = side !== 'b' && side !== 'black' && side !== '2'
  switch ((kind || '').toLowerCase()) {
    case 'k':
    case 'king':
      return white ? '♔' : '♚'
    case 'q':
    case 'queen':
      return white ? '♕' : '♛'
    case 'r':
    case 'rook':
      return white ? '♖' : '♜'
    case 'b':
    case 'bishop':
      return white ? '♗' : '♘'
    case 'n':
    case 'knight':
      return white ? '♘' : '♗'
    case 'p':
    case 'pawn':
      return white ? '♙' : '♟'
    default:
      return ''
  }
}

const UNICODE_FEN_PIECES: Record<string, string> = {
  P: '♙', N: '♘', B: '♗', R: '♖', Q: '♕', K: '♔',
  p: '♟', n: '♞', b: '♝', r: '♜', q: '♛', k: '♚',
}

/** Build a display board from whatever the API gives us. */
function useBoard(match: Match | null) {
  return useMemo(() => {
    const fen = typeof match?.fen === 'string' ? match.fen : ''
    if (fen) {
      try {
        const rows = fen.split(' ')[0].split('/')
        const grid: (string | null)[] = []
        for (const row of rows) {
          for (const ch of row) {
            if (/\d/.test(ch)) {
              for (let i = 0; i < Number(ch); i++) grid.push(null)
            } else {
              grid.push(UNICODE_FEN_PIECES[ch] || null)
            }
          }
        }
        if (grid.length === 64) return grid
      } catch {
        /* fall through */
      }
    }

    const grid: (string | null)[] = Array(64).fill(null)
    const sans = (match?.moves || []).map((m) => m?.san).filter(Boolean) as string[]
    if (sans.length) {
      try {
        const g = new Chess()
        for (const san of sans) g.move(san)
        const board = g.board() // [rank 8..1][file a..h] rows of {type,color} | null
        for (let r = 0; r < 8; r++) {
          for (let f = 0; f < 8; f++) {
            const sq = board[r][f]
            if (sq) grid[r * 8 + f] = UNICODE_FEN_PIECES[sq.color === 'w' ? sq.type.toUpperCase() : sq.type] || null
          }
        }
        return grid
      } catch {
        /* fall through */
      }
    }

    if (Array.isArray(match?.board) && match!.board!.length === 64) {
      return match!.board!.map((v) => (typeof v === 'string' && v ? v : null))
    }
    return null
  }, [match])
}

function Board({ grid, flipped }: { grid: (string | null)[] | null; flipped: boolean }) {
  const squares = []
  for (let i = 0; i < 64; i++) {
    const r = Math.floor(i / 8)
    const c = i % 8
    const dark = (r + c) % 2 === 1
    const idx = flipped ? 63 - i : i
    squares.push(
      <div key={i} className={dark ? 'ar-sq ar-sq-d' : 'ar-sq'}>
        <span>{grid ? grid[idx] : ''}</span>
      </div>,
    )
  }
  return <div className="ar-board">{squares}</div>
}

function outcomeText(match: Match): { head: string; why: string } {
  const term = String(match.termination || '').toLowerCase()
  const whiteName = agentName(match.white_agent_id, 'White')
  const blackName = agentName(match.black_agent_id, 'Black')
  const winnerIsWhite = Boolean(match.winner_agent_id) && match.winner_agent_id === match.white_agent_id
  const winnerName = match.winner_agent_id
    ? agentName(match.winner_agent_id, winnerIsWhite ? 'White' : 'Black')
    : ''
  if (match.result === 'draw') {
    const why =
      term === 'stalemate'
        ? 'stalemate — the side to move has no legal move'
        : term === 'insufficient_material'
          ? 'not enough pieces left to checkmate'
          : term.includes('repetition')
            ? 'the same position repeated three times'
            : term.includes('seventy') || term.includes('fifty')
              ? 'the move-count rule'
              : 'draw tickets win the pool, side bets lose'
    return { head: 'Draw', why }
  }
  if (winnerName) {
    const loserName = match.white_agent_id ? (winnerIsWhite ? blackName : whiteName) : ''
    let why = 'on the board'
    if (term === 'timeout' || term === 'flag' || term === 'time') {
      why = loserName ? `${loserName} ran out of time` : 'ran out of time'
    } else if (term === 'checkmate' || term === 'mate') {
      why = 'by checkmate'
    } else if (term === 'resignation' || term === 'resign') {
      why = 'the other side resigned'
    } else if (term) {
      why = term.replace(/_/g, ' ')
    }
    return { head: `${winnerName} wins`, why }
  }
  return { head: 'Game over', why: term ? term.replace(/_/g, ' ') : '' }
}

function StatusLine({ match, loading }: { match: Match | null; loading: boolean }) {
  if (!match && loading) return <p className="ar-note">Asking the house what’s on the board…</p>
  if (!match) return <p className="ar-note">The table is quiet. Check back soon — the house agents play often.</p>
  const status = String(match.status || '')
  const settled = status === 'settled' || Boolean(match.result)
  if (settled) {
    const o = outcomeText(match)
    return (
      <p className="ar-note">
        <strong>{o.head}</strong>
        {o.why ? <> — {o.why}</> : null}
      </p>
    )
  }
  const list = Array.isArray(match.moves) ? match.moves : []
  const last = list.length ? list[list.length - 1] : null
  const check = last && last.is_check ? ' · check!' : ''
  return (
    <p className="ar-note">
      <strong>Playing now</strong> — move {list.length}
      {check}
    </p>
  )
}

function fmtClock(ms: number | null): string {
  if (ms == null) return '—:—'
  const s = Math.max(0, Math.floor(ms / 1000))
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
}

/**
 * One side's chess clock. Only the side to move ticks, and only this little
 * span re-renders each second — the board and bet slip stay still.
 */
function ChessClock({
  clock,
  active,
  receivedAt,
}: {
  clock: ClockSide | undefined
  /** game is running and it is this side's move */
  active: boolean
  /** when the remaining_ms reading arrived from the house */
  receivedAt: number
}) {
  const base = clock && typeof clock.remaining_ms === 'number' ? clock.remaining_ms : null
  const ticking = active && base != null
  const now = useNow(1000, ticking)
  const ms = base == null ? null : ticking ? Math.max(0, base - Math.max(0, now - receivedAt)) : base
  const flagged = Boolean(clock?.flag)
  const low = ms != null && ms < 30000
  const cls = flagged
    ? 'ar-clock ar-clock-flag'
    : active
      ? low
        ? 'ar-clock ar-clock-run ar-clock-low'
        : 'ar-clock ar-clock-run'
      : low
        ? 'ar-clock ar-clock-low'
        : 'ar-clock'
  return (
    <span className={cls}>
      {fmtClock(ms)}
      {flagged ? <span className="ar-flag">flagged</span> : null}
    </span>
  )
}

/** When the house seats the next table — its own 1s heartbeat for the countdown. */
function NextTableLine({ schedule, match, settled }: { schedule: ScheduleInfo | null; match: Match | null; settled: boolean }) {
  const cad = Number(schedule?.cadence_sec || 0)
  // Authoritative: the API computes this with the same clock-aligned math
  // the house session uses to seat a table. Fall back to a rough anchor.
  const at = useMemo(() => {
    if (!schedule?.ok || !schedule.enabled || !cad) return NaN
    const parsed = Date.parse(String(schedule.next_game_at || ''))
    if (Number.isFinite(parsed)) return parsed
    const fallbackIso =
      !settled && match?.created_at
        ? String(match.created_at)
        : String(schedule.last_settled_at || match?.settled_at || '')
    const a = Date.parse(fallbackIso)
    return Number.isFinite(a) ? a + cad * 1000 : NaN
  }, [schedule, cad, settled, match?.created_at, match?.settled_at])
  const now = useNow(1000, Number.isFinite(at))

  if (!schedule?.ok) return null
  let label: string | null
  if (!schedule.enabled) {
    label = 'The house floor is paused — the next table opens when the desk turns it back on.'
  } else if (!cad) {
    label = null
  } else {
    const every = schedule.every_minutes || Math.max(1, Math.round(cad / 60))
    const perDay = schedule.games_per_day || Math.floor(86400 / cad)
    if (!Number.isFinite(at)) {
      label = `A fresh table seats about every ${every} minutes — roughly ${perDay} games a day.`
    } else {
      const d = at - now
      const hm = new Date(at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
      if (d <= 0) {
        label = `Next table seats any moment — the house plays about every ${every} minutes.`
      } else {
        const totalSec = Math.floor(d / 1000)
        const inStr =
          totalSec >= 3600
            ? `${Math.floor(totalSec / 3600)}h ${Math.floor((totalSec % 3600) / 60)}m`
            : `${Math.floor(totalSec / 60)}:${String(totalSec % 60).padStart(2, '0')}`
        label = `Next game around ${hm} — starts in ${inStr}. A fresh table seats about every ${every} minutes (${perDay} a day).`
      }
    }
  }
  if (!label) return null
  return (
    <p className="rm-muted" style={{ fontSize: '0.8rem', margin: '-0.9rem 0 1.5rem' }}>
      {label}
    </p>
  )
}

/** Share of the whole spectator pot sitting on the draw, as a CSS width. */
function drawShare(totals: { a?: string | number; b?: string | number; draw?: string | number } | undefined): string {
  if (!totals) return '0%'
  const n = (v: unknown) => Math.max(0, Number(v ?? 0) || 0)
  const a = n(totals.a)
  const b = n(totals.b)
  const d = n(totals.draw)
  const total = a + b + d
  if (!(total > 0)) return '0%'
  return `${Math.min(100, (d / total) * 100)}%`
}

/** The last move, drawn from its origin square to its destination. */
function LastMoveArrow({ moves }: { moves: MatchMove[] }) {
  const uci = moves.length ? moves[moves.length - 1]?.uci || '' : ''
  if (uci.length < 4) return null
  const fx = uci.charCodeAt(0) - 97
  const fr = Number(uci[1])
  const tx = uci.charCodeAt(2) - 97
  const tr = Number(uci[3])
  if (fx < 0 || fx > 7 || tx < 0 || tx > 7 || !(fr >= 1 && fr <= 8) || !(tr >= 1 && tr <= 8)) return null
  const x1 = fx + 0.5
  const y1 = 8 - fr + 0.5
  const x2 = tx + 0.5
  const y2 = 8 - tr + 0.5
  const dx = x2 - x1
  const dy = y2 - y1
  const len = Math.hypot(dx, dy) || 1
  const ex = x2 - (dx / len) * 0.34
  const ey = y2 - (dy / len) * 0.34
  const ink = 'rgba(37, 107, 72, 0.85)'
  return (
    <svg className="ar-arrow" viewBox="0 0 8 8" aria-hidden="true">
      <defs>
        <marker
          id="ar-arrow-head"
          viewBox="0 0 10 10"
          refX="7.5"
          refY="5"
          markerWidth="3.4"
          markerHeight="3.4"
          orient="auto-start-reverse"
        >
          <path d="M0 0 L10 5 L0 10 z" fill={ink} />
        </marker>
      </defs>
      <line
        x1={x1}
        y1={y1}
        x2={ex}
        y2={ey}
        stroke={ink}
        strokeWidth="0.16"
        strokeLinecap="round"
        markerEnd="url(#ar-arrow-head)"
      />
    </svg>
  )
}

/** Tiered platform fee on the spectator pot — mirrors economy/spectator.py. */
function tieredFee(pot: number): number {
  if (pot <= 0) return 0
  if (pot < 10) return Math.min(1, pot / 4)
  if (pot <= 1000) return pot * 0.07
  return pot * 0.1
}

const CREATOR_BPS = 200 // 2% of the pot to both agents' creators

/**
 * "If you bet now, the pot pays about…" — a $1 ticket's estimated return:
 * the pot after fees, split across the money already on that side. Mirrors
 * the settle math in economy/spectator.py. The draw quote leaves out the
 * house draw seeds, so it errs low — never promises more than it pays.
 */
function payoutPerDollar(pot: number, pool: number): number | null {
  if (pot <= 0 || pool <= 0) return null
  const distributable = pot - tieredFee(pot) - (pot * CREATOR_BPS) / 10_000
  if (distributable <= 0) return null
  const dec = distributable / pool
  if (dec < 1.01) return null
  return Math.min(50, dec)
}

type BetChecker = { settled: boolean; outcome?: 'win' | 'loss' | 'refund'; payout?: number; endedAt?: string };

export default function ArenaPage() {
  const [match, setMatch] = useState<Match | null>(null)
  const [loading, setLoading] = useState(true)
  const [notice, setNotice] = useState<string | null>(null)
  const [stale, setStale] = useState(false)
  /** The house API itself is down (502/504, timeout, backend_offline). */
  const [offline, setOffline] = useState(false)
  const [betAmount, setBetAmount] = useState(1)
  const [betSide, setBetSide] = useState<'a' | 'b' | 'draw'>('a')
  const [betBusy, setBetBusy] = useState(false)
  const [me, setMe] = useState<{ tag?: string; balance?: number } | null>(null)
  const [authOpen, setAuthOpen] = useState(false)
  const [schedule, setSchedule] = useState<ScheduleInfo | null>(null)
  const [ticket, setTicket] = useState<Ticket | null>(null)

  // Restore the last ticket from this browser so a resolved ticket is never
  // silently replaced by the next table's fresh bet card.
  useEffect(() => {
    try {
      const raw = window.localStorage.getItem(TICKET_KEY)
      if (!raw) return
      const saved = JSON.parse(raw)
      if (saved && (saved.state === 'printed' || saved.state === 'settled')) {
        setTicket(saved as Ticket)
      }
    } catch {
      // ignore corrupt storage
    }
  }, [])
  const [lastSettled, setLastSettled] = useState(false)
  /** When the current clock reading arrived — the ticking clock counts from here. */
  const [receivedAt, setReceivedAt] = useState(0)

  const load = useCallback(async () => {
    const r = await fetchJson<HousePlayResponse>('/api/agentic/house-play', 8000)
    const data = r.data || {}
    setLoading(false)
    if (r.ok && data.ok && data.match_id) {
      setMatch({ ...(data.match || {}), match_id: data.match_id, status: data.status })
      setStale(false)
      setOffline(false)
      setLastSettled(Boolean(data.last_settled))
      setReceivedAt(Date.now())
      return true
    }
    if (r.ok && data.ok === true) {
      // Server definitively answered: nothing live (and no recent settle).
      setMatch(null)
      setStale(false)
      setOffline(false)
      setLastSettled(false)
      setReceivedAt(Date.now())
      return true
    }
    // Transient failure (tunnel/API blip) — keep the last board visible;
    // a 502/504/timeout means the house itself is down.
    setStale(true)
    setOffline(r.offline)
    return false
  }, [])

  // ~10s while visible; paused in hidden tabs; 20s → 40s → … → 2m while failing.
  usePolling(load, { intervalMs: 10_000, maxMs: 120_000 })

  useEffect(() => {
    ;(async () => {
      try {
        const s = await api('/api/rematch/app/session')
        if (s.ok) {
          const m = await api<{ tag?: string; balance?: number }>('/api/rematch/app/me')
          if (m.ok) setMe(m.data)
        }
      } catch {
        /* signed out */
      }
    })()
  }, [])

  // Refresh the seat time as games settle so the countdown stays honest.
  const pullSchedule = useCallback(async () => {
    const r = await fetchJson<ScheduleInfo>('/api/agentic/house-schedule', 8000)
    if (r.data?.ok) setSchedule(r.data)
    return r.ok
  }, [])
  usePolling(pullSchedule, { intervalMs: 30_000, maxMs: 5 * 60_000 })

  // Telegram approval: poll until the ticket prints (or fails). Starts brisk
  // (the bettor is tapping Yes right now), eases off to 8s, backs off harder
  // on errors, and checks at once when the bettor comes back from Telegram.
  useEffect(() => {
    if (ticket?.state !== 'pending') return
    const aid = ticket.approval_id
    const pendingAmount = ticket.amount
    const pendingSide = ticket.side
    const pendingMatch = ticket.match_id
    const deadline = Date.now() + 2 * 60_000
    let dead = false
    let inflight = false
    let delay = 2000
    let timer: number | undefined

    const step = async () => {
      if (dead || inflight) return
      inflight = true
      let transient = false
      try {
        const r = await api(`/api/agentic/spectator-bet?approval_id=${encodeURIComponent(aid)}`)
        if (dead) return
        if (r.ok) {
          const d = (r.data || {}) as { amount?: number; match_id?: string; balance?: number }
          const printed: Ticket = {
            state: 'printed',
            amount: Number(d.amount ?? pendingAmount),
            side: pendingSide,
            match_id: String(d.match_id || pendingMatch),
            balance: d.balance != null ? Number(d.balance) : undefined,
          }
          setTicket(printed)
          try {
            window.localStorage.setItem(TICKET_KEY, JSON.stringify(printed))
          } catch {}
          if (d.balance != null) setMe((m) => (m ? { ...m, balance: Number(d.balance) } : m))
          return
        }
        const d = (r.data || {}) as { pending?: boolean; error?: string; message?: string }
        if (String(d.error || '').startsWith('approval_')) {
          setTicket({
            state: 'failed',
            message: String(d.message || 'The approval was declined or expired — nothing was charged.'),
          })
          return
        }
        transient = !d.pending // still waiting on Telegram vs. a poll error
      } catch {
        transient = true
      } finally {
        inflight = false
      }
      if (dead) return
      if (Date.now() > deadline) {
        setTicket({ state: 'failed', message: 'Approval timed out — nothing was charged. Try again.' })
        return
      }
      delay = transient ? Math.min(15_000, delay * 2) : Math.min(8_000, Math.round(delay * 1.4))
      timer = window.setTimeout(step, delay)
    }

    const onVisibility = () => {
      if (document.hidden) return
      window.clearTimeout(timer)
      timer = window.setTimeout(step, 0)
    }

    timer = window.setTimeout(step, delay)
    document.addEventListener('visibilitychange', onVisibility)
    return () => {
      dead = true
      window.clearTimeout(timer)
      document.removeEventListener('visibilitychange', onVisibility)
    }
  }, [ticket])

  // Ticket outcome checker: every printed ticket resolves visibly — win,
  // loss, or refund — never silently. Polls only while its table may still
  // be live; once resolved the ticket card itself carries the verdict.
  const checkTicket = useCallback(async () => {
    if (!ticket || ticket.state !== 'printed') return true
    const r = await fetchJson<{
      settled?: boolean
      outcome?: 'win' | 'loss' | 'refund'
      payout?: number
      ended_at?: string
    }>(`/api/agentic/house-play?status_for=${encodeURIComponent(ticket.match_id)}`, 8000)
    const d = r.data || {}
    if (!d.settled || !d.outcome) return r.ok
    const resolved: Ticket = {
      state: 'settled',
      amount: ticket.amount,
      side: ticket.side,
      match_id: ticket.match_id,
      outcome: d.outcome,
      payout: d.payout,
      endedAt: d.ended_at,
    }
    setTicket(resolved)
    try {
      window.localStorage.setItem(TICKET_KEY, JSON.stringify(resolved))
    } catch {}
    return true
  }, [ticket])
  usePolling(checkTicket, { intervalMs: 20_000, maxMs: 5 * 60_000, enabled: ticket?.state === 'printed' })

  const grid = useBoard(match)
  const moves = useMemo(() => (match?.moves || []).map((m) => m?.san).filter(Boolean) as string[], [match])

  const settled = match?.status === 'settled' || Boolean(match?.result)
  // Draw share of the whole spectator pot (a + b + draw), clamped to 100%.
  const drawWidth = useMemo(() => drawShare(match?.spectator_book?.totals), [match])
  const odds = useMemo(() => {
    if (!match || settled) return null
    const t = match.spectator_book?.totals || {}
    const a = Number(t.a ?? 0) || 0
    const b = Number(t.b ?? 0) || 0
    const d = Number(t.draw ?? 0) || 0
    const sidePot = a + b
    return {
      raja: payoutPerDollar(sidePot, a),
      nero: payoutPerDollar(sidePot, b),
      draw: payoutPerDollar(sidePot + d, d),
    }
  }, [match, settled])

  // Side A/B names straight off the match record — works for any pair
  const nameA = agentName(match?.agent_a_id as string | undefined, 'Side A')
  const nameB = agentName(match?.agent_b_id as string | undefined, 'Side B')
  const aIsWhite =
    !match?.white_agent_id || match.white_agent_id === match?.agent_a_id

  const pot =
    Number(match?.pot_usdc ?? 0) ||
    Number(match?.stake_usdc ?? 0) * 2

  // ── clocks: names sit on their own side of the board, ticking ──
  const whiteName = aIsWhite ? nameA : nameB
  const blackName = aIsWhite ? nameB : nameA
  const plies = match?.moves?.length || 0
  const toMove: 'white' | 'black' = plies % 2 === 0 ? 'white' : 'black'
  const running = match?.status === 'playing' && !settled

  async function placeBet() {
    if (!match?.match_id || settled) return
    setBetBusy(true)
    setNotice(null)
    setTicket(null)
    try {
      const res = await api('/api/agentic/spectator-bet', {
        method: 'POST',
        body: JSON.stringify({
          match_id: match.match_id,
          side: betSide,
          amount: betAmount,
        }),
      })
      const d = (res.data || {}) as {
        pending?: boolean
        approval_id?: string
        match_id?: string
        balance?: number
        amount?: number
        message?: string
        error?: string
      }
      if (!res.ok) {
        setTicket({
          state: 'failed',
          message: String(d.message || d.error || 'The bet did not go through. Try again.'),
        })
        return
      }
      if (d.pending && d.approval_id) {
        setTicket({
          state: 'pending',
          approval_id: String(d.approval_id),
          amount: betAmount,
          side: betSide,
          match_id: String(d.match_id || match.match_id),
          message: String(d.message || ''),
        })
        return
      }
      setTicket({
        state: 'printed',
        amount: Number(d.amount ?? betAmount),
        side: betSide,
        match_id: String(d.match_id || match.match_id),
        balance: d.balance != null ? Number(d.balance) : undefined,
      })
      if (d.balance != null) setMe((m) => (m ? { ...m, balance: Number(d.balance) } : m))
    } catch {
      setTicket({ state: 'failed', message: 'Network hiccup — nothing was charged. Try again.' })
    } finally {
      setBetBusy(false)
    }
  }

  return (
    <BookShell title="The chess table">
      <div style={{ maxWidth: '46rem', margin: '0 auto', padding: '0 1rem 3.5rem' }}>
        <p className="bk-lede" style={{ margin: '0 0 1.5rem' }}>
          Three house agents — Raja, Nero and Sheila — each a chess engine with
          its own style: Raja and Nero run Stockfish, Sheila runs Ethereal. They
          take turns at the table on real clocks, playing for test USDC on Arc
          testnet, and the house pays the winner when the game ends.{' '}
          <em>Leaving this page does not pause the game.</em>
        </p>
        <NextTableLine schedule={schedule} match={match} settled={settled} />

        <div className="rm-stack-lg">
          {offline && !match ? (
          <div className="rm-card rm-card-hero ar-offline" role="status">
            <span className="bk-stamp">HOUSE OFFLINE</span>
            <p className="ar-note">
              <strong>The house is offline — back soon.</strong> The agents’ table runs on
              the house server and it isn’t answering right now. This page keeps checking
              on its own; no bets are taken while the house is down.
            </p>
          </div>
          ) : (
          <div className="rm-card rm-card-hero">
            <div className="ar-side">
              <span className="ar-player">
                <strong>{blackName.toUpperCase()}</strong> · black
              </span>
              <ChessClock
                clock={match?.clock?.black}
                active={running && toMove === 'black'}
                receivedAt={receivedAt}
              />
            </div>
            <div className="ar-board-wrap">
              <div className="ar-board-frame">
                <div className="ar-ranks">
                  {[8, 7, 6, 5, 4, 3, 2, 1].map((r) => (
                    <span key={r}>{r}</span>
                  ))}
                </div>
                <div className="ar-board-stack">
                  <Board grid={grid} flipped={false} />
                  <LastMoveArrow moves={Array.isArray(match?.moves) ? match!.moves! : []} />
                </div>
                <div className="ar-files">
                  {FILES.map((f) => (
                    <span key={f}>{f}</span>
                  ))}
                </div>
              </div>
            </div>
            <div className="ar-side ar-side-bottom">
              <span className="ar-player">
                <strong>{whiteName.toUpperCase()}</strong> · white
              </span>
              <ChessClock
                clock={match?.clock?.white}
                active={running && toMove === 'white'}
                receivedAt={receivedAt}
              />
            </div>
            <StatusLine match={match} loading={loading} />
            {stale ? (
              <p className="ar-note" style={{ opacity: 0.75 }}>
                {offline
                  ? 'The house is offline — this is the last board we saw. Back soon; the page keeps checking.'
                  : 'Connection hiccup — reconnecting, the board may be a move behind.'}
              </p>
            ) : null}
            {!stale && lastSettled ? (
              <p className="ar-note" style={{ opacity: 0.75 }}>
                No table live right now — you're looking at the last finished game.
              </p>
            ) : null}
            <div className="ar-ledger">
              <div>
                <span className="v2-mono-dim">POT</span>
                <strong>{pot > 0 ? `${pot.toFixed(2)} USDC` : '—'}</strong>
              </div>
              <div>
                <span className="v2-mono-dim">MOVES</span>
                <strong>{moves.length}</strong>
              </div>
              <div>
                <span className="v2-mono-dim">TABLE</span>
                <strong>{match?.match_id ? match.match_id.slice(0, 10) : '—'}</strong>
              </div>
            </div>
          </div>
          )}

          <div className="rm-card">
            <p className="rm-section-title">Bet on the game</p>
            {me ? (
              <>
                <p className="rm-muted" style={{ margin: '0 0 0.9rem' }}>
                  Money comes from your play wallet ({me.balance != null ? `$${Number(me.balance).toFixed(2)}` : 'check the wallet page'}).
                  {offline ? (
                    <>
                      {' '}
                      <strong>The house is offline — betting reopens when it’s back.</strong>
                    </>
                  ) : settled || !match?.match_id ? (
                    <>
                      {' '}
                      <strong>This table is finished — betting is closed.</strong>
                    </>
                  ) : (
                    <>
                      {' '}
                      Betting on table <span className="rm-code">{match.match_id.slice(0, 12)}</span> — {whiteName} (white) vs {blackName} (black), live.
                    </>
                  )}
                </p>
                <div className="ar-bet-row">
                  <div className="ar-bet-sides">
                    <button
                      type="button"
                      className={`rm-tile ${betSide === 'a' ? 'rm-tile-active' : ''}`}
                      onClick={() => setBetSide('a')}
                    >
                      {nameA}
                      {odds?.raja ? (
                        <span className="ar-tile-odds">pays about ${odds.raja.toFixed(2)} per $1</span>
                      ) : null}
                    </button>
                    <button
                      type="button"
                      className={`rm-tile ${betSide === 'b' ? 'rm-tile-active' : ''}`}
                      onClick={() => setBetSide('b')}
                    >
                      {nameB}
                      {odds?.nero ? (
                        <span className="ar-tile-odds">pays about ${odds.nero.toFixed(2)} per $1</span>
                      ) : null}
                    </button>
                    <button
                      type="button"
                      className={`rm-tile ${betSide === 'draw' ? 'rm-tile-active' : ''}`}
                      onClick={() => setBetSide('draw')}
                    >
                      Draw
                      {odds?.draw ? (
                        <span className="ar-tile-odds">pays about ${odds.draw.toFixed(2)} per $1</span>
                      ) : null}
                    </button>
                  </div>
                  <label className="rm-label" htmlFor="ar-amount">
                    How much
                  </label>
                  <input
                    id="ar-amount"
                    className="rm-input"
                    type="number"
                    min={0.25}
                    max={50}
                    step={0.25}
                    value={betAmount}
                    onChange={(e) => setBetAmount(Number(e.target.value))}
                  />
                  <button
                    type="button"
                    className="rm-btn rm-btn-primary"
                    disabled={betBusy || offline || !match?.match_id || pot <= 0 || settled}
                    onClick={placeBet}
                  >
                    {betBusy ? 'Placing…' : 'Place the bet'}
                  </button>
                </div>
                {ticket?.state === 'settled' ? (
                  <div className="bk-slip" style={{ margin: '0.9rem 0 0', opacity: 0.95 }}>
                    <div className="bk-slip-head">
                      <span>
                        {ticket.outcome === 'win'
                          ? '✅ Ticket paid'
                          : ticket.outcome === 'refund'
                            ? '↩️ Ticket refunded'
                            : '📻 Ticket settled'}
                      </span>
                      <span>${ticket.amount.toFixed(2)}</span>
                    </div>
                    <div className="bk-slip-row">
                      <span>Table</span>
                      <strong>{ticket.match_id.slice(0, 12) || '—'}</strong>
                    </div>
                    {ticket.payout ? (
                      <div className="bk-slip-row">
                        <span>Paid out</span>
                        <strong className="bk-ink">${ticket.payout.toFixed(2)}</strong>
                      </div>
                    ) : null}
                    <p className="rm-muted" style={{ margin: '0.55rem 0 0', fontSize: '0.85rem' }}>
                      {ticket.outcome === 'win'
                        ? `Your ticket hit — $${(ticket.payout ?? 0).toFixed(2)} is on the play wallet.`
                        : ticket.outcome === 'refund'
                          ? 'Nobody backed the result, or the table was called off — your stake is back on the play wallet.'
                          : 'Your side didn\'t hit this time. The line at the top says when the next table seats.'}
                    </p>
                  </div>
                ) : ticket?.state === 'pending' ? (
                  <div className="bk-slip" style={{ margin: '0.9rem 0 0' }}>
                    <div className="bk-slip-head">
                      <span>Ticket pending</span>
                      <span>${ticket.amount.toFixed(2)}</span>
                    </div>
                    <div className="bk-slip-row">
                      <span>Table</span>
                      <strong>{ticket.match_id.slice(0, 12) || '—'}</strong>
                    </div>
                    <div className="bk-slip-row">
                      <span>Side</span>
                      <strong>{ticket.side === 'a' ? nameA : ticket.side === 'b' ? nameB : 'Draw'}</strong>
                    </div>
                    <p className="rm-muted" style={{ margin: '0.55rem 0 0', fontSize: '0.85rem' }}>
                      Open the bot and tap <strong>Yes</strong> — your ticket prints the moment you
                      approve. Nothing is charged until you do.{ticket.message ? ` ${ticket.message}` : ''}
                    </p>
                  </div>
                ) : ticket?.state === 'printed' ? (
                  <div className="bk-slip" style={{ margin: '0.9rem 0 0' }}>
                    <div className="bk-slip-head">
                      <span>Ticket printed</span>
                      <span>${ticket.amount.toFixed(2)}</span>
                    </div>
                    <div className="bk-slip-row">
                      <span>On</span>
                      <strong>{ticket.side === 'a' ? nameA : ticket.side === 'b' ? nameB : 'Draw'}</strong>
                    </div>
                    <div className="bk-slip-row">
                      <span>Table</span>
                      <strong>{ticket.match_id.slice(0, 12) || '—'}</strong>
                    </div>
                    {ticket.balance != null ? (
                      <div className="bk-slip-row">
                        <span>Wallet</span>
                        <strong className="bk-ink">${ticket.balance.toFixed(2)}</strong>
                      </div>
                    ) : null}
                    <p className="rm-muted" style={{ margin: '0.55rem 0 0', fontSize: '0.85rem' }}>
                      This ticket settles when the game ends — watch the clocks above.
                    </p>
                  </div>
                ) : ticket?.state === 'failed' ? (
                  <p className="rm-err" style={{ margin: '0.75rem 0 0' }}>
                    {ticket.message}
                  </p>
                ) : null}
                <p className="rm-muted" style={{ fontSize: '0.75rem', margin: '0.75rem 0 0' }}>
                  Bets are test USDC and close after the opening (12 moves each).
                  If it ends in a draw, draw tickets win the pool — side bets on
                  either agent lose.
                </p>
                {notice ? <p className="rm-ok" style={{ margin: '0.75rem 0 0' }}>{notice}</p> : null}
              </>
            ) : authOpen ? (
              <div className="rm-stack">
                <TelegramLogin
                  botUsername={REMATCH_BOT_USERNAME}
                  onAuth={async () => {
                    setAuthOpen(false)
                    window.location.reload()
                  }}
                  onMissing={() => setNotice('Open the Telegram bot once first, then sign in here.')}
                />
                <a href={REMATCH_BOT_URL} target="_blank" rel="noreferrer" className="rm-btn rm-btn-ghost rm-btn-sm">
                  Open the bot
                </a>
                <WalletLogin intent="login" onAuth={() => window.location.reload()} />
              </div>
            ) : (
              <>
                <p className="rm-muted" style={{ margin: '0 0 0.9rem' }}>
                  Sign in with Telegram to place a bet. Same account as the bot —
                  same play wallet.
                </p>
                <button type="button" className="rm-btn rm-btn-primary" onClick={() => setAuthOpen(true)}>
                  Sign in to bet
                </button>
              </>
            )}
          </div>

          <div className="rm-card ar-odds-card">
            <div className="ar-odds-head">
              <strong>Live odds &amp; pot</strong>
              <span className="ar-odds-meta">
                <span className="ar-odds-dot"></span>
                {match?.spectator_book?.totals ? (
                  <>
                    <span className="ar-lex">{nameA}</span>
                    <span className="ar-lex ar-lex-dim">${Number(match.spectator_book.totals.a ?? 0).toFixed(2)}</span>
                    <span className="ar-lex">{nameB}</span>
                    <span className="ar-lex ar-lex-dim">${Number(match.spectator_book.totals.b ?? 0).toFixed(2)}</span>
                    <span className="ar-lex ar-lex-dim">draw</span>
                    <span className="ar-lex ar-lex-dim">${Number(match.spectator_book.totals.draw ?? 0).toFixed(2)}</span>
                  </>
                ) : null}
              </span>
            </div>            {odds ? (
              <div className="ar-odds-chart">
                <div className="ar-odds-grid">
                  <div className="ar-odds-row">
                    <span className="ar-od">{nameA}</span>
                    <span className="ar-od-bar">
                      <span className="ar-od-fill raja" style={{ width: `${Math.max(6, Math.min(100, (odds.raja ?? 0) * 80))}%` }} />
                    </span>
                    <span className="ar-od-val">{odds.raja ? `${odds.raja.toFixed(2)}` : '—'}</span>
                  </div>
                  <div className="ar-odds-row">
                    <span className="ar-od">{nameB}</span>
                    <span className="ar-od-bar">
                      <span className="ar-od-fill" style={{ width: `${Math.max(6, Math.min(100, (odds.nero ?? 0) * 80))}%` }} />
                    </span>
                    <span className="ar-od-val">{odds.nero ? `${odds.nero.toFixed(2)}` : '—'}</span>
                  </div>
                  <div className="ar-odds-row">
                    <span className="ar-od">Draw</span>
                    <span className="ar-od-bar">
                      <span className="ar-od-fill draw" style={{ width: drawWidth }} />
                    </span>
                    <span className="ar-od-val">{odds.draw ? `${odds.draw.toFixed(2)}` : '—'}</span>
                  </div>
                </div>
                <div className="ar-odds-pots">
                  {match?.spectator_book?.totals ? (
                    <>
                      <div>
                        <span className="ar-pk-label">Pot</span>
                        <strong className="ar-pk">
                          ${Number(match.spectator_book.totals.a ?? 0) + Number(match.spectator_book.totals.b ?? 0) + Number(match.spectator_book.totals.draw ?? 0)}
                          <span className="ar-pk-sub">test USDC · before fees</span>
                        </strong>
                      </div>
                      <div>
                        <span className="ar-pk-label">Draw pool</span>
                        <strong className="ar-pk">
                          ${Number(match.spectator_book.totals.draw ?? 0)}
                        </strong>
                      </div>
                    </>
                  ) : null}
                </div>
              </div>
            ) : null}
          </div>

          <div className="rm-card">
            <p className="rm-section-title">The moves so far</p>
            {moves.length === 0 ? (
              <p className="rm-muted" style={{ margin: 0 }}>
                No moves yet — the last game finished and the next one is warming up.
              </p>
            ) : (
              <div className="ar-movelog">
                {moves.map((san, i) => (
                  <span key={i} className="ar-move">
                    {i % 2 === 0 ? <b>{Math.floor(i / 2) + 1}.</b> : null} {san}
                  </span>
                ))}
              </div>
            )}
          </div>
        </div>

        <div className="rm-btn-row" style={{ maxWidth: '30rem', margin: '1.75rem auto 0' }}>
          <a href="/games" className="rm-btn rm-btn-ghost">
            All games
          </a>
          <a href="/how-it-works" className="rm-btn rm-btn-ghost">
            How it works
          </a>
        </div>
      </div>
    </BookShell>
  )
}
