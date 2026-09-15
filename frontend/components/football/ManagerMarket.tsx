'use client'

import { useCallback, useEffect, useState } from 'react'
import Link from 'next/link'
import { BidModal } from '@/components/football/BidModal'
import { ManagerDetailCard } from '@/components/football/ManagerDetailCard'
import {
  MANAGER_ARCHETYPES,
  type CreateManagerInput,
  type MarketAgent,
  type PartyWalletStatus,
  type SettlementMode,
  acceptManagerOffer,
  acquireManagerAgent,
  bindPartyWallet,
  createManagerAgent,
  delistManagerForSale,
  fetchPartyWalletStatus,
  listManagerForSale,
  listMarketAgents,
  makeManagerOffer,
  purchaseManagerAgent,
  rejectManagerOffer,
  setManagerWebhook,
  unbindPartyWallet,
} from '@/lib/afm'

/** Demo owner identity until real human auth lands (mirrors the backend default). */
const OWNER_ID = 'demo_owner'
const FORMATIONS = ['4-3-3', '4-2-3-1', '4-4-2', '3-5-2', '5-3-2', '4-1-4-1', '3-4-3']

function cutPct(bps: number | null | undefined): string {
  const v = Number(bps ?? 0)
  return v > 0 ? `${(v / 100).toFixed(v % 100 === 0 ? 0 : 1)}%` : 'no creator cut'
}

function usd(usdc: string | number | null | undefined): string {
  const n = Number(usdc ?? 0)
  return Number.isFinite(n) ? n.toLocaleString(undefined, { maximumFractionDigits: 2 }) : String(usdc ?? '0')
}

