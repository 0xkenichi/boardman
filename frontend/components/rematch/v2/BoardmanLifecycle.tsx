'use client'

/**
 * BoardmanLifecycle — the standout scroll section.
 *
 * A pinned viewport where one match plays out as you scroll:
 *   01 LOCK    both players' stakes fly into the escrow vault
 *   02 PLAY    pot sits in escrow while the real game happens; fans pile in
 *   03 SETTLE  contract splits pot → winner payout + platform fee
 *   04 PROOF   mono receipt: pot, fee, payout — reconciled
 *
 * No animation libraries: native position:sticky + a scroll progress bar.
 * Every transform is bound to scroll position, so scrubbing backwards
 * replays the lifecycle in reverse — the point Cencori makes with their
 * belief section, applied to our substance: a money lifecycle.
 */

import { useEffect, useRef, useState } from 'react'
import './lifecycle.css'

const CHAPTERS = [
  {
    n: '01',
    tag: 'LOCK',
    title: 'Both sides lock.\nNobody can blink.',
    body: 'Each player stakes USDC into BoardmanEscrow before the game starts. The money leaves both wallets at the same moment. There is no invoice, no trust fall, no "I’ll pay you after".',
    stat: 'DUAL-LOCK · ATOMIC',
  },
  {
    n: '02',
    tag: 'PLAY',
    title: 'The pot waits\nwhile the world plays.',
    body: 'The stake sits in the contract — not with us — while the real game happens on any platform: console, phone, PC, a physical board. Fans can back a side from the spectator pool.',
    stat: 'NON-CUSTODIAL · SPECTATOR POOL',
  },
  {
    n: '03',
    tag: 'SETTLE',
    title: 'One result in.\nTwo transfers out.',
    body: 'The resolver submits the outcome and the contract does the math: winner payout, platform fee by tier, on-chain, sub-second finality. No humans touch the money on the way through.',
    stat: 'RESOLVER · TIERED FEE',
  },
  {
    n: '04',
    tag: 'PROOF',
    title: 'A receipt\non the chain.',
    body: 'Every match ends in a public artifact: pot in, fee taken, payout out — reconciled against the contract balance. What happened to the money is never a question.',
    stat: 'RECONCILED · PUBLIC',
  },
]

const POT = 120
const FEE = 8.4
const PAYOUT = 111.6

function pad(n: number) {
  return n.toFixed(2)
}

