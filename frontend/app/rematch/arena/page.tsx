'use client'

/**
 * /arena — the live robot chess table, rebuilt as a React page in the book.
 * Replaced the retired public/agentic/arena.html. Polls /api/agentic/house-play (which
 * proxies the Stack house floor), renders moves via chess.js, and posts
 * spectator bets to /api/agentic/spectator-bet.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Chess, type Square } from 'chess.js'
import { BookShell } from '@/components/rematch/BookShell'
import { TelegramLogin } from '@/components/TelegramLogin'
import { api } from '@/lib/appClient'
import { REMATCH_BOT_URL } from '@/lib/rematchLinks'

const FILES = ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h'] as const

type MatchMove = { ply?: number; side?: string; san?: string }
type Match = {
  match_id?: string
  status?: string
  result?: string
  winner_agent_id?: string
  agent_a_id?: string
  agent_b_id?: string
  stake_usdc?: number
  pot_usdc?: number
  moves?: MatchMove[]
  fen?: string
  ply?: number
  board?: string[]
  spectator_book?: {
    totals?: { a?: string | number; b?: string | number; draw?: string | number }
    status?: string
  }
  [k: string]: unknown
}

type ScheduleInfo = {
  ok: boolean
  enabled?: boolean
  cadence_sec?: number
  every_minutes?: number
}

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

function agentName(id: string | undefined, fallback: string): string {
  const s = String(id || '')
  if (s.includes('raja')) return 'Raja'
  if (s.includes('nero')) return 'Nero'
  if (s.includes('sheila')) return 'Sheila'
  return fallback
}

function StatusLine({ match }: { match: Match | null }) {
  if (!match) return <p className="ar-note">The table is quiet. Check back soon — the robots play often.</p>
  const status = String(match.status || '')
  const settled = status === 'settled' || Boolean(match.result)
  const who = match.winner_agent_id
    ? `${agentName(match.winner_agent_id, 'The house agent')} wins`
    : match.result === 'draw'
      ? 'A draw — draw tickets win, side bets lose'
      : ''
  return (
    <p className="ar-note">
      {settled ? (
        <>
          Game over. <strong>{who || 'Result in'}</strong>
        </>
      ) : (
        <>
          <strong>Playing now</strong> — move {Array.isArray(match.moves) ? match.moves.length : 0}
        </>
      )}
    </p>
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

export default function ArenaPage() {
  const [match, setMatch] = useState<Match | null>(null)
  const [loading, setLoading] = useState(true)
  const [notice, setNotice] = useState<string | null>(null)
  const [betAmount, setBetAmount] = useState(1)
  const [betSide, setBetSide] = useState<'a' | 'b' | 'draw'>('a')
  const [betBusy, setBetBusy] = useState(false)
  const [me, setMe] = useState<{ tag?: string; balance?: number } | null>(null)
  const [authOpen, setAuthOpen] = useState(false)
  const [schedule, setSchedule] = useState<ScheduleInfo | null>(null)
  const pollRef = useRef<number | null>(null)

  const load = useCallback(async () => {
    try {
      const res = await fetch('/api/agentic/house-play', { cache: 'no-store' })
      const data = await res.json().catch(() => ({}))
      if (data.ok && data.match_id) {
        setMatch({ ...data.match, match_id: data.match_id, status: data.status })
      } else {
        setMatch(null)
      }
    } catch {
      setMatch(null)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
    pollRef.current = window.setInterval(load, 4000)
    return () => {
      if (pollRef.current) window.clearInterval(pollRef.current)
    }
  }, [load])

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

  useEffect(() => {
    let dead = false
    fetch('/api/agentic/house-schedule', { cache: 'no-store' })
      .then((r) => r.json())
      .then((s: ScheduleInfo) => {
        if (!dead) setSchedule(s)
      })
      .catch(() => {})
    return () => {
      dead = true
    }
  }, [])

  const grid = useBoard(match)
  const moves = useMemo(() => (match?.moves || []).map((m) => m?.san).filter(Boolean) as string[], [match])

  const settled = match?.status === 'settled' || Boolean(match?.result)
  const drawWidth = useMemo(() => {
    if (!match?.spectator_book?.totals) return null
    const d = Number(match.spectator_book.totals.draw ?? 0)
    const a = Number(match.spectator_book.totals.a ?? 0)
    const b = Number(match.spectator_book.totals.b ?? 0)
    const total = a + b
    if (total <= 0) return null
    return (d / total) * 100
  }, [match])
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

  async function placeBet() {
    setBetBusy(true)
    setNotice(null)
    try {
      const res = await api('/api/agentic/spectator-bet', {
        method: 'POST',
        body: JSON.stringify({
          match_id: match?.match_id,
          side: betSide,
          amount: betAmount,
        }),
      })
      if (!res.ok) {
        setNotice(String(res.data?.error || 'The bet did not go through. Try again.'))
        return
      }
      setNotice(
        `You are on ${
          betSide === 'a' ? nameA : betSide === 'b' ? nameB : 'the draw'
        } for $${betAmount}. Good luck.`
      )
    } catch {
      setNotice('Network hiccup. Try again.')
    } finally {
      setBetBusy(false)
    }
  }

  return (
    <BookShell title="The chess table">
      <div style={{ maxWidth: '46rem', margin: '0 auto', padding: '0 1rem 3.5rem' }}>
        <p className="bk-lede" style={{ margin: '0 0 1.5rem' }}>
          Two house robots, three minds, two different engines. Real clocks,
          real stake, and the winner gets paid by the box — no person needed.{' '}
          <em>Leaving this page does not pause the game.</em>
        </p>
        {schedule?.ok ? (
          <p className="rm-muted" style={{ fontSize: '0.8rem', margin: '-0.9rem 0 1.5rem' }}>
            {schedule.enabled
              ? schedule.cadence_sec
                ? `The house seats a fresh table about every ${schedule.every_minutes} minutes — roughly ${Math.floor(86400 / (schedule.cadence_sec || 1))} games a day.`
                : 'Games run back-to-back, around the clock.'
              : 'The house floor is paused — the next table opens when the desk turns it back on.'}
          </p>
        ) : null}

        <div className="rm-stack-lg">
          <div className="rm-card rm-card-hero">
            <div className="ar-table-head">
              <span className="ar-player">
                <strong>{nameA.toUpperCase()}</strong> · {aIsWhite ? 'white' : 'black'}
              </span>
              <span className="ar-vs">vs</span>
              <span className="ar-player ar-player-b">
                <strong>{nameB.toUpperCase()}</strong> · {aIsWhite ? 'black' : 'white'}
              </span>
            </div>
            <div className="ar-board-wrap">
              <Board grid={grid} flipped={false} />
            </div>
            <StatusLine match={match} />
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

          <div className="rm-card">
            <p className="rm-section-title">Bet on the game</p>
            {me ? (
              <>
                <p className="rm-muted" style={{ margin: '0 0 0.9rem' }}>
                  Money comes from your play wallet ({me.balance != null ? `$${Number(me.balance).toFixed(2)}` : 'check the wallet page'}).
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
                    disabled={betBusy || !match?.match_id || pot <= 0}
                    onClick={placeBet}
                  >
                    {betBusy ? 'Placing…' : 'Place the bet'}
                  </button>
                </div>
                <p className="rm-muted" style={{ fontSize: '0.75rem', margin: '0.75rem 0 0' }}>
                  Bets close while the game is young. If it ends in a draw,
                  draw tickets win the pool — side bets on either robot lose.
                </p>
                {notice ? <p className="rm-ok" style={{ margin: '0.75rem 0 0' }}>{notice}</p> : null}
              </>
            ) : authOpen ? (
              <div className="rm-stack">
                <TelegramLogin
                  botUsername={process.env.NEXT_PUBLIC_BOT_USERNAME || 'myboardmanOfficialBot'}
                  onAuth={async () => {
                    setAuthOpen(false)
                    window.location.reload()
                  }}
                  onMissing={() => setNotice('Open the Telegram bot once first, then sign in here.')}
                />
                <a href={REMATCH_BOT_URL} target="_blank" rel="noreferrer" className="rm-btn rm-btn-ghost rm-btn-sm">
                  Open the bot
                </a>
              </div>
            ) : (
              <>
                <p className="rm-muted" style={{ margin: '0 0 0.9rem' }}>
                  Sign in with Telegram to place a bet. Same account as the bot —
                  same money.
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
                      <span className="ar-od-fill draw" style={{ width: drawWidth ?? '0%' }} />
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
                          <span className="ar-pk-sub">dec / 5% off</span>
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
