'use client'

/**
 * Public Rematch leaderboard + open challenges.
 */
import { useEffect, useState } from 'react'
import Link from 'next/link'
import { LiveRoomsCard } from '@/components/rematch/LiveRoomsCard'
import { REMATCH_BOT_URL, REMATCH_GROUP_URL } from '@/lib/rematchLinks'

const BOT = REMATCH_BOT_URL
const FAUCET = 'https://faucet.circle.com/'

type LeaderRow = {
  rank: number
  tag: string
  name: string
  play_points: number
  reputation: number
  wins: number
  losses: number
  draws: number
  streak: number
  tier_label?: string
}

type OpenChallenge = {
  code: string
  stake: number
  game: string
  chain: string
  creator_tag: string
}

export default function RematchLeaderboardPage() {
  const [leaders, setLeaders] = useState<LeaderRow[]>([])
  const [opens, setOpens] = useState<OpenChallenge[]>([])
  const [err, setErr] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const res = await fetch('/api/rematch/public', { cache: 'no-store' })
        const data = await res.json().catch(() => ({}))
        if (cancelled) return
        if (!res.ok) {
          setErr(data.error || 'Failed to load')
          return
        }
        setLeaders(data.leaders || [])
        setOpens(data.open_challenges || [])
      } catch (e: any) {
        if (!cancelled) setErr(e?.message || 'Failed to load')
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [])

  return (
    <div style={{ maxWidth: '42rem', margin: '0 auto', padding: '2rem 1rem 3rem' }}>
      <div style={{ marginBottom: '1.75rem' }}>
        <p className="rm-section-title">Public board</p>
        <h1
          style={{
            margin: '0 0 0.5rem',
            fontSize: 'clamp(1.75rem, 5vw, 2.25rem)',
            fontWeight: 900,
            letterSpacing: '-0.03em',
          }}
        >
          <span style={{ color: '#34d399' }}>Leaderboard</span>
          <span style={{ color: '#fff' }}> & open matches</span>
        </h1>
        <p className="rm-muted" style={{ margin: '0 0 1rem', maxWidth: '28rem' }}>
          PLAY standings and open challenges. Play on Arc via web or Telegram.
        </p>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem' }}>
          <Link
            href="/app"
            className="rm-btn rm-btn-primary"
            style={{ width: 'auto', padding: '0.55rem 1rem', fontSize: '0.8rem' }}
          >
            Open app
          </Link>
          <a
            href={REMATCH_GROUP_URL}
            target="_blank"
            rel="noreferrer"
            className="rm-btn rm-btn-ghost"
            style={{ width: 'auto', padding: '0.55rem 1rem', fontSize: '0.8rem' }}
          >
            Live rooms
          </a>
          <a
            href={BOT}
            target="_blank"
            rel="noreferrer"
            className="rm-btn rm-btn-ghost"
            style={{ width: 'auto', padding: '0.55rem 1rem', fontSize: '0.8rem' }}
          >
            Open bot
          </a>
          <a
            href={FAUCET}
            target="_blank"
            rel="noreferrer"
            className="rm-btn rm-btn-ghost"
            style={{ width: 'auto', padding: '0.55rem 1rem', fontSize: '0.8rem' }}
          >
            Get USDC
          </a>
        </div>
      </div>

      <div style={{ marginBottom: '1.5rem' }}>
        <LiveRoomsCard variant="compact" />
      </div>

      {loading && (
        <div className="rm-stack" style={{ marginBottom: '1.5rem' }}>
          <div className="rm-skeleton" style={{ height: 120, borderRadius: 16 }} />
          <div className="rm-skeleton" style={{ height: 200, borderRadius: 16 }} />
        </div>
      )}

      {err && (
        <div className="rm-card rm-card-warn" style={{ marginBottom: '1.25rem' }}>
          <p className="rm-warn-text" style={{ margin: 0 }}>
            Could not load live data. Open the bot, or try again later.
          </p>
        </div>
      )}

      <div className="rm-stack-lg">
        <section className="rm-card">
          <h2 className="rm-h2" style={{ color: '#34d399', marginBottom: '0.85rem' }}>
            Open challenges
          </h2>
          {!loading && opens.length === 0 && (
            <p className="rm-muted" style={{ margin: 0 }}>
              No open public challenges right now. Create one in the app.
            </p>
          )}
          <ul style={{ listStyle: 'none', margin: 0, padding: 0 }} className="rm-stack">
            {opens.map((o) => (
              <li
                key={o.code}
                style={{
                  display: 'flex',
                  flexWrap: 'wrap',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  gap: 8,
                  padding: '0.75rem 0.9rem',
                  borderRadius: 12,
                  border: '1px solid rgba(255,255,255,0.06)',
                  background: 'rgba(0,0,0,0.25)',
                  fontSize: '0.875rem',
                }}
              >
                <span>
                  <code style={{ color: '#34d399', fontWeight: 800 }}>{o.code}</code>
                  <span style={{ color: '#6b7280' }}> · </span>
                  <span style={{ color: '#fff', fontWeight: 700 }}>${o.stake}</span>
                  <span style={{ color: '#6b7280' }}> · {o.game}</span>
                </span>
                <span style={{ color: '#9ca3af' }}>@{o.creator_tag}</span>
              </li>
            ))}
          </ul>
        </section>

        <section className="rm-card">
          <h2 className="rm-h2" style={{ color: '#34d399', marginBottom: '0.85rem' }}>
            PLAY leaderboard
          </h2>
          {!loading && leaders.length === 0 && (
            <p className="rm-muted" style={{ margin: 0 }}>
              No ranked players yet — win a match.
            </p>
          )}
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', fontSize: '0.875rem', borderCollapse: 'collapse' }}>
              <thead>
                <tr style={{ textAlign: 'left', color: '#6b7280', borderBottom: '1px solid rgba(255,255,255,0.06)' }}>
                  <th style={{ padding: '0.5rem 0.4rem' }}>#</th>
                  <th style={{ padding: '0.5rem 0.4rem' }}>Player</th>
                  <th style={{ padding: '0.5rem 0.4rem' }}>PLAY</th>
                  <th style={{ padding: '0.5rem 0.4rem' }}>Rep</th>
                  <th style={{ padding: '0.5rem 0.4rem' }}>W/L</th>
                </tr>
              </thead>
              <tbody>
                {leaders.map((r) => (
                  <tr
                    key={r.rank + r.tag}
                    style={{ borderBottom: '1px solid rgba(255,255,255,0.04)', color: '#d1d5db' }}
                  >
                    <td style={{ padding: '0.7rem 0.4rem', color: '#6b7280' }}>{r.rank}</td>
                    <td style={{ padding: '0.7rem 0.4rem' }}>
                      <span style={{ color: '#fff', fontWeight: 600 }}>@{r.tag}</span>
                      {r.streak > 0 && (
                        <span style={{ color: '#fb923c', fontSize: '0.75rem', marginLeft: 6 }}>
                          🔥{r.streak}
                        </span>
                      )}
                    </td>
                    <td style={{ padding: '0.7rem 0.4rem', color: '#34d399', fontWeight: 700 }}>
                      {r.play_points.toLocaleString()}
                    </td>
                    <td style={{ padding: '0.7rem 0.4rem' }}>{r.reputation}</td>
                    <td style={{ padding: '0.7rem 0.4rem' }}>
                      {r.wins}/{r.losses}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        <p style={{ textAlign: 'center', margin: 0 }}>
          <Link href="/" className="rm-muted" style={{ fontSize: '0.8rem' }}>
            About Boardman
          </Link>
        </p>
      </div>
    </div>
  )
}