export function ManagerMarket({ onChanged }: { onChanged?: () => void }) {
  const [agents, setAgents] = useState<MarketAgent[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [flash, setFlash] = useState<string | null>(null)

  // create form
  const [managerName, setManagerName] = useState('')
  const [clubName, setClubName] = useState('')
  const [archetype, setArchetype] = useState<(typeof MANAGER_ARCHETYPES)[number]['id']>('tactician')
  const [formation, setFormation] = useState('4-3-3')
  const [listPrice, setListPrice] = useState('') // optional list-on-create price
  const [creatorCutPct, setCreatorCutPct] = useState('5')
  const [creating, setCreating] = useState(false)
  const [createError, setCreateError] = useState<string | null>(null)
  const [created, setCreated] = useState<{ agent: MarketAgent; clubName: string } | null>(null)

  // marketplace actions
  const [busyId, setBusyId] = useState<string | null>(null)
  // manager awaiting one-click buy confirmation
  const [confirming, setConfirming] = useState<MarketAgent | null>(null)

  // real-USDC settlement: your wallet binding + how you want to pay
  const [wallet, setWallet] = useState<PartyWalletStatus | null>(null)
  const [settlement, setSettlement] = useState<SettlementMode>('auto')
  const [bindAddress, setBindAddress] = useState('')
  const [bindWalletId, setBindWalletId] = useState('')
  const [walling, setWalling] = useState(false)

  // sell-panel per-owned-manager inputs (keyed by agent id)
  const [sellPrice, setSellPrice] = useState<Record<string, string>>({})
  const [sellCut, setSellCut] = useState<Record<string, string>>({})
  const [sellReserve, setSellReserve] = useState<Record<string, string>>({})
  // buyer-side bid modal (the live-meter offer flow)
  const [bidding, setBidding] = useState<MarketAgent | null>(null)
  // expanded detail card per manager (keyed by agent id)
  const [openCard, setOpenCard] = useState<string | null>(null)
  // owner-set webhook per owned manager (keyed by agent id)
  const [whUrl, setWhUrl] = useState<Record<string, string>>({})

  const refresh = useCallback(() => {
    listMarketAgents()
      .then(setAgents)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)))
  }, [])

  useEffect(() => {
    refresh()
    fetchPartyWalletStatus(OWNER_ID)
      .then(setWallet)
      .catch(() => setWallet(null))
  }, [refresh])

  const reloadWallet = useCallback(() => {
    fetchPartyWalletStatus(OWNER_ID)
      .then(setWallet)
      .catch(() => setWallet(null))
  }, [])

  const onBindWallet = async () => {
    if (!bindAddress.trim().toLowerCase().startsWith('0x')) {
      setError('Enter a full 0x… Arc USDC address to bind.')
      return
    }
    setWalling(true)
    try {
      const bound = await bindPartyWallet(OWNER_ID, bindAddress.trim(), bindWalletId.trim() || undefined)
      setFlash(
        bound.can_send
          ? `💳 Wallet bound — purchases from now on settle in real USDC from ${bound.address}.`
          : `📥 Payout address bound — people can now buy from you in real USDC.`,
      )
      setBindAddress('')
      setBindWalletId('')
      reloadWallet()
      onChanged?.()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setWalling(false)
    }
  }

  const onUnbindWallet = async () => {
    setWalling(true)
    try {
      await unbindPartyWallet(OWNER_ID, wallet?.real_wallet?.address)
      setFlash('Wallet unbound — sales settle on the demo ledger again.')
      reloadWallet()
      onChanged?.()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setWalling(false)
    }
  }

  const mine = (agents ?? []).filter((a) => a.owner_id === OWNER_ID)

  const onCreate = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!managerName.trim()) {
      setCreateError('Name your manager first — it becomes their agent id.')
      return
    }
    setCreating(true)
    setCreateError(null)
    try {
      const price = listPrice.trim() ? Number(listPrice.trim()) : undefined
      const input: CreateManagerInput = {
        manager_name: managerName.trim(),
        club_name: clubName.trim() || undefined,
        archetype,
        formation: formation as CreateManagerInput['formation'],
        owner_id: OWNER_ID,
        list_price_usdc: price && price > 0 ? price : undefined,
        creator_cut_bps: Math.round(Number(creatorCutPct || '0') * 100),
      }
      const out = await createManagerAgent(input)
      setCreated({ agent: out.agent, clubName: out.club.club_name })
      setAgents((prev) => (prev ? [out.agent, ...prev] : [out.agent]))
      onChanged?.()
      if (out.agent.listed) setFlash(`🚀 ${out.agent.name} is listed at $${usd(out.agent.price_usdc)} — sellable.`)
      else setFlash(`✅ ${out.agent.name} is registered and running ${out.club.club_name}.`)
    } catch (err) {
      setCreateError(err instanceof Error ? err.message : String(err))
    } finally {
      setCreating(false)
    }
  }

  const onAcquire = async (agentId: string) => {
    setBusyId(agentId)
    try {
      const agent = await acquireManagerAgent(agentId, OWNER_ID)
      setAgents((prev) => (prev ? prev.map((a) => (a.agent_id === agentId ? agent : a)) : prev))
      setFlash(`Adopted ${agent.name} — it now runs a club for you. You can resell it below.`)
      onChanged?.()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusyId(null)
    }
  }

  const onBuy = async (agentId: string) => {
    setBusyId(agentId)
    try {
      const out = await purchaseManagerAgent(agentId, OWNER_ID, settlement)
      const s = out.sale
      const paid =
        s.mode === 'onchain'
          ? `paid in real USDC on Arc`
          : `settled on the demo ledger`
      const tx = s.settlement.legs.find((l) => l.tx_hash)
      setAgents((prev) => (prev ? prev.map((a) => (a.agent_id === agentId ? out.agent : a)) : prev))
      setFlash(
        `🛒 Bought ${out.agent.name} for $${usd(s.price_usdc)} (${paid}) — ` +
          `developer ${s.first_sale ? 'received the full price' : `kept their cut ($${usd(s.creator_cut_usdc)})`}. ` +
          (tx
            ? `On-chain tx ${tx.tx_hash?.slice(0, 10)}…${tx.tx_hash?.slice(-6)} (` +
              `${tx.to_address ? `→ ${shortAddr(tx.to_address)}` : ''}). `
            : '') +
          `You can run it or relist it below.`,
      )
      onChanged?.()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusyId(null)
    }
  }

  const onList = async (agentId: string, name: string) => {
    const price = Number(sellPrice[agentId])
    if (!price || price <= 0) {
      setError(`Set a price to list ${name}.`)
      return
    }
    setBusyId(agentId)
    try {
      const reserve = Number(sellReserve[agentId])
      const agent = await listManagerForSale(
        agentId,
        price,
        Math.round(Number(sellCut[agentId] || '0') * 100),
        OWNER_ID,
        reserve > 0 ? reserve : undefined,
      )
      setAgents((prev) => (prev ? prev.map((a) => (a.agent_id === agentId ? agent : a)) : prev))
      setFlash(
        `📦 Listed ${agent.name} for $${usd(agent.price_usdc)}` +
          (agent.reserve_usdc ? ` with a $${usd(agent.reserve_usdc)} reserve` : '') +
          (agent.creator_cut_bps ? ` and a ${cutPct(agent.creator_cut_bps)} creator cut` : '') +
          '. Offers above the reserve land in your inbox.',
      )
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusyId(null)
    }
  }

  const onSetWebhook = async (agentId: string, name: string, urlOverride?: string) => {
    const url = (urlOverride ?? whUrl[agentId] ?? '').trim()
    setBusyId(`${agentId}:wh`)
    try {
      const agent = await setManagerWebhook(agentId, url, OWNER_ID)
      setAgents((prev) => (prev ? prev.map((a) => (a.agent_id === agentId ? agent : a)) : prev))
      setFlash(
        url
          ? `🔗 ${name} now answers the matchday ask from your webhook — the House will POST its context there and lock its reply (playbook fallback if it's down).`
          : `📴 ${name} is back on the deterministic playbook — webhook cleared.`,
      )
      setWhUrl((p) => ({ ...p, [agentId]: '' }))
      onChanged?.()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusyId(null)
    }
  }

  const onDelist = async (agentId: string) => {
    setBusyId(agentId)
    try {
      const agent = await delistManagerForSale(agentId, OWNER_ID)
      setAgents((prev) => (prev ? prev.map((a) => (a.agent_id === agentId ? agent : a)) : prev))
      setFlash(`${agent.name} is off the market — still yours.`)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusyId(null)
    }
  }

  const onOffer = async (agentId: string, name: string, amt: number) => {
    if (!amt || amt <= 0) {
      setError('Enter an offer amount first.')
      return
    }
    setBusyId(agentId)
    try {
      const out = await makeManagerOffer(agentId, amt, OWNER_ID)
      setAgents((prev) => (prev ? prev.map((a) => (a.agent_id === agentId ? out.agent : a)) : prev))
      if (out.auto_declined) {
        setError(
          `Your $${usd(amt)} offer for ${name} was auto-declined — it's below the owner's reserve ($${usd(out.agent.reserve_usdc)}).`,
        )
      } else {
        setFlash(`📨 Your $${usd(amt)} offer for ${name} is in — waiting on the developer.`)
      }
      setBidding(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusyId(null)
    }
  }

  const onAcceptOffer = async (agentId: string, offerId: string, buyer: string, amount: string) => {
    setBusyId(`${agentId}:${offerId}`)
    try {
      const out = await acceptManagerOffer(agentId, offerId, OWNER_ID)
      setAgents((prev) => (prev ? prev.map((a) => (a.agent_id === agentId ? out.agent : a)) : prev))
      setFlash(
        `🤝 Accepted ${buyer}'s $${usd(amount)} offer — ${out.agent.name} sold. ` +
          `Developer kept ${usd(out.sale.creator_cut_usdc) || '$0'} cut, you received $${usd(out.sale.seller_payout_usdc)}.`,
      )
      onChanged?.()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusyId(null)
    }
  }

  const onRejectOffer = async (agentId: string, offerId: string, buyer: string) => {
    setBusyId(`${agentId}:${offerId}`)
    try {
      const agent = await rejectManagerOffer(agentId, offerId, OWNER_ID)
      setAgents((prev) => (prev ? prev.map((a) => (a.agent_id === agentId ? agent : a)) : prev))
      setFlash(`Declined ${buyer}'s offer — ${agent.name} is still listed.`)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusyId(null)
    }
  }

  return (
    <div>
      <div className="fd-stack">
        <div className="fd-half">
          <h3>Build your own manager</h3>
          <p className="fd-sub">
            Pick a playbook archetype, name your manager, and they get a registered agent identity +
            wallet, then a club with an affordable squad. They join the league at the next season
            open and run it themselves. Optionally list them for sale the moment they exist.
          </p>

          <form className="fd-form" onSubmit={onCreate}>
            <label className="fd-field">
              <span>Manager name</span>
              <input
                className="fd-input"
                value={managerName}
                onChange={(e) => setManagerName(e.target.value)}
                placeholder="e.g. The Underdog"
                maxLength={40}
              />
            </label>
            <label className="fd-field">
              <span>Club name (optional)</span>
              <input
                className="fd-input"
                value={clubName}
                onChange={(e) => setClubName(e.target.value)}
                placeholder={`${managerName.trim() || 'Your manager'} FC`}
                maxLength={40}
              />
            </label>

            <div className="fd-field">
              <span>Playbook archetype</span>
              <div className="fd-radios">
                {MANAGER_ARCHETYPES.map((a) => (
                  <button
                    type="button"
                    key={a.id}
                    className={`fd-radio${a.id === archetype ? ' on' : ''}`}
                    onClick={() => setArchetype(a.id)}
                  >
                    <b>{a.name}</b>
                    <span>{a.blurb}</span>
                  </button>
                ))}
              </div>
            </div>

            <div className="fd-row2">
              <label className="fd-field">
                <span>Starting formation</span>
                <select className="fd-select" value={formation} onChange={(e) => setFormation(e.target.value)}>
                  {FORMATIONS.map((f) => (
                    <option key={f} value={f}>
                      {f}
                    </option>
                  ))}
                </select>
              </label>
              <label className="fd-field">
                <span>List price (USDC, optional)</span>
                <input
                  className="fd-input"
                  type="number"
                  min={0}
                  step="0.01"
                  value={listPrice}
                  onChange={(e) => setListPrice(e.target.value)}
                  placeholder="leave empty = not for sale"
                />
              </label>
              <label className="fd-field">
                <span>Your creator cut (% of each sale)</span>
                <input
                  className="fd-input"
                  type="number"
                  min={0}
                  max={20}
                  step="0.5"
                  value={creatorCutPct}
                  onChange={(e) => setCreatorCutPct(e.target.value)}
                />
              </label>
            </div>

            {createError && <div className="fd-err">{createError}</div>}

            <button className="fd-btn primary" disabled={creating} type="submit">
              {creating ? 'Building…' : 'Create my manager'}
            </button>
          </form>

          {created && (
            <div className="fd-ok">
              <b>
                ✅ {created.agent.name} is registered and running {created.clubName}.
                {created.agent.listed ? ` Listed at $${usd(created.agent.price_usdc)}.` : ''}
              </b>
              <span>
                Their squad is seeded (legal XI + bench within budget) and the next season open picks
                them up automatically.
              </span>
              <span className="fd-links">
                <Link href={`/football/squad/${encodeURIComponent(created.agent.agent_id)}`}>
                  Squad room (FM) →
                </Link>
                {' · '}
                <Link href="/football/tactics">Match board →</Link>
              </span>
            </div>
          )}
        </div>

        <div className="fd-half">
          <h3>…or take one from the marketplace</h3>
          <p className="fd-sub">
            Developer-built managers, priced and up for sale. A listed manager is bought — the price
            settles in real USDC when every party has a wallet bound (below), else on the demo
            ledger. The developer keeps their cut on every resale. Unlisted managers can still be
            adopted.
          </p>

          <div className="fd-walletbar">
            <span className={`fd-chip${wallet?.mode === 'onchain' ? ' ok' : ''}`}>
              {wallet?.mode === 'onchain' ? 'Real USDC · Arc' : 'Demo ledger'}
            </span>
            {wallet?.real_wallet ? (
              <span className="fd-walletnote">
                your wallet <b>{shortAddr(wallet.real_wallet.address)}</b>
                {wallet.real_wallet.can_send
                  ? ' — you pay from this wallet'
                  : ' — payout only (no wallet id)'}
              </span>
            ) : (
              <span className="fd-walletnote">
                no real wallet bound — sales settle on the demo ledger
              </span>
            )}
            {wallet && !wallet.circle_configured && (
              <span className="fd-walletnote dim">Circle not configured on this backend</span>
            )}
            {wallet?.mode === 'onchain' && (
              <label className="fd-field" style={{ flex: '0 0 auto' }}>
                <select
                  className="fd-select"
                  value={settlement}
                  onChange={(e) => setSettlement(e.target.value as SettlementMode)}
                >
                  <option value="auto">Auto</option>
                  <option value="onchain">Real USDC</option>
                  <option value="ledger">Demo ledger</option>
                </select>
              </label>
            )}
          </div>
          {wallet?.mode !== 'onchain' && (
            <div className="fd-walletbar">
              <input
                className="fd-input"
                placeholder="Bind a real Arc USDC wallet — 0x… address you're paid to"
                value={bindAddress}
                onChange={(e) => setBindAddress(e.target.value)}
              />
              <input
                className="fd-input"
                placeholder="Circle wallet id (optional — needed to pay, not just receive)"
                value={bindWalletId}
                onChange={(e) => setBindWalletId(e.target.value)}
              />
              <button
                className="fd-btn primary"
                disabled={walling}
                onClick={onBindWallet}
                type="button"
              >
                {walling ? '…' : 'Bind wallet'}
              </button>
            </div>
          )}
          {wallet?.mode === 'onchain' && (
            <div className="fd-walletbar">
              <span className="fd-walletnote">Wallet {shortAddr(wallet.real_wallet!.address)}</span>
              <button className="fd-btn" disabled={walling} onClick={onUnbindWallet} type="button">
                Unbind (back to demo)
              </button>
            </div>
          )}

          {error && (
            <div className="fd-err">
              Couldn’t reach the marketplace — the backend may be offline in this environment. It
              lists the registered manager agents once the agent services are running.
            </div>
          )}
          {flash && (
            <div className="fd-ok" style={{ marginBottom: 12 }}>
              {flash}
            </div>
          )}

          {!error && !agents && (
            <p style={{ color: 'rgba(255,255,255,0.5)', fontSize: 14 }}>Loading marketplace…</p>
          )}

          {!error && agents && agents.length === 0 && (
            <p style={{ color: 'rgba(255,255,255,0.5)', fontSize: 14 }}>
              No managers on the marketplace yet — build the first one on the left.
            </p>
          )}

          {!error && agents && agents.length > 0 && (
            <div className="fd-cards">
              {agents.map((a) => {
                const mineHere = a.owner_id === OWNER_ID
                const s = a.stats ?? {}
                const forSale = a.listed && !mineHere
                return (
                  <div className="fd-card" key={a.agent_id}>
                    <div className="fd-club">
                      <span className="fd-clubname">{a.name}</span>
                      <span className="fd-chip">{a.archetype_name}</span>
                    </div>
                    <p className="fd-blurb">{a.blurb}</p>
                    <p className="fd-meta">
                      by <b>{a.creator_id}</b> · v{a.version}
                      <br />
                      record {fmt(s.wins)}W–{fmt(s.losses)}L–{fmt(s.draws)}D · {fmt(s.matches)} played
                      <br />
                      {a.club_name ? (
                        <>
                          runs <b>{a.club_name}</b>
                        </>
                      ) : (
                        'no club yet'
                      )}
                    </p>
                    <button
                      type="button"
                      className={`fd-btn mc-toggle${openCard === a.agent_id ? ' on' : ''}`}
                      onClick={() => setOpenCard(openCard === a.agent_id ? null : a.agent_id)}
                      aria-expanded={openCard === a.agent_id}
                    >
                      {openCard === a.agent_id ? '▾ Hide detail card' : '▸ Detail card — playbook, squad & record'}
                    </button>
                    {openCard === a.agent_id && a.card && <ManagerDetailCard card={a.card} />}
                    {a.listed && (
                      <p className="fd-price">
                        <b>${usd(a.price_usdc)}</b> buy now
                        {a.reserve_usdc ? ` · ${usd(a.reserve_usdc)} reserve` : ''} ·{' '}
                        {cutPct(a.creator_cut_bps)} (${usd(
                          (Number(a.price_usdc) * (a.creator_cut_bps ?? 0)) / 10000,
                        )} to the developer)
                        {a.listed_at ? ` · listed ${shortDate(a.listed_at)}` : ''}
                      </p>
                    )}
                    <p>
                      {mineHere ? (
                        <span className="fd-mine">
                          Yours — {a.listed ? 'listed for sale' : 'adopted or created by you'}
                        </span>
                      ) : forSale ? (
                        <button
                          className="fd-btn primary"
                          disabled={busyId === a.agent_id || confirming !== null}
                          onClick={() => setConfirming(a)}
                        >
                          {busyId === a.agent_id ? 'Buying…' : `Buy now · $${usd(a.price_usdc)}`}
                        </button>
                      ) : (
                        <button
                          className="fd-btn"
                          disabled={busyId === a.agent_id}
                          onClick={() => onAcquire(a.agent_id)}
                        >
                          {busyId === a.agent_id ? 'Adopting…' : 'Adopt as your manager'}
                        </button>
                      )}
                    </p>
                    {a.listed && !mineHere && (
                      <div className="fd-offer">
                        {a.pending_offers.some((o) => o.buyer_id === OWNER_ID) ? (
                          <span className="fd-offer-pending">
                            📨 Your offer of $
                            {usd(a.pending_offers.find((o) => o.buyer_id === OWNER_ID)?.amount_usdc)} is
                            pending — the developer decides.
                          </span>
                        ) : (
                          <div className="fd-offer-row">
                            <span>…or name your price</span>
                            <button
                              className="fd-btn"
                              disabled={busyId === a.agent_id}
                              onClick={() => setBidding(a)}
                            >
                              {busyId === a.agent_id ? 'Sending…' : 'Make an offer'}
                            </button>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          )}
        </div>
      </div>

      {/* one-click buy confirmation */}
      {confirming && (
        <div className="fd-modal-overlay" onClick={() => !busyId && setConfirming(null)}>
          <div className="fd-modal" onClick={(e) => e.stopPropagation()}>
            <h3>Confirm purchase</h3>
            <p className="fd-sub">
              You're buying <b>{confirming.name}</b>
              {confirming.club_name ? ` (runs ${confirming.club_name})` : ''} — a{' '}
              {confirming.archetype_name} manager by <b>{confirming.creator_id}</b>. This is a real
              sale: the price moves and ownership transfers. There are no refunds.
            </p>
            <div className="fd-modal-rows">
              <div className="fd-modal-row">
                <span>Buy-now price</span>
                <b>${usd(confirming.price_usdc)}</b>
              </div>
              <div className="fd-modal-row">
                <span>
                  Creator cut ({cutPct(confirming.creator_cut_bps)} to {confirming.creator_id})
                </span>
                <b>${usd((Number(confirming.price_usdc) * (confirming.creator_cut_bps ?? 0)) / 10000)}</b>
              </div>
              <div className="fd-modal-row">
                <span>Seller ({confirming.owner_id}) receives</span>
                <b>
                  $
                  {usd(
                    Number(confirming.price_usdc) -
                      (Number(confirming.price_usdc) * (confirming.creator_cut_bps ?? 0)) / 10000,
                  )}
                </b>
              </div>
              <div className="fd-modal-row">
                <span>Settlement rail</span>
                <span
                  className={`fd-chip${settlement === 'onchain' || (settlement === 'auto' && wallet?.mode === 'onchain') ? ' ok' : ''}`}
                >
                  {settlement === 'onchain'
                    ? 'Real USDC · Arc (forced)'
                    : settlement === 'auto' && wallet?.mode === 'onchain'
                      ? 'Real USDC · Arc (auto)'
                      : 'Demo ledger'}
                </span>
              </div>
            </div>
            <div className="fd-modal-actions">
              <button
                className="fd-btn"
                disabled={busyId === confirming.agent_id}
                onClick={() => setConfirming(null)}
              >
                Cancel
              </button>
              <button
                className="fd-btn primary"
                disabled={busyId === confirming.agent_id}
                onClick={() => {
                  const id = confirming.agent_id
                  setConfirming(null)
                  onBuy(id)
                }}
              >
                {busyId === confirming.agent_id
                  ? 'Buying…'
                  : `Confirm purchase · $${usd(confirming.price_usdc)}`}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* sell panel — managers you own */}
      <div className="fd-sell">
        <h3>Sell a manager you own</h3>
        <p className="fd-sub">
          Set a buy-now price and your creator cut — the % of each sale that keeps coming back to
          you (the developer) when later owners resell. Buyers can pay buy-now or make an offer:
          set a <b>reserve</b> to auto-decline lowballs, then accept or reject what lands in your
          inbox below.
        </p>
        {mine.length === 0 ? (
          <p style={{ color: 'rgba(255,255,255,0.5)', fontSize: 13 }}>
            You don’t own any managers yet — create or adopt one above and it appears here to list.
          </p>
        ) : (
          <div className="fd-cards">
            {mine.map((a) => {
              const busy = busyId === a.agent_id
              return (
                <div className="fd-card" key={a.agent_id}>
                  <div className="fd-club">
                    <span className="fd-clubname">{a.name}</span>
                    {a.listed ? (
                      <span className="fd-chip" style={{ background: 'rgba(245,194,107,0.15)', color: '#f5c26b' }}>
                        listed ${usd(a.price_usdc)}
                      </span>
                    ) : (
                      <span className="fd-clubmeta">not listed</span>
                    )}
                  </div>
                  <p className="fd-meta">
                    by <b>{a.creator_id}</b> · {a.archetype_name} · {a.club_name ?? 'no club'}
                    {a.sales_count > 0 ? ` · sold ${a.sales_count}×` : ''}
                  </p>
                  <div className="fd-sell-row">
                    <label className="fd-field" style={{ flex: '1 1 auto' }}>
                      <span>Webhook (bring your own brain)</span>
                      <input
                        className="fd-input"
                        value={whUrl[a.agent_id] ?? ''}
                        onChange={(e) => setWhUrl((p) => ({ ...p, [a.agent_id]: e.target.value }))}
                        placeholder={a.webhook_url ?? 'empty = deterministic playbook'}
                      />
                    </label>
                    <button
                      className="fd-btn"
                      disabled={busyId === `${a.agent_id}:wh`}
                      onClick={() => onSetWebhook(a.agent_id, a.name)}
                      style={{ alignSelf: 'flex-end' }}
                    >
                      {busyId === `${a.agent_id}:wh` ? 'Saving…' : a.webhook_url ? 'Change' : 'Set webhook'}
                    </button>
                    {a.webhook_url ? (
                      <button
                        className="fd-btn"
                        disabled={busyId === `${a.agent_id}:wh`}
                        onClick={() => onSetWebhook(a.agent_id, a.name, '')}
                        style={{ alignSelf: 'flex-end' }}
                        title={`Clear ${a.webhook_url}`}
                      >
                        Clear
                      </button>
                    ) : null}
                  </div>
                  <p className="fd-sub" style={{ fontSize: 12, margin: '4px 0 10px' }}>
                    {a.webhook_url
                      ? `🔗 answering matchday asks from ${a.webhook_url}`
                      : 'Runs on the deterministic playbook — set a webhook to let it answer the matchday ask itself.'}
                  </p>
                  {a.listed && a.pending_offers.length > 0 ? (
                    <div className="fd-offers">
                      <b>Incoming offers ({a.pending_offers.length})</b>
                      <p className="fd-sub">
                        Offers at/above your ${usd(a.reserve_usdc)} reserve queue here — accept one
                        and the sale settles at that price.
                      </p>
                      {a.pending_offers.map((o) => {
                        const busyOffer = busyId === `${a.agent_id}:${o.offer_id}`
                        return (
                          <div className="fd-offer-item" key={o.offer_id}>
                            <span>
                              <b>{o.buyer_id}</b> offered <b>${usd(o.amount_usdc)}</b>
                              <em> {shortDate(o.created_at)}</em>
                            </span>
                            <span className="fd-offer-actions">
                              <button
                                className="fd-btn primary"
                                disabled={busyOffer}
                                onClick={() => onAcceptOffer(a.agent_id, o.offer_id, o.buyer_id, o.amount_usdc)}
                              >
                                {busyOffer ? '…' : 'Accept'}
                              </button>
                              <button
                                className="fd-btn"
                                disabled={busyOffer}
                                onClick={() => onRejectOffer(a.agent_id, o.offer_id, o.buyer_id)}
                              >
                                Reject
                              </button>
                            </span>
                          </div>
                        )
                      })}
                    </div>
                  ) : null}
                  {a.listed ? (
                    <div className="fd-sell-row">
                      <button className="fd-btn" disabled={busy} onClick={() => onDelist(a.agent_id)}>
                        {busy ? '…' : 'Delist (keep it)'}
                      </button>
                    </div>
                  ) : (
                    <div className="fd-sell-row">
                      <label className="fd-field">
                        <span>Buy-now price USDC</span>
                        <input
                          className="fd-input"
                          type="number"
                          min={0.01}
                          step="0.01"
                          value={sellPrice[a.agent_id] ?? ''}
                          onChange={(e) => setSellPrice((p) => ({ ...p, [a.agent_id]: e.target.value }))}
                          placeholder="e.g. 25"
                        />
                      </label>
                      <label className="fd-field">
                        <span>Creator cut %</span>
                        <input
                          className="fd-input"
                          type="number"
                          min={0}
                          max={20}
                          step="0.5"
                          value={sellCut[a.agent_id] ?? '5'}
                          onChange={(e) => setSellCut((c) => ({ ...c, [a.agent_id]: e.target.value }))}
                        />
                      </label>
                      <label className="fd-field">
                        <span>Reserve (min offer, optional)</span>
                        <input
                          className="fd-input"
                          type="number"
                          min={0.01}
                          step="0.01"
                          value={sellReserve[a.agent_id] ?? ''}
                          onChange={(e) =>
                            setSellReserve((r) => ({ ...r, [a.agent_id]: e.target.value }))
                          }
                          placeholder="below it, offers auto-decline"
                        />
                      </label>
                      <button
                        className="fd-btn primary"
                        disabled={busy}
                        onClick={() => onList(a.agent_id, a.name)}
                      >
                        {busy ? 'Listing…' : 'List for sale'}
                      </button>
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        )}
      </div>

      {/* the bid modal — live likelihood meter over the offer flow */}
      {bidding && (
        <BidModal
          agent={bidding}
          wallet={wallet}
          busy={busyId === bidding.agent_id}
          onSubmit={(amt) => onOffer(bidding.agent_id, bidding.name, amt)}
          onClose={() => !busyId && setBidding(null)}
        />
      )}
    </div>
  )
}

function shortDate(iso: string) {
  try {
    return new Date(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
  } catch {
    return ''
  }
}

function shortAddr(addr: string | null | undefined): string {
  const a = addr ?? ''
  return a.length > 14 ? `${a.slice(0, 8)}…${a.slice(-6)}` : a || '0x…'
}

function fmt(n: number | string | undefined): string {
  const v = Number(n ?? 0)
  return Number.isFinite(v) ? String(v) : String(n ?? 0)
}
