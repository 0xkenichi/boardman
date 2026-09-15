'use client'

/**
 * Transfer-bid modal — Boardman rebuild of the reference clip's signature
 * interaction: a large bid amount with −/+ steppers and quick presets, and a
 * horizontal likelihood meter that recolors + relabels live as the number
 * moves, over a key-value ledger and proactive constraint checkmarks.
 *
 * Honesty rule (the brief's): the meter only encodes what the House actually
 * enforces — below reserve is a deterministic auto-decline; at/above buy-now
 * you should just buy. Everything in between is genuinely the owner's call,
 * so the meter says "owner decides", never a fake probability.
 */
import { useEffect, useMemo, useState } from 'react'
import type { MarketAgent, PartyWalletStatus } from '@/lib/afm'

interface BidModalProps {
  agent: MarketAgent
  wallet: PartyWalletStatus | null
  busy: boolean
  onSubmit: (amountUsdc: number) => void
  onClose: () => void
}

/** Read the demo owner's spendable cash from the wallet status (best effort). */
function cashAfterNote(view: PartyWalletStatus | null): string | null {
  // PartyWalletStatus carries the binding state, not a balance — so the ledger
  // shows the rail instead of inventing a number.
  if (!view) return null
  if (view.mode === 'onchain' && view.real_wallet) return 'paid from your bound Arc wallet'
  return 'settled on the demo ledger'
}

