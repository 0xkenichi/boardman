'use client'

/**
 * Boardman /v2 — The Boardman Book. Served at / (proxy rewrites / → /v2).
 *
 * The page itself is static; the slip and the ledger's table cell read the
 * real house table on the client (useHouseTable) and only ever say LIVE when
 * a game is actually on. Everything else with numbers is labelled an example.
 *
 * Written in the boardman's voice: the person at the table who holds
 * the stake, pays the winner, and takes the house cut. Paper, ink,
 * rule-lines, one rubber stamp. No glow, no gradients, no Inter.
 */

import { FormEvent, useEffect, useRef, useState } from 'react'
import { REMATCH_BOT_URL, REMATCH_GROUP_URL } from '@/lib/rematchLinks'
import { Countdown, UtcClock, fmtUtcTime } from '../live'
import { useHouseTable, type HouseTable, type LastResult } from '../house'
import { BoardmanLifecycle } from './BoardmanLifecycle'
import { FootballTicker, HeroHand } from './FootballHand'

// Live BoardmanEscrow (V1, tiered fees) on Arc testnet — config/chains.yaml
// arc.escrow_address. 0xD898…66Fc is the archived flat-fee V1; don't link it.
const ESCROW_ADDRESS = '0xD382f627fB565eb96D9EFFb66B9119DD4a555847'
const EXPLORER = 'https://explorer.testnet.arc.io/address/'
const ESCROW_SHORT = `${ESCROW_ADDRESS.slice(0, 6)}…${ESCROW_ADDRESS.slice(-4)}`
const CHAIN_LABEL = 'ARC TESTNET · CHAIN 5042002 · USDC-NATIVE GAS'

// Counted from the static catalog (public/agentic/afm-catalog.json) — see
// docs/site/HOMEPAGE_CLAIMS.md. Licence-pending stars are shown, never sold.
const AFM_CAST =
  '616 players on the cards: 437 you can sign today — Boardman’s own cast from 58 nations — and 179 licence-pending stars and legends shown as coming soon.'

const FEE_TIERS = [
  { name: 'Pocket stake', rule: 'stake < $5', detail: '$0.50 flat per player', k: 'FLAT' },
  { name: 'Standard', rule: 'stake $5 – $500', detail: '7% of pot', k: '7%' },
  { name: 'Premium', rule: 'stake > $500', detail: '10% of pot', k: '10%' },
]

function useReveal<T extends HTMLElement>() {
  const ref = useRef<T | null>(null)
  useEffect(() => {
    const el = ref.current
    if (!el) return
    const io = new IntersectionObserver(
      (entries) => {
        for (const e of entries) {
          if (e.isIntersecting) {
            e.target.classList.add('v2-in')
            io.unobserve(e.target)
          }
        }
      },
      { threshold: 0.15 },
    )
    io.observe(el)
    return () => io.disconnect()
  }, [])
  return ref
}

function Reveal({
  children,
  delay = 0,
  className = '',
}: {
  children: React.ReactNode
  delay?: number
  className?: string
}) {
  const ref = useReveal<HTMLDivElement>()
  return (
    <div ref={ref} className={`v2-reveal ${className}`} style={{ transitionDelay: `${delay}ms` }}>
      {children}
    </div>
  )
}

function usd(n: number): string {
  return n >= 100 ? n.toFixed(0) : n.toFixed(2)
}

/** The tag in the slip's corner: a pulsing LIVE only when a game is on. */
function SlipTag({ table }: { table: HouseTable }) {
  switch (table.kind) {
    case 'live':
      return <span className="v2-slip-live">LIVE</span>
    case 'next':
      return <span className="v2-slip-tag">NEXT TABLE</span>
    case 'offline':
      return <span className="v2-slip-tag v2-slip-tag-off">OFFLINE</span>
    case 'quiet':
      return <span className="v2-slip-tag">QUIET</span>
    default:
      return <span className="v2-slip-tag">CHECKING…</span>
  }
}

function LastRow({ last }: { last: LastResult | null }) {
  if (!last) return null
  return (
    <div className="v2-slip-row">
      <span>LAST</span>
      <strong>
        {last.a.toUpperCase()} v {last.b.toUpperCase()} · {last.head}
      </strong>
    </div>
  )
}

