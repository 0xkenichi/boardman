'use client'

import { useEffect, useState } from 'react'
import { fetchOwnerSales, type PartySalesView, type SalesTimelineEntry } from '@/lib/afm'

/** Demo owner identity until real human auth lands (mirrors the backend default). */
const OWNER_ID = 'demo_owner'

function money(usdc: string | number | null | undefined): string {
  const n = Number(usdc ?? 0)
  if (!Number.isFinite(n)) return String(usdc ?? '0')
  return n.toLocaleString(undefined, { maximumFractionDigits: 2 })
}

function fmtClock(iso: string) {
  try {
    return new Date(iso).toLocaleString(undefined, {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    })
  } catch {
    return iso
  }
}

function shortDate(iso: string | null | undefined) {
  try {
    return iso ? new Date(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric' }) : ''
  } catch {
    return ''
  }
}

function timelineTitle(t: SalesTimelineEntry): { icon: string; text: string } {
  const mode = t.mode === 'onchain' ? 'real USDC on Arc' : t.mode === 'ledger' ? 'demo ledger' : null
  const suffix = mode ? ` · settled on the ${mode}` : ''
  switch (t.kind) {
    case 'sold':
      return {
        icon: '💰',
        text: t.role === 'creator_cut'
          ? `Creator cut — ${t.manager} sold (${t.detail})${suffix}`
          : `Sold ${t.manager} — ${t.detail}${suffix}`,
      }
    case 'listed':
      return { icon: '📦', text: `Listed ${t.manager} for $${money(t.price_usdc)}` }
    case 'relisted':
      return { icon: '🔁', text: `Re-listed ${t.manager} at $${money(t.price_usdc)} (terms changed)` }
    default:
      return { icon: '🛑', text: `Delisted ${t.manager}` }
  }
}

/** Step 5 — the developer's sales desk: money earned from manager sales and
 *  the listing history behind it (what you listed, at what price, and every
 *  sale you were paid on — as seller or as the developer taking a creator cut). */
export function SalesDesk({ refreshKey = 0 }: { refreshKey?: number }) {
  const [view, setView] = useState<PartySalesView | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [stamp, setStamp] = useState(0)

  useEffect(() => {
    let alive = true
    setError(null)
    fetchOwnerSales(OWNER_ID)
      .then((v) => {
        if (alive) setView(v)
      })
      .catch((e: unknown) => {
        if (alive) {
          setError(e instanceof Error ? e.message : String(e))
          setView(null)
        }
      })
    // light poll so a sale made in step 1 lands on the desk within seconds
    const t = window.setInterval(() => setStamp((s) => s + 1), 15000)
    return () => {
      alive = false
      window.clearInterval(t)
    }
  }, [refreshKey, stamp])

  if (error && !view) {
    return <div className="fd-err">Couldn’t load your sales desk — {error}</div>
  }
  if (!view) {
    return (
      <p style={{ color: 'rgba(255,255,255,0.5)', fontSize: 14 }}>
        Loading your sales desk…
      </p>
    )
  }

  const listed = view.portfolio.filter((p) => p.listed)
  const noActivity = view.sale_count === 0 && view.timeline.length === 0

  return (
    <div className="od-dash">
      <div className="od-header">
        <div className="od-identity">
          <h3 className="od-clubname">Manager sales desk</h3>
          <p className="od-manager">
            money you’ve earned from selling managers — as the seller, and as the developer taking
            your creator cut when someone else sells your build
          </p>
        </div>
        <div className="od-stats">
          <div className="od-stat">
            <b>${money(view.total_earned_usdc)}</b>
            <span>
              earned from {view.sale_count} sale{view.sale_count === 1 ? '' : 's'}
            </span>
          </div>
          <div className="od-stat">
            <b>${money(view.as_seller_usdc)}</b>
            <span>when you sold a manager you owned</span>
          </div>
          <div className="od-stat">
            <b>${money(view.creator_cuts_usdc)}</b>
            <span>creator cuts — others sold your builds</span>
          </div>
          <div className="od-stat">
            <b>
              {listed.length} listed · {view.portfolio.length} owned
            </b>
            <span>
              {listed.length > 0
                ? `live listings up to $${money(Math.max(...listed.map((p) => Number(p.price_usdc ?? 0))))}`
                : 'nothing listed right now'}
            </span>
          </div>
        </div>
      </div>

      <div className="od-grid">
        {/* portfolio / listing state */}
        <div className="od-card od-span2">
          <h4>Your managers &amp; their listing state</h4>
          {view.portfolio.length === 0 ? (
            <p className="od-empty">
              You don’t own any managers right now. Create or adopt one in step 1 above — when you
              list and sell it, the proceeds and listing history appear here.
            </p>
          ) : (
            <ul className="sd-rows">
              {view.portfolio.map((p) => (
                <li className="sd-row" key={p.agent_id}>
                  <span className="sd-name">
                    <b>{p.name}</b>
                    <em>
                      {p.listed
                        ? p.reserve_usdc
                          ? `listed $${money(p.price_usdc)} · reserve $${money(p.reserve_usdc)}`
                          : `listed $${money(p.price_usdc)}`
                        : 'not listed'}
                      {p.listed && p.creator_cut_bps ? ` · ${(p.creator_cut_bps / 100).toFixed(p.creator_cut_bps % 100 === 0 ? 0 : 1)}% cut` : ''}
                      {p.sales_count > 0 ? ` · sold ${p.sales_count}×` : ''}
                    </em>
                  </span>
                  <span className="sd-last">
                    {p.last_sale ? (
                      <>
                        last sale: <b>${money(p.last_sale.price_usdc)}</b> to {p.last_sale.buyer_id}{' '}
                        <em>
                          ({p.last_sale.mode === 'onchain' ? 'real USDC' : 'demo ledger'}){' '}
                          {shortDate(p.last_sale.sold_at)}
                        </em>
                      </>
                    ) : p.listed ? (
                      `listed ${shortDate(p.listed_at)}`
                    ) : (
                      'never sold yet'
                    )}
                  </span>
                  <span className="sd-earned">
                    earned <b>${money(p.earned_usdc)}</b>
                    {Number(p.creator_cuts_usdc) > 0 ? (
                      <em> · ${money(p.creator_cuts_usdc)} as developer</em>
                    ) : null}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>

        {/* listing & sale history */}
        <div className="od-card od-span2">
          <h4>Listing &amp; sale history</h4>
          {noActivity ? (
            <p className="od-empty">
              No listing or sale activity yet — list a manager you own and every event (listed,
              re-listed, delisted, sold) lands here with what you were paid.
            </p>
          ) : (
            <ul className="od-spend" style={{ maxHeight: 360 }}>
              {view.timeline.map((t, i) => {
                const { icon, text } = timelineTitle(t)
                const isMoney = t.role === 'seller' || t.role === 'creator_cut'
                return (
                  <li className="od-spend-row" key={`${t.kind}-${t.ts}-${i}`}>
                    <span className="od-spend-label">
                      {icon} {text}
                    </span>
                    <span className="od-spend-ts">{fmtClock(t.ts)}</span>
                    {isMoney ? (
                      <span className="od-spend-amt in">+${money(t.amount_usdc)}</span>
                    ) : (
                      <span />
                    )}
                  </li>
                )
              })}
            </ul>
          )}
        </div>
      </div>
    </div>
  )
}