export function BidModal({ agent, wallet, busy, onSubmit, onClose }: BidModalProps) {
  const price = Number(agent.price_usdc ?? 0)
  const reserve = agent.reserve_usdc ? Number(agent.reserve_usdc) : null
  const hasReserve = reserve != null && reserve > 0

  const [amount, setAmount] = useState(() =>
    hasReserve ? reserve! : price > 0 ? Math.round(price * 0.85 * 100) / 100 : 1,
  )

  // Esc closes, background scroll locks while open.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && !busy) onClose()
    }
    window.addEventListener('keydown', onKey)
    document.body.style.overflow = 'hidden'
    return () => {
      window.removeEventListener('keydown', onKey)
      document.body.style.overflow = ''
    }
  }, [busy, onClose])

  const step = useMemo(() => {
    const base = Math.max(amount, price || amount, 1)
    if (base >= 200) return 10
    if (base >= 50) return 5
    if (base >= 10) return 1
    return 0.5
  }, [amount, price])

  const clamp = (v: number) => Math.max(0.01, Math.round(v * 100) / 100)

  const presets = useMemo(() => {
    const list: { label: string; value: number | null; hint: string }[] = [
      hasReserve
        ? { label: 'Their floor', value: reserve!, hint: `the owner's reserve — offers below auto-decline` }
        : { label: 'Opening', value: Math.round(price * 0.7 * 100) / 100 || 1, hint: 'a sane first bid on an unreserved listing' },
      { label: 'Fair', value: Math.round(price * 0.9 * 100) / 100 || 1, hint: 'just under buy-now' },
      { label: 'Buy-now', value: price || null, hint: 'skip the negotiation — buy at the listed price' },
    ]
    return list
  }, [hasReserve, reserve, price])

  /** Verdict — the single source of truth for the meter's color, label and note. */
  const verdict = useMemo(() => {
    if (price > 0 && amount >= price) {
      return {
        tone: 'green' as const,
        label: 'BUY-NOW TERRITORY',
        note: `At or above the ${price} USDC buy-now — use "Buy now" on the card instead; the sale settles instantly.`,
        pct: 100,
      }
    }
    if (hasReserve && amount < reserve!) {
      return {
        tone: 'red' as const,
        label: 'WILL AUTO-DECLINE',
        note: `Below the owner's ${reserve} USDC reserve — the House declines it without showing them.`,
        pct: Math.max(4, Math.round((amount / reserve!) * 62)),
      }
    }
    // at/above reserve (or no reserve): pending offer the owner must answer
    const near =
      !hasReserve
        ? amount >= price * 0.95
          ? 1
          : 0
        : (amount - reserve!) / Math.max(price - reserve!, 0.01)
    if (near >= 0.9) {
      return {
        tone: 'green' as const,
        label: 'VERY LIKELY ACCEPTED',
        note: 'Close to buy-now — most owners take this without hesitating.',
        pct: 88,
      }
    }
    if (near >= 0.5) {
      return {
        tone: 'amber' as const,
        label: 'OWNER DECIDES',
        note: 'Solid offer — lands in their inbox with your name on it.',
        pct: 62,
      }
    }
    return {
      tone: 'amber' as const,
      label: 'OWNER DECIDES',
      note: 'It clears the reserve, but a lowball can sit unanswered.',
      pct: 34,
    }
  }, [amount, price, reserve, hasReserve])

  const creatorCut = (amount * (agent.creator_cut_bps ?? 0)) / 10000
  const sellerGets = amount - creatorCut

  const cashNote = cashAfterNote(wallet)

  return (
    <div className="fd-modal-overlay" onClick={() => !busy && onClose()}>
      <div className="fd-modal bm-bid" onClick={(e) => e.stopPropagation()}>
        <div className="bm-bid-head">
          <h3>Make an offer — {agent.name}</h3>
          <p className="fd-sub">
            {agent.archetype_name} · by <b>{agent.creator_id}</b>
            {agent.club_name ? ` · runs ${agent.club_name}` : ''} · record{' '}
            {agent.stats?.wins ?? 0}W–{agent.stats?.losses ?? 0}L–{agent.stats?.draws ?? 0}D
          </p>
        </div>

        {/* segmented pill: offer vs buy-now */}
        <div className="bm-bid-seg">
          <button className="on">Offer</button>
          <button
            onClick={() => {
              onClose()
            }}
            title="Buying outright lives on the market card — this modal negotiates"
          >
            Buy now
          </button>
        </div>

        {/* the amount */}
        <div className="bm-bid-amount">
          <button aria-label="decrease" onClick={() => setAmount((a) => clamp(a - step))}>
            −
          </button>
          <input
            type="number"
            min={0.01}
            step={step}
            value={String(amount)}
            onChange={(e) => setAmount(clamp(Number(e.target.value)))}
            aria-label="Offer amount in USDC"
          />
          <button aria-label="increase" onClick={() => setAmount((a) => clamp(a + step))}>
            +
          </button>
        </div>

        {/* quick presets */}
        <div className="bm-bid-presets">
          {presets.map((p) => (
            <button
              key={p.label}
              type="button"
              disabled={p.value == null}
              title={p.hint}
              onClick={() => p.value != null && setAmount(clamp(p.value))}
            >
              {p.label}
            </button>
          ))}
        </div>

        {/* the live likelihood meter */}
        <div className={`bm-meter ${verdict.tone}`}>
          <div className="bm-meter-track">
            <div className="bm-meter-fill" style={{ width: `${verdict.pct}%` }} />
          </div>
          <div className="bm-meter-row">
            <b>{verdict.label}</b>
            <span>{amount.toFixed(2)} USDC</span>
          </div>
          <p className="bm-meter-note">{verdict.note}</p>
        </div>

        {/* key-value ledger */}
        <div className="bm-ledger">
          <div><span>Buy-now price</span><b>{price > 0 ? `${price.toFixed(2)} USDC` : 'not listed — offer only'}</b></div>
          {hasReserve && <div><span>Owner reserve</span><b>{reserve!.toFixed(2)} USDC</b></div>}
          {(agent.creator_cut_bps ?? 0) > 0 && (
            <div>
              <span>Creator cut ({((agent.creator_cut_bps ?? 0) / 100).toFixed(1)}% to {agent.creator_id})</span>
              <b>{creatorCut.toFixed(2)} USDC</b>
            </div>
          )}
          <div><span>Seller receives</span><b>{sellerGets.toFixed(2)} USDC</b></div>
          <div><span>Settlement rail</span><b>{cashNote ?? 'demo ledger'}</b></div>
        </div>

        {/* proactive constraint checks */}
        <div className="bm-checks">
          <div className={hasReserve && amount < reserve! ? 'bad' : 'ok'}>
            <i>{hasReserve && amount < reserve! ? '✕' : '✓'}</i>
            {hasReserve
              ? amount < reserve!
                ? `Offer is under the ${reserve} reserve — it will bounce`
                : 'Offer clears the reserve'
              : 'No reserve set — every offer reaches the owner'}
          </div>
          <div className={price > 0 && amount >= price ? 'warn' : 'ok'}>
            <i>{price > 0 && amount >= price ? '!' : '✓'}</i>
            {price > 0 && amount >= price
              ? 'This matches buy-now — you should just buy it'
              : 'Under buy-now — negotiating'}
          </div>
        </div>

        <div className="fd-modal-actions">
          <button className="fd-btn" disabled={busy} onClick={onClose}>
            Cancel
          </button>
          <button
            className="fd-btn primary"
            disabled={busy || (hasReserve && amount < reserve!)}
            onClick={() => onSubmit(amount)}
          >
            {busy ? 'Sending…' : `Submit offer · ${amount.toFixed(2)} USDC`}
          </button>
        </div>
      </div>
    </div>
  )
}