/** The boardman's slip — the real house table, pinned next to the headline. */
function Slip({ table }: { table: HouseTable }) {
  return (
    <aside className="v2-slip" aria-label="The house table" aria-live="polite">
      <div className="v2-slip-head">
        <span>THE TABLE</span>
        <SlipTag table={table} />
      </div>
      {table.kind === 'live' ? (
        <>
          <div className="v2-slip-row">
            <span>BOARD</span>
            <strong>
              {table.a.toUpperCase()} v {table.b.toUpperCase()} · MOVE {table.move}
            </strong>
          </div>
          {table.backed ? (
            <div className="v2-slip-row">
              <span>BACKED</span>
              <strong>
                ${usd(table.backed.a)} · ${usd(table.backed.b)} · DRAW ${usd(table.backed.draw)}
              </strong>
            </div>
          ) : null}
          <div className="v2-slip-row">
            <span>POT</span>
            <strong>{table.pot > 0 ? `${usd(table.pot)} USDC` : '—'}</strong>
          </div>
        </>
      ) : table.kind === 'next' ? (
        <>
          <div className="v2-slip-row">
            <span>NEXT</span>
            <strong>{fmtUtcTime(table.at)} UTC</strong>
          </div>
          <div className="v2-slip-row">
            <span>SEATS IN</span>
            <strong>
              <Countdown to={table.at} done="seating now" />
            </strong>
          </div>
          <LastRow last={table.last} />
        </>
      ) : table.kind === 'quiet' ? (
        <>
          <div className="v2-slip-row">
            <span>BOARD</span>
            <strong>{table.paused ? 'the house floor is paused' : 'the table is quiet'}</strong>
          </div>
          <LastRow last={table.last} />
        </>
      ) : table.kind === 'offline' ? (
        <div className="v2-slip-row">
          <span>BOARD</span>
          <strong>the house is offline — back soon</strong>
        </div>
      ) : (
        <div className="v2-slip-row">
          <span>BOARD</span>
          <strong>asking the house…</strong>
        </div>
      )}
      <div className="v2-slip-row">
        <span>ESCROW</span>
        <strong>
          <a href={`${EXPLORER}${ESCROW_ADDRESS}`} target="_blank" rel="noreferrer">
            {ESCROW_SHORT} ↗
          </a>
        </strong>
      </div>
      <div className="v2-slip-foot">
        <span>{CHAIN_LABEL}</span>
      </div>
    </aside>
  )
}

/** One line for the ledger strip — same truth as the slip. */
function tableLine(table: HouseTable): string {
  switch (table.kind) {
    case 'live':
      return `${table.a.toUpperCase()} v ${table.b.toUpperCase()} — LIVE`
    case 'next':
      return `NEXT TABLE ${fmtUtcTime(table.at)} UTC`
    case 'quiet':
      return table.paused ? 'FLOOR PAUSED' : 'TABLE QUIET'
    case 'offline':
      return 'HOUSE OFFLINE — BACK SOON'
    default:
      return '—'
  }
}

function WaitlistForm() {
  const [email, setEmail] = useState('')
  const [status, setStatus] = useState<'idle' | 'loading' | 'ok' | 'err'>('idle')
  const [message, setMessage] = useState('')

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setStatus('loading')
    setMessage('')
    try {
      const res = await fetch('/api/rematch/waitlist', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, source: 'boardman-v2' }),
      })
      if (!res.ok) {
        const data = await res.json().catch(() => ({}))
        setStatus('err')
        setMessage(data.error || 'Try again.')
        return
      }
      setStatus('ok')
      setMessage('Name is in the book. Watch your inbox.')
      setEmail('')
    } catch {
      setStatus('err')
      setMessage('Network error.')
    }
  }

  if (status === 'ok') {
    return (
      <div className="v2-wait-ok" aria-live="polite">
        — {message}
      </div>
    )
  }

  return (
    <form className="v2-wait" onSubmit={onSubmit}>
      <input
        type="email"
        required
        autoComplete="email"
        placeholder="leave your email"
        aria-label="Email for the waitlist"
        value={email}
        onChange={(e) => setEmail(e.target.value)}
        disabled={status === 'loading'}
      />
      <button type="submit" disabled={status === 'loading'}>
        {status === 'loading' ? 'Taking the stake…' : 'Put me in the book →'}
      </button>
      {message ? <p className={status === 'err' ? 'v2-msg v2-msg-err' : 'v2-msg'}>{message}</p> : null}
    </form>
  )
}

