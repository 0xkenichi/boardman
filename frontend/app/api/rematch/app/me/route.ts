import { NextResponse } from 'next/server'
import { requireSession } from '@/lib/bff'
import { stackConfigured, stackFetch } from '@/lib/stackServer'
import { fetchProfileWallet } from '@/lib/supabaseAdmin'
import { usdcBalanceOf } from '@/lib/arcUsdc'
import { isBoardmanAdmin } from '@/lib/adminAuth'

export const dynamic = 'force-dynamic'

/**
 * Same number the Telegram bot shows: Arc USDC on the play address.
 * Never prefer the legacy profiles.wallet_balance_usdc ledger when chain has funds.
 */
export async function GET(req: Request) {
  const auth = requireSession(req)
  if ('error' in auth) return auth.error
  const { session: s } = auth

  const row = await fetchProfileWallet(s.profileId)
  const address = (
    row?.gaming_deposit_address ||
    row?.wallet_address ||
    row?.linked_wallet ||
    ''
  )
    .trim()
    .toLowerCase()
  const ledger = Number(row?.wallet_balance_usdc ?? 0)

  const rpcP =
    address && /^0x[a-f0-9]{40}$/.test(address)
      ? usdcBalanceOf(address, { timeoutMs: 5000 })
      : Promise.resolve(null)
  const apiP = stackConfigured()
    ? stackFetch(`/api/rematch/web/wallet?profile_id=${encodeURIComponent(s.profileId)}`, {
        signal: AbortSignal.timeout(5000),
      }).catch(() => ({ ok: false, status: 0, data: null }))
    : Promise.resolve({ ok: false, status: 0, data: null })

  const [rpc, api] = await Promise.all([rpcP, apiP])
  const onchain = rpc && rpc.ok ? Number(rpc.balance_usdc) : null
  const apiSpend =
    api.ok && api.data?.success !== false && api.data?.balance != null
      ? Number(api.data.balance)
      : null
  const apiOther = api.ok ? Number(api.data?.other_balance ?? 0) : 0

  // Bot welcome = spendable + other. Prefer a live Arc read of the play address.
  const spendable =
    onchain != null && Number.isFinite(onchain)
      ? onchain
      : apiSpend != null && Number.isFinite(apiSpend)
        ? apiSpend
        : ledger
  const other = apiOther > 0.009 ? apiOther : 0
  const display = spendable + other

  return NextResponse.json({
    ok: true,
    profileId: s.profileId,
    tag: (api.data && api.data.gaming_tag) || row?.gaming_tag || s.tag,
    name: (api.data && api.data.display_name) || row?.display_name || s.name,
    telegramId: s.telegramId,
    admin: isBoardmanAdmin(s),
    balance: display,
    spendable,
    otherBalance: other,
    otherAddress: (api.data && api.data.other_address) || '',
    totalBalance: display,
    address: (api.data && api.data.address) || address || '',
    chainId: (api.data && api.data.chain_id) || 'arc',
    ledger_usdc: Number((api.data && api.data.ledger_usdc) ?? ledger),
    onchain_usdc: onchain,
    playPoints: Number((api.data && api.data.play_points) ?? row?.play_points ?? 0),
    paused: Boolean(api.data && api.data.paused),
    balanceError: (rpc && !rpc.ok && rpc.error) || (api.data && api.data.balance_error) || null,
    demo: false,
    source: onchain != null ? 'arc_play_address' : apiSpend != null ? 'rematch_api' : 'supabase_ledger',
  })
}
