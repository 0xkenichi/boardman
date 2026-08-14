import { NextResponse } from 'next/server'
import { requireSession } from '@/lib/bff'
import { stackConfigured, stackFetch } from '@/lib/stackServer'
import { fetchProfileWallet } from '@/lib/supabaseAdmin'
import { usdcBalanceOf } from '@/lib/arcUsdc'
import { isBoardmanAdmin } from '@/lib/adminAuth'

export const dynamic = 'force-dynamic'

/**
 * Same idea as the Telegram bot welcome/wallet screen:
 * spendable = USDC on the user's **play fund address** (gaming_deposit_address),
 * not the legacy profiles.wallet_balance_usdc ledger alone (often 0 while Arc has funds).
 */
export async function GET(req: Request) {
  const auth = requireSession(req)
  if ('error' in auth) return auth.error
  const { session: s } = auth

  // 1) Preferred: gaming API wallet snapshot (spendable = play wallet)
  if (stackConfigured()) {
    const res = await stackFetch(
      `/api/rematch/web/wallet?profile_id=${encodeURIComponent(s.profileId)}`
    )
    if (res.ok && res.data?.success !== false && res.data?.balance != null) {
      const balance = Number(res.data.balance ?? 0)
      const otherBalance = Number(res.data.other_balance ?? 0)
      // If API returns 0 but we have a deposit address, double-check Arc (wrong API host)
      if (balance > 0.0001 || !res.data.address) {
        return NextResponse.json({
          ok: true,
          profileId: s.profileId,
          tag: res.data.gaming_tag || s.tag,
          name: res.data.display_name || s.name,
          telegramId: s.telegramId,
          admin: isBoardmanAdmin(s),
          balance,
          totalBalance: Number(res.data.total_balance ?? balance + otherBalance),
          otherBalance,
          otherAddress: res.data.other_address || '',
          address: res.data.address || '',
          chainId: res.data.chain_id || 'arc',
          playPoints: Number(res.data.play_points ?? 0),
          paused: Boolean(res.data.paused),
          balanceError: res.data.balance_error || null,
          demo: false,
          source: 'rematch_api',
        })
      }
    }
  }

  // 2) Supabase profile + Arc USDC on play deposit address (matches bot)
  try {
    const row = await fetchProfileWallet(s.profileId)
    if (row) {
      const address = (
        row.gaming_deposit_address ||
        row.wallet_address ||
        row.linked_wallet ||
        ''
      )
        .trim()
        .toLowerCase()
      const ledger = Number(row.wallet_balance_usdc ?? 0)

      let onchain = 0
      let onchainOk = false
      let onchainError: string | null = null
      if (address && /^0x[a-f0-9]{40}$/.test(address)) {
        const r = await usdcBalanceOf(address)
        onchainOk = r.ok
        onchain = r.ok ? Number(r.balance_usdc) : 0
        onchainError = r.ok ? null : r.error || 'rpc_failed'
      }

      // Bot shows spendable from play address; fall back to ledger if RPC fails
      const balance = onchainOk ? onchain : ledger
      const totalBalance = onchainOk ? onchain + (ledger > onchain ? 0 : 0) : ledger

      return NextResponse.json({
        ok: true,
        profileId: s.profileId,
        tag: row.gaming_tag || s.tag,
        name: row.display_name || s.name,
        telegramId: s.telegramId,
        admin: isBoardmanAdmin(s),
        balance,
        totalBalance: onchainOk ? onchain : totalBalance,
        otherBalance: 0,
        otherAddress: '',
        address: address || '',
        chainId: 'arc',
        playPoints: Number(row.play_points ?? 0),
        paused: false,
        balanceError: onchainError,
        ledger_usdc: ledger,
        onchain_usdc: onchainOk ? onchain : null,
        demo: false,
        source: onchainOk ? 'arc_play_address' : 'supabase_ledger',
        note: onchainOk
          ? 'Spendable = Arc USDC on your play fund address (same as Telegram bot).'
          : 'Could not read Arc; showing profiles.wallet_balance_usdc ledger only.',
      })
    }
  } catch (e) {
    console.error('[me] profile+arc wallet failed', e)
  }

  // 3) Last resort — session only
  return NextResponse.json({
    ok: true,
    profileId: s.profileId,
    tag: s.tag,
    name: s.name,
    telegramId: s.telegramId,
    admin: isBoardmanAdmin(s),
    balance: Number(process.env.REMATCH_DEMO_BALANCE || 0),
    otherBalance: 0,
    otherAddress: '',
    address: '',
    playPoints: 0,
    demo: true,
    source: 'session_only',
    message:
      'Could not load live wallet. Check Supabase service role + gaming_deposit_address on profile.',
  })
}