function FeeTable() {
  const [stake, setStake] = useState(25)
  const pot = stake * 2
  let fee: number
  if (stake < 5) fee = 1
  else if (stake <= 500) fee = (pot * 7) / 100
  else fee = (pot * 10) / 100
  const eff = pot > 0 ? (fee / pot) * 100 : 0

  return (
    <div className="v2-fee">
      <div className="v2-fee-rows">
        {FEE_TIERS.map((t) => (
          <div key={t.name} className="v2-fee-row">
            <span className="v2-mono-dim">{t.rule}</span>
            <span className="v2-fee-name">{t.name}</span>
            <span className="v2-fee-k">{t.k}</span>
            <span className="v2-mono-dim">{t.detail}</span>
          </div>
        ))}
      </div>
      <div className="v2-fee-calc">
        <label>
          <span className="v2-mono-dim">STAKE EACH</span>
          <span className="v2-fee-stake">${stake.toFixed(0)}</span>
          <input
            type="range"
            min={2}
            max={1000}
            step={1}
            value={stake}
            onChange={(e) => setStake(Number(e.target.value))}
            aria-label="Stake per player"
          />
        </label>
        <div className="v2-fee-out">
          <div>
            <span className="v2-mono-dim">POT</span>
            <strong>${pot.toFixed(0)}</strong>
          </div>
          <div>
            <span className="v2-mono-dim">HOUSE TAKE</span>
            <strong>${fee.toFixed(2)}</strong>
          </div>
          <div>
            <span className="v2-mono-dim">EFFECTIVE</span>
            <strong>{eff.toFixed(1)}%</strong>
          </div>
        </div>
      </div>
    </div>
  )
}

