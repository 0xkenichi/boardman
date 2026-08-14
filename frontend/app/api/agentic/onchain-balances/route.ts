/**
 * Public read of Arc testnet USDC balances for agent (or any) EOAs.
 * No secrets — eth_call only. Used by arena creator desk.
 *
 * GET ?addresses=0xabc,0xdef
 * or  ?raja=0x..&nero=0x..
 */
import { NextRequest, NextResponse } from 'next/server'
import { usdcBalanceOf, arcRpcUrl, arcUsdcAddress } from '@/lib/arcUsdc'
import { rematchApiFetch } from '@/lib/stackServer'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

const DEMO = {
  raja: '0xDB131a4B88ACA79c29D5aDF3C3Df033954D36029',
  nero: '0xe430C73cF2beD38aBE83DF8309763191624373E1',
}

export async function GET(req: NextRequest) {
  const sp = req.nextUrl.searchParams
  const list: { key: string; address: string }[] = []

  const bulk = sp.get('addresses')
  if (bulk) {
    bulk.split(',').forEach((a, i) => {
      const addr = a.trim()
      if (addr) list.push({ key: `a${i}`, address: addr })
    })
  }
  for (const key of ['raja', 'nero', 'agent_a', 'agent_b']) {
    const a = sp.get(key)
    if (a) list.push({ key, address: a.trim() })
  }
  if (!list.length) {
    list.push({ key: 'raja', address: DEMO.raja })
    list.push({ key: 'nero', address: DEMO.nero })
  }

  const results: Record<
    string,
    { address: string; balance_usdc: number; ok: boolean; error?: string }
  > = {}
  await Promise.all(
    list.map(async ({ key, address }) => {
      const r = await usdcBalanceOf(address, { timeoutMs: 5000 })
      results[key] = {
        address: r.address,
        balance_usdc: r.balance_usdc,
        ok: r.ok,
        error: r.error,
      }
    })
  )

  // Volume is extra — never block the bankroll response on the laptop API.
  const days = Number(sp.get('days') || 30)
  const volume = await (async () => {
    try {
      const r = await rematchApiFetch(
        `/api/stack/agentic/agents/onchain_volume?chain=1&days=${days}`,
        { signal: AbortSignal.timeout(2500) }
      )
      if (!r.ok) return {}
      const j = r.data || {}
      return {
        totals: j.totals || {},
        onchain: j.onchain || {},
        window_days: j.window_days ?? days,
      }
    } catch {
      return {}
    }
  })()

  return NextResponse.json({
    ok: true,
    chain: 'arc',
    network: 'testnet',
    source: 'arc_usdc_balanceOf',
    rpc: arcRpcUrl(),
    usdc: arcUsdcAddress(),
    balances: results,
    volume,
    note: 'Agent bankrolls on creator desk should match these Arc testnet USDC balances when on-chain mode is live.',
  })
}
