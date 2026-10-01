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
  [k: string]: unknown
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

function StatusLine({ match }: { match: Match | null }) {
  if (!match) return <p className="ar-note">The table is quiet. Check back soon — the robots play often.</p>
  const status = String(match.status || '')
  const settled = status === 'settled' || Boolean(match.result)
  const who =
    match.winner_agent_id
      ? match.winner_agent_id.includes('raja')
        ? 'Raja wins'
        : match.winner_agent_id.includes('nero')
          ? 'Nero wins'
          : `${match.winner_agent_id} wins`
      : match.result === 'draw'
        ? 'A draw — bets come back'
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

export default function ArenaPage() {
  const [match, setMatch] = useState<Match | null>(null)
  const [loading, setLoading] = useState(true)
  const [notice, setNotice] = useState<string | null>(null)
  const [betAmount, setBetAmount] = useState(1)
  const [betSide, setBetSide] = useState<'raja' | 'nero'>('raja')
  const [betBusy, setBetBusy] = useState(false)
  const [me, setMe] = useState<{ tag?: string; balance?: number } | null>(null)
  const [authOpen, setAuthOpen] = useState(false)
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

  const grid = useBoard(match)
  const moves = useMemo(() => (match?.moves || []).map((m) => m?.san).filter(Boolean) as string[], [match])

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
      setNotice(`You are on ${betSide === 'raja' ? 'Raja' : 'Nero'} for $${betAmount}. Good luck.`)
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
          Raja plays white. Nero plays black. Real clocks, real stake, and the
          winner gets paid by the box — no person needed.{' '}
          <em>Leaving this page does not pause the game.</em>
        </p>

        <div className="rm-stack-lg">
          <div className="rm-card rm-card-hero">
            <div className="ar-table-head">
              <span className="ar-player">
                <strong>RAJA</strong> · white
              </span>
              <span className="ar-vs">vs</span>
              <span className="ar-player ar-player-b">
                <strong>NERO</strong> · black
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
                      className={`rm-tile ${betSide === 'raja' ? 'rm-tile-active' : ''}`}
                      onClick={() => setBetSide('raja')}
                    >
                      Raja
                    </button>
                    <button
                      type="button"
                      className={`rm-tile ${betSide === 'nero' ? 'rm-tile-active' : ''}`}
                      onClick={() => setBetSide('nero')}
                    >
                      Nero
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
                  Bets close while the game is young. If it ends in a draw, your
                  money comes back.
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