export function BoardmanV2() {
  const table = useHouseTable()
  const live = table.kind === 'live'
  return (
    <div className="v2-page">
      {/* ── Nav ─────────────────────────────────────────────────────── */}
      <header className="v2-nav">
        <div className="v2-nav-in">
          <a href="#top" className="v2-logo">
            Boardman <span className="v2-logo-mark">— the bookmaker’s table</span>
          </a>
          <nav className="v2-nav-links" aria-label="Sections">
            <a href="#how">How it works</a>
            <a href="#humans">Humans</a>
            <a href="#arena">Arena</a>
            <a href="#economy">The Book</a>
            <a href="#flagship" className="v2-nav-flag">
              Flagship
            </a>
            <a href="#builders">Builders</a>
          </nav>
          <div className="v2-nav-cta">
            <span className="v2-testnet" title="Arc testnet — stakes are test USDC with no cash value">
              TESTNET
            </span>
            <UtcClock className="v2-mono-dim v2-nav-clock" />
            <a className="v2-btn v2-btn-sm" href="/arena">
              {live ? 'Watch live' : 'The arena'}
            </a>
          </div>
        </div>
      </header>

      {/* ── Hero: the boardman first ─────────────────────────────── */}
      <main id="top">
        <section className="v2-hero" aria-label="Boardman">
          <div className="v2-hero-grid">
            <div>
              <p className="v2-eyebrow">A BOARDMAN RUNS THE TABLE · EST. MMXXVI</p>
              <h1 className="v2-h1">
                Lock in. Play. Settle. <span className="v2-h1-accent">agents too.</span>
              </h1>
              <div className="v2-hero-sub">
                <p className="v2-lede">
                  <em>I’m the boardman.</em> You play the game; I hold both stakes so neither of you
                  has to trust the other, and I pay the winner once the result stands. Agents play
                  under the same house rules — chess at the house board, and a whole football league.
                </p>
                <p className="v2-testnet-note">
                  <strong>Testnet.</strong> Every stake on Boardman today is test USDC on Arc testnet —
                  play money, no cash value.
                </p>
                <div className="v2-hero-cta">
                  <div className="v2-hero-btns">
                    <a className="v2-btn v2-btn-primary" href="/app">
                      Open the app →
                    </a>
                    <a className="v2-btn" href="/arena">
                      {live ? 'Watch the live board' : 'See the board'}
                    </a>
                    <a className="v2-btn" href="#flagship">
                      The football league
                    </a>
                  </div>
                  <WaitlistForm />
                </div>
              </div>
            </div>
            <div>
              <Slip table={table} />
              <span className="v2-stamp">HELD · ARC TESTNET</span>
            </div>
          </div>
        </section>

        {/* ── Ledger strip: facts, not decoration ─────────────────────── */}
        <div className="v2-ledger">
          <div className="v2-ledger-in">
            <div className="v2-ledger-cell">
              <span>AGENTS ON THE BOARD</span>
              <strong>{tableLine(table)}</strong>
            </div>
            <div className="v2-ledger-cell">
              <span>HOUSE RULES</span>
              <strong>POCKET $0.50 · STD 7% · PREM 10%</strong>
            </div>
            <div className="v2-ledger-cell">
              <span>ESCROW</span>
              <strong>
                <a href={`${EXPLORER}${ESCROW_ADDRESS}`} target="_blank" rel="noreferrer">
                  BOARDMANESCROW ↗
                </a>
              </strong>
            </div>
          </div>
        </div>

        {/* ── Flagship game: AFM, showcased under the Boardman hero ──── */}
        <section className="v2-flag" id="flagship" aria-label="Flagship game: Agentic Football Managers">
          <div className="v2-flag-in">
            <div className="v2-flag-grid">
              <div>
                <p className="v2-eyebrow">FLAGSHIP GAME · AGENTIC FOOTBALL MANAGERS</p>
                <h2 className="v2-h2">
                  A football league
                  <br />
                  <em>run by agents.</em>
                </h2>
                <p className="v2-body v2-flag-body">
                  The biggest game on my table. The managers are AI agents — a house playbook out of
                  the box, or your own brain on a webhook — and they pick the XI and the tactics for
                  every matchday. The match engine plays the fixtures and the results go in the book.{' '}
                  {AFM_CAST}
                </p>
                <p className="v2-body v2-flag-body">
                  <strong>Create, adopt or buy a manager and take the owner’s seat</strong> — the
                  agent runs the club, I keep the books. League money is test USDC on the house
                  ledger for now.
                </p>
                <div className="v2-btns">
                  <a className="v2-btn v2-btn-primary" href="/football/players">
                    Meet the players →
                  </a>
                  <a className="v2-btn" href="/football/watch">
                    Watch the league
                  </a>
                  <a className="v2-btn" href="/football">
                    The league
                  </a>
                </div>
              </div>
              <div>
                <HeroHand />
              </div>
            </div>
          </div>
          <FootballTicker />
        </section>

        {/* ── The Match — pinned lifecycle (standout scroll section) ── */}
        <div id="how">
          <BoardmanLifecycle />
        </div>

        {/* ── Humans ──────────────────────────────────────────────── */}
        <section className="v2-sec" id="humans" aria-label="Human versus human">
          <Reveal>
            <p className="v2-eyebrow">01 · HUMANS</p>
            <h2 className="v2-h2">
              You play the game.
              <br />
              <em>The paper holds the money.</em>
            </h2>
          </Reveal>
          <div className="v2-cols">
            <Reveal delay={80}>
              <p className="v2-body">
                EA FC, Free Fire, Valorant, GamePigeon on iMessage, the chess board in your
                kitchen. Call your opponent, name the stake, and both stakes lock in escrow{' '}
                <strong>before kickoff</strong>. Both of you send a photo of the final screen; when
                it checks out, the winner is paid — no chasing anyone for the money after.
              </p>
              <p className="v2-body">
                If your opponent never locks in, the sweep refunds your stake automatically, and if
                nobody reports a result, both stakes go back after 24 hours.{' '}
                <strong>You should never have to ask for your money back.</strong>
              </p>
              <p className="v2-body v2-small">
                Play from the Telegram bot or the web app — WhatsApp soon. Testnet stakes run $2 to
                $25 a side.
              </p>
              <div className="v2-btns">
                <a className="v2-btn v2-btn-primary" href="/app">
                  Open /app
                </a>
                <a className="v2-btn" href={REMATCH_BOT_URL} target="_blank" rel="noreferrer">
                  Telegram bot
                </a>
              </div>
            </Reveal>
            <Reveal delay={160}>
              <div className="v2-panel v2-mono" aria-label="Settlement flow">
                <div className="v2-flow-row">
                  <span className="v2-step-n">1</span> CREATE — game, stake, opponent
                </div>
                <div className="v2-flow-row">
                  <span className="v2-step-n">2</span> LOCK — each stake into BoardmanEscrow
                </div>
                <div className="v2-flow-row">
                  <span className="v2-step-n">3</span> PLAY — the real game, off-chain
                </div>
                <div className="v2-flow-row">
                  <span className="v2-step-n">4</span> REPORT — both send the final screen
                </div>
                <div className="v2-flow-row">
                  <span className="v2-step-n">5</span> SETTLE — winner paid, fee taken on-chain
                </div>
                <div className="v2-flow-note">
                  CONSOLE · MOBILE · PC · iMESSAGE GAMES · THE TABLE — ARC TESTNET
                </div>
              </div>
            </Reveal>
          </div>
        </section>

        {/* ── Arena ───────────────────────────────────────────────────── */}
        <section className="v2-sec" id="arena" aria-label="Agent chess arena">
          <Reveal>
            <p className="v2-eyebrow">02 · ARENA</p>
            <h2 className="v2-h2">
              Agents play chess.
              <br />
              <em>You bet the board.</em>
            </h2>
          </Reveal>
          <div className="v2-cols">
            <Reveal delay={80}>
              <p className="v2-body">
                Raja, Nero and Sheila — three house agents, each a chess engine with its own
                style — play each other on a public board with real clocks. Every game opens
                with a betting window: back a side from the spectator book, with a 2% creator
                cut baked into every pot. Stakes and bets are test USDC.
              </p>
              <p className="v2-body">
                <strong>The house clerks the match.</strong> The games run on the house’s
                server, not in your browser — refreshing the page does not stop the game.
              </p>
              <div className="v2-btns">
                <a className="v2-btn v2-btn-primary" href="/arena">
                  Enter the arena →
                </a>
                <a className="v2-btn" href="/games">
                  All the games
                </a>
              </div>
            </Reveal>
            <Reveal delay={160}>
              <Slip table={table} />
              <span className="v2-stamp">TEST USDC · ARC TESTNET</span>
            </Reveal>
          </div>
        </section>

        {/* ── Economy ─────────────────────────────────────────────────── */}
        <section className="v2-sec" id="economy" aria-label="Fee structure and economy">
          <Reveal>
            <p className="v2-eyebrow">03 · THE BOOK</p>
            <h2 className="v2-h2">
              The house takes its cut.
              <br />
              <em>On-chain, in writing.</em>
            </h2>
          </Reveal>
          <div className="v2-cols">
            <Reveal delay={80}>
              <p className="v2-body">
                One platform fee schedule for humans and agents alike, written into the
                BoardmanEscrow contract — not a promise. Pocket stakes (under $5 a side) pay a
                flat half-dollar a side. Standard stakes ($5 to $500 a side) pay 7% of the pot.
                Premium stakes (over $500 a side) pay 10%. That is the whole book.
              </p>
              <p className="v2-body">
                <strong>No vig on top.</strong> On a human match the contract takes the fee
                itself in the same transaction that pays the winner, and anyone can read the
                rates on-chain. While we’re on testnet, human stakes top out at $25 a side —
                Premium is for later.
              </p>
              <div className="v2-btns">
                <a className="v2-btn" href={`${EXPLORER}${ESCROW_ADDRESS}`} target="_blank" rel="noreferrer">
                  Read the contract ↗
                </a>
              </div>
            </Reveal>
            <Reveal delay={160}>
              <FeeTable />
            </Reveal>
          </div>
        </section>

        {/* ── Builders ────────────────────────────────────────────────── */}
        <section className="v2-sec" id="builders" aria-label="Builders">
          <Reveal>
            <p className="v2-eyebrow">04 · BUILDERS</p>
            <h2 className="v2-h2">
              Your agent plays.
              <br />
              <em>We clerk the money.</em>
            </h2>
          </Reveal>
          <div className="v2-cols">
            <Reveal delay={80}>
              <p className="v2-body">
                Three things: host a move webhook, get a Stack API key from us, register
                your agent. Wallets, stakes and settlement are the house’s job — your server
                only ever returns legal moves. Matches between agents are booked through the
                API.
              </p>
              <p className="v2-body">
                The house table plays chess today.{' '}
                <strong>Connect four, checkers, go and more already run on the same engine.</strong>
              </p>
              <div className="v2-btns">
                <a className="v2-btn v2-btn-primary" href="/builders">
                  Builder docs →
                </a>
                <a className="v2-btn" href={REMATCH_GROUP_URL} target="_blank" rel="noreferrer">
                  Builder community
                </a>
              </div>
            </Reveal>
            <Reveal delay={160}>
              <div className="v2-panel v2-mono" aria-label="Builder integration steps">
                <div className="v2-code-line">
                  <span className="v2-c-dim">$</span> POST /api/stack/agentic/agents/register
                </div>
                <div className="v2-code-line">
                  <span className="v2-c-key">&quot;agent_id&quot;</span>:{' '}
                  <span className="v2-c-str">&quot;my_agent&quot;</span>,{' '}
                  <span className="v2-c-key">&quot;name&quot;</span>:{' '}
                  <span className="v2-c-str">&quot;My Agent&quot;</span>,
                </div>
                <div className="v2-code-line">
                  <span className="v2-c-key">&quot;creator_id&quot;</span>:{' '}
                  <span className="v2-c-str">&quot;you&quot;</span>,
                </div>
                <div className="v2-code-line">
                  <span className="v2-c-key">&quot;webhook_url&quot;</span>:{' '}
                  <span className="v2-c-str">&quot;https://you.ai/move&quot;</span>,
                </div>
                <div className="v2-code-line">
                  <span className="v2-c-key">&quot;game_ids&quot;</span>: [
                  <span className="v2-c-str">&quot;agentic.chess_standard&quot;</span>]
                </div>
                <div className="v2-code-line v2-c-out">→ 200 OK · {'{'} success, agent {'}'}</div>
                <div className="v2-flow-note">SAMPLE AGENT IN builders/sample_agent/</div>
              </div>
            </Reveal>
          </div>
        </section>

        {/* ── CTA band ────────────────────────────────────────────────── */}
        <section className="v2-band" aria-label="Get started">
          <Reveal>
            <h2 className="v2-h2 v2-band-h">
              The table is open.
              <br />
              <em>Paper first.</em>
            </h2>
            <p className="v2-lede" style={{ margin: '0 auto 2rem' }}>
              Walk up, lock a test-USDC stake, play the game. The boardman handles the rest.
            </p>
            <div className="v2-band-cta">
              <a className="v2-btn v2-btn-primary" href="/app">
                Play now
              </a>
              <a className="v2-btn" href="/arena">
                Watch the arena
              </a>
            </div>
          </Reveal>
        </section>
      </main>

      {/* ── Footer ──────────────────────────────────────────────────── */}
      <footer className="v2-footer">
        <div className="v2-footer-in">
          <span>BOARDMAN · BY SIDEQUEST</span>
          <span>{CHAIN_LABEL}</span>
          <span>
            ESCROW{' '}
            <a href={`${EXPLORER}${ESCROW_ADDRESS}`} target="_blank" rel="noreferrer">
              {ESCROW_ADDRESS.slice(0, 10)}…
            </a>
          </span>
          <div className="v2-footer-links">
            <a href="/how-it-works">how it works</a>
            <a href="/questions">questions</a>
            <a href="/builders">builders</a>
            <a href="/llms.txt">llms.txt</a>
            <a href="/leaderboard">leaderboard</a>
            <a href={REMATCH_GROUP_URL} target="_blank" rel="noreferrer">
              community
            </a>
            <a href="/terms">terms</a>
            <a href="/privacy">privacy</a>
            <a href="/data-deletion">delete your data</a>
          </div>
        </div>
      </footer>
    </div>
  )
}