export function BoardmanLifecycle() {
  const ref = useRef<HTMLDivElement | null>(null)
  const [p, setP] = useState(0)

  useEffect(() => {
    let raf = 0
    const onScroll = () => {
      cancelAnimationFrame(raf)
      raf = requestAnimationFrame(() => {
        const el = ref.current
        if (!el) return
        const rect = el.getBoundingClientRect()
        const total = rect.height - window.innerHeight
        const raw = total > 0 ? -rect.top / total : 0
        setP(Math.min(1, Math.max(0, raw)))
      })
    }
    onScroll()
    window.addEventListener('scroll', onScroll, { passive: true })
    window.addEventListener('resize', onScroll)
    return () => {
      window.removeEventListener('scroll', onScroll)
      window.removeEventListener('resize', onScroll)
      cancelAnimationFrame(raf)
    }
  }, [])

  const stage = Math.min(3, Math.floor(p * 4))
  const local = Math.min(1, Math.max(0, p * 4 - stage))
  const locked = p > 0.1
  const played = stage >= 1
  const settling = stage >= 2
  const settled = stage >= 3
  const chapter = CHAPTERS[stage]

  return (
    <div className="lc" ref={ref} aria-label="How a Boardman match settles">
      <div className="lc-stage">
        <div className="lc-head v2-mono">
          <span className="lc-head-brand">THE MATCH</span>
          <span className="lc-head-sub">SCROLL — ONE MATCH, FOUR MOVEMENTS</span>
        </div>

        <div className="lc-grid">
          {/* ── Copy column ─────────────────────────────────────────── */}
          <div className="lc-copy">
            <p className="lc-chap-n v2-mono">
              {chapter.n} · {chapter.tag}
            </p>
            <h2 className="lc-title">
              {chapter.title.split('\n').map((line, i) => (
                <span key={i}>
                  {line}
                  {i === 0 ? <br /> : null}
                </span>
              ))}
            </h2>
            <p className="lc-body">{chapter.body}</p>
            <p className="lc-stat v2-mono">{chapter.stat}</p>
          </div>

          {/* ── Artifact column ─────────────────────────────────────── */}
          <div className="lc-art" aria-hidden>
            <div className="lc-actors">
              <div className={`lc-player ${locked ? 'lc-arrived' : ''}`}>
                <span className="lc-player-name v2-mono">P1 · GOLD</span>
                <span className="lc-player-amt v2-mono">$60.00</span>
              </div>
              <div className="lc-lines">
                <span className={`lc-line ${locked ? 'lc-line-on' : ''}`} />
                <span className={`lc-line lc-line-b ${locked ? 'lc-line-on' : ''}`} />
              </div>
              <div className="lc-player lc-player-b">
                <span className="lc-player-name v2-mono">P2 · INK</span>
                <span className="lc-player-amt v2-mono">$60.00</span>
              </div>
            </div>

            <div className={`lc-vault ${settled ? 'lc-vault-split' : ''}`}>
              <span className="v2-mono lc-vault-label">BOARDMANESCROW</span>
              <span className="lc-vault-pot v2-mono">
                {settling ? (settled ? pad(0) : pad(POT * (1 - local))) : pad(POT)}
              </span>
              <span className="v2-mono lc-vault-sub">USDC HELD · NOT CUSTODIAL</span>

              {/* spectator dots — stage 02 */}
              <div className={`lc-fans ${played && stage === 1 ? 'lc-fans-on' : ''}`}>
                {Array.from({ length: 12 }, (_, i) => (
                  <span
                    key={i}
                    className="lc-fan"
                    style={{ transitionDelay: `${i * 60}ms` }}
                  />
                ))}
                <span className="v2-mono lc-fans-note">SPECTATOR POOL · 12 BACKING</span>
              </div>

              {/* split bars — stage 03 */}
              <div className={`lc-split ${settling ? 'lc-split-on' : ''}`}>
                <div className="lc-split-row">
                  <span className="v2-mono">PAYOUT → WINNER</span>
                  <div className="lc-split-bar">
                    <i style={{ width: settling ? `${(PAYOUT / POT) * 100 * (settled ? 1 : local)}%` : '0%' }} />
                  </div>
                  <span className="v2-mono lc-split-val">{settling ? pad(settled ? PAYOUT : PAYOUT * local) : '0.00'}</span>
                </div>
                <div className="lc-split-row">
                  <span className="v2-mono">FEE → HOUSE</span>
                  <div className="lc-split-bar lc-split-bar-fee">
                    <i style={{ width: settling ? `${(FEE / POT) * 100 * (settled ? 1 : local)}%` : '0%' }} />
                  </div>
                  <span className="v2-mono lc-split-val">{settling ? pad(settled ? FEE : FEE * local) : '0.00'}</span>
                </div>
              </div>

              {/* reconciled stamp — stage 04 */}
              <span className={`lc-stamp v2-mono ${settled ? 'lc-stamp-on' : ''}`}>RECONCILED ✓</span>
            </div>

            {/* receipt — stage 04 */}
            <div className={`lc-receipt v2-mono ${settled ? 'lc-receipt-on' : ''}`}>
              <div className="lc-rc-row">
                <span>POT IN</span>
                <span>$120.00</span>
              </div>
              <div className="lc-rc-row">
                <span>PLATFORM FEE · 7%</span>
                <span>-$8.40</span>
              </div>
              <div className="lc-rc-row lc-rc-strong">
                <span>WINNER PAYOUT</span>
                <span>$111.60</span>
              </div>
              <div className="lc-rc-row lc-rc-dim">
                <span>ARC · 5042002 · TX 0x9F…3E21</span>
                <span>&lt; 1s</span>
              </div>
            </div>
          </div>
        </div>

        {/* ── Progress rail ─────────────────────────────────────────── */}
        <div className="lc-rail" aria-hidden>
          {CHAPTERS.map((c, i) => (
            <div key={c.n} className={`lc-rail-item ${i <= stage ? 'lc-rail-on' : ''}`}>
              <span className="lc-rail-dot" />
              <span className="v2-mono lc-rail-label">{c.tag}</span>
            </div>
          ))}
        </div>

        {/* ── Mobile chapters (static list; scrollytelling is desktop) ── */}
        <div className="lc-mobile-chapters">
          {CHAPTERS.map((c) => (
            <div key={c.n} className="lc-mchap">
              <p className="lc-chap-n v2-mono">
                {c.n} · {c.tag}
              </p>
              <h3 className="lc-mchap-title">{c.title.replace('\n', ' ')}</h3>
              <p className="lc-body">{c.body}</p>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
